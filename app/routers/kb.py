from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from datetime import datetime
from bson import ObjectId
from app.database import get_db
from app.schemas.kb import KbArticleCreate, KbArticleOut
from app.models.ticket import TicketCategory
from app.models.user import UserRole
from app.routers.auth import get_current_user, require_roles
from app.services.kb_service import KbService

router = APIRouter(prefix="/api/kb", tags=["Knowledge Base"])

@router.get("/articles", response_model=List[KbArticleOut])
async def list_kb_articles(
    query: Optional[str] = None,
    category: Optional[TicketCategory] = None,
    limit: int = 10,
    db = Depends(get_db)
):
    if query:
        # Perform similarity ranking search
        articles = await KbService.search_articles(db, query, category, limit=limit)
        return articles
        
    # Standard query without search text
    filter_query = {}
    if category:
        filter_query["category"] = category.value
        
    cursor = db.kb_articles.find(filter_query).limit(limit)
    articles = []
    async for a in cursor:
        articles.append(a)
    return articles

@router.get("/articles/{article_id}", response_model=KbArticleOut)
async def get_kb_article(
    article_id: str,
    db = Depends(get_db)
):
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID format")
        
    article = await db.kb_articles.find_one({"_id": ObjectId(article_id)})
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article

@router.post("/articles", response_model=KbArticleOut, status_code=status.HTTP_201_CREATED)
async def create_kb_article(
    article_in: KbArticleCreate,
    current_user = Depends(require_roles([UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    new_article = {
        "title": article_in.title,
        "content": article_in.content,
        "category": article_in.category.value,
        "tags": article_in.tags,
        "created_by": str(current_user["_id"]),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await db.kb_articles.insert_one(new_article)
    new_article["_id"] = str(result.inserted_id)
    return new_article
