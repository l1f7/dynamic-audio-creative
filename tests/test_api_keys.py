"""Tests for per-advertiser API keys (prompt 1)."""

from app.extensions import db as _db
from app.models import Advertiser, ApiKey, Campaign
from app.push.keys import create_key, resolve_key, revoke_key


def _advertiser(name="Acme"):
    adv = Advertiser(name=name)
    _db.session.add(adv)
    _db.session.commit()
    return adv


class TestResolveKey:
    def test_valid_key_resolves_to_its_advertiser(self, db):
        adv = _advertiser()
        api_key, plaintext = create_key(adv, "Studio A")
        assert plaintext.startswith("dac_")
        assert api_key.key_prefix == plaintext[:8]
        assert plaintext not in api_key.key_hash
        assert resolve_key(plaintext).id == adv.id

    def test_last_used_at_updates(self, db):
        adv = _advertiser()
        api_key, plaintext = create_key(adv, "Studio A")
        assert api_key.last_used_at is None
        resolve_key(plaintext)
        assert api_key.last_used_at is not None

    def test_revoked_key_is_rejected(self, db):
        adv = _advertiser()
        api_key, plaintext = create_key(adv, "Studio A")
        revoke_key(api_key)
        assert resolve_key(plaintext) is None

    def test_unknown_key_is_rejected(self, db):
        _advertiser()
        assert resolve_key("dac_definitely-not-a-key") is None
        assert resolve_key(None) is None
        assert resolve_key("") is None

    def test_shared_prefix_does_not_confuse_lookup(self, db):
        adv = _advertiser()
        api_key, plaintext = create_key(adv, "Studio A")
        assert resolve_key(plaintext[:8] + "tampered") is None

    def test_inactive_advertiser_key_is_rejected(self, db):
        adv = _advertiser()
        _, plaintext = create_key(adv, "Studio A")
        adv.is_active = False
        _db.session.commit()
        assert resolve_key(plaintext) is None


class TestScoping:
    def test_keys_never_see_each_others_data(self, client, db):
        acme, other = _advertiser("Acme"), _advertiser("Other")
        _, acme_key = create_key(acme, "a")
        _, other_key = create_key(other, "o")
        acme_campaign = Campaign(name="Acme Spring", advertiser_id=acme.id, feed_type="weather")
        other_campaign = Campaign(name="Other Fall", advertiser_id=other.id, feed_type="weather")
        _db.session.add_all([acme_campaign, other_campaign])
        _db.session.commit()

        acme_view = client.get("/api/v1/campaigns", headers={"X-API-Key": acme_key}).get_json()
        other_view = client.get("/api/v1/campaigns", headers={"X-API-Key": other_key}).get_json()
        assert [c["name"] for c in acme_view] == ["Acme Spring"]
        assert [c["name"] for c in other_view] == ["Other Fall"]

        resp = client.get(f"/api/v1/campaigns/{other_campaign.id}/runs", headers={"X-API-Key": acme_key})
        assert resp.status_code == 404


class TestGlobalKey:
    def test_global_key_only_works_for_tick(self, client, app, db, monkeypatch):
        monkeypatch.setattr("app.jobs.scheduler.deliver_pending_pushes", lambda: 0)
        app.config["API_KEY"] = "global-secret"
        try:
            headers = {"X-API-Key": "global-secret"}
            assert client.post("/api/v1/scheduler/tick", headers=headers).status_code == 200
            assert client.get("/api/v1/me", headers=headers).status_code == 401
            assert client.post("/api/v1/scheduler/tick", headers={"X-API-Key": "nope"}).status_code == 401
        finally:
            app.config.pop("API_KEY")


class TestAdminKeys:
    def test_create_list_revoke(self, authenticated_client, db):
        adv = _advertiser()
        resp = authenticated_client.post(
            f"/admin/advertisers/{adv.id}/keys", data={"name": "Studio B"}, follow_redirects=True
        )
        assert resp.status_code == 200
        assert b"dac_" in resp.data
        key = ApiKey.query.filter_by(advertiser_id=adv.id).one()
        assert key.name == "Studio B"

        listing = authenticated_client.get(f"/admin/advertisers/{adv.id}/keys")
        assert key.key_prefix.encode() in listing.data
        assert b"dac_" + key.key_prefix[4:].encode() not in listing.data.replace(key.key_prefix.encode(), b"")

        resp = authenticated_client.post(
            f"/admin/advertisers/{adv.id}/keys/{key.id}/revoke", follow_redirects=True
        )
        assert b"revoked" in resp.data
        _db.session.refresh(key)
        assert key.is_revoked

    def test_revoke_across_advertisers_is_404(self, authenticated_client, db):
        acme, other = _advertiser("Acme"), _advertiser("Other")
        key, _ = create_key(other, "o")
        resp = authenticated_client.post(f"/admin/advertisers/{acme.id}/keys/{key.id}/revoke")
        assert resp.status_code == 404
