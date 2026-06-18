import re
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from app.models.user import UserRole

# Password Policy: Min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special character
PASSWORD_REGEX = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&])[A-Za-z\d@$!%*?&]{8,}$"

def validate_password_strength(password: str) -> str:
    if not re.match(PASSWORD_REGEX, password):
        raise ValueError(
            "Password must be at least 8 characters long and contain at "
            "least one uppercase letter, one lowercase letter, one number, "
            "and one special character (e.g., Welcome@123)"
        )
    return password

class UserRegister(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    role: UserRole = Field(default=UserRole.EMPLOYEE)
    password: str

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)

class UserLogin(BaseModel):
    email: Optional[EmailStr] = None
    password: str
    role: Optional[str] = None

class ChangePasswordRequest(BaseModel):
    oldPassword: str
    newPassword: str

    @field_validator("newPassword")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    email: str

class MfaRequiredResponse(BaseModel):
    status: str = "mfa_required"
    mfa_token: str

class MfaVerifyRequest(BaseModel):
    mfa_token: str
    code: str

class MfaSetupResponse(BaseModel):
    secret: str
    qr_code_url: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    email: EmailStr
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)
