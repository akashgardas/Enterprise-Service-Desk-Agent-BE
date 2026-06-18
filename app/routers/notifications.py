from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from bson import ObjectId
from datetime import datetime
from app.database import get_db
from app.routers.auth import get_current_user

router = APIRouter(prefix="/notifications", tags=["Notifications"])

def format_notification(notif: dict) -> dict:
    if not notif:
        return {}
    nid = str(notif.get("_id") or notif.get("id"))
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
    cursor = db.notifications.find({"user_id": str(current_user["_id"])}).sort("created_at", -1)
    notifications = []
    async for n in cursor:
        notifications.append(format_notification(n))
    return notifications

@router.patch("/{notification_id}/read", response_model=Any)
async def mark_notification_read(
    notification_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Marks a single notification as read."""
    if not ObjectId.is_valid(notification_id):
        raise HTTPException(status_code=400, detail="Invalid notification ID format")
        
    notif = await db.notifications.find_one({"_id": ObjectId(notification_id)})
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    if notif["user_id"] != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to update this notification")
        
    updated = await db.notifications.find_one_and_update(
        {"_id": ObjectId(notification_id)},
        {"$set": {"is_read": True}},
        return_document=True
    )
    return format_notification(updated)

@router.post("/read-all", response_model=Dict[str, bool])
async def mark_all_notifications_read(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Marks all notifications for the current user as read."""
    await db.notifications.update_many(
        {"user_id": str(current_user["_id"]), "is_read": False},
        {"$set": {"is_read": True}}
    )
    return {"success": True}
