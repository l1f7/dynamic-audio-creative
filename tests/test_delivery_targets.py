"""The delivery seam — one interface over the ad servers, one fan-out.

These replace six near-identical guard/try/except blocks that used to sit in
run_pipeline, rerun_from_script and redeliver, plus a seventh in the scheduler.
"""

import pytest

from app.delivery.targets import DV360Target, FrequencyTarget, all_targets, deliver_run
from app.models import AdRun, Advertiser, Campaign
from app.models.ad_run import (
    DELIVERY_DELIVERED,
    DELIVERY_FAILED,
    DELIVERY_NOT_ATTEMPTED,
    DELIVERY_PARTIAL,
)
from app.models.delivery_attempt import TARGET_DV360, TARGET_FREQUENCY


@pytest.fixture
def advertiser(db):
    adv = Advertiser(
        name="Acme",
        frequency_client="acme",
        dv360_advertiser_id="dv-1", dv360_service_account_json="{}",
    )
    db.session.add(adv)
    db.session.commit()
    return adv


def _campaign(db, advertiser, **overrides):
    fields = dict(
        name="Spring", advertiser_id=advertiser.id, feed_type="weather",
        delivery_enabled=True, frequency_app_id="app-1", frequency_token="tok",
        dv360_enabled=True, dv360_line_item_id="li-1",
    )
    fields.update(overrides)
    camp = Campaign(**fields)
    db.session.add(camp)
    db.session.commit()
    return camp


def _run(db, campaign):
    run = AdRun(campaign_id=campaign.id, triggered_by="cron", status="pending")
    db.session.add(run)
    db.session.commit()
    return run


@pytest.fixture
def both_available(monkeypatch):
    monkeypatch.setattr("app.delivery.frequency.is_delivery_available", lambda: True)
    monkeypatch.setattr("app.delivery.dv360.is_delivery_available", lambda: True)


class TestTargetsAgreeOnTheInterface:
    def test_every_target_implements_it(self):
        for target in all_targets():
            assert target.name
            assert target.errors
            for method in ("unconfigured_reason", "missing_credentials_reason", "unavailable_reason", "deliver"):
                assert callable(getattr(target, method))

    def test_names_are_unique(self):
        names = [t.name for t in all_targets()]
        assert len(names) == len(set(names))


class TestConfigurationReasons:
    """One answer to 'can this campaign deliver', replacing three that disagreed."""

    def test_frequency_needs_the_campaign_flag(self, db, advertiser):
        campaign = _campaign(db, advertiser, delivery_enabled=False)
        assert "delivery_enabled" in FrequencyTarget().unconfigured_reason(campaign)

    def test_frequency_needs_an_app_id(self, db, advertiser):
        campaign = _campaign(db, advertiser, frequency_app_id=None)
        assert "frequency_app_id" in FrequencyTarget().unconfigured_reason(campaign)

    def test_frequency_needs_a_campaign_token(self, db, advertiser):
        campaign = _campaign(db, advertiser, frequency_token=None)
        assert "frequency_token" in FrequencyTarget().unconfigured_reason(campaign)

    def test_frequency_needs_advertiser_client(self, db, advertiser):
        """runner.py used to skip this check and only fail inside deliver_ad."""
        advertiser.frequency_client = None
        db.session.commit()
        campaign = _campaign(db, advertiser)
        assert "Frequency client" in FrequencyTarget().unconfigured_reason(campaign)

    def test_dv360_needs_its_line_item(self, db, advertiser):
        campaign = _campaign(db, advertiser, dv360_line_item_id=None)
        assert "dv360_line_item_id" in DV360Target().unconfigured_reason(campaign)

    def test_fully_configured_campaign_has_no_reason(self, db, advertiser):
        campaign = _campaign(db, advertiser)
        assert FrequencyTarget().unconfigured_reason(campaign) is None
        assert DV360Target().unconfigured_reason(campaign) is None

    def test_missing_credentials_ignores_the_pause_switch(self, db, advertiser):
        """A paused campaign with no app id is misconfigured, not merely paused."""
        paused_broken = _campaign(db, advertiser, delivery_enabled=False, frequency_app_id=None)
        assert "frequency_app_id" in FrequencyTarget().missing_credentials_reason(paused_broken)
        paused_fine = _campaign(db, advertiser, delivery_enabled=False)
        assert FrequencyTarget().missing_credentials_reason(paused_fine) is None


class TestFanOut:
    def test_delivers_to_every_configured_target(self, client, db, advertiser, both_available, monkeypatch):
        monkeypatch.setattr("app.delivery.frequency.deliver_ad", lambda r, a: "<VAST/>")
        monkeypatch.setattr("app.delivery.dv360.deliver_ad", lambda r, a: "creatives/9")
        run = _run(db, _campaign(db, advertiser))

        deliver_run(run, b"audio")

        assert run.delivery_state == DELIVERY_DELIVERED
        assert {t for t, _ in run.attempted_targets} == {TARGET_FREQUENCY, TARGET_DV360}
        assert run.vast_response == "<VAST/>"
        assert run.dv360_creative_name == "creatives/9"

    def test_one_target_failing_leaves_the_other_delivered(self, client, db, advertiser, both_available, monkeypatch):
        """The whole reason failures are recorded and never raised."""
        from app.delivery.dv360 import DV360DeliveryError

        monkeypatch.setattr("app.delivery.frequency.deliver_ad", lambda r, a: "<VAST/>")

        def boom(r, a):
            raise DV360DeliveryError("quota exceeded")

        monkeypatch.setattr("app.delivery.dv360.deliver_ad", boom)
        run = _run(db, _campaign(db, advertiser))

        deliver_run(run, b"audio")

        assert run.delivery_state == DELIVERY_PARTIAL
        assert run.delivered_at is not None
        assert run.dv360_delivery_error == "quota exceeded"

    def test_unexpected_errors_are_recorded_not_raised(self, client, db, advertiser, both_available, monkeypatch):
        """A run must never be stranded mid-'delivering' by a surprise."""
        def boom(r, a):
            raise RuntimeError("socket closed")

        monkeypatch.setattr("app.delivery.frequency.deliver_ad", boom)
        monkeypatch.setattr("app.delivery.dv360.deliver_ad", lambda r, a: "creatives/9")
        run = _run(db, _campaign(db, advertiser))

        deliver_run(run, b"audio")

        assert run.delivery_error == "socket closed"
        assert run.delivery_state == DELIVERY_PARTIAL

    def test_unconfigured_targets_are_skipped_silently(self, client, db, advertiser, both_available, monkeypatch):
        monkeypatch.setattr("app.delivery.frequency.deliver_ad", lambda r, a: "<VAST/>")
        campaign = _campaign(db, advertiser, dv360_enabled=False)
        run = _run(db, campaign)

        deliver_run(run, b"audio")

        assert [t for t, _ in run.attempted_targets] == [TARGET_FREQUENCY]

    def test_only_restricts_the_fan_out(self, client, db, advertiser, both_available, monkeypatch):
        """Backs the rerun/redeliver checkboxes in the admin UI."""
        monkeypatch.setattr("app.delivery.frequency.deliver_ad", lambda r, a: "<VAST/>")
        monkeypatch.setattr("app.delivery.dv360.deliver_ad", lambda r, a: "creatives/9")
        run = _run(db, _campaign(db, advertiser))

        deliver_run(run, b"audio", only=[TARGET_DV360])

        assert [t for t, _ in run.attempted_targets] == [TARGET_DV360]

    def test_nothing_configured_means_no_attempts(self, client, db, advertiser, both_available):
        campaign = _campaign(db, advertiser, delivery_enabled=False, dv360_enabled=False)
        run = _run(db, campaign)

        assert deliver_run(run, b"audio") == []
        assert run.delivery_state == DELIVERY_NOT_ATTEMPTED

    def test_on_first_attempt_fires_once_and_only_if_something_runs(self, client, db, advertiser, both_available, monkeypatch):
        monkeypatch.setattr("app.delivery.frequency.deliver_ad", lambda r, a: "<VAST/>")
        monkeypatch.setattr("app.delivery.dv360.deliver_ad", lambda r, a: "creatives/9")
        calls = []
        run = _run(db, _campaign(db, advertiser))

        deliver_run(run, b"audio", on_first_attempt=lambda: calls.append(1))
        assert calls == [1]

        skipped = _run(db, _campaign(db, advertiser, delivery_enabled=False, dv360_enabled=False))
        deliver_run(skipped, b"audio", on_first_attempt=lambda: calls.append(1))
        assert calls == [1], "nothing was attempted, so the status should not have moved"


class TestAttemptHistory:
    def test_a_retry_appends_rather_than_overwriting(self, client, db, advertiser, both_available, monkeypatch):
        """The old columns could not express this — a redelivery erased the past."""
        from app.delivery.frequency import FrequencyDeliveryError

        campaign = _campaign(db, advertiser, dv360_enabled=False)
        run = _run(db, campaign)

        def boom(r, a):
            raise FrequencyDeliveryError("ad unit rejected it")

        monkeypatch.setattr("app.delivery.frequency.deliver_ad", boom)
        deliver_run(run, b"audio")
        assert run.delivery_state == DELIVERY_FAILED

        monkeypatch.setattr("app.delivery.frequency.deliver_ad", lambda r, a: "<VAST/>")
        deliver_run(run, b"audio")

        assert run.delivery_state == DELIVERY_DELIVERED, "the later success wins"
        assert len(run.delivery_attempts) == 2, "but the failure is still on record"
        assert run.delivery_attempts[0].error == "ad unit rejected it"
        assert run.delivery_error is None


class TestHistoryIsVisible:
    def test_run_detail_shows_the_attempt_timeline(self, authenticated_client, db, advertiser):
        campaign = _campaign(db, advertiser, dv360_enabled=False)
        run = _run(db, campaign)
        run.record_delivery(TARGET_FREQUENCY, False, error="ad unit rejected it")
        run.record_delivery(TARGET_FREQUENCY, True, reference="<VAST/>")
        db.session.commit()

        body = authenticated_client.get(f"/admin/runs/{run.id}").data
        assert b"Delivery History" in body
        assert b"ad unit rejected it" in body

    def test_a_single_attempt_needs_no_timeline(self, authenticated_client, db, advertiser):
        campaign = _campaign(db, advertiser, dv360_enabled=False)
        run = _run(db, campaign)
        run.record_delivery(TARGET_FREQUENCY, True, reference="<VAST/>")
        db.session.commit()

        assert b"Delivery History" not in authenticated_client.get(f"/admin/runs/{run.id}").data
