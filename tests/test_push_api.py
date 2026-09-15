"""Tests for the desktop push mode API (app/api/push.py)."""

from datetime import datetime, timezone

import pytest
from botocore.exceptions import ClientError

from app.extensions import db as _db
from app.models import AdRun, Advertiser, Campaign
from app.push import audio, service
from app.push.keys import create_key
from tests.test_frequency_token import make_token

HASH_A = "a" * 64
HASH_B = "b" * 64
AD_UNIT_SECONDS = 30
TOKEN = make_token({"campaign_name": "Spring", "creative_duration": str(AD_UNIT_SECONDS)})
TOKEN_NO_DURATION = make_token({"campaign_name": "Spring"})


@pytest.fixture
def advertiser(db):
    adv = Advertiser(name="Acme Motors", frequency_client="acme", frequency_token=TOKEN)
    db.session.add(adv)
    db.session.commit()
    return adv


@pytest.fixture
def campaign(db, advertiser):
    camp = Campaign(name="Spring Sale", advertiser_id=advertiser.id, feed_type="push",
                    campaign_type="push", frequency_app_id="app-1", delivery_enabled=True)
    db.session.add(camp)
    db.session.commit()
    return camp


@pytest.fixture
def headers(advertiser):
    _, plaintext = create_key(advertiser, "test station")
    return {"X-API-Key": plaintext}


@pytest.fixture
def other_campaign(db):
    other = Advertiser(name="Other")
    db.session.add(other)
    db.session.commit()
    theirs = Campaign(name="Theirs", advertiser_id=other.id, feed_type="push",
                      campaign_type="push")
    db.session.add(theirs)
    db.session.commit()
    return theirs


@pytest.fixture
def fake_storage(monkeypatch):
    """S3 stand-in that records uploads and serves any key."""
    store = {}
    monkeypatch.setattr(service.s3, "download", lambda key: store.get(key, b"audio"))
    monkeypatch.setattr(service.s3, "upload", lambda key, data, content_type="audio/mpeg": store.__setitem__(key, data))
    monkeypatch.setattr("app.api.push.s3.is_configured", lambda: True)
    monkeypatch.setattr(
        "app.api.push.s3.generate_upload_url",
        lambda key, content_type, expires_in: f"https://bucket/{key}?ct={content_type}",
    )
    return store


@pytest.fixture
def mp3_probe(monkeypatch):
    monkeypatch.setattr(audio, "probe", lambda raw, name: audio.ProbedAudio("mp3", float(AD_UNIT_SECONDS)))


def _push(client, headers, campaign_id, content_hash=HASH_A, filename="spot.mp3"):
    return client.post(
        f"/api/v1/campaigns/{campaign_id}/push",
        json={"upload_key": f"pushed/{campaign_id}/{content_hash}.mp3",
              "content_hash": content_hash, "filename": filename},
        headers=headers,
    )


def _delivered_run(campaign, content_hash=HASH_A, **overrides):
    fields = dict(campaign_id=campaign.id, triggered_by="watcher", status="complete",
                  source_content_hash=content_hash, source_filename="spot.wav",
                  final_ad_s3_key="k", delivered_at=datetime.now(timezone.utc))
    fields.update(overrides)
    run = AdRun(**fields)
    _db.session.add(run)
    _db.session.commit()
    return run


class TestMe:
    def test_rejects_missing_key(self, client, advertiser):
        assert client.get("/api/v1/me").status_code == 401

    def test_rejects_bad_key(self, client, advertiser):
        assert client.get("/api/v1/me", headers={"X-API-Key": "dac_nope"}).status_code == 401

    def test_names_owner(self, client, advertiser, headers):
        resp = client.get("/api/v1/me", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json() == {"advertiser_id": advertiser.id, "advertiser_name": "Acme Motors"}


class TestCampaigns:
    def test_lists_only_own_active_campaigns(self, client, db, advertiser, campaign, headers, other_campaign):
        db.session.add(Campaign(name="Retired", advertiser_id=advertiser.id, feed_type="push",
                                campaign_type="push", is_active=False))
        db.session.commit()
        resp = client.get("/api/v1/campaigns", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json() == [{
            "id": campaign.id, "name": "Spring Sale", "advertiser_name": "Acme Motors",
            "delivery_enabled": True, "deliverable": True,
        }]

    @pytest.mark.parametrize("missing", ["frequency_app_id", "frequency_client", "frequency_token"])
    def test_not_deliverable_when_credential_missing(self, client, db, advertiser, campaign, headers, missing):
        target = campaign if missing == "frequency_app_id" else advertiser
        setattr(target, missing, None)
        db.session.commit()
        assert client.get("/api/v1/campaigns", headers=headers).get_json()[0]["deliverable"] is False

    def test_bad_key_is_401(self, client, campaign):
        assert client.get("/api/v1/campaigns", headers={"X-API-Key": "dac_bad"}).status_code == 401

    def test_foreign_campaign_is_404_json(self, client, headers, other_campaign):
        resp = client.post(f"/api/v1/campaigns/{other_campaign.id}/pause", json={"paused": True}, headers=headers)
        assert resp.status_code == 404
        assert resp.get_json() == {"error": "Campaign not found"}


class TestUploads:
    def _request(self, client, headers, campaign_id, content_hash=HASH_A):
        return client.post(
            f"/api/v1/campaigns/{campaign_id}/uploads",
            json={"filename": "spot.wav", "content_hash": content_hash,
                  "size": 4194304, "content_type": "audio/wav"},
            headers=headers,
        )

    def test_presigned_url_for_declared_content_type(self, client, campaign, headers, fake_storage):
        body = self._request(client, headers, campaign.id).get_json()
        assert body["upload_key"] == f"pushed/{campaign.id}/{HASH_A}.wav"
        assert f"/pushed/{campaign.id}/" in body["upload_url"]
        assert body["upload_url"].endswith("?ct=audio/wav")

    def test_wrong_advertiser_is_404(self, client, headers, other_campaign, fake_storage):
        assert self._request(client, headers, other_campaign.id).status_code == 404

    def test_malformed_hash_is_400(self, client, campaign, headers, fake_storage):
        assert self._request(client, headers, campaign.id, content_hash="XYZ").status_code == 400

    def test_duplicate_of_delivered_run(self, client, campaign, headers, fake_storage):
        run = _delivered_run(campaign)
        assert self._request(client, headers, campaign.id).get_json() == {"duplicate_run_id": run.id}

    def test_failed_run_is_not_a_duplicate(self, client, campaign, headers, fake_storage):
        _delivered_run(campaign, status="failed", delivered_at=None)
        assert "upload_url" in self._request(client, headers, campaign.id).get_json()

    def test_storage_unconfigured_is_retryable(self, client, campaign, headers, monkeypatch):
        monkeypatch.setattr("app.api.push.s3.is_configured", lambda: False)
        assert self._request(client, headers, campaign.id).status_code == 503


class TestPush:
    def test_push_creates_pending_run(self, client, campaign, headers, fake_storage, mp3_probe):
        resp = _push(client, headers, campaign.id)
        assert resp.status_code == 200
        run = _db.session.get(AdRun, resp.get_json()["run_id"])
        assert run.triggered_by == "watcher"
        assert run.status == "pending"
        assert run.source_content_hash == HASH_A
        assert run.source_filename == "spot.mp3"
        assert run.source_bytes == len(b"audio")
        assert run.final_ad_s3_key == f"pushed/{campaign.id}/{HASH_A}.mp3"
        assert run.status_label == "Waiting for delivery..."

    def test_same_hash_twice_returns_same_run(self, client, campaign, headers, fake_storage, mp3_probe):
        first = _push(client, headers, campaign.id).get_json()["run_id"]
        second = _push(client, headers, campaign.id).get_json()["run_id"]
        assert first == second
        assert AdRun.query.count() == 1

    def test_unique_constraint_backs_idempotency(self, db, campaign):
        _delivered_run(campaign)
        db.session.add(AdRun(campaign_id=campaign.id, triggered_by="watcher", status="pending",
                             source_content_hash=HASH_A))
        from sqlalchemy.exc import IntegrityError
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    def test_repush_of_failed_run_requeues_it(self, client, campaign, headers, fake_storage, mp3_probe):
        run = _delivered_run(campaign, status="failed", delivered_at=None, delivery_error="boom")
        assert _push(client, headers, campaign.id).get_json()["run_id"] == run.id
        assert run.status == "pending"
        assert run.delivery_error is None
        assert AdRun.query.count() == 1

    def test_other_advertisers_campaign_is_404(self, client, headers, other_campaign, fake_storage, mp3_probe):
        assert _push(client, headers, other_campaign.id).status_code == 404

    def test_missing_s3_object_is_rejected(self, client, campaign, headers, fake_storage, monkeypatch):
        def missing(key):
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "gone"}}, "GetObject")
        monkeypatch.setattr(service.s3, "download", missing)
        assert _push(client, headers, campaign.id).status_code == 400
        assert AdRun.query.count() == 0

    def test_foreign_upload_key_is_400(self, client, campaign, headers, fake_storage):
        resp = client.post(
            f"/api/v1/campaigns/{campaign.id}/push",
            json={"upload_key": "pushed/999/other.mp3", "content_hash": HASH_A, "filename": "x.mp3"},
            headers=headers,
        )
        assert resp.status_code == 400

    def test_paused_campaign_still_accepts_push(self, client, db, campaign, headers, fake_storage, mp3_probe):
        campaign.delivery_enabled = False
        db.session.commit()
        resp = _push(client, headers, campaign.id)
        assert resp.status_code == 200
        assert _db.session.get(AdRun, resp.get_json()["run_id"]).status == "pending"


class TestAudioValidation:
    def test_duration_within_tolerance_passes(self, client, campaign, headers, fake_storage, monkeypatch):
        monkeypatch.setattr(audio, "probe", lambda raw, name: audio.ProbedAudio("mp3", 30.6))
        assert _push(client, headers, campaign.id).status_code == 200

    def test_duration_mismatch_is_422_with_readable_reason(self, client, campaign, headers, fake_storage, monkeypatch):
        monkeypatch.setattr(audio, "probe", lambda raw, name: audio.ProbedAudio("mp3", 15.0))
        resp = _push(client, headers, campaign.id)
        assert resp.status_code == 422
        assert resp.mimetype == "text/plain"
        assert resp.get_data(as_text=True) == "Audio is 15.0s but the ad unit expects 30s"
        assert AdRun.query.count() == 0

    def test_token_without_duration_skips_check(self, client, db, advertiser, campaign, headers, fake_storage, monkeypatch):
        advertiser.frequency_token = TOKEN_NO_DURATION
        db.session.commit()
        monkeypatch.setattr(audio, "probe", lambda raw, name: audio.ProbedAudio("mp3", 15.0))
        assert _push(client, headers, campaign.id).status_code == 200

    def test_unreadable_audio_is_422(self, client, campaign, headers, fake_storage, monkeypatch):
        def bad_probe(raw, name):
            raise audio.PushRejected("Unsupported or unreadable audio format")
        monkeypatch.setattr(audio, "probe", bad_probe)
        resp = _push(client, headers, campaign.id)
        assert resp.status_code == 422
        assert "Unsupported" in resp.get_data(as_text=True)

    def test_wav_is_transcoded_to_mp3(self, client, campaign, headers, fake_storage, monkeypatch):
        monkeypatch.setattr(audio, "probe", lambda raw, name: audio.ProbedAudio("wav", 30.0))
        monkeypatch.setattr(audio, "transcode_to_mp3", lambda raw, name: b"mp3-bytes")
        resp = client.post(
            f"/api/v1/campaigns/{campaign.id}/push",
            json={"upload_key": f"pushed/{campaign.id}/{HASH_A}.wav",
                  "content_hash": HASH_A, "filename": "spot.wav"},
            headers=headers,
        )
        run = _db.session.get(AdRun, resp.get_json()["run_id"])
        assert run.final_ad_s3_key == f"pushed/{campaign.id}/{HASH_A}.mp3"
        assert fake_storage[run.final_ad_s3_key] == b"mp3-bytes"


class TestRuns:
    def test_run_status(self, client, db, campaign, headers):
        run = AdRun(campaign_id=campaign.id, triggered_by="watcher", status="delivering")
        db.session.add(run)
        db.session.commit()
        resp = client.get(f"/api/v1/runs/{run.id}", headers=headers)
        assert resp.get_json() == {"run_id": run.id, "status": "delivering", "delivery_error": None}

    def test_foreign_run_is_404(self, client, db, headers, other_campaign):
        run = AdRun(campaign_id=other_campaign.id, triggered_by="watcher", status="complete")
        db.session.add(run)
        db.session.commit()
        assert client.get(f"/api/v1/runs/{run.id}", headers=headers).status_code == 404

    def test_history_newest_first_with_one_active(self, client, db, campaign, headers):
        older = _delivered_run(campaign, HASH_A, source_filename="v1.wav",
                               created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
                               delivered_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc))
        newer = _delivered_run(campaign, HASH_B, source_filename="v2.wav",
                               created_at=datetime(2026, 9, 8, tzinfo=timezone.utc),
                               delivered_at=datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc))
        broken = _delivered_run(campaign, "c" * 64, status="failed", source_filename="v3.wav",
                                created_at=datetime(2026, 9, 9, tzinfo=timezone.utc),
                                delivered_at=None, delivery_error="duration wrong")
        no_audio = AdRun(campaign_id=campaign.id, triggered_by="manual", status="failed",
                         created_at=datetime(2026, 9, 10, tzinfo=timezone.utc))
        db.session.add(no_audio)
        db.session.commit()

        body = client.get(f"/api/v1/campaigns/{campaign.id}/runs", headers=headers).get_json()
        assert [r["run_id"] for r in body] == [broken.id, newer.id, older.id]
        assert body[0] == {"run_id": broken.id, "filename": "v3.wav", "delivered_at": None,
                           "status": "failed", "is_active": False, "error": "duration wrong"}
        assert body[1]["delivered_at"] == "2026-09-08T12:00:00Z"
        assert [r["is_active"] for r in body] == [False, True, False]

    def test_pipeline_run_filename_falls_back_to_key(self, client, db, campaign, headers):
        db.session.add(AdRun(campaign_id=campaign.id, triggered_by="cron", status="complete",
                             final_ad_s3_key="campaigns/1/runs/5/final_ad_x.mp3"))
        db.session.commit()
        body = client.get(f"/api/v1/campaigns/{campaign.id}/runs", headers=headers).get_json()
        assert body[0]["filename"] == "final_ad_x.mp3"


class TestRevert:
    @pytest.fixture
    def redeliver_spy(self, monkeypatch):
        calls = []

        def fake_redeliver(run_id, deliver_frequency=False, deliver_dv360=False):
            calls.append((run_id, deliver_frequency))
            run = _db.session.get(AdRun, run_id)
            run.delivered_at = datetime(2026, 9, 9, tzinfo=timezone.utc)
            _db.session.commit()
        monkeypatch.setattr("app.pipeline.runner.redeliver", fake_redeliver)
        monkeypatch.setattr("app.delivery.frequency.is_delivery_available", lambda: True)
        return calls

    def test_revert_redelivers_and_becomes_active(self, client, campaign, headers, redeliver_spy):
        old = _delivered_run(campaign, HASH_A, delivered_at=datetime(2026, 9, 1, tzinfo=timezone.utc))
        _delivered_run(campaign, HASH_B, delivered_at=datetime(2026, 9, 5, tzinfo=timezone.utc))
        resp = client.post(f"/api/v1/campaigns/{campaign.id}/revert", json={"run_id": old.id}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json() == {"run_id": old.id}
        assert redeliver_spy == [(old.id, True)]
        assert service.active_run_id(campaign) == old.id

    def test_revert_failure_is_502(self, client, campaign, headers, monkeypatch):
        def failing(run_id, deliver_frequency=False, deliver_dv360=False):
            run = _db.session.get(AdRun, run_id)
            run.delivery_error = "Frequency publish draft failed"
            _db.session.commit()
        monkeypatch.setattr("app.pipeline.runner.redeliver", failing)
        monkeypatch.setattr("app.delivery.frequency.is_delivery_available", lambda: True)
        run = _delivered_run(campaign)
        resp = client.post(f"/api/v1/campaigns/{campaign.id}/revert", json={"run_id": run.id}, headers=headers)
        assert resp.status_code == 502
        assert resp.get_json()["error"] == "Frequency publish draft failed"

    def test_revert_of_other_advertisers_run_is_404(self, client, headers, other_campaign, redeliver_spy):
        run = _delivered_run(other_campaign)
        resp = client.post(f"/api/v1/campaigns/{other_campaign.id}/revert", json={"run_id": run.id}, headers=headers)
        assert resp.status_code == 404
        assert redeliver_spy == []

    def test_revert_of_never_delivered_run_is_rejected(self, client, campaign, headers, redeliver_spy):
        run = _delivered_run(campaign, status="failed", delivered_at=None)
        resp = client.post(f"/api/v1/campaigns/{campaign.id}/revert", json={"run_id": run.id}, headers=headers)
        assert resp.status_code == 409
        assert redeliver_spy == []

    def test_revert_on_paused_campaign_is_rejected(self, client, db, campaign, headers, redeliver_spy):
        run = _delivered_run(campaign)
        campaign.delivery_enabled = False
        db.session.commit()
        resp = client.post(f"/api/v1/campaigns/{campaign.id}/revert", json={"run_id": run.id}, headers=headers)
        assert resp.status_code == 409


class TestPause:
    def test_pause_flips_flag_and_unpause_restores(self, client, campaign, headers):
        resp = client.post(f"/api/v1/campaigns/{campaign.id}/pause", json={"paused": True}, headers=headers)
        assert resp.status_code == 200
        assert resp.get_json() == {}
        assert campaign.delivery_enabled is False
        assert client.get("/api/v1/campaigns", headers=headers).get_json()[0]["delivery_enabled"] is False

        client.post(f"/api/v1/campaigns/{campaign.id}/pause", json={"paused": False}, headers=headers)
        assert campaign.delivery_enabled is True

    def test_pause_requires_boolean(self, client, campaign, headers):
        resp = client.post(f"/api/v1/campaigns/{campaign.id}/pause", json={"paused": "yes"}, headers=headers)
        assert resp.status_code == 400
