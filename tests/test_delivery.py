"""Tests for Frequency delivery configuration guards."""

import pytest

from app.delivery.frequency import (
    FrequencyNotConfiguredError,
    _creative_list,
    _row_index_for_new_creative,
    _serve_option_for_new_creative,
    deliver_ad,
    is_delivery_available,
)
from app.models import Advertiser, Campaign


def _make_ad_run(db, **campaign_overrides):
    adv = Advertiser(name="Test Advertiser")
    db.session.add(adv)
    db.session.commit()

    defaults = {
        "name": "Test Campaign",
        "advertiser_id": adv.id,
        "feed_type": "weather",
    }
    defaults.update(campaign_overrides)
    campaign = Campaign(**defaults)
    db.session.add(campaign)
    db.session.commit()

    class FakeAdRun:
        id = 1

    run = FakeAdRun()
    run.campaign = campaign
    return run


class TestFrequencyConfigGuards:
    def test_delivery_not_available_outside_app_context(self):
        """Without an app context, availability check fails closed."""
        assert is_delivery_available() is False

    def test_delivery_not_available_when_unconfigured(self, app, monkeypatch):
        """FREQUENCY_ENABLED / CMPAPI_BASE_URL unset means unavailable."""
        monkeypatch.setitem(app.config, "FREQUENCY_ENABLED", False)
        monkeypatch.setitem(app.config, "CMPAPI_BASE_URL", None)
        with app.app_context():
            assert is_delivery_available() is False

    def test_delivery_available_when_configured(self, app):
        with app.app_context():
            app.config["FREQUENCY_ENABLED"] = True
            app.config["CMPAPI_BASE_URL"] = "https://cmpapi.example.com"
            try:
                assert is_delivery_available() is True
            finally:
                app.config.pop("FREQUENCY_ENABLED")
                app.config.pop("CMPAPI_BASE_URL")

    def test_deliver_raises_without_base_url(self, client, db):
        """deliver_ad refuses to run when CMPAPI_BASE_URL is not set."""
        run = _make_ad_run(db, frequency_app_id="12345")

        with pytest.raises(FrequencyNotConfiguredError):
            deliver_ad(run, b"fake-mp3-bytes")

    def test_deliver_raises_without_campaign_token(self, client, db, app):
        """deliver_ad refuses to run when the campaign has no Frequency token."""
        run = _make_ad_run(db, frequency_app_id="12345", frequency_token=None)
        run.campaign.advertiser.frequency_client = "acme"
        app.config["CMPAPI_BASE_URL"] = "https://cmpapi.example.com"
        try:
            with pytest.raises(FrequencyNotConfiguredError, match="no Frequency token"):
                deliver_ad(run, b"fake-mp3-bytes")
        finally:
            app.config.pop("CMPAPI_BASE_URL")

    def test_deliver_raises_without_app_id(self, client, db, app):
        """deliver_ad refuses to run when the campaign has no Frequency app ID."""
        run = _make_ad_run(db, frequency_app_id=None)
        app.config["CMPAPI_BASE_URL"] = "https://cmpapi.example.com"
        try:
            with pytest.raises(FrequencyNotConfiguredError) as exc_info:
                deliver_ad(run, b"fake-mp3-bytes")
        finally:
            app.config.pop("CMPAPI_BASE_URL")

        assert "no frequency app id" in str(exc_info.value).lower()


class TestExistingCreatives:
    """The generated ad joins whatever creative the ad unit already carries."""

    def test_creative_list_accepts_bare_array(self):
        assert _creative_list([{"fileName": "a.mp3"}]) == [{"fileName": "a.mp3"}]

    def test_creative_list_unwraps_envelopes(self):
        for key in ("creatives", "data", "rows", "result"):
            assert _creative_list({key: [{"fileName": "a.mp3"}]}) == [{"fileName": "a.mp3"}]

    def test_creative_list_tolerates_unexpected_shapes(self):
        assert _creative_list({"message": "no creatives"}) == []
        assert _creative_list(None) == []
        assert _creative_list([{"fileName": "a.mp3"}, "junk"]) == [{"fileName": "a.mp3"}]

    def test_row_index_defaults_to_zero_when_draft_is_empty(self):
        assert _row_index_for_new_creative([]) == 0

    def test_row_index_joins_lowest_existing_audio_row(self):
        existing = [
            {"type": "audio", "rowIndex": 2},
            {"type": "audio", "rowIndex": 1},
        ]
        assert _row_index_for_new_creative(existing) == 1

    def test_row_index_ignores_non_audio_creatives(self):
        existing = [{"type": "image", "rowIndex": 3}]
        assert _row_index_for_new_creative(existing) == 0

    def test_row_index_tolerates_missing_or_bad_values(self):
        existing = [{"type": "audio"}, {"type": "audio", "rowIndex": "not-a-number"}]
        assert _row_index_for_new_creative(existing) == 0

    def test_serve_option_matches_existing_creative(self):
        assert _serve_option_for_new_creative([{"serveOption": "sequential"}]) == "sequential"

    def test_serve_option_defaults_to_random(self):
        assert _serve_option_for_new_creative([]) == "random"
        assert _serve_option_for_new_creative([{"serveOption": None}]) == "random"
