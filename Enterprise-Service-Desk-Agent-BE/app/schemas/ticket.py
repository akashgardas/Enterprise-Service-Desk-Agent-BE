from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.ticket import TicketStatus, TicketCategory, TicketPriority

class AttachmentSchema(BaseModel):
    filename: str
    file_path: str
    content_type: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)

class TicketCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    description: str = Field(..., min_length=10, max_length=2000)
    category: Optional[TicketCategory] = None  # If None, AI detects it
    priority: Optional[TicketPriority] = None  # If None, AI assigns it
    attachments: Optional[List[AttachmentSchema]] = []
    allowAiPasswordReset: Optional[bool] = False

class TicketUpdate(BaseModel):
    status: Optional[TicketStatus] = None
    priority: Optional[TicketPriority] = None
    assigned_to: Optional[str] = None
    employee_response: Optional[str] = None
    admin_response: Optional[str] = None

class TicketOut(BaseModel):
    id: str = Field(..., alias="_id")
    ticket_number: str
    title: str
    description: str
    category: TicketCategory
    priority: TicketPriority
    status: TicketStatus
    created_by: str
    assigned_to: Optional[str] = None
    assigned_team: Optional[str] = None
    attachments: List[AttachmentSchema] = []
    created_at: datetime
    updated_at: datetime
    resolution_time: Optional[int] = None
    sla_deadline: Optional[datetime] = None
    master_incident_id: Optional[str] = None
    risk_score: Optional[float] = None
    confidence_score: Optional[float] = None
    ai_explanation: Optional[str] = None
    employee_response: Optional[str] = None
    admin_response: Optional[str] = None
    resolution_steps: Optional[List[str]] = []

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
