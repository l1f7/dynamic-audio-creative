"""Tests for tick-driven delivery of pushed runs (prompts 5 and 7)."""

import pytest

from app.extensions import db as _db
from app.jobs.scheduler import deliver_pending_pushes
from app.models import AdRun, Advertiser, Campaign

HASH = "f" * 64


@pytest.fixture
def campaign(db):
    adv = Advertiser(name="Acme", frequency_client="acme", frequency_token="tok")
    _db.session.add(adv)
    _db.session.commit()
    camp = Campaign(name="Spring", advertiser_id=adv.id, feed_type="weather",
                    frequency_app_id="app-1", delivery_enabled=True)
    _db.session.add(camp)
    _db.session.commit()
    return camp


@pytest.fixture
def delivery(monkeypatch):
    calls = []
    monkeypatch.setattr("app.delivery.frequency.is_delivery_available", lambda: True)
    monkeypatch.setattr("app.delivery.frequency.deliver_ad", lambda run, data: calls.append(run.id) or "<VAST/>")
    monkeypatch.setattr("app.pipeline.runner._load_final_ad", lambda run: b"audio")
    return calls


def _pushed_run(campaign, status="pending", content_hash=HASH):
    run = AdRun(campaign_id=campaign.id, triggered_by="watcher", status=status,
                source_content_hash=content_hash, final_ad_s3_key="pushed/k.mp3")
    _db.session.add(run)
    _db.session.commit()
    return run


class TestDeliverPendingPushes:
    def test_pending_pushed_run_is_delivered(self, campaign, delivery):
        run = _pushed_run(campaign)
        assert deliver_pending_pushes() == 1
        assert delivery == [run.id]
        assert run.status == "complete"
        assert run.delivered_at is not None
        assert run.vast_response == "<VAST/>"
        assert run.delivery_reference == "frequency"

    def test_run_already_delivering_is_skipped(self, campaign, delivery):
        _pushed_run(campaign, status="delivering")
        assert deliver_pending_pushes() == 0
        assert delivery == []

    def test_failure_records_error_and_marks_failed(self, campaign, delivery, monkeypatch):
        from app.delivery.frequency import FrequencyDeliveryError

        def boom(run, data):
            raise FrequencyDeliveryError("Frequency publish draft failed: HTTP 500")
        monkeypatch.setattr("app.delivery.frequency.deliver_ad", boom)
        run = _pushed_run(campaign)
        deliver_pending_pushes()
        assert run.status == "failed"
        assert run.delivery_error == "Frequency publish draft failed: HTTP 500"
        assert run.completed_at is not None

    def test_generated_run_is_untouched(self, campaign, delivery):
        run = AdRun(campaign_id=campaign.id, triggered_by="cron", status="pending", final_ad_s3_key="k")
        _db.session.add(run)
        _db.session.commit()
        assert deliver_pending_pushes() == 0
        assert run.status == "pending"

    def test_paused_campaign_pushes_stay_pending(self, campaign, delivery):
        campaign.delivery_enabled = False
        _db.session.commit()
        run = _pushed_run(campaign)
        assert deliver_pending_pushes() == 0
        assert run.status == "pending"

        campaign.delivery_enabled = True
        _db.session.commit()
        assert deliver_pending_pushes() == 1
        assert run.status == "complete"

    def test_delivery_unavailable_leaves_runs_pending(self, campaign, monkeypatch):
        monkeypatch.setattr("app.delivery.frequency.is_delivery_available", lambda: False)
        run = _pushed_run(campaign)
        assert deliver_pending_pushes() == 0
        assert run.status == "pending"


class TestTickEndpoint:
    def test_tick_delivers(self, client, app, campaign, delivery):
        _pushed_run(campaign)
        app.config["API_KEY"] = "global"
        try:
            resp = client.post("/api/v1/scheduler/tick", headers={"X-API-Key": "global"})
        finally:
            app.config.pop("API_KEY")
        assert resp.status_code == 200
        assert resp.get_json() == {"delivered_pushes": 1}
