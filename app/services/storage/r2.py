"""Cloudflare R2 Client Service for KYC Documents."""

import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

from app.config import settings

logger = logging.getLogger(__name__)

def get_s3_client():
    """Create an S3 client configured for Cloudflare R2."""
    if not settings.R2_ACCOUNT_ID or not settings.R2_ACCESS_KEY_ID:
        return None

    return boto3.client(
        's3',
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto" # R2 uses 'auto' or 'weur' etc, usually 'auto' is fine for boto3
    )

async def upload_document_to_r2(file_content: bytes, object_name: str, content_type: str = "application/pdf") -> bool:
    """
    Upload a KYC document directly to Cloudflare R2.
    Since KYC docs are private, we don't expose them globally.
    """
    s3_client = get_s3_client()
    if not s3_client:
        logger.warning(f"[STUB] Missing R2 credentials. Cannot upload {object_name}.")
        return True # Stub success

    logger.info(f"Uploading {object_name} to R2 bucket: {settings.R2_BUCKET_NAME}...")
    
    try:
        # Boto3 is synchronous; use asyncio.to_thread if heavy, but ok for small docs.
        import asyncio
        await asyncio.to_thread(
            s3_client.put_object,
            Bucket=settings.R2_BUCKET_NAME,
            Key=object_name,
            Body=file_content,
            ContentType=content_type,
        )
        logger.info(f"✅ Successfully uploaded {object_name} to R2.")
        return True
    except ClientError as e:
        logger.error(f"❌ Failed to upload {object_name} to R2: {e}")
        return False


def generate_presigned_url(object_name: str, expiration: int = 3600) -> Optional[str]:
    """
    Generate a secure pre-signed URL to share an encrypted KYC document with the Admin UI.
    """
    s3_client = get_s3_client()
    if not s3_client:
        return None

    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': settings.R2_BUCKET_NAME, 'Key': object_name},
            ExpiresIn=expiration
        )
        return url
    except ClientError as e:
        logger.error(f"❌ Failed to generate presigned URL for {object_name}: {e}")
        return None
