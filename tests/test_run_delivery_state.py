"""A run's delivery outcome is separate from whether its audio was produced.

These two answers used to be conflated on AdRun.status, so a run that both ad
servers rejected still reported "complete" and rendered a green badge. The
failure existed only in delivery_error, which nothing surfaced.
"""

from datetime import datetime, timezone

import pytest

from app.models import AdRun, Advertiser, Campaign
from app.models.delivery_attempt import TARGET_DV360, TARGET_FREQUENCY
from app.models.ad_run import (
    DELIVERY_DELIVERED,
    DELIVERY_FAILED,
    DELIVERY_NOT_ATTEMPTED,
    DELIVERY_PARTIAL,
    STATUS_COMPLETE,
    STATUS_FAILED,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def campaign(db):
    adv = Advertiser(name="Acme")
    db.session.add(adv)
    db.session.commit()
    camp = Campaign(name="Spring", advertiser_id=adv.id, feed_type="weather")
    db.session.add(camp)
    db.session.commit()
    return camp


def _run(db, campaign, *, frequency=None, dv360=None, **fields):
    """A run with delivery attempts recorded.

    frequency / dv360 take True for a success, or an error string for a
    failure. A list records several attempts against that target in order,
    which is what the old per-target columns could not represent.
    """
    fields.setdefault("status", "pending")
    run = AdRun(campaign_id=campaign.id, triggered_by="cron", **fields)
    db.session.add(run)
    db.session.flush()
    for target, outcomes in ((TARGET_FREQUENCY, frequency), (TARGET_DV360, dv360)):
        if outcomes is None:
            continue
        for outcome in outcomes if isinstance(outcomes, list) else [outcomes]:
            if outcome is True:
                run.record_delivery(target, True, reference="<ref/>")
            else:
                run.record_delivery(target, False, error=outcome)
    db.session.commit()
    return run


class TestDeliveryState:
    def test_no_attempt_is_not_attempted(self, db, campaign):
        assert _run(db, campaign).delivery_state == DELIVERY_NOT_ATTEMPTED

    def test_single_target_success_is_delivered(self, db, campaign):
        run = _run(db, campaign, frequency=True)
        assert run.delivery_state == DELIVERY_DELIVERED
        assert run.delivery_errors == []

    def test_both_targets_succeed_is_delivered(self, db, campaign):
        run = _run(db, campaign, frequency=True, dv360=True)
        assert run.delivery_state == DELIVERY_DELIVERED

    def test_one_of_two_failing_is_partial(self, db, campaign):
        run = _run(db, campaign, frequency=True, dv360="quota exceeded")
        assert run.delivery_state == DELIVERY_PARTIAL
        assert run.delivery_errors == ["dv360: quota exceeded"]

    def test_every_attempt_failing_is_failed(self, db, campaign):
        run = _run(
            db, campaign,
            frequency="ad unit rejected it",
            dv360="quota exceeded",
        )
        assert run.delivery_state == DELIVERY_FAILED
        assert run.delivery_errors == [
            "frequency: ad unit rejected it",
            "dv360: quota exceeded",
        ]

    def test_delivered_at_with_an_error_does_not_count_as_success(self, db, campaign):
        """A redelivery that set delivered_at earlier then failed is still a failure."""
        run = _run(db, campaign, frequency=[True, "later rejected"])
        assert run.delivery_state == DELIVERY_FAILED

    def test_label_is_human_readable(self, db, campaign):
        assert _run(db, campaign, frequency=True).delivery_label == "Delivered"
        assert _run(db, campaign, frequency="x").delivery_label == "Delivery failed"


class TestSettleRun:
    """_settle_run is what every pipeline path uses to pick its terminal status."""

    def test_all_deliveries_failing_makes_the_run_failed(self, db, campaign):
        from app.pipeline.runner import _settle_run

        run = _run(db, campaign, frequency="ad unit rejected it")
        _settle_run(run)

        assert run.status == STATUS_FAILED
        assert "ad unit rejected it" in run.error_message
        assert run.completed_at is not None

    def test_partial_delivery_stays_complete(self, db, campaign):
        """One ad server got it — that is not an outright failure."""
        from app.pipeline.runner import _settle_run

        run = _run(db, campaign, frequency=True, dv360="quota")
        _settle_run(run)

        assert run.status == STATUS_COMPLETE
        assert run.delivery_state == DELIVERY_PARTIAL

    def test_no_delivery_configured_stays_complete(self, db, campaign):
        """Generating audio with no ad server wired up is a success."""
        from app.pipeline.runner import _settle_run

        run = _run(db, campaign)
        _settle_run(run)

        assert run.status == STATUS_COMPLETE
        assert run.delivery_state == DELIVERY_NOT_ATTEMPTED


class TestStatusVocabularyIsShared:
    def test_scheduler_and_service_use_the_model_constants(self):
        """One source of truth — these modules used to each define their own."""
        from app.jobs import scheduler
        from app.models import ad_run
        from app.push import service

        assert scheduler.STATUS_PENDING is ad_run.STATUS_PENDING
        assert scheduler.STATUS_FAILED is ad_run.STATUS_FAILED
        assert service.STATUS_PENDING is ad_run.STATUS_PENDING
        assert ad_run.TERMINAL_STATUSES == (ad_run.STATUS_COMPLETE, ad_run.STATUS_FAILED)


class TestPipelineEndToEnd:
    """The helper is only useful if the pipeline actually routes through it."""

    @staticmethod
    def _stub_audio(monkeypatch):
        from app.pipeline import runner as runner_module

        monkeypatch.setattr(
            runner_module, "generate_voiceover",
            lambda script, voice_id, is_custom=False: b"fake-vo",
        )
        monkeypatch.setattr(runner_module, "mix_audio", lambda **kw: (b"fake-final", None))
        monkeypatch.setattr(runner_module, "_get_music_bed", lambda campaign: b"fake-music")
        monkeypatch.setattr(runner_module, "_save_outputs", lambda *a, **kw: None)

    def _deliverable_campaign(self, db):
        adv = Advertiser(name="Acme", frequency_client="acme")
        db.session.add(adv)
        db.session.commit()
        camp = Campaign(
            name="Spring", advertiser_id=adv.id, feed_type="world_cup",
            fallback_script="A static script.",
            delivery_enabled=True, frequency_tags=[{"token": "tok", "app_id": "app-1"}],
        )
        db.session.add(camp)
        db.session.commit()
        return camp

    def test_failed_delivery_makes_the_whole_run_failed(self, client, db, monkeypatch):
        from app.delivery.frequency import FrequencyDeliveryError
        from app.pipeline.runner import run_pipeline

        self._stub_audio(monkeypatch)
        monkeypatch.setattr("app.delivery.frequency.is_delivery_available", lambda: True)

        def boom(run, tag, data):
            raise FrequencyDeliveryError("ad unit rejected it")

        monkeypatch.setattr("app.delivery.frequency.deliver_ad", boom)
        campaign = self._deliverable_campaign(db)

        ad_run = run_pipeline(campaign.id, triggered_by="cron")

        assert ad_run.status == STATUS_FAILED, "a run nobody received is not complete"
        assert ad_run.delivery_state == DELIVERY_FAILED
        assert "ad unit rejected it" in ad_run.error_message

    def test_successful_delivery_is_complete_and_delivered(self, client, db, monkeypatch):
        from app.pipeline.runner import run_pipeline

        self._stub_audio(monkeypatch)
        monkeypatch.setattr("app.delivery.frequency.is_delivery_available", lambda: True)
        monkeypatch.setattr("app.delivery.frequency.deliver_ad", lambda run, tag, data: "<VAST/>")
        campaign = self._deliverable_campaign(db)

        ad_run = run_pipeline(campaign.id, triggered_by="cron")

        assert ad_run.status == STATUS_COMPLETE
        assert ad_run.delivery_state == DELIVERY_DELIVERED

    def test_failed_delivery_leaves_a_manual_override_armed(self, client, db, monkeypatch):
        """The override is one-shot on success; a run nobody received can retry."""
        from app.delivery.frequency import FrequencyDeliveryError
        from app.pipeline.runner import run_pipeline

        self._stub_audio(monkeypatch)
        monkeypatch.setattr("app.delivery.frequency.is_delivery_available", lambda: True)

        def boom(run, tag, data):
            raise FrequencyDeliveryError("ad unit rejected it")

        monkeypatch.setattr("app.delivery.frequency.deliver_ad", boom)
        campaign = self._deliverable_campaign(db)
        campaign.manual_override_script = "Staged copy."
        campaign.use_manual_override = True
        db.session.commit()

        run_pipeline(campaign.id, triggered_by="cron")

        db.session.refresh(campaign)
        assert campaign.use_manual_override is True


class TestBadgesRender:
    """The lying green badge was the visible symptom — check the pages now say it."""

    def _run_for(self, db, campaign, **fields):
        return _run(db, campaign, **fields)

    def test_run_detail_shows_delivery_failure(self, authenticated_client, db, campaign):
        run = self._run_for(
            db, campaign, status=STATUS_FAILED, frequency="ad unit rejected it"
        )
        body = authenticated_client.get(f"/admin/runs/{run.id}").data
        assert b"Delivery failed" in body

    def test_run_detail_shows_partial_delivery(self, authenticated_client, db, campaign):
        run = self._run_for(
            db, campaign, status=STATUS_COMPLETE,
            frequency=True, dv360="quota exceeded",
        )
        body = authenticated_client.get(f"/admin/runs/{run.id}").data
        assert b"Partially delivered" in body

    def test_campaign_detail_shows_delivery_state(self, authenticated_client, db, campaign):
        self._run_for(db, campaign, status=STATUS_COMPLETE, frequency=True)
        body = authenticated_client.get(f"/admin/campaigns/{campaign.id}").data
        assert b"Delivered" in body

    def test_dashboard_renders_with_the_macro(self, authenticated_client, db, campaign):
        self._run_for(db, campaign, status=STATUS_COMPLETE, frequency="nope")
        body = authenticated_client.get("/admin/").data
        assert b"Delivery failed" in body
