from fastapi import APIRouter, Depends, HTTPException, status, Header
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from bson import ObjectId
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
from app.models.user import UserRole, UserDoc

router = APIRouter(prefix="/auth", tags=["Authentication"])

def format_user(user: dict) -> dict:
    uid = str(user.get("_id") or user.get("id"))
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
    
    user = await db.users.find_one({"email": payload.get("sub")})
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
    existing = await db.users.find_one({"email": user_data.email.lower()})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists"
        )
    
    hashed = hash_password(user_data.password)
    
    new_user = {
        "name": user_data.name,
        "email": user_data.email.lower(),
        "role": user_data.role.value,
        "password_hash": hashed,
        "mfa_secret": None,
        "mfa_enabled": False,
        "failed_login_attempts": 0,
        "lockout_until": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await db.users.insert_one(new_user)
    return {"message": "User registered successfully"}

@router.post("/login", response_model=Any)
async def login(credentials: UserLogin, db = Depends(get_db)):
    if not credentials.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is required"
        )
    user = await db.users.find_one({"email": credentials.email.lower()})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    # Check Account Lockout policy
    lockout_until = user.get("lockout_until")
    if lockout_until:
        # Check if localized in timezone or UTC naive
        if lockout_until > datetime.utcnow():
            remaining_seconds = int((lockout_until - datetime.utcnow()).total_seconds())
            remaining_minutes = max(1, remaining_seconds // 60)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Account locked due to too many failed attempts. Try again in {remaining_minutes} minutes."
            )
        else:
            # Lockout expired, reset counter
            await db.users.update_one(
                {"_id": user["_id"]},
                {"$set": {"failed_login_attempts": 0, "lockout_until": None}}
            )
            user["failed_login_attempts"] = 0
            user["lockout_until"] = None

    # Verify Password
    if not verify_password(credentials.password, user.get("password_hash", "")):
        # Increment failed login attempts
        attempts = user.get("failed_login_attempts", 0) + 1
        update_fields = {"failed_login_attempts": attempts}
        
        if attempts >= 5:
            lock_time = datetime.utcnow() + timedelta(minutes=15)
            update_fields["lockout_until"] = lock_time
            logger.warning(f"User {credentials.email} locked out for 15 minutes.")
            
        await db.users.update_one({"_id": user["_id"]}, {"$set": update_fields})
        
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
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"failed_login_attempts": 0, "lockout_until": None}}
    )

    # Check Multi-Factor Authentication
    if user.get("mfa_enabled", False):
        mfa_token = create_mfa_token(user["email"])
        return MfaRequiredResponse(mfa_token=mfa_token)

    # Generate standard JWT Access Token
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

@router.post("/mfa/setup", response_model=MfaSetupResponse)
async def setup_mfa(current_user = Depends(get_current_user), db = Depends(get_db)):
    """Generates MFA setup details. User must configure Authenticator App."""
    secret = generate_mfa_secret()
    qr_url = get_totp_uri(secret, current_user["email"])
    
    # Store secret temporarily
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"mfa_secret": secret, "updated_at": datetime.utcnow()}}
    )
    
    return MfaSetupResponse(secret=secret, qr_code_url=qr_url)

@router.post("/mfa/enable", response_model=Dict[str, str])
async def enable_mfa(request: MfaVerifyRequest, db = Depends(get_db)):
    """Verifies setup code and enables MFA permanently on user profile."""
    # decode temporary mfa validation token or identify user from active session
    email = decode_mfa_token(request.mfa_token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification session"
        )
        
    user = await db.users.find_one({"email": email})
    if not user or not user.get("mfa_secret"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA configuration not initialized"
        )
        
    if verify_totp_code(user["mfa_secret"], request.code):
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$set": {"mfa_enabled": True, "updated_at": datetime.utcnow()}}
        )
        return {"message": "MFA enabled successfully"}
        
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid verification code. Please try again."
    )

@router.post("/mfa/verify", response_model=Any)
async def verify_mfa(request: MfaVerifyRequest, db = Depends(get_db)):
    """Verifies MFA OTP during login process."""
    email = decode_mfa_token(request.mfa_token)
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="MFA session expired or invalid"
        )
        
    user = await db.users.find_one({"email": email})
    if not user or not user.get("mfa_secret"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA is not configured for this user"
        )
        
    if verify_totp_code(user["mfa_secret"], request.code):
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
        
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid MFA code"
    )

@router.post("/logout", response_model=Dict[str, Any])
async def logout(current_user = Depends(get_current_user)):
    """Logs out user session. (Client discards JWT token)."""
    return {"success": True, "message": "Logged out successfully"}

@router.post("/change-password", response_model=Dict[str, Any])
async def change_password(
    request: ChangePasswordRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Changes password for the authenticated user."""
    # Verify old password
    if not verify_password(request.oldPassword, current_user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect old password"
        )
    
    hashed = hash_password(request.newPassword)
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"password_hash": hashed, "updated_at": datetime.utcnow()}}
    )
    return {"success": True, "message": "Password changed successfully"}

@router.post("/password/reset-request", response_model=Dict[str, str])
async def password_reset_request(request: PasswordResetRequest, db = Depends(get_db)):
    """Initiates a password reset process by generating a dummy reset token."""
    user = await db.users.find_one({"email": request.email.lower()})
    if not user:
        # Return success even if email not found to prevent user enumeration attacks
        return {"message": "If the email exists, a password reset link has been generated."}
        
    # Generate random string reset token
    reset_token = "RST-" + generate_mfa_secret()[:8]
    # In a real environment, send this token to user's email.
    # In mock, we log it.
    logger.info(f"\n[Password Reset Token generated for {request.email}]: {reset_token}\n")
    
    # Store token in database with expiry (e.g. 15 minutes)
    await db.password_resets.update_one(
        {"email": request.email.lower()},
        {"$set": {"token": reset_token, "expires_at": datetime.utcnow() + timedelta(minutes=15)}},
        upsert=True
    )
    
    return {"message": "If the email exists, a password reset token has been generated."}

@router.post("/password/reset-confirm", response_model=Dict[str, str])
async def password_reset_confirm(request: PasswordResetConfirm, db = Depends(get_db)):
    """Verifies reset token and updates the user's password."""
    reset_record = await db.password_resets.find_one({"email": request.email.lower()})
    if not reset_record or reset_record.get("token") != request.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )
        
    if reset_record.get("expires_at") < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired"
        )
        
    hashed = hash_password(request.new_password)
    await db.users.update_one(
        {"email": request.email.lower()},
        {"$set": {"password_hash": hashed, "failed_login_attempts": 0, "lockout_until": None}}
    )
    
    # Delete reset token
    await db.password_resets.delete_one({"email": request.email.lower()})
    
    return {"message": "Password updated successfully"}
