"""One interface over the ad servers, and one place that fans out to them.

Before this, Frequency and DV360 happened to expose the same three functions by
convention, and nothing enforced it. Every caller hand-wired both: six
near-identical guard/try/except blocks across run_pipeline, rerun_from_script
and redeliver, plus a seventh in the scheduler for pushed files. The imports
had to be aliased at each site (`deliver_ad as dv360_deliver_ad`) purely to
dodge a name collision, which is the smell that gave the game away.

There were also three different answers to "can this campaign deliver?" —
runner.py checked the campaign flags, push/service.py checked the advertiser
credentials, and frequency.deliver_ad re-checked everything from scratch and
raised. A target now answers that question about itself, once.

Adding a third ad server means writing one adapter and adding it to TARGETS.
"""

import logging
from dataclasses import dataclass

from app.extensions import db
from app.models.campaign import FREQUENCY_TAG_APP_ID_KEY, FREQUENCY_TAG_TOKEN_KEY
from app.models.delivery_attempt import TARGET_DV360, TARGET_FREQUENCY

logger = logging.getLogger(__name__)


@dataclass
class DeliveryOutcome:
    """What happened when one ad unit was handed the audio."""

    succeeded: bool
    reference: str | None = None
    error: str | None = None
    detail: str | None = None  # which ad unit, for targets with more than one


class DeliveryTarget:
    """What every ad server has to be able to answer.

    The three checks are deliberately separate, and each returns a human
    sentence rather than a bool, because "we skipped it" needs a reason in the
    log and in the UI — that is what the old nested if/elif chains were for.
    """

    name: str = ""
    errors: tuple = ()

    def unconfigured_reason(self, campaign) -> str | None:
        """Why this campaign cannot use this target, or None if it can."""
        raise NotImplementedError

    def missing_credentials_reason(self, campaign) -> str | None:
        """Why this target could never reach this campaign, ignoring pause switches."""
        raise NotImplementedError

    def unavailable_reason(self) -> str | None:
        """Why this server is off for the whole deployment, or None."""
        raise NotImplementedError

    def deliver(self, ad_run, audio_bytes: bytes) -> list[DeliveryOutcome]:
        """Hand over the audio, once per ad unit this target has configured."""
        raise NotImplementedError

    def _attempt(self, deliver_one, detail: str | None = None) -> DeliveryOutcome:
        """Run one delivery call, turning any failure into an outcome rather than a raise."""
        try:
            reference = deliver_one()
        except self.errors as exc:
            return DeliveryOutcome(succeeded=False, error=str(exc), detail=detail)
        except Exception as exc:  # noqa: BLE001 — one ad unit's surprise must not sink the others
            logger.exception("[%s] Unexpected delivery error (%s)", self.name, detail or "")
            return DeliveryOutcome(succeeded=False, error=str(exc), detail=detail)
        return DeliveryOutcome(succeeded=True, reference=reference, detail=detail)


class FrequencyTarget(DeliveryTarget):
    name = TARGET_FREQUENCY

    def __init__(self):
        from app.delivery.frequency import (
            FrequencyDeliveryError,
            FrequencyNotConfiguredError,
        )

        self.errors = (FrequencyDeliveryError, FrequencyNotConfiguredError)

    def unconfigured_reason(self, campaign):
        if not campaign.delivery_enabled:
            return "delivery_enabled is off for this campaign"
        return self.missing_credentials_reason(campaign)

    def missing_credentials_reason(self, campaign):
        if not campaign.frequency_tag_list:
            return "campaign has no frequency_tags"
        advertiser = campaign.advertiser
        if not advertiser.frequency_client:
            return f"advertiser '{advertiser.name}' has no Frequency client"
        return None

    def unavailable_reason(self):
        from flask import current_app

        from app.delivery.frequency import is_delivery_available

        if is_delivery_available():
            return None
        config = current_app.config
        return (
            f"Frequency delivery is off (FREQUENCY_ENABLED="
            f"{config.get('FREQUENCY_ENABLED')}, CMPAPI_BASE_URL="
            f"{config.get('CMPAPI_BASE_URL') or '(not set)'})"
        )

    def deliver(self, ad_run, audio_bytes):
        return [
            self._deliver_to_tag(ad_run, tag, audio_bytes)
            for tag in ad_run.campaign.frequency_tag_list
        ]

    def _deliver_to_tag(self, ad_run, tag, audio_bytes) -> DeliveryOutcome:
        from app.delivery.frequency import deliver_ad

        detail = tag.get(FREQUENCY_TAG_APP_ID_KEY) or tag.get(FREQUENCY_TAG_TOKEN_KEY)
        return self._attempt(lambda: deliver_ad(ad_run, tag, audio_bytes), detail=detail)


class DV360Target(DeliveryTarget):
    name = TARGET_DV360

    def __init__(self):
        from app.delivery.dv360 import DV360DeliveryError, DV360NotConfiguredError

        self.errors = (DV360DeliveryError, DV360NotConfiguredError)

    def unconfigured_reason(self, campaign):
        if not campaign.dv360_enabled:
            return "dv360_enabled is off for this campaign"
        return self.missing_credentials_reason(campaign)

    def missing_credentials_reason(self, campaign):
        if not campaign.dv360_line_item_id:
            return "campaign has no dv360_line_item_id"
        if not campaign.dv360_advertiser_id or not campaign.dv360_service_account_json:
            return "campaign has no DV360 credentials"
        return None

    def unavailable_reason(self):
        from app.delivery.dv360 import is_delivery_available

        return None if is_delivery_available() else "DV360 delivery is off (DV360_ENABLED)"

    def deliver(self, ad_run, audio_bytes):
        from app.delivery.dv360 import deliver_ad

        return [self._attempt(lambda: deliver_ad(ad_run, audio_bytes))]


def all_targets() -> list[DeliveryTarget]:
    """Every ad server this app knows how to deliver to.

    Built per call rather than at import: the adapters resolve their exception
    types from the delivery modules, and those import Flask config.
    """
    return [FrequencyTarget(), DV360Target()]


def deliver_run(ad_run, audio_bytes: bytes, only=None, on_first_attempt=None) -> list:
    """Deliver one run's audio to every target configured for its campaign.

    Args:
        ad_run: the run whose audio this is.
        audio_bytes: the finished MP3.
        only: target names to restrict to, or None for all of them.
        on_first_attempt: called once before the first real attempt — the
            pipeline uses it to move the run into "delivering".

    Returns the DeliveryAttempt rows written, which may be empty when no target
    was configured. Delivery failure is recorded, never raised: one ad server
    being down must not lose a run that another accepted. Callers read the
    outcome from ad_run.delivery_state.
    """
    campaign = ad_run.campaign
    attempts = []
    announced = False

    for target in all_targets():
        if only is not None and target.name not in only:
            continue

        skipped = target.unconfigured_reason(campaign) or target.unavailable_reason()
        if skipped:
            logger.info("[%s] SKIP run #%d — %s", target.name, ad_run.id, skipped)
            continue

        if not announced and on_first_attempt is not None:
            on_first_attempt()
            announced = True

        try:
            outcomes = target.deliver(ad_run, audio_bytes)
        except Exception as exc:  # noqa: BLE001 — see the docstring
            # target.deliver catches its own delivery errors; reaching here
            # means the target itself is broken, which must still leave the
            # run in an honest state rather than stuck in "delivering" forever.
            outcomes = [DeliveryOutcome(succeeded=False, error=str(exc))]
            logger.exception("[%s] Target implementation error for run #%d", target.name, ad_run.id)

        for outcome in outcomes:
            attempts.append(
                ad_run.record_delivery(
                    target.name, outcome.succeeded,
                    reference=outcome.reference, error=outcome.error, detail=outcome.detail,
                )
            )
            if outcome.succeeded:
                logger.info("[%s] Delivered run #%d (%s)", target.name, ad_run.id, outcome.detail or "")
            else:
                logger.error(
                    "[%s] Delivery FAILED for run #%d (%s): %s",
                    target.name, ad_run.id, outcome.detail or "", outcome.error,
                )
            db.session.commit()

    return attempts
