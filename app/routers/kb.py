from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional, Any, Dict
from datetime import datetime
from bson import ObjectId
from pydantic import BaseModel, Field
from app.database import get_db
from app.models.ticket import TicketCategory
from app.models.user import UserRole
from app.routers.auth import get_current_user, require_roles
from app.services.kb_service import KbService

router = APIRouter(prefix="/articles", tags=["Knowledge Base"])
kb_router = APIRouter(prefix="/kb", tags=["Knowledge Base"])

class ArticleCreate(BaseModel):
    title: str = Field(..., min_length=5, max_length=200)
    category: TicketCategory
    content: str = Field(..., min_length=10, max_length=5000)

class ArticleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=5, max_length=200)
    category: Optional[TicketCategory] = None
    content: Optional[str] = Field(None, min_length=10, max_length=5000)

def format_article(article: dict) -> dict:
    if not article:
        return {}
    aid = str(article.get("_id") or article.get("id"))
    created_at = article.get("created_at")
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    updated_at = article.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()
        
    return {
        "id": aid,
        "_id": aid,
        "title": article.get("title"),
        "category": article.get("category"),
        "content": article.get("content"),
        "author": article.get("author", "Admin"),
        "authorId": article.get("created_by") or article.get("authorId"),
        "created_by": article.get("created_by") or article.get("authorId"),
        "views": article.get("views", 0),
        "createdAt": created_at,
        "created_at": created_at,
        "updatedAt": updated_at,
        "updated_at": updated_at
    }

@router.get("", response_model=List[Any])
@kb_router.get("", response_model=List[Any])
async def list_kb_articles(
    search: Optional[str] = None,
    query: Optional[str] = None,
    category: Optional[TicketCategory] = None,
    limit: int = 20,
    db = Depends(get_db)
):
    """Retrieves KB articles filtered by search text and/or category."""
    search_term = search or query
    if search_term:
        # Perform similarity ranking search
        articles = await KbService.search_articles(db, search_term, category, limit=limit)
        return [format_article(a) for a in articles]
        
    # Standard query without search text
    filter_query = {}
    if category:
        filter_query["category"] = category.value
        
    cursor = db.kb_articles.find(filter_query).limit(limit)
    articles = []
    async for a in cursor:
        articles.append(format_article(a))
    return articles

@router.get("/{article_id}", response_model=Any)
@kb_router.get("/{article_id}", response_model=Any)
async def get_kb_article(
    article_id: str,
    db = Depends(get_db)
):
    """Retrieves a single KB article by ID. Increments views count."""
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID format")
        
    article = await db.kb_articles.find_one_and_update(
        {"_id": ObjectId(article_id)},
        {"$inc": {"views": 1}},
        return_document=True
    )
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
        
    return format_article(article)

@router.post("", response_model=Any, status_code=status.HTTP_201_CREATED)
@kb_router.post("", response_model=Any, status_code=status.HTTP_201_CREATED)
async def create_kb_article(
    article_in: ArticleCreate,
    current_user = Depends(require_roles([UserRole.AGENT, UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Creates a new KB article (Agents, Managers, Admins only)."""
    new_article = {
        "title": article_in.title,
        "content": article_in.content,
        "category": article_in.category.value,
        "author": current_user.get("name", "Support Agent"),
        "created_by": str(current_user["_id"]),
        "views": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    result = await db.kb_articles.insert_one(new_article)
    new_article["_id"] = str(result.inserted_id)
    return format_article(new_article)

@router.patch("/{article_id}", response_model=Any)
@kb_router.patch("/{article_id}", response_model=Any)
async def update_kb_article(
    article_id: str,
    article_update: ArticleUpdate,
    current_user = Depends(require_roles([UserRole.AGENT, UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Updates a KB article (Agents, Managers, Admins only)."""
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID format")
        
    existing = await db.kb_articles.find_one({"_id": ObjectId(article_id)})
    if not existing:
        raise HTTPException(status_code=404, detail="Article not found")
        
    update_fields = {}
    if article_update.title is not None:
        update_fields["title"] = article_update.title
    if article_update.category is not None:
        update_fields["category"] = article_update.category.value
    if article_update.content is not None:
        update_fields["content"] = article_update.content
        
    if not update_fields:
        return format_article(existing)
        
    update_fields["updated_at"] = datetime.utcnow()
    
    updated = await db.kb_articles.find_one_and_update(
        {"_id": ObjectId(article_id)},
        {"$set": update_fields},
        return_document=True
    )
    return format_article(updated)

@router.delete("/{article_id}", response_model=Dict[str, bool])
@kb_router.delete("/{article_id}", response_model=Dict[str, bool])
async def delete_kb_article(
    article_id: str,
    current_user = Depends(require_roles([UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Deletes a KB article (Admin only)."""
    if not ObjectId.is_valid(article_id):
        raise HTTPException(status_code=400, detail="Invalid article ID format")
        
    result = await db.kb_articles.delete_one({"_id": ObjectId(article_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Article not found")
        
    return {"success": True}
