"""Tests for the Frequency delivery placeholder."""

import pytest

from app.delivery.frequency import (
    FrequencyNotConfiguredError,
    deliver_ad,
    is_delivery_available,
)


class TestFrequencyPlaceholder:
    def test_delivery_not_available(self):
        """Delivery should report as unavailable until implemented."""
        assert is_delivery_available() is False

    def test_deliver_raises_not_configured(self):
        """Calling deliver_ad should raise FrequencyNotConfiguredError."""

        class FakeAdRun:
            id = 1
            final_ad_s3_key = "campaigns/1/runs/1/final_ad.mp3"

        with pytest.raises(FrequencyNotConfiguredError):
            deliver_ad(FakeAdRun())

    def test_error_message_is_helpful(self):
        class FakeAdRun:
            id = 42
            final_ad_s3_key = "campaigns/1/runs/42/final_ad.mp3"

        with pytest.raises(FrequencyNotConfiguredError) as exc_info:
            deliver_ad(FakeAdRun())

        assert "not yet implemented" in str(exc_info.value).lower()
        assert "manual download" in str(exc_info.value).lower()
