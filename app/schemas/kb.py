from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from app.models.ticket import TicketCategory

class KbArticleCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=150)
    content: str = Field(..., min_length=10, max_length=10000)
    category: TicketCategory
    tags: List[str] = []

class KbArticleOut(BaseModel):
    id: str = Field(..., alias="_id")
    title: str
    content: str
    category: TicketCategory
    tags: List[str]
    created_by: str
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
