"""Tests for the Frequency Tags editor on campaign save.

A campaign may need to reach more than one Frequency ad unit, so tokens are
entered as repeatable rows (freq_token_0, freq_token_1, ...) rather than a
single field. Each token's app_id is resolved against Frequency on save; the
validate call needs the advertiser's client name, which the route looks up
from the campaign's chosen advertiser.
"""

import pytest

from app.delivery.frequency import FrequencyDeliveryError
from app.models import Advertiser, Campaign
from tests.test_frequency_token import make_token

VALID_TOKEN = make_token({"advertiser_name": "KFC", "campaign_name": "hello 1016",
                          "flight_name": "Test 135", "creative_type": "standard",
                          "creative_duration": "15", "cm_unit_id": 13433})
OTHER_TOKEN = make_token({"advertiser_name": "KFC", "campaign_name": "evening 2200",
                          "flight_name": "Test 200", "creative_type": "standard",
                          "creative_duration": "15", "cm_unit_id": 13999})
STAGING_URL = "https://staging-cmp.frequencyads.com"


@pytest.fixture
def advertiser(db):
    adv = Advertiser(name="Acme", frequency_client="acme")
    db.session.add(adv)
    db.session.commit()
    return adv


def _post_campaign(client, advertiser, tokens=(), **overrides):
    data = {
        "name": "Spring", "advertiser_id": advertiser.id, "is_active": "y",
        "feed_type": "weather", "intro_seconds": 2.0, "outro_seconds": 2.0,
        "duck_volume": 0.2, "duck_fade": 0.5, "target_seconds": 30, "target_words": 75,
    }
    data.update({f"freq_token_{i}": token for i, token in enumerate(tokens)})
    data.update(overrides)
    return client.post("/admin/campaigns/new", data=data, follow_redirects=True)


class TestTagsOnSave:
    def test_malformed_token_is_rejected_with_message(self, authenticated_client, db, advertiser):
        resp = _post_campaign(authenticated_client, advertiser, tokens=["not-a-jwt"])
        assert resp.status_code == 200
        assert b"three dot-separated parts" in resp.data
        assert Campaign.query.count() == 0

    def test_valid_token_fields_are_displayed(self, authenticated_client, db, app, monkeypatch, advertiser):
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", None)
        resp = _post_campaign(authenticated_client, advertiser, tokens=[VALID_TOKEN])
        assert b"Campaign hello 1016" in resp.data
        assert b"Flight Test 135" in resp.data
        assert b"Creative duration (s) 15" in resp.data
        assert Campaign.query.one().frequency_tags == [{"token": VALID_TOKEN, "app_id": None}]

    def test_blank_token_is_stored_as_none(self, authenticated_client, db, advertiser):
        _post_campaign(authenticated_client, advertiser, tokens=["  "])
        assert Campaign.query.one().frequency_tags is None

    def test_two_tokens_are_both_stored(self, authenticated_client, db, app, monkeypatch, advertiser):
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", None)
        _post_campaign(authenticated_client, advertiser, tokens=[VALID_TOKEN, OTHER_TOKEN])
        tags = Campaign.query.one().frequency_tags
        assert [t["token"] for t in tags] == [VALID_TOKEN, OTHER_TOKEN]

    def test_one_bad_token_blocks_the_whole_save(self, authenticated_client, db, app, monkeypatch, advertiser):
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", None)
        resp = _post_campaign(authenticated_client, advertiser, tokens=[VALID_TOKEN, "not-a-jwt"])
        assert b"three dot-separated parts" in resp.data
        assert Campaign.query.count() == 0

    def test_edit_page_shows_saved_token_summary(self, authenticated_client, db, advertiser):
        camp = Campaign(name="Spring", advertiser_id=advertiser.id, feed_type="weather",
                        frequency_tags=[{"token": VALID_TOKEN, "app_id": None}])
        db.session.add(camp)
        db.session.commit()
        resp = authenticated_client.get(f"/admin/campaigns/{camp.id}/edit")
        assert b"hello 1016" in resp.data

    def test_advertiser_form_no_longer_takes_a_token(self, authenticated_client, db):
        resp = authenticated_client.get("/admin/advertisers/new")
        assert b"frequency_token" not in resp.data

    def test_validation_failure_warns_but_saves(self, authenticated_client, db, app, monkeypatch, advertiser):
        def failing_validate(base_url, client, token):
            raise FrequencyDeliveryError("Frequency validate failed: HTTP 405")
        monkeypatch.setattr("app.delivery.frequency._validate", failing_validate)
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", STAGING_URL)

        resp = _post_campaign(authenticated_client, advertiser, tokens=[VALID_TOKEN])
        assert b"Frequency did not accept this token" in resp.data
        assert Campaign.query.count() == 1

    def test_validation_uses_the_advertisers_client(self, authenticated_client, db, app, monkeypatch, advertiser):
        seen = {}

        class FakeResponse:
            def json(self):
                return {"authToken": "x", "tokenData": {"campaign_id": 1016, "application_id": 77}}

        def fake_validate(base_url, client, token):
            seen["client"] = client
            return FakeResponse()
        monkeypatch.setattr("app.delivery.frequency._validate", fake_validate)
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", STAGING_URL)

        resp = _post_campaign(authenticated_client, advertiser, tokens=[VALID_TOKEN])
        assert seen["client"] == "acme"
        assert b"Frequency token is live (campaign 1016)" in resp.data
        assert b"application ID 77" in resp.data
        assert Campaign.query.one().frequency_tags == [{"token": VALID_TOKEN, "app_id": 77}]

    def test_validation_skipped_when_advertiser_has_no_client(self, authenticated_client, db, app, monkeypatch, advertiser):
        advertiser.frequency_client = None
        db.session.commit()
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", STAGING_URL)
        resp = _post_campaign(authenticated_client, advertiser, tokens=[VALID_TOKEN])
        assert b"Frequency validation skipped" in resp.data
        assert Campaign.query.count() == 1
