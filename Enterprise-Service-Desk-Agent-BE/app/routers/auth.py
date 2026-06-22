import uuid
import logging
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Header
from app.database import get_db
from app.schemas.auth import (
    UserRegister, UserLogin, TokenResponse, MfaRequiredResponse,
    MfaVerifyRequest, MfaSetupResponse, PasswordResetRequest, PasswordResetConfirm,
    ChangePasswordRequest
)
from app.utils.security import (
    hash_password, verify_password, create_access_token, decode_access_token,
    create_mfa_token, decode_mfa_token
)
from app.utils.mfa import generate_mfa_secret, get_totp_uri, verify_totp_code
from app.models.user import UserRole
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/auth", tags=["Authentication"])

def format_user(user: dict) -> dict:
    uid = str(user.get("id") or user.get("_id"))
    created_at = user.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return {
        "id": uid,
        "_id": uid,
        "name": user.get("name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "department": user.get("department", "IT"),
        "phone": user.get("phone", ""),
        "status": user.get("status", "active"),
        "createdAt": created_at,
        "created_at": created_at
    }

# Logger for this router
logger = logging.getLogger("enterprise_support.auth")

# Helper dependency to authenticate users from JWT token in the Authorization header
async def get_current_user(authorization: str = Header(None), db = Depends(get_db)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header"
        )
    token = authorization.split(" ")[1]
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid token"
        )
    
    response = db.table("profiles").select("*").eq("email", payload.get("sub").lower()).execute()
    user = response.data[0] if response.data else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )
    return user

# Helper dependency to enforce Role-Based Access Control
def require_roles(allowed_roles: List[UserRole]):
    async def dependency(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in [r.value for r in allowed_roles]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Insufficient permissions"
            )
        return current_user
    return dependency

@router.post("/register", response_model=Dict[str, str], status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db = Depends(get_db)):
    # Check if user already exists
    response = db.table("profiles").select("*").eq("email", user_data.email.lower()).execute()
    existing = response.data[0] if response.data else None
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    
    hashed = hash_password(user_data.password)
    
    new_user = {
        "id": str(uuid.uuid4()),
        "name": user_data.name,
        "email": user_data.email.lower(),
        "role": user_data.role.value,
        "password_hash": hashed,
        "mfa_secret": None,
        "mfa_enabled": False,
        "failed_login_attempts": 0,
        "lockout_until": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    
    db.table("profiles").insert(new_user).execute()
    return {"message": "User registered successfully"}

@router.post("/login", response_model=Any)
async def login(credentials: UserLogin, db = Depends(get_db)):
    if not credentials.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required"
        )
    
    response = db.table("profiles").select("*").eq("email", credentials.email.lower()).execute()
    user = response.data[0] if response.data else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check Account Lockout policy
    lockout_until_str = user.get("lockout_until")
    if lockout_until_str:
        lockout_until = datetime.fromisoformat(lockout_until_str.replace("Z", "+00:00")).replace(tzinfo=None)
        if lockout_until > datetime.utcnow():
            remaining_seconds = int((lockout_until - datetime.utcnow()).total_seconds())
            remaining_minutes = max(1, remaining_seconds // 60)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account locked due to too many failed attempts. Try again in {remaining_minutes} minutes."
            )
        else:
            # Lockout expired, reset counter
            db.table("profiles").update({"failed_login_attempts": 0, "lockout_until": None}).eq("id", user["id"]).execute()
            user["failed_login_attempts"] = 0
            user["lockout_until"] = None

    # Verify Password
    if not verify_password(credentials.password, user.get("password_hash", "")):
        attempts = user.get("failed_login_attempts", 0) + 1
        update_fields = {"failed_login_attempts": attempts}
        
        if attempts >= 5:
            lock_time = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
            update_fields["lockout_until"] = lock_time
            logger.warning(f"User {credentials.email} locked out for 15 minutes.")
            
        db.table("profiles").update(update_fields).eq("id", user["id"]).execute()
        
        if attempts >= 5:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed attempts. Account locked for 15 minutes."
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid email or password. Attempt {attempts} of 5."
        )

    # Successful Password Validation: Reset Lockout fields
    db.table("profiles").update({"failed_login_attempts": 0, "lockout_until": None}).eq("id", user["id"]).execute()

    # Generate 6-digit OTP code and send via Brevo
    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    
    # Store OTP code in `otps` table
    db.table("otps").insert({
        "id": str(uuid.uuid4()),
        "email": user["email"],
        "code": otp_code,
        "expires_at": expires_at,
        "used": False,
        "created_at": datetime.utcnow().isoformat()
    }).execute()
    
    # Send Email asynchronously (or synchronously for verification reliability)
    await NotificationService.send_otp_email(user["email"], otp_code)

    mfa_token = create_mfa_token(user["email"])
    return {
        "otp_required": True,
        "mfa_token": mfa_token,
        "email": user["email"]
    }

@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def setup_mfa(current_user = Depends(get_current_user), db = Depends(get_db)):
    """Generates MFA setup details. User must configure Authenticator App."""
    secret = generate_mfa_secret()
    qr_url = get_totp_uri(secret, current_user["email"])
    
    db.table("profiles").update({
        "mfa_secret": secret, 
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", current_user["id"]).execute()
    
    return MfaSetupResponse(secret=secret, qr_code_url=qr_url)

@router.post("/mfa/enable", response_model=Dict[str, str])
async def enable_mfa(request: MfaVerifyRequest, db = Depends(get_db)):
    """Verifies setup code and enables MFA permanently on user profile."""
    email = decode_mfa_token(request.mfa_token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification session"
        )
        
    response = db.table("profiles").select("*").eq("email", email).execute()
    user = response.data[0] if response.data else None
    if not user or not user.get("mfa_secret"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA configuration not initialized"
        )
        
    if verify_totp_code(user["mfa_secret"], request.code):
        db.table("profiles").update({
            "mfa_enabled": True, 
            "updated_at": datetime.utcnow().isoformat()
        }).eq("id", user["id"]).execute()
        return {"message": "MFA enabled successfully"}
        
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid verification code. Please try again."
    )

@router.post("/mfa/verify", response_model=Any)
async def verify_mfa(request: MfaVerifyRequest, db = Depends(get_db)):
    """Verifies MFA OTP/Brevo OTP during login process."""
    email = decode_mfa_token(request.mfa_token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA session expired or invalid"
        )
        
    # Check for Brevo 6-digit OTP verification first
    now = datetime.utcnow().isoformat()
    response = db.table("otps").select("*").eq("email", email).eq("code", request.code).eq("used", False).gte("expires_at", now).execute()
    
    if response.data:
        # Mark code as used
        otp_record = response.data[0]
        db.table("otps").update({"used": True}).eq("id", otp_record["id"]).execute()
        
        user_response = db.table("profiles").select("*").eq("email", email).execute()
        user = user_response.data[0]
        
        # Generate final JWT
        access_token = create_access_token(data={"sub": user["email"], "role": user["role"]})
        formatted_u = format_user(user)
        return {
            "access_token": access_token,
            "token": access_token,
            "token_type": "bearer",
            "role": user["role"],
            "name": user["name"],
            "email": user["email"],
            "user": formatted_u
        }
        
    # Check TOTP fallback
    user_response = db.table("profiles").select("*").eq("email", email).execute()
    user = user_response.data[0] if user_response.data else None
    
    if user and user.get("mfa_secret") and verify_totp_code(user["mfa_secret"], request.code):
        access_token = create_access_token(data={"sub": user["email"], "role": user["role"]})
        formatted_u = format_user(user)
        return {
            "access_token": access_token,
            "token": access_token,
            "token_type": "bearer",
            "role": user["role"],
            "name": user["name"],
            "email": user["email"],
            "user": formatted_u
        }
        
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid verification code"
    )

@router.post("/logout", response_model=Dict[str, Any])
async def logout(current_user = Depends(get_current_user)):
    """Logs out user session."""
    return {"success": True, "message": "Logged out successfully"}

@router.post("/change-password", response_model=Dict[str, Any])
async def change_password(
    request: ChangePasswordRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Changes password for the authenticated user."""
    if not verify_password(request.oldPassword, current_user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )
    
    hashed = hash_password(request.newPassword)
    db.table("profiles").update({
        "password_hash": hashed, 
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", current_user["id"]).execute()
    return {"success": True, "message": "Password changed successfully"}

@router.post("/password/reset-request", response_model=Dict[str, str])
async def password_reset_request(request: PasswordResetRequest, db = Depends(get_db)):
    """Initiates a password reset process by generating a dummy reset token."""
    response = db.table("profiles").select("*").eq("email", request.email.lower()).execute()
    user = response.data[0] if response.data else None
    if not user:
        return {"message": "If the email exists, a password reset link has been generated."}
        
    reset_token = "RST-" + generate_mfa_secret()[:8]
    logger.info(f"\n[Password Reset Token generated for {request.email}]: {reset_token}\n")
    
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
    db.table("password_resets").upsert({
        "email": request.email.lower(),
        "token": reset_token,
        "expires_at": expires_at
    }, on_conflict="email").execute()
    
    return {"message": "If the email exists, a password reset token has been generated."}

@router.post("/password/reset-confirm", response_model=Dict[str, str])
async def password_reset_confirm(request: PasswordResetConfirm, db = Depends(get_db)):
    """Verifies reset token and updates the user's password."""
    response = db.table("password_resets").select("*").eq("email", request.email.lower()).execute()
    reset_record = response.data[0] if response.data else None
    if not reset_record or reset_record.get("token") != request.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
    
    expires_at = datetime.fromisoformat(reset_record.get("expires_at").replace("Z", "+00:00")).replace(tzinfo=None)
    if expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
        
    hashed = hash_password(request.new_password)
    db.table("profiles").update({
        "password_hash": hashed, 
        "failed_login_attempts": 0, 
        "lockout_until": None
    }).eq("email", request.email.lower()).execute()
    
    db.table("password_resets").delete().eq("email", request.email.lower()).execute()
    
    return {"message": "Password updated successfully"}
