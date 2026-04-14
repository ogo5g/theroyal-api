"""Application settings loaded from environment variables via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production"
    FRONTEND_URL: str = "http://localhost:3000"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/primeheritagecommunity"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = "change-me-jwt-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Platnova
    PLATNOVA_API_KEY: str = ""
    PLATNOVA_WALLET_ID: str = ""
    PLATNOVA_WEBHOOK_SECRET: str = ""
    PLATNOVA_BASE_URL: str = "https://api.platnova.co"

    # Paystack (For bank list and resolution)
    PAYSTACK_SECRET_KEY: str = ""

    # Termii
    TERMII_API_KEY: str = ""
    TERMII_SENDER_ID: str = "PrimeHC"

    # Resend
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@reach.primeheritagecommunity.com"
    
    # SMTP Fallback
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 465
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    
    # Cloudflare R2
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "primeheritagecommunity-kyc"
    R2_ENDPOINT: str = ""

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""

    # Cloudflare Turnstile
    TURNSTILE_SECRET_KEY: str = ""

    # Encryption (Fernet key for BVN/NIN/account numbers)
    FIELD_ENCRYPTION_KEY: str = ""

    # Sentry
    SENTRY_DSN: str = ""

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    def model_post_init(self, __context) -> None:
        """Normalize DATABASE_URL to always use the asyncpg driver."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            object.__setattr__(
                self, "DATABASE_URL",
                url.replace("postgresql://", "postgresql+asyncpg://", 1),
            )
        elif url.startswith("postgres://"):
            object.__setattr__(
                self, "DATABASE_URL",
                url.replace("postgres://", "postgresql+asyncpg://", 1),
            )


settings = Settings()
