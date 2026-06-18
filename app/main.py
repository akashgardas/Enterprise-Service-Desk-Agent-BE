import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import connect_db, disconnect_db
from app.routers import tickets
from app.routers import analytics
from app.routers import auth
from app.routers import chat
from app.routers import kb
from app.routers import users
from app.routers import ai
from app.routers import notifications
from app.routers import activities

# Configure logger formatting
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
)
logger = logging.getLogger("enterprise_support.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB connection on startup
    connect_db()
    yield
    # Close DB connection on shutdown
    disconnect_db()

app = FastAPI(
    title="Enterprise Service Desk API",
    description="Backend API for Enterprise IT Service Desk featuring 7-step multi-agent ticket pipelines and dynamic AI chatbot.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configurations
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers under /api (legacy backend compatibility)
app.include_router(auth.router, prefix="/api")
app.include_router(tickets.router, prefix="/api")
app.include_router(tickets.router, prefix="/api/auth")
app.include_router(kb.router, prefix="/api")
app.include_router(kb.kb_router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(ai.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(activities.router, prefix="/api")

# Include API Routers under root / (frontend integration)
app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(kb.router)
app.include_router(kb.kb_router)
app.include_router(chat.router)
app.include_router(analytics.router)
app.include_router(users.router)
app.include_router(ai.router)
app.include_router(notifications.router)
app.include_router(activities.router)


@app.get("/", tags=["Health Check"])
def health_check():
    return {
        "status": "healthy",
        "service": "Enterprise Service Desk Agent BE",
        "mock_mode": settings.MOCK_SERVICES
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
