"""Tests for Frequency delivery configuration guards."""

import pytest

from app.delivery.frequency import (
    FrequencyNotConfiguredError,
    _banners_for_row,
    _creative_list,
    _row_index_for_new_creative,
    _serve_option_for_new_creative,
    deliver_ad,
    is_delivery_available,
)
from app.models import Advertiser, Campaign
from app.models.campaign import FREQUENCY_TAG_APP_ID_KEY, FREQUENCY_TAG_TOKEN_KEY


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


def _tag(app_id="12345", token="tok"):
    return {FREQUENCY_TAG_APP_ID_KEY: app_id, FREQUENCY_TAG_TOKEN_KEY: token}


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
        run = _make_ad_run(db)

        with pytest.raises(FrequencyNotConfiguredError):
            deliver_ad(run, _tag(), b"fake-mp3-bytes")

    def test_deliver_raises_without_tag_token(self, client, db, app):
        """deliver_ad refuses to run when the tag has no token."""
        run = _make_ad_run(db)
        run.campaign.advertiser.frequency_client = "acme"
        app.config["CMPAPI_BASE_URL"] = "https://cmpapi.example.com"
        try:
            with pytest.raises(FrequencyNotConfiguredError, match="no Frequency token"):
                deliver_ad(run, _tag(token=None), b"fake-mp3-bytes")
        finally:
            app.config.pop("CMPAPI_BASE_URL")

    def test_deliver_raises_without_app_id(self, client, db, app):
        """deliver_ad refuses to run when the tag has no app ID."""
        run = _make_ad_run(db)
        app.config["CMPAPI_BASE_URL"] = "https://cmpapi.example.com"
        try:
            with pytest.raises(FrequencyNotConfiguredError) as exc_info:
                deliver_ad(run, _tag(app_id=None), b"fake-mp3-bytes")
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

    def test_row_index_avoids_banner_already_in_row_zero(self):
        existing = [{"type": "image", "rowIndex": 0}]
        assert _row_index_for_new_creative(existing) == 1

    def test_row_index_skips_every_occupied_row(self):
        existing = [
            {"type": "image", "rowIndex": 0},
            {"type": "image", "rowIndex": 1},
        ]
        assert _row_index_for_new_creative(existing) == 2

    def test_row_index_tolerates_missing_or_bad_values(self):
        existing = [{"type": "audio"}, {"type": "audio", "rowIndex": "not-a-number"}]
        assert _row_index_for_new_creative(existing) == 0

    def test_banners_carry_forward_from_the_joined_row(self):
        banner = [{"name": "companion.png", "width": 300, "height": 250, "fileUrl": "https://x/companion.png"}]
        existing = [{"type": "audio", "rowIndex": 1, "banners": banner}]
        assert _banners_for_row(existing, 1) == banner

    def test_banners_empty_for_a_fresh_row(self):
        existing = [{"type": "image", "rowIndex": 0}]
        assert _banners_for_row(existing, 1) == []

    def test_banners_ignored_from_a_different_row(self):
        banner = [{"name": "companion.png"}]
        existing = [{"type": "audio", "rowIndex": 2, "banners": banner}]
        assert _banners_for_row(existing, 1) == []

    def test_serve_option_matches_existing_creative(self):
        assert _serve_option_for_new_creative([{"serveOption": "sequential"}]) == "sequential"

    def test_serve_option_defaults_to_random(self):
        assert _serve_option_for_new_creative([]) == "random"
        assert _serve_option_for_new_creative([{"serveOption": None}]) == "random"


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class TestDeliverAdCarriesBannersThroughAttach:
    """The unit tests above prove the helpers compute the right values in
    isolation; this proves deliver_ad actually wires that value into the
    live HTTP call — the thing a live account never gets to see fail. No
    network involved: every CMP API boundary call is stubbed out so this
    runs against no real Frequency environment, staging or otherwise.
    """

    def _run_delivery(self, monkeypatch, db, app, existing_creatives):
        from app.delivery import frequency

        run = _make_ad_run(db)
        run.campaign.advertiser.frequency_client = "acme"
        app.config["CMPAPI_BASE_URL"] = "https://cmpapi.example.com"

        monkeypatch.setattr(
            frequency, "_validate",
            lambda *a, **k: _FakeResponse(
                {"tokenData": {"campaign_id": 999}, "authToken": "tok123", "vastUrls": []}
            ),
        )
        monkeypatch.setattr(frequency, "_create_draft", lambda *a, **k: {"id": 42})
        monkeypatch.setattr(frequency, "_get_draft_creatives", lambda *a, **k: existing_creatives)
        monkeypatch.setattr(frequency, "_probe_duration", lambda *a, **k: 30)
        monkeypatch.setattr(
            frequency, "_upload_creative",
            lambda *a, **k: {"name": "ad.mp3", "url": "https://x/ad.mp3"},
        )
        monkeypatch.setattr(frequency, "_publish_draft", lambda *a, **k: "<VAST/>")

        captured = {}

        def fake_attach(base_url, app_id, draft_id, creative_data, headers, cookies,
                         row_index=0, serve_option="random", banners=None):
            captured["row_index"] = row_index
            captured["serve_option"] = serve_option
            captured["banners"] = banners

        monkeypatch.setattr(frequency, "_attach_creative", fake_attach)

        try:
            result = frequency.deliver_ad(run, _tag(), b"fake-mp3-bytes")
        finally:
            app.config.pop("CMPAPI_BASE_URL")

        return result, captured

    def test_banner_paired_with_the_joined_row_is_attached_with_the_new_audio(
        self, client, db, app, monkeypatch
    ):
        banner = [{"name": "companion.png", "width": 300, "height": 250, "fileUrl": "https://x/companion.png"}]
        existing = [{"type": "audio", "rowIndex": 0, "banners": banner, "serveOption": "random"}]

        result, captured = self._run_delivery(monkeypatch, db, app, existing)

        assert result == "<VAST/>"
        assert captured["row_index"] == 0
        assert captured["banners"] == banner

    def test_fresh_row_next_to_a_banner_attaches_with_no_banners(
        self, client, db, app, monkeypatch
    ):
        """A banner sitting at row 0 with no audio yet must not be dragged
        into the new audio's row — it has nothing to do with this creative."""
        existing = [{"type": "image", "rowIndex": 0, "banners": [{"name": "unrelated.png"}]}]

        result, captured = self._run_delivery(monkeypatch, db, app, existing)

        assert result == "<VAST/>"
        assert captured["row_index"] == 1
        assert captured["banners"] == []
