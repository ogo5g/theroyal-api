"""Re-export all models for Alembic auto-discovery."""

from app.models.base import Base
from app.models.user import User, UserRole, OnboardingStep
from app.models.account import Account
from app.models.kyc import KYC, KYCStatus, DocumentType
from app.models.wallet import WalletTransaction, TransactionType, TransactionCategory, TransactionStatus
from app.models.plan import SavingsPlan, PlanStatus, PenaltyType
from app.models.subscription import Subscription, PaymentSchedule, SubscriptionStatus, ScheduleStatus
from app.models.notification import Notification, NotificationType, NotificationChannel
from app.models.audit import AuditLog

__all__ = [
    "Base",
    "User", "UserRole",
    "Account",
    "KYC", "KYCStatus", "DocumentType",
    "WalletTransaction", "TransactionType", "TransactionCategory", "TransactionStatus",
    "SavingsPlan", "PlanStatus", "PenaltyType",
    "Subscription", "PaymentSchedule", "SubscriptionStatus", "ScheduleStatus",
    "Notification", "NotificationType", "NotificationChannel",
    "AuditLog",
]
