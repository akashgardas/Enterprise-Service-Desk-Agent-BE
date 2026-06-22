from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime

class ChatMessage(BaseModel):
    sender: str = Field(..., description="Either 'user' or 'assistant'")
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatSessionCreate(BaseModel):
    pass

class ChatSessionOut(BaseModel):
    id: str = Field(..., alias="_id")
    user_id: str
    messages: List[ChatMessage] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class ChatRequest(BaseModel):
    text: str

class ChatResponse(BaseModel):
    text: str
    suggested_action: Optional[dict] = None  # Holds ticket template fields if we offer ticket creation
    chat_session_id: str
