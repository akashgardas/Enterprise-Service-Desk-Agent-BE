import uuid
import json
import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from app.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ChatSessionOut, ChatMessage
from app.models.user import UserRole
from app.routers.auth import get_current_user
from app.services.ai_service import AIService
from app.services.kb_service import KbService

router = APIRouter(prefix="/chat", tags=["AI Chatbot"])
logger = logging.getLogger("enterprise_support.chat")

def is_valid_uuid(val: str) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except ValueError:
        return False

def format_session(session: dict) -> dict:
    if not session:
        return {}
    sid = str(session.get("id") or session.get("_id"))
    messages = session.get("messages") or []
    formatted_messages = []
    for m in messages:
        timestamp = m.get("timestamp")
        if isinstance(timestamp, datetime):
            timestamp = timestamp.isoformat()
        formatted_messages.append({
            "sender": m.get("sender"),
            "text": m.get("text"),
            "timestamp": timestamp
        })
        
    created_at = session.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    updated_at = session.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()
        
    return {
        "id": sid,
        "_id": sid,
        "user_id": session.get("user_id"),
        "messages": formatted_messages,
        "created_at": created_at,
        "updated_at": updated_at
    }

@router.post("/sessions", response_model=Any, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Creates a new chatbot session."""
    session = {
        "id": str(uuid.uuid4()),
        "user_id": str(current_user["id"]),
        "messages": [],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }
    db.table("chat_sessions").insert(session).execute()
    return format_session(session)

@router.get("/sessions", response_model=List[Any])
async def list_chat_sessions(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Retrieves chat sessions for the current user."""
    res = db.table("chat_sessions").select("*").eq("user_id", str(current_user["id"])).order("updated_at", desc=True).execute()
    sessions = [format_session(s) for s in res.data] if res.data else []
    return sessions

@router.get("/sessions/{session_id}", response_model=Any)
async def get_chat_session(
    session_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Retrieves details of a specific chat session."""
    if not is_valid_uuid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
        
    res = db.table("chat_sessions").select("*").eq("id", session_id).execute()
    session = res.data[0] if res.data else None
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    if session["user_id"] != str(current_user["id"]) and current_user["role"] not in [UserRole.AGENT.value, UserRole.MANAGER.value, UserRole.ADMIN.value]:
        raise HTTPException(status_code=403, detail="Not authorized to view this session")
        
    return format_session(session)

@router.post("/sessions/{session_id}/message", response_model=ChatResponse)
async def send_message(
    session_id: str,
    chat_req: ChatRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Sends a message to the chatbot session and returns the AI reply."""
    if not is_valid_uuid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
        
    res = db.table("chat_sessions").select("*").eq("id", session_id).execute()
    session = res.data[0] if res.data else None
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    # Append user message
    user_msg = {
        "sender": "user",
        "text": chat_req.text,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    messages = session.get("messages") or []
    messages.append(user_msg)
    
    db.table("chat_sessions").update({
        "messages": messages,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", session_id).execute()
    
    # Reload messages to get updated history
    history = messages
    
    # RAG: Retrieve related KB articles based on user query
    kb_articles = await KbService.search_articles(db, chat_req.text, limit=2)
    
    # Generate bot response
    ai_resp = await AIService.generate_chat_response(history, kb_articles, session_id)
    
    bot_msg = {
        "sender": "assistant",
        "text": ai_resp["text"],
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Append bot message
    messages.append(bot_msg)
    db.table("chat_sessions").update({
        "messages": messages,
        "updated_at": datetime.utcnow().isoformat()
    }).eq("id", session_id).execute()
    
    return ChatResponse(
        text=ai_resp["text"],
        suggested_action=ai_resp.get("suggested_action"),
        chat_session_id=session_id
    )

@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str, db = Depends(get_db)):
    """WebSocket endpoint for dynamic real-time chatbot interaction."""
    if not is_valid_uuid(session_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    res = db.table("chat_sessions").select("*").eq("id", session_id).execute()
    session = res.data[0] if res.data else None
    if not session:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    
    try:
        while True:
            # Receive text payload
            data = await websocket.receive_text()
            payload = json.loads(data)
            user_text = payload.get("text", "").strip()
            
            if not user_text:
                continue
                
            # Append user message
            user_msg = {
                "sender": "user",
                "text": user_text,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Fetch latest messages
            res = db.table("chat_sessions").select("messages").eq("id", session_id).execute()
            messages = res.data[0].get("messages") or [] if res.data else []
            messages.append(user_msg)
            
            db.table("chat_sessions").update({
                "messages": messages,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", session_id).execute()
            
            history = messages
            
            # Fetch KB articles
            kb_articles = await KbService.search_articles(db, user_text, limit=2)
            
            # Generate response
            ai_resp = await AIService.generate_chat_response(history, kb_articles, session_id)
            
            bot_msg = {
                "sender": "assistant",
                "text": ai_resp["text"],
                "timestamp": datetime.utcnow().isoformat()
            }
            messages.append(bot_msg)
            
            db.table("chat_sessions").update({
                "messages": messages,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("id", session_id).execute()
            
            # Push back response payload
            response_data = {
                "sender": "assistant",
                "text": ai_resp["text"],
                "suggested_action": ai_resp.get("suggested_action"),
                "timestamp": datetime.utcnow().isoformat()
            }
            await websocket.send_text(json.dumps(response_data))
            
    except WebSocketDisconnect:
        # Client disconnected
        pass
    except Exception as e:
        logger.error(f"WebSocket error in session {session_id}: {e}")
        pass
