"""Onboarding business logic — progressive profile completion."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import OnboardingStep, User
from app.models.kyc import KYC
from app.schemas.onboarding import BasicInfoRequest, NINSubmitRequest, BVNSubmitRequest, ProfilePhotoRequest
from app.utils.security import encrypt_field


# ---------------------------------------------------------------------------
# Step ordering — enforce sequential completion
# ---------------------------------------------------------------------------
STEP_ORDER = [
    OnboardingStep.REGISTERED,
    OnboardingStep.EMAIL_VERIFIED,
    OnboardingStep.PASSWORD_SET,
    OnboardingStep.BASIC_INFO,
    OnboardingStep.NIN_SUBMITTED,
    OnboardingStep.BVN_SUBMITTED,
    OnboardingStep.PROFILE_UPLOADED,
    OnboardingStep.COMPLETED,
]


def _check_step(user: User, required_step: OnboardingStep) -> None:
    """Ensure the user is at the correct step to proceed."""
    current_idx = STEP_ORDER.index(user.onboarding_step)
    required_idx = STEP_ORDER.index(required_step)

    if current_idx > required_idx:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This step has already been completed",
        )
    if current_idx < required_idx:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Please complete the previous step first. Current step: {user.onboarding_step.value}",
        )


# ---------------------------------------------------------------------------
# Step 1: Basic Info
# ---------------------------------------------------------------------------
async def submit_basic_info(user: User, data: BasicInfoRequest, db: AsyncSession) -> User:
    """Save basic profile information."""
    _check_step(user, OnboardingStep.PASSWORD_SET)

    # Check phone uniqueness
    existing = await db.execute(
        select(User).where(User.phone_number == data.phone_number, User.id != user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This phone number is already registered to another account",
        )

    user.first_name = data.first_name
    user.last_name = data.last_name
    user.other_name = data.other_name
    user.phone_number = data.phone_number
    user.date_of_birth = data.date_of_birth
    user.address = data.address
    user.onboarding_step = OnboardingStep.BASIC_INFO

    return user


# ---------------------------------------------------------------------------
# Step 2: NIN Submission
# ---------------------------------------------------------------------------
async def submit_nin(user: User, data: NINSubmitRequest, db: AsyncSession) -> User:
    """Encrypt and store NIN."""
    _check_step(user, OnboardingStep.BASIC_INFO)

    # Create or update KYC record
    result = await db.execute(select(KYC).where(KYC.user_id == user.id))
    kyc = result.scalar_one_or_none()

    if kyc:
        kyc.nin = encrypt_field(data.nin)
    else:
        from datetime import datetime, timezone
        kyc = KYC(
            user_id=user.id,
            nin=encrypt_field(data.nin),
            # Set required fields with placeholders — updated later or made nullable
            date_of_birth=user.date_of_birth or "2000-01-01",
            address=user.address or "",
            state="",
            bank_name="",
            bank_code="",
            account_number=encrypt_field("0000000000"),
            account_name="",
            document_type="national_id",
            document_url="",
            submitted_at=datetime.now(timezone.utc),
        )
        db.add(kyc)

    user.onboarding_step = OnboardingStep.NIN_SUBMITTED
    return user


# ---------------------------------------------------------------------------
# Step 3: BVN Submission
# ---------------------------------------------------------------------------
async def submit_bvn(user: User, data: BVNSubmitRequest, db: AsyncSession) -> User:
    """Encrypt and store BVN."""
    _check_step(user, OnboardingStep.NIN_SUBMITTED)

    result = await db.execute(select(KYC).where(KYC.user_id == user.id))
    kyc = result.scalar_one_or_none()

    if not kyc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please submit your NIN first",
        )

    kyc.bvn = encrypt_field(data.bvn)
    user.onboarding_step = OnboardingStep.BVN_SUBMITTED

    return user


from fastapi import UploadFile
from app.services.storage.cloudinary import upload_image_to_cloudinary

# ---------------------------------------------------------------------------
# Step 4: Profile Photo Upload
# ---------------------------------------------------------------------------
async def upload_profile_photo(user: User, file: UploadFile, db: AsyncSession) -> User:
    """Save profile photo URL and complete onboarding."""
    _check_step(user, OnboardingStep.BVN_SUBMITTED)

    image_url = await upload_image_to_cloudinary(file)
    user.profile_image_url = image_url
    user.onboarding_step = OnboardingStep.COMPLETED

    return user


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
async def get_onboarding_status(user: User) -> dict:
    """Return the user's current onboarding step and completion state."""
    current_idx = STEP_ORDER.index(user.onboarding_step)
    total = len(STEP_ORDER) - 1  # exclude COMPLETED from count

    return {
        "current_step": user.onboarding_step.value,
        "steps_completed": current_idx,
        "total_steps": total,
        "is_complete": user.onboarding_step == OnboardingStep.COMPLETED,
    }
