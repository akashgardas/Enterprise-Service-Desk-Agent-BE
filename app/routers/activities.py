from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from bson import ObjectId
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
    aid = str(act.get("_id") or act.get("id"))
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
    query = {}
    if current_user["role"] not in [UserRole.MANAGER.value, UserRole.ADMIN.value]:
        # Employees/agents only see activities matching their email or name
        query["$or"] = [
            {"user": current_user["email"]},
            {"user": current_user["name"]}
        ]
        
    cursor = db.audit_logs.find(query).sort("timestamp", -1)
    activities = []
    async for a in cursor:
        activities.append(format_activity(a))
    return activities

@router.post("", response_model=Any, status_code=status.HTTP_201_CREATED)
async def log_activity(
    activity_in: ActivityCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Logs a new system activity (Audit Log)."""
    new_act = {
        "type": activity_in.type,
        "action": activity_in.action,
        "detail": activity_in.detail,
        "user": activity_in.user,
        "role": activity_in.role,
        "status": activity_in.status,
        "timestamp": datetime.utcnow()
    }
    
    result = await db.audit_logs.insert_one(new_act)
    new_act["_id"] = str(result.inserted_id)
    return format_activity(new_act)
