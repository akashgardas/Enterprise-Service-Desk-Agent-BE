from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from enum import Enum

class UserRole(str, Enum):
    EMPLOYEE = "employee"
    AGENT = "agent"
    MANAGER = "manager"
    ADMIN = "admin"

class UserDoc(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    email: str
    role: UserRole = UserRole.EMPLOYEE
    password_hash: str
    mfa_secret: Optional[str] = None
    mfa_enabled: bool = False
    failed_login_attempts: int = 0
    lockout_until: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
