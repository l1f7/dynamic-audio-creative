"""S3-compatible storage — upload, download, signed URLs.

Provider-agnostic: works with Cloudflare R2, AWS S3, Backblaze B2,
or any S3-compatible service. Configured entirely via env vars.
"""

import logging

import boto3
from flask import current_app

logger = logging.getLogger(__name__)


def get_client():
    """Create a boto3 S3 client from app config."""
    return boto3.client(
        "s3",
        endpoint_url=current_app.config["S3_ENDPOINT_URL"],
        aws_access_key_id=current_app.config["S3_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["S3_SECRET_KEY"],
        region_name=current_app.config["S3_REGION"],
    )


def upload(key: str, data: bytes, content_type: str = "audio/mpeg"):
    """Upload bytes to S3."""
    client = get_client()
    client.put_object(
        Bucket=current_app.config["S3_BUCKET"],
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    logger.info("Uploaded %s (%d bytes)", key, len(data))


def download(key: str) -> bytes:
    """Download an object from S3 and return its bytes."""
    client = get_client()
    resp = client.get_object(
        Bucket=current_app.config["S3_BUCKET"], Key=key
    )
    return resp["Body"].read()


def generate_signed_url(key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed URL for downloading an S3 object."""
    client = get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": current_app.config["S3_BUCKET"],
            "Key": key,
        },
        ExpiresIn=expires_in,
    )


def delete(key: str):
    """Delete an object from S3."""
    client = get_client()
    client.delete_object(
        Bucket=current_app.config["S3_BUCKET"], Key=key
    )
    logger.info("Deleted %s", key)
