from fastapi import APIRouter, Depends, status
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.database import get_db
from app.routers.auth import get_current_user
from app.services.ai_service import AIService
from app.services.kb_service import KbService

router = APIRouter(prefix="/ai", tags=["AI Assistant"])

class ChatMessageIn(BaseModel):
    sender: str  # "user" or "assistant"
    text: str

class AIChatRequest(BaseModel):
    message: str
    history: List[ChatMessageIn] = Field(default=[])

@router.post("/chat", response_model=Any)
async def ai_chat(
    request: AIChatRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Session-less chat with AI assistant. Reroutes to KB search and Gemini."""
    history_list = []
    for msg in request.history:
        # Standardize sender labels
        sender = msg.sender.lower()
        if sender in ["model", "assistant", "bot", "ai"]:
            sender_label = "assistant"
        else:
            sender_label = "user"
        history_list.append({"sender": sender_label, "text": msg.text})
        
    # Append current message as the latest user message
    history_list.append({"sender": "user", "text": request.message})
    
    # Retrieve related KB articles based on user query
    kb_articles = await KbService.search_articles(db, request.message, limit=2)
    
    # Generate bot response
    ai_resp = await AIService.generate_chat_response(history_list, kb_articles, "temp_session")
    
    suggested_actions = []
    if ai_resp.get("suggested_action"):
        s_act = ai_resp["suggested_action"]
        suggested_actions.append({
            "label": "Create Ticket",
            "action": s_act.get("action"),
            "payload": s_act.get("payload")
        })
        
    return {
        "text": ai_resp["text"],
        "timestamp": datetime.utcnow().isoformat(),
        "suggestedActions": suggested_actions
    }

@router.get("/suggested-questions", response_model=List[str])
def get_suggested_questions(current_user = Depends(get_current_user)):
    """Returns a list of suggested questions for the AI assistant."""
    return [
        "How do I connect to VPN?",
        "How do I setup my corporate email on Outlook?",
        "How do I report a suspicious phishing email?",
        "How do I install standard software applications?",
        "My external monitor connected to the laptop dock is not displaying, what should I do?"
    ]
