"""Frequency ad server delivery — placeholder.

This module handles delivering generated ad MP3s to Frequency, the ad
trafficking/delivery server. The actual integration is pending API/SFTP
documentation from the Frequency team.

When the documentation arrives, implement one of:
  - REST API: POST the MP3 (or a signed URL) to Frequency's creative endpoint
  - SFTP: Upload the MP3 to a designated drop folder on Frequency's SFTP server

Configuration lives in:
  - Campaign.delivery_enabled — per-campaign toggle
  - Campaign.delivery_config — JSON blob for campaign-specific delivery params
    (e.g. Frequency creative ID, flight dates, rotation weight)
  - App config: FREQUENCY_API_URL, FREQUENCY_API_KEY, FREQUENCY_SFTP_HOST, etc.

The pipeline runner calls deliver_ad() after a successful generation. If delivery
is not enabled or not implemented, it logs a warning and the ad remains available
for manual download from the admin UI.
"""

import logging

logger = logging.getLogger(__name__)


class FrequencyDeliveryError(Exception):
    """Raised when delivery to Frequency fails."""
    pass


class FrequencyNotConfiguredError(Exception):
    """Raised when delivery is attempted but Frequency is not configured."""
    pass


def is_delivery_available() -> bool:
    """Check whether Frequency delivery is implemented and configured.

    Returns False until the integration is built. The admin UI uses this
    to show/hide delivery options.
    """
    # TODO: Check FREQUENCY_ENABLED config and credentials
    return False


def deliver_ad(ad_run, final_ad_bytes: bytes = None, final_ad_url: str = None) -> str:
    """Deliver a completed ad to the Frequency ad server.

    Args:
        ad_run: AdRun model instance with final_ad_s3_key populated.
        final_ad_bytes: Raw MP3 bytes (if pushing the file directly).
        final_ad_url: Signed URL to the MP3 (if Frequency can pull from a URL).

    Returns:
        A delivery reference string from Frequency (creative ID, filename, etc.).

    Raises:
        FrequencyNotConfiguredError: If Frequency integration is not yet available.
        FrequencyDeliveryError: If delivery is attempted but fails.
    """
    # ------------------------------------------------------------------
    # TODO: Implement when Frequency API/SFTP documentation is available.
    #
    # Expected integration patterns:
    #
    # Option A — REST API:
    #   1. POST to FREQUENCY_API_URL/creatives with:
    #      - MP3 file or signed URL
    #      - Metadata: campaign name, advertiser, flight dates
    #      - Frequency-specific fields from campaign.delivery_config
    #   2. Parse response for creative ID
    #   3. Return creative ID as delivery_reference
    #
    # Option B — SFTP:
    #   1. Connect to FREQUENCY_SFTP_HOST with credentials
    #   2. Upload MP3 to designated folder (e.g. /incoming/{campaign_id}/)
    #   3. Optionally upload a metadata sidecar file (XML/JSON)
    #   4. Return the remote path as delivery_reference
    #
    # Configuration to add to Campaign.delivery_config:
    #   - frequency_creative_id: maps this campaign to a Frequency slot
    #   - frequency_station_ids: which stations receive this ad
    #   - frequency_flight_start / frequency_flight_end: scheduling
    #   - frequency_rotation_weight: how often to play
    # ------------------------------------------------------------------

    logger.warning(
        "Frequency delivery not yet implemented. "
        "Ad run #%s generated successfully but not delivered. "
        "Download manually from the admin UI.",
        ad_run.id,
    )

    raise FrequencyNotConfiguredError(
        "Frequency delivery is not yet implemented. "
        "The ad has been generated and is available for manual download."
    )
