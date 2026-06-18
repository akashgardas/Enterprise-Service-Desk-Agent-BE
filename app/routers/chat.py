from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
import json
from app.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse, ChatSessionOut, ChatMessage
from app.models.user import UserRole
from app.routers.auth import get_current_user
from app.services.ai_service import AIService
from app.services.kb_service import KbService

router = APIRouter(prefix="/chat", tags=["AI Chatbot"])

@router.post("/sessions", response_model=ChatSessionOut, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Creates a new chatbot session."""
    session = {
        "user_id": str(current_user["_id"]),
        "messages": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    result = await db.chat_sessions.insert_one(session)
    session["_id"] = str(result.inserted_id)
    return session

@router.get("/sessions", response_model=List[ChatSessionOut])
async def list_chat_sessions(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Retrieves chat sessions for the current user."""
    cursor = db.chat_sessions.find({"user_id": str(current_user["_id"])}).sort("updated_at", -1)
    sessions = []
    async for s in cursor:
        sessions.append(s)
    return sessions

@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
async def get_chat_session(
    session_id: str,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Retrieves details of a specific chat session."""
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
        
    session = await db.chat_sessions.find_one({"_id": ObjectId(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    if session["user_id"] != str(current_user["_id"]) and current_user["role"] not in [UserRole.AGENT.value, UserRole.MANAGER.value, UserRole.ADMIN.value]:
        raise HTTPException(status_code=403, detail="Not authorized to view this session")
        
    return session

@router.post("/sessions/{session_id}/message", response_model=ChatResponse)
async def send_message(
    session_id: str,
    chat_req: ChatRequest,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Sends a message to the chatbot session and returns the AI reply."""
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID format")
        
    session = await db.chat_sessions.find_one({"_id": ObjectId(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
        
    # Append user message
    user_msg = {
        "sender": "user",
        "text": chat_req.text,
        "timestamp": datetime.utcnow()
    }
    
    await db.chat_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {
            "$push": {"messages": user_msg},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )
    
    # Reload messages to get updated history
    session = await db.chat_sessions.find_one({"_id": ObjectId(session_id)})
    history = session.get("messages", [])
    
    # RAG: Retrieve related KB articles based on user query
    kb_articles = await KbService.search_articles(db, chat_req.text, limit=2)
    
    # Generate bot response
    ai_resp = await AIService.generate_chat_response(history, kb_articles, session_id)
    
    bot_msg = {
        "sender": "assistant",
        "text": ai_resp["text"],
        "timestamp": datetime.utcnow()
    }
    
    # Append bot message
    await db.chat_sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$push": {"messages": bot_msg}}
    )
    
    return ChatResponse(
        text=ai_resp["text"],
        suggested_action=ai_resp.get("suggested_action"),
        chat_session_id=session_id
    )

@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str, db = Depends(get_db)):
    """WebSocket endpoint for dynamic real-time chatbot interaction."""
    # Note: Authentication can be verified via query params or subprotocols,
    # for simplicity, we verify the session is valid in database.
    if not ObjectId.is_valid(session_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    session = await db.chat_sessions.find_one({"_id": ObjectId(session_id)})
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
                "timestamp": datetime.utcnow()
            }
            await db.chat_sessions.update_one(
                {"_id": ObjectId(session_id)},
                {"$push": {"messages": user_msg}, "$set": {"updated_at": datetime.utcnow()}}
            )
            
            # Fetch updated history
            updated_session = await db.chat_sessions.find_one({"_id": ObjectId(session_id)})
            history = updated_session.get("messages", [])
            
            # Fetch KB articles
            kb_articles = await KbService.search_articles(db, user_text, limit=2)
            
            # Generate response
            ai_resp = await AIService.generate_chat_response(history, kb_articles, session_id)
            
            bot_msg = {
                "sender": "assistant",
                "text": ai_resp["text"],
                "timestamp": datetime.utcnow()
            }
            await db.chat_sessions.update_one(
                {"_id": ObjectId(session_id)},
                {"$push": {"messages": bot_msg}}
            )
            
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
        # Catch connection faults
        pass
