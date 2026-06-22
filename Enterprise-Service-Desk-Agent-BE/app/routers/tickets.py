import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from app.database import get_db
from app.schemas.ticket import TicketCreate, TicketUpdate, TicketOut
from app.models.ticket import TicketStatus, TicketPriority, TicketCategory
from app.models.user import UserRole
from app.routers.auth import get_current_user, require_roles
from app.services.orchestrator import OrchestratorService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/tickets", tags=["Tickets"])

class CommentCreate(BaseModel):
    userId: Optional[str] = None
    user_id: Optional[str] = None
    userName: Optional[str] = None
    user_name: Optional[str] = None
    text: str

def format_ticket(ticket: dict) -> dict:
    if not ticket:
        return {}
    tid = str(ticket.get("id") or ticket.get("_id"))
    comments = ticket.get("comments", [])
    timeline = ticket.get("timeline", [])
    
    formatted_comments = []
    for c in comments:
        cid = str(c.get("id") or c.get("_id") or "")
        created_at = c.get("created_at") or c.get("createdAt")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        formatted_comments.append({
            "id": cid,
            "userId": c.get("user_id") or c.get("userId"),
            "user_id": c.get("user_id") or c.get("userId"),
            "userName": c.get("user_name") or c.get("userName"),
            "user_name": c.get("user_name") or c.get("userName"),
            "text": c.get("text"),
            "createdAt": created_at,
            "created_at": created_at
        })
        
    formatted_timeline = []
    for t in timeline:
        timestamp = t.get("timestamp")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        formatted_timeline.append({
            "activity": t.get("activity"),
            "actor": t.get("actor"),
            "timestamp": timestamp
        })
        
    created_at = ticket.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
        
    updated_at = ticket.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()
        
    sla_deadline = ticket.get("sla_deadline") or ticket.get("slaDeadline")
    if isinstance(sla_deadline, datetime):
        sla_deadline = sla_deadline.isoformat()
        
    if not formatted_timeline and created_at:
        formatted_timeline.append({
            "activity": "Ticket Created",
            "actor": ticket.get("created_by") or "system",
            "timestamp": created_at
        })
        
    return {
        "id": tid,
        "_id": tid,
        "ticket_number": ticket.get("ticket_number") or tid,
        "title": ticket.get("title"),
        "description": ticket.get("description"),
        "category": ticket.get("category"),
        "priority": ticket.get("priority"),
        "status": ticket.get("status"),
        "created_by": ticket.get("created_by"),
        "createdBy": ticket.get("created_by"),
        "assigned_to": ticket.get("assigned_to") or ticket.get("assignedTo"),
        "assignedTo": ticket.get("assigned_to") or ticket.get("assignedTo"),
        "assigned_team": ticket.get("assigned_team"),
        "attachments": ticket.get("attachments", []),
        "created_at": created_at,
        "createdAt": created_at,
        "updated_at": updated_at,
        "updatedAt": updated_at,
        "sla_deadline": sla_deadline,
        "slaDeadline": sla_deadline,
        "resolution_time": ticket.get("resolution_time"),
        "master_incident_id": ticket.get("master_incident_id"),
        "risk_score": ticket.get("risk_score"),
        "confidence_score": ticket.get("confidence_score"),
        "ai_explanation": ticket.get("ai_explanation"),
        "employee_response": ticket.get("employee_response"),
        "admin_response": ticket.get("admin_response"),
        "resolution_steps": ticket.get("resolution_steps", []),
        "comments": formatted_comments,
        "timeline": formatted_timeline,
        "department": ticket.get("department", "IT")
    }

# Strict status transition matrix
VALID_TRANSITIONS = {
    TicketStatus.OPEN: [TicketStatus.ASSIGNED, TicketStatus.PENDING_USER, TicketStatus.RESOLVED, TicketStatus.LINKED, TicketStatus.CLOSED],
    TicketStatus.ASSIGNED: [TicketStatus.IN_PROGRESS, TicketStatus.PENDING_USER, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.IN_PROGRESS: [TicketStatus.RESOLVED, TicketStatus.PENDING_USER, TicketStatus.CLOSED],
    TicketStatus.PENDING_USER: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.RESOLVED: [TicketStatus.CLOSED, TicketStatus.IN_PROGRESS],
    TicketStatus.CLOSED: [TicketStatus.OPEN],  # Reopen ticket
    TicketStatus.LINKED: [TicketStatus.OPEN, TicketStatus.CLOSED]
}

@router.post("", response_model=Any, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    ticket_in: TicketCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    ticket = await OrchestratorService.process_new_ticket(
        db=db,
        user_id=str(current_user["id"]),
        user_email=current_user["email"],
        title=ticket_in.title,
        description=ticket_in.description,
        category_input=ticket_in.category,
        priority_input=ticket_in.priority,
        attachments=[att.dict() for att in ticket_in.attachments],
        allow_ai_reset=ticket_in.allowAiPasswordReset
    )
    return format_ticket(ticket)

@router.get("", response_model=List[Any])
async def list_tickets(
    status_filter: Optional[TicketStatus] = None,
    priority_filter: Optional[TicketPriority] = None,
    category_filter: Optional[TicketCategory] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    createdBy: Optional[str] = None,
    created_by: Optional[str] = None,
    assignedTo: Optional[str] = None,
    assigned_to: Optional[str] = None,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    query = db.table("tickets").select("*")
    
    # RBAC constraint: Employees can only view tickets they created
    if current_user["role"] == UserRole.EMPLOYEE.value:
        query = query.eq("created_by", str(current_user["id"]))
        
    s_val = status_filter.value if status_filter else status
    if s_val:
        query = query.eq("status", s_val)
    p_val = priority_filter.value if priority_filter else priority
    if p_val:
        query = query.eq("priority", p_val)
    c_val = category_filter.value if category_filter else category
    if c_val:
        query = query.eq("category", c_val)
        
    created_by_val = createdBy or created_by
    if created_by_val:
        query = query.eq("created_by", created_by_val)
        
    assigned_to_val = assignedTo or assigned_to
    if assigned_to_val:
        query = query.eq("assigned_to", assigned_to_val)

    res = query.order("created_at", desc=True).execute()
    tickets = [format_ticket(t) for t in res.data] if res.data else []
    return tickets

@router.get("/{ticket_id}", response_model=Any)
async def get_ticket(
    ticket_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    res = db.table("tickets").select("*").eq("id", ticket_id).execute()
    ticket = res.data[0] if res.data else None
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    # RBAC: Employees can only view their own tickets
    if current_user["role"] == UserRole.EMPLOYEE.value and ticket["created_by"] != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Not authorized to view this ticket")
        
    return format_ticket(ticket)

@router.patch("/{ticket_id}", response_model=Any)
async def update_ticket(
    ticket_id: str,
    ticket_update: TicketUpdate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    res = db.table("tickets").select("*").eq("id", ticket_id).execute()
    ticket = res.data[0] if res.data else None
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # RBAC validation
    user_role = current_user["role"]
    is_creator = ticket["created_by"] == str(current_user["id"])
    
    if user_role == UserRole.EMPLOYEE.value and not is_creator:
        raise HTTPException(status_code=403, detail="Not authorized to modify this ticket")
        
    # Employees can only change status to closed (canceling/finishing their ticket) or reopen
    if user_role == UserRole.EMPLOYEE.value and ticket_update.status:
        if ticket_update.status not in [TicketStatus.CLOSED, TicketStatus.OPEN]:
            raise HTTPException(status_code=403, detail="Employees can only close or reopen their tickets")

    update_fields = {}
    timeline_events = []
    
    # Process status transition validation
    if ticket_update.status:
        current_status = TicketStatus(ticket["status"])
        target_status = ticket_update.status
        
        if target_status != current_status:
            # Enforce workflow state transitions rules
            allowed = VALID_TRANSITIONS.get(current_status, [])
            if target_status not in allowed:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid workflow transition from {current_status.value} to {target_status.value}"
                )
                
            update_fields["status"] = target_status.value
            
            timeline_events.append({
                "activity": f"Status changed to {target_status.value.upper()}",
                "actor": current_user["email"],
                "timestamp": datetime.utcnow().isoformat()
            })
            
            # If ticket is being resolved, record resolution duration
            if target_status == TicketStatus.RESOLVED:
                created_dt_str = ticket["created_at"]
                created_dt = datetime.fromisoformat(created_dt_str.replace("Z", "+00:00")).replace(tzinfo=None)
                res_time = int((datetime.utcnow() - created_dt).total_seconds())
                update_fields["resolution_time"] = res_time
                
            # Trigger notifications
            await NotificationService.create_notification(
                db,
                ticket["created_by"],
                title=f"Ticket {ticket.get('ticket_number', ticket_id)} Updated",
                message=f"Your ticket status has changed to {target_status.value.upper()}.",
                notification_type=f"ticket_{target_status.value}",
                ticket_id=ticket_id
            )

    # Agent assignment check
    if ticket_update.assigned_to:
        # Verify assignee is an Agent, Manager or Admin
        assignee_res = db.table("profiles").select("*").eq("id", ticket_update.assigned_to).execute()
        assignee = assignee_res.data[0] if assignee_res.data else None
        
        if not assignee or assignee["role"] not in [UserRole.AGENT.value, UserRole.MANAGER.value, UserRole.ADMIN.value]:
            raise HTTPException(status_code=400, detail="Tickets can only be assigned to Agents, Managers, or Admins")
            
        update_fields["assigned_to"] = str(assignee["id"])
        
        timeline_events.append({
            "activity": f"Assigned to {assignee['name']}",
            "actor": current_user["email"],
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # If ticket was open, automatically shift it to Assigned
        if TicketStatus(ticket["status"]) == TicketStatus.OPEN:
            update_fields["status"] = TicketStatus.ASSIGNED.value
            timeline_events.append({
                "activity": f"Status changed to ASSIGNED",
                "actor": current_user["email"],
                "timestamp": datetime.utcnow().isoformat()
            })

        # Send notification to assigned agent
        await NotificationService.create_notification(
            db,
            str(assignee["id"]),
            title="Ticket Assigned",
            message=f"Ticket {ticket.get('ticket_number', ticket_id)} has been assigned to you.",
            notification_type="ticket_assigned",
            ticket_id=ticket_id
        )
        # Send notification to creator
        await NotificationService.create_notification(
            db,
            ticket["created_by"],
            title="Ticket Assigned",
            message=f"Your ticket {ticket.get('ticket_number', ticket_id)} has been assigned to {assignee['name']}.",
            notification_type="ticket_assigned",
            ticket_id=ticket_id
        )

    # Priority changes
    if ticket_update.priority:
        if user_role not in [UserRole.AGENT.value, UserRole.MANAGER.value, UserRole.ADMIN.value]:
            raise HTTPException(status_code=403, detail="Only support staff can change ticket priority")
        update_fields["priority"] = ticket_update.priority.value
        
        timeline_events.append({
            "activity": f"Priority changed to {ticket_update.priority.value.upper()}",
            "actor": current_user["email"],
            "timestamp": datetime.utcnow().isoformat()
        })

    # Direct response additions
    if ticket_update.employee_response:
        update_fields["employee_response"] = ticket_update.employee_response
    if ticket_update.admin_response:
        update_fields["admin_response"] = ticket_update.admin_response

    # Read current timeline
    current_timeline = ticket.get("timeline") or []
    if timeline_events:
        current_timeline.extend(timeline_events)
        update_fields["timeline"] = current_timeline

    if not update_fields:
        return format_ticket(ticket)

    update_fields["updated_at"] = datetime.utcnow().isoformat()
    
    updated_res = db.table("tickets").update(update_fields).eq("id", ticket_id).execute()
    updated_ticket = updated_res.data[0] if updated_res.data else None
    return format_ticket(updated_ticket)

@router.post("/{ticket_id}/comments", response_model=Any)
async def add_comment(
    ticket_id: str,
    comment_in: CommentCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    res = db.table("tickets").select("*").eq("id", ticket_id).execute()
    ticket = res.data[0] if res.data else None
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    user_id = comment_in.userId or comment_in.user_id or str(current_user["id"])
    user_name = comment_in.userName or comment_in.user_name or current_user.get("name", "User")
    
    new_comment = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "user_name": user_name,
        "text": comment_in.text,
        "created_at": datetime.utcnow().isoformat()
    }
    
    timeline_entry = {
        "activity": f"Comment added by {user_name}",
        "actor": current_user["email"],
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Read, update and write back JSONB lists
    comments = ticket.get("comments") or []
    comments.append(new_comment)
    
    timeline = ticket.get("timeline") or []
    timeline.append(timeline_entry)
    
    update_data = {
        "comments": comments,
        "timeline": timeline,
        "updated_at": datetime.utcnow().isoformat()
    }
    
    db.table("tickets").update(update_data).eq("id", ticket_id).execute()
    
    return {
        "id": new_comment["id"],
        "userId": user_id,
        "user_id": user_id,
        "userName": user_name,
        "user_name": user_name,
        "text": comment_in.text,
        "createdAt": new_comment["created_at"],
        "created_at": new_comment["created_at"]
    }
