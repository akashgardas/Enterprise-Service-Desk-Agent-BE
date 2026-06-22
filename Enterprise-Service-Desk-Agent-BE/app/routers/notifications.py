from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])

def format_notification(notif: dict) -> dict:
    if not notif:
        return {}
    nid = str(notif.get("id") or notif.get("_id"))
    created_at = notif.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    return {
        "id": nid,
        "_id": nid,
        "userId": notif.get("user_id"),
        "user_id": notif.get("user_id"),
        "type": notif.get("type"),
        "message": notif.get("message"),
        "read": notif.get("is_read", False),
        "is_read": notif.get("is_read", False),
        "ticketId": notif.get("ticket_id"),
        "ticket_id": notif.get("ticket_id"),
        "createdAt": created_at,
        "created_at": created_at
    }

@router.get("", response_model=List[Any])
async def list_notifications(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Retrieves all notifications for the current authenticated user."""
    res = db.table("notifications").select("*").eq("user_id", str(current_user["id"])).order("created_at", desc=True).execute()
    notifications = [format_notification(n) for n in res.data] if res.data else []
    return notifications

@router.patch("/{notification_id}/read", response_model=Any)
async def mark_notification_read(
    notification_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Marks a single notification as read."""
    res = db.table("notifications").select("*").eq("id", notification_id).execute()
    notif = res.data[0] if res.data else None
    
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    if notif["user_id"] != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to update this notification")
        
    updated_res = db.table("notifications").update({"is_read": True}).eq("id", notification_id).execute()
    updated = updated_res.data[0] if updated_res.data else None
    return format_notification(updated)

@router.post("/read-all", response_model=Dict[str, bool])
async def mark_all_notifications_read(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Marks all notifications for the current user as read."""
    db.table("notifications").update({"is_read": True}).eq("user_id", str(current_user["id"])).eq("is_read", False).execute()
    return {"success": True}
