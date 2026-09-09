"""Tests for Frequency token inspection on advertiser save (prompt 9)."""

from app.delivery.frequency import FrequencyDeliveryError
from app.models import Advertiser
from tests.test_frequency_token import make_token

VALID_TOKEN = make_token({"advertiser_name": "KFC", "campaign_name": "hello 1016",
                          "flight_name": "Test 135", "creative_type": "standard",
                          "creative_duration": "15", "cm_unit_id": 13433})


def _post_advertiser(client, **overrides):
    data = {"name": "Acme", "is_active": "y", "frequency_client": "acme"}
    data.update(overrides)
    return client.post("/admin/advertisers/new", data=data, follow_redirects=True)


class TestTokenOnSave:
    def test_malformed_token_is_rejected_with_message(self, authenticated_client, db):
        resp = _post_advertiser(authenticated_client, frequency_token="not-a-jwt")
        assert resp.status_code == 200
        assert b"three dot-separated parts" in resp.data
        assert Advertiser.query.count() == 0

    def test_valid_token_fields_are_displayed(self, authenticated_client, db, app):
        app.config["CMPAPI_BASE_URL"] = None
        resp = _post_advertiser(authenticated_client, frequency_token=VALID_TOKEN)
        assert b"Campaign hello 1016" in resp.data
        assert b"Flight Test 135" in resp.data
        assert b"Creative duration (s) 15" in resp.data
        assert Advertiser.query.count() == 1

    def test_edit_page_shows_saved_token_summary(self, authenticated_client, db):
        adv = Advertiser(name="Acme", frequency_token=VALID_TOKEN)
        db.session.add(adv)
        db.session.commit()
        resp = authenticated_client.get(f"/admin/advertisers/{adv.id}/edit")
        assert b"Saved token points at" in resp.data
        assert b"hello 1016" in resp.data

    def test_validation_failure_warns_but_saves(self, authenticated_client, db, app, monkeypatch):
        def failing_validate(base_url, client, token):
            raise FrequencyDeliveryError("Frequency validate failed: HTTP 405")
        monkeypatch.setattr("app.delivery.frequency._validate", failing_validate)
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", "https://staging-cmp.frequencyads.com")

        resp = _post_advertiser(authenticated_client, frequency_token=VALID_TOKEN)
        assert b"Frequency did not accept this token" in resp.data
        assert Advertiser.query.count() == 1

    def test_validation_success_reports_live_and_app_id(self, authenticated_client, db, app, monkeypatch):
        class FakeResponse:
            def json(self):
                return {"authToken": "x", "tokenData": {"campaign_id": 1016, "application_id": 77}}
        monkeypatch.setattr("app.delivery.frequency._validate", lambda b, c, t: FakeResponse())
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", "https://staging-cmp.frequencyads.com")

        resp = _post_advertiser(authenticated_client, frequency_token=VALID_TOKEN)
        assert b"Frequency token is live (campaign 1016)" in resp.data
        assert b"application ID 77" in resp.data
