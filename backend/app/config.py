from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Optional

class Settings(BaseSettings):
    # MongoDB settings
    MONGO_URI: str = Field(default="mongodb://localhost:27017")
    DATABASE_NAME: str = Field(default="enterprise_support")

    # Security settings
    JWT_SECRET_KEY: str = Field(default="8f7d9e4a3b2c1d0e9f8a7b6c5d4e3f2g1h0i9j8k7l6m5n4o3p2q1r0s")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)  # Session timeout 30 minutes
    MFA_JWT_SECRET_KEY: str = Field(default="9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d")

    # AI settings
    GEMINI_API_KEY: Optional[str] = Field(default=None)

    # Email & Notifications settings
    SMTP_HOST: str = Field(default="localhost")
    SMTP_PORT: int = Field(default=1025)
    SMTP_USER: Optional[str] = Field(default=None)
    SMTP_PASSWORD: Optional[str] = Field(default=None)
    EMAIL_FROM: str = Field(default="support@company.com")
    MOCK_SERVICES: bool = Field(default=True)

    # Web Auth Remediation Mock configurations
    WEB_AUTH_URL: str = Field(default="http://localhost:5000")
    RESET_API_KEY: str = Field(default="unisys-reset-secret-key-2024")

    # Allowed CORS Origins
    ALLOWED_ORIGINS: List[str] = Field(default=["http://localhost:3000", "http://localhost:5173", "http://localhost:8000"])

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
