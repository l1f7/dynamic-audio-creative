"""Tests for Frequency delivery configuration guards."""

import pytest

from app.delivery.frequency import (
    FrequencyNotConfiguredError,
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

    def test_delivery_not_available_when_unconfigured(self, app):
        """FREQUENCY_ENABLED / CMPAPI_BASE_URL unset means unavailable."""
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
