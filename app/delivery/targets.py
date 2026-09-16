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

from app.extensions import db
from app.models.delivery_attempt import TARGET_DV360, TARGET_FREQUENCY

logger = logging.getLogger(__name__)


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

    def deliver(self, ad_run, audio_bytes: bytes) -> str:
        """Hand over the audio. Returns the server's reference for it."""
        raise NotImplementedError


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
        if not campaign.frequency_app_id:
            return "campaign has no frequency_app_id"
        if not campaign.frequency_token:
            return "campaign has no frequency_token"
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
        from app.delivery.frequency import deliver_ad

        return deliver_ad(ad_run, audio_bytes)


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

        return deliver_ad(ad_run, audio_bytes)


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
            reference = target.deliver(ad_run, audio_bytes)
        except target.errors as exc:
            attempts.append(ad_run.record_delivery(target.name, False, error=str(exc)))
            logger.error("[%s] Delivery FAILED for run #%d: %s", target.name, ad_run.id, exc)
        except Exception as exc:  # noqa: BLE001 — see the docstring
            # An ad server throwing something we did not anticipate must still
            # leave the run in an honest state rather than stuck in
            # "delivering" forever, so it is recorded like any other failure.
            attempts.append(ad_run.record_delivery(target.name, False, error=str(exc)))
            logger.exception("[%s] Unexpected delivery error for run #%d", target.name, ad_run.id)
        else:
            attempts.append(ad_run.record_delivery(target.name, True, reference=reference))
            logger.info("[%s] Delivered run #%d", target.name, ad_run.id)
        db.session.commit()

    return attempts
