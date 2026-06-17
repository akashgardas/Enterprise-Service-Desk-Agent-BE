from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from app.database import get_db
from app.schemas.ticket import TicketCreate, TicketUpdate, TicketOut
from app.models.ticket import TicketStatus, TicketPriority, TicketCategory
from app.models.user import UserRole
from app.routers.auth import get_current_user, require_roles
from app.services.orchestrator import OrchestratorService
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/api/tickets", tags=["Tickets"])

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

@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    ticket_in: TicketCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    ticket = await OrchestratorService.process_new_ticket(
        db=db,
        user_id=str(current_user["_id"]),
        user_email=current_user["email"],
        title=ticket_in.title,
        description=ticket_in.description,
        category_input=ticket_in.category,
        priority_input=ticket_in.priority,
        attachments=[att.dict() for att in ticket_in.attachments],
        allow_ai_reset=ticket_in.allowAiPasswordReset
    )
    return ticket

@router.get("", response_model=List[TicketOut])
async def list_tickets(
    status_filter: Optional[TicketStatus] = None,
    priority_filter: Optional[TicketPriority] = None,
    category_filter: Optional[TicketCategory] = None,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    query = {}
    
    # RBAC constraint: Employees can only view tickets they created
    if current_user["role"] == UserRole.EMPLOYEE.value:
        query["created_by"] = str(current_user["_id"])
        
    if status_filter:
        query["status"] = status_filter.value
    if priority_filter:
        query["priority"] = priority_filter.value
    if category_filter:
        query["category"] = category_filter.value

    cursor = db.tickets.find(query).sort("created_at", -1)
    tickets = []
    async for t in cursor:
        tickets.append(t)
    return tickets

@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    if not ObjectId.is_valid(ticket_id):
        raise HTTPException(status_code=400, detail="Invalid ticket ID format")
        
    ticket = await db.tickets.find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
        
    # RBAC: Employees can only view their own tickets
    if current_user["role"] == UserRole.EMPLOYEE.value and ticket["created_by"] != str(current_user["_id"]):
        raise HTTPException(status_code=403, detail="Not authorized to view this ticket")
        
    return ticket

@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: str,
    ticket_update: TicketUpdate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    if not ObjectId.is_valid(ticket_id):
        raise HTTPException(status_code=400, detail="Invalid ticket ID format")

    ticket = await db.tickets.find_one({"_id": ObjectId(ticket_id)})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # RBAC validation
    user_role = current_user["role"]
    is_creator = ticket["created_by"] == str(current_user["_id"])
    
    if user_role == UserRole.EMPLOYEE.value and not is_creator:
        raise HTTPException(status_code=403, detail="Not authorized to modify this ticket")
        
    # Employees can only change status to closed (canceling/finishing their ticket) or reopen
    if user_role == UserRole.EMPLOYEE.value and ticket_update.status:
        if ticket_update.status not in [TicketStatus.CLOSED, TicketStatus.OPEN]:
            raise HTTPException(status_code=403, detail="Employees can only close or reopen their tickets")

    update_fields = {}
    
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
            
            # If ticket is being resolved, record resolution duration
            if target_status == TicketStatus.RESOLVED:
                created_dt = ticket["created_at"]
                res_time = int((datetime.utcnow() - created_dt).total_seconds())
                update_fields["resolution_time"] = res_time
                
            # Trigger notifications
            await NotificationService.create_notification(
                db,
                ticket["created_by"],
                title=f"Ticket {ticket['ticket_number']} Updated",
                message=f"Your ticket status has changed to {target_status.value.upper()}.",
                notification_type=f"ticket_{target_status.value}"
            )

    # Agent assignment check
    if ticket_update.assigned_to:
        # Verify assignee is an Agent, Manager or Admin
        assignee = await db.users.find_one({"_id": ObjectId(ticket_update.assigned_to)})
        if not assignee or assignee["role"] not in [UserRole.AGENT.value, UserRole.MANAGER.value, UserRole.ADMIN.value]:
            raise HTTPException(status_code=400, detail="Tickets can only be assigned to Agents, Managers, or Admins")
            
        update_fields["assigned_to"] = str(assignee["_id"])
        # If ticket was open, automatically shift it to Assigned
        if TicketStatus(ticket["status"]) == TicketStatus.OPEN:
            update_fields["status"] = TicketStatus.ASSIGNED.value

        # Send notification to assigned agent
        await NotificationService.create_notification(
            db,
            str(assignee["_id"]),
            title="Ticket Assigned",
            message=f"Ticket {ticket['ticket_number']} has been assigned to you.",
            notification_type="ticket_assigned"
        )
        # Send notification to creator
        await NotificationService.create_notification(
            db,
            ticket["created_by"],
            title="Ticket Assigned",
            message=f"Your ticket {ticket['ticket_number']} has been assigned to {assignee['name']}.",
            notification_type="ticket_assigned"
        )

    # Priority changes
    if ticket_update.priority:
        if user_role not in [UserRole.AGENT.value, UserRole.MANAGER.value, UserRole.ADMIN.value]:
            raise HTTPException(status_code=403, detail="Only support staff can change ticket priority")
        update_fields["priority"] = ticket_update.priority.value

    # Direct response additions
    if ticket_update.employee_response:
        update_fields["employee_response"] = ticket_update.employee_response
    if ticket_update.admin_response:
        update_fields["admin_response"] = ticket_update.admin_response

    if not update_fields:
        return ticket

    update_fields["updated_at"] = datetime.utcnow()
    
    updated_ticket = await db.tickets.find_one_and_update(
        {"_id": ObjectId(ticket_id)},
        {"$set": update_fields},
        return_document=True
    )
    return updated_ticket
