"""Tests for decoding the Frequency JWT payload (prompts 8 and 9)."""

import base64
import json

import pytest

from app.delivery import frequency_token


def make_token(payload: dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{body}.signature"


SAMPLE = {
    "advertiser_name": "KFC", "campaign_name": "hello 1016", "flight_name": "Test 135",
    "creative_type": "standard", "creative_duration": "15", "cm_unit_id": 13433,
}


class TestDecode:
    def test_decodes_payload_without_verifying_signature(self):
        assert frequency_token.decode_payload(make_token(SAMPLE))["campaign_name"] == "hello 1016"

    def test_rejects_non_jwt(self):
        with pytest.raises(frequency_token.InvalidFrequencyToken):
            frequency_token.decode_payload("not-a-jwt")

    def test_rejects_garbage_payload(self):
        with pytest.raises(frequency_token.InvalidFrequencyToken):
            frequency_token.decode_payload("a.!!!.c")

    def test_rejects_non_object_payload(self):
        with pytest.raises(frequency_token.InvalidFrequencyToken):
            frequency_token.decode_payload(make_token([1, 2]))


class TestCreativeDuration:
    def test_string_duration_becomes_float(self):
        assert frequency_token.creative_duration(make_token(SAMPLE)) == 15.0

    def test_missing_duration_is_none(self):
        assert frequency_token.creative_duration(make_token({"campaign_name": "x"})) is None

    def test_invalid_token_is_none(self):
        assert frequency_token.creative_duration("garbage") is None
        assert frequency_token.creative_duration(None) is None


class TestSummarise:
    def test_orders_known_fields(self):
        labels = [label for label, _ in frequency_token.summarise(SAMPLE)]
        assert labels == ["Advertiser", "Campaign", "Flight", "Creative type", "Creative duration (s)", "Ad unit ID"]
