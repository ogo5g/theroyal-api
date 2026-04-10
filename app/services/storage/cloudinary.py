"""Cloudinary Client Service for Media Uploads (e.g., Profile Photos)."""

import logging
import cloudinary
import cloudinary.uploader
from fastapi import UploadFile, HTTPException, status

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Cloudinary
if settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY:
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


async def upload_image_to_cloudinary(file: UploadFile, folder: str = "theroyalsaving/profile_photos") -> str:
    """
    Uploads an image file to Cloudinary and returns the secure URL.
    Returns a placeholder URL if Cloudinary is not configured.
    """
    if not settings.CLOUDINARY_API_KEY:
        logger.warning("[STUB] Cloudinary is not configured. Returning placeholder profile photo URL.")
        return "https://res.cloudinary.com/demo/image/upload/v1312461204/sample.jpg"

    try:
        # FastAPI's UploadFile requires reading into bytes for Cloudinary
        contents = await file.read()
        
        logger.info(f"Uploading {file.filename} to Cloudinary...")
        
        # Upload using the synchronous SDK (runs in threadpool under the hood usually, 
        # or we could use asyncio.to_thread, but for small profile pics it's acceptable)
        import asyncio
        response = await asyncio.to_thread(
            cloudinary.uploader.upload,
            contents,
            folder=folder,
            resource_type="image",
            format="webp", # Auto-convert to WebP for performance
            quality="auto",
        )
        
        secure_url = response.get("secure_url")
        logger.info(f"✅ Successfully uploaded to Cloudinary: {secure_url}")
        return secure_url

    except Exception as e:
        logger.error(f"❌ Failed to upload image to Cloudinary: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to upload profile photo to media server.",
        )
