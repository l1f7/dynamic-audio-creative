"""Tests for the Push campaign type — what it hides, and what it stops running."""

import pytest

from app.extensions import db as _db
from app.jobs.scheduler import run_due_campaigns
from app.models import Advertiser, Campaign
from app.models.campaign import CAMPAIGN_TYPE_AUTOMATED, CAMPAIGN_TYPE_PUSH
from app.pipeline.exceptions import PushCampaignError
from app.pipeline.runner import run_pipeline
from app.push.keys import create_key


@pytest.fixture
def advertiser(db):
    adv = Advertiser(name="Acme Motors")
    db.session.add(adv)
    db.session.commit()
    return adv


@pytest.fixture
def headers(advertiser):
    _, plaintext = create_key(advertiser, "studio a")
    return {"X-API-Key": plaintext}


def _campaign(advertiser, name, campaign_type, **kwargs):
    camp = Campaign(
        name=name,
        advertiser_id=advertiser.id,
        feed_type="push" if campaign_type == CAMPAIGN_TYPE_PUSH else "weather",
        campaign_type=campaign_type,
        **kwargs,
    )
    _db.session.add(camp)
    _db.session.commit()
    return camp


class TestDefaults:
    def test_campaign_is_automated_unless_told_otherwise(self, db, advertiser):
        camp = Campaign(name="Legacy", advertiser_id=advertiser.id, feed_type="weather")
        db.session.add(camp)
        db.session.commit()
        assert camp.campaign_type == CAMPAIGN_TYPE_AUTOMATED
        assert camp.is_push is False


class TestNoAutomation:
    def test_scheduler_skips_push_campaigns(self, db, advertiser, monkeypatch):
        """A push campaign with a due cron schedule is still never generated."""
        ran = []
        monkeypatch.setattr(
            "app.jobs.scheduler.run_pipeline",
            lambda campaign_id, triggered_by=None: ran.append(campaign_id),
        )
        _campaign(advertiser, "Pushed", CAMPAIGN_TYPE_PUSH, cron_schedule="* * * * *")
        run_due_campaigns()
        assert ran == []

    def test_scheduler_still_runs_automated_campaigns(self, db, advertiser, monkeypatch):
        ran = []

        class _Run:
            id, status = 1, "complete"

        def _fake(campaign_id, triggered_by=None):
            ran.append(campaign_id)
            return _Run()

        monkeypatch.setattr("app.jobs.scheduler.run_pipeline", _fake)
        camp = _campaign(advertiser, "Auto", CAMPAIGN_TYPE_AUTOMATED, cron_schedule="* * * * *")
        run_due_campaigns()
        assert ran == [camp.id]

    def test_run_pipeline_refuses_a_push_campaign(self, db, advertiser):
        camp = _campaign(advertiser, "Pushed", CAMPAIGN_TYPE_PUSH)
        with pytest.raises(PushCampaignError):
            run_pipeline(camp.id, triggered_by="manual")
        assert camp.ad_runs.count() == 0


class TestApiVisibility:
    def test_list_returns_only_push_campaigns(self, client, db, advertiser, headers):
        _campaign(advertiser, "Auto", CAMPAIGN_TYPE_AUTOMATED)
        _campaign(advertiser, "Pushed", CAMPAIGN_TYPE_PUSH)
        body = client.get("/api/v1/campaigns", headers=headers).get_json()
        assert [c["name"] for c in body] == ["Pushed"]

    def test_automated_campaign_is_not_reachable(self, client, db, advertiser, headers):
        auto = _campaign(advertiser, "Auto", CAMPAIGN_TYPE_AUTOMATED)
        for path in (f"/api/v1/campaigns/{auto.id}/runs", f"/api/v1/campaigns/{auto.id}/uploads"):
            method = client.get if path.endswith("runs") else client.post
            assert method(path, headers=headers, json={}).status_code == 404


class TestAdminGuards:
    def test_generate_is_refused_for_a_push_campaign(self, authenticated_client, db, advertiser):
        camp = _campaign(advertiser, "Pushed", CAMPAIGN_TYPE_PUSH)
        resp = authenticated_client.post(
            f"/admin/campaigns/{camp.id}/generate", follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"nothing to generate" in resp.data
        assert camp.ad_runs.count() == 0

    def test_saving_as_push_clears_the_automation_config(self, authenticated_client, db, advertiser):
        camp = _campaign(
            advertiser, "Was Auto", CAMPAIGN_TYPE_AUTOMATED,
            cron_schedule="0 6 * * *", feed_url="https://example.com/feed",
        )
        resp = authenticated_client.post(
            f"/admin/campaigns/{camp.id}/edit",
            data={
                "name": "Now Push",
                "advertiser_id": str(advertiser.id),
                "campaign_type": CAMPAIGN_TYPE_PUSH,
                "feed_type": "",
                "cron_schedule": "0 6 * * *",
                "intro_seconds": "2.0", "outro_seconds": "2.0",
                "duck_volume": "0.2", "duck_fade": "0.5",
                "target_seconds": "30", "target_words": "75",
                "is_active": "y",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200
        _db.session.refresh(camp)
        assert camp.is_push
        assert camp.cron_schedule is None
        assert camp.feed_url is None
        assert camp.feed_type == "push"

    def test_automated_campaign_still_requires_a_feed_type(self, authenticated_client, db, advertiser):
        resp = authenticated_client.post(
            "/admin/campaigns/new",
            data={
                "name": "No Feed",
                "advertiser_id": str(advertiser.id),
                "campaign_type": CAMPAIGN_TYPE_AUTOMATED,
                "feed_type": "",
                "intro_seconds": "2.0", "outro_seconds": "2.0",
                "duck_volume": "0.2", "duck_fade": "0.5",
                "target_seconds": "30", "target_words": "75",
            },
        )
        assert resp.status_code == 200
        assert b"Feed type is required" in resp.data
        assert Campaign.query.filter_by(name="No Feed").first() is None
