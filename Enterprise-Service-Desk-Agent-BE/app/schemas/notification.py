from pydantic import BaseModel, Field
from datetime import datetime

class NotificationOut(BaseModel):
    id: str = Field(..., alias="_id")
    user_id: str
    title: str
    message: str
    type: str  # ticket_created, ticket_assigned, etc.
    is_read: bool
    created_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
