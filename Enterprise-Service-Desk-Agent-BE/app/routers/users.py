import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field
from app.database import get_db
from app.models.user import UserRole
from app.routers.auth import get_current_user, require_roles, format_user
from app.utils.security import hash_password

router = APIRouter(prefix="/users", tags=["Users"])

class UserProvision(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    phone: Optional[str] = ""
    role: UserRole = UserRole.EMPLOYEE
    department: Optional[str] = "IT"

@router.get("", response_model=List[Any])
async def list_users(
    current_user = Depends(require_roles([UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Retrieves all users (Admin only)."""
    response = db.table("profiles").select("*").order("created_at", desc=True).execute()
    users = [format_user(u) for u in response.data] if response.data else []
    return users

@router.get("/me", response_model=Any)
async def get_me(current_user = Depends(get_current_user)):
    """Retrieves the current authenticated user."""
    return format_user(current_user)

@router.get("/{user_id}", response_model=Any)
async def get_user_by_id(
    user_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Retrieves a user by their ID."""
    response = db.table("profiles").select("*").eq("id", user_id).execute()
    user = response.data[0] if response.data else None
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    return format_user(user)

@router.post("", response_model=Any, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_in: UserProvision,
    current_user = Depends(require_roles([UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Provisions/creates a new user (Admin only)."""
    response = db.table("profiles").select("*").eq("email", user_in.email.lower()).execute()
    existing = response.data[0] if response.data else None
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    
    # Generate a default password
    default_password_hash = hash_password("Welcome@123")
    user_id = str(uuid.uuid4())
    
    new_user = {
        "id": user_id,
        "name": user_in.name,
        "email": user_in.email.lower(),
        "role": user_in.role.value,
        "password_hash": default_password_hash,
        "department": user_in.department,
        "phone": user_in.phone,
        "status": "active",
        "mfa_secret": None,
        "mfa_enabled": False,
        "failed_login_attempts": 0,
        "lockout_until": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    db.table("profiles").insert(new_user).execute()
    return format_user(new_user)
