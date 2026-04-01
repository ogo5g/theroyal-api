"""Auto-generators for IDs, codes, and references."""

import secrets
import string
from uuid import uuid4


def generate_uuid() -> str:
    return str(uuid4())


def generate_plan_code() -> str:
    """Generate a plan code like PLAN-A1B2C3."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"PLAN-{suffix}"


def generate_subscription_sid() -> str:
    """Generate a subscription ID like SUB-A1B2C3D4."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(8))
    return f"SUB-{suffix}"


def generate_txn_id() -> str:
    """Generate a transaction ID like TXN-A1B2C3D4E5F6."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(12))
    return f"TXN-{suffix}"


def generate_referral_code() -> str:
    """Generate a referral code like REF-A1B2C3."""
    chars = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(chars) for _ in range(6))
    return f"REF-{suffix}"


def generate_otp(length: int = 6) -> str:
    """Generate a numeric OTP code."""
    return "".join(secrets.choice(string.digits) for _ in range(length))


def generate_reference() -> str:
    """Generate a unique payment reference."""
    return f"TRS-{secrets.token_hex(12).upper()}"


# Alias for backward compatibility
generate_payment_reference = generate_reference
