import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.database import get_db
from app.models.user import UserRole
from app.routers.auth import get_current_user

router = APIRouter(prefix="/activities", tags=["Activities"])

class ActivityCreate(BaseModel):
    type: str
    action: str
    detail: str
    user: str
    role: str
    status: str

def format_activity(act: dict) -> dict:
    if not act:
        return {}
    aid = str(act.get("id") or act.get("_id"))
    timestamp = act.get("timestamp") or act.get("created_at") or datetime.utcnow()
    if isinstance(timestamp, datetime):
        timestamp = timestamp.isoformat()
    return {
        "id": aid,
        "type": act.get("type"),
        "action": act.get("action"),
        "detail": act.get("detail"),
        "user": act.get("user"),
        "role": act.get("role"),
        "timestamp": timestamp,
        "status": act.get("status")
    }

@router.get("", response_model=List[Any])
async def list_activities(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Retrieves system activities. Filtered by RBAC constraints."""
    query = db.table("audit_logs").select("*")
    if current_user["role"] not in [UserRole.MANAGER.value, UserRole.ADMIN.value]:
        # Filter where user field equals user's email or name
        query = query.or_(f"user.eq.{current_user['email']},user.eq.{current_user['name']}")
        
    res = query.order("timestamp", desc=True).execute()
    activities = [format_activity(a) for a in res.data] if res.data else []
    return activities

@router.post("", response_model=Any, status_code=status.HTTP_201_CREATED)
async def log_activity(
    activity_in: ActivityCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Logs a new system activity (Audit Log)."""
    new_act = {
        "id": str(uuid.uuid4()),
        "type": activity_in.type,
        "action": activity_in.action,
        "detail": activity_in.detail,
        "user": activity_in.user,
        "role": activity_in.role,
        "status": activity_in.status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    db.table("audit_logs").insert(new_act).execute()
    return format_activity(new_act)
