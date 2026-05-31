import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "PaperlessBoss Backend API"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-key-change-me-in-production-1234567890-paperlessboss")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    OTP_EXPIRY_MINUTES: int = 10
    EMAILS_FROM_EMAIL: str = "noreply@paperlessboss.com"
    EMAILS_FROM_NAME: str = "PaperlessBoss"
    EMAIL_PASS: str = ""
    SMTP_TLS: bool = True
    SMTP_PORT: int = 587
    SMTP_HOST: str = ""
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ENVIRONMENT: str = "production"

    def model_post_init(self, __context):
        if self.EMAILS_FROM_EMAIL and self.EMAIL_PASS:
            if not self.SMTP_USER:
                self.SMTP_USER = self.EMAILS_FROM_EMAIL
            if not self.SMTP_PASSWORD:
                self.SMTP_PASSWORD = self.EMAIL_PASS
            if not self.SMTP_HOST:
                if self.EMAILS_FROM_EMAIL.strip().endswith("@paperlessboss.com"):
                    self.SMTP_HOST = "smtp.titan.email"
                else:
                    self.SMTP_HOST = "smtp.gmail.com"
        if not self.SMTP_PORT:
            self.SMTP_PORT = 587

    model_config = {
        "env_file": ".env",
        "extra": "ignore",
        "case_sensitive": True
    }

settings = Settings()
