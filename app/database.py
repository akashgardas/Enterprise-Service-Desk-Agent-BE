import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

logger = logging.getLogger("enterprise_support.database")

class Database:
    client: AsyncIOMotorClient = None
    db = None

db_instance = Database()

def connect_db():
    logger.info("Connecting to MongoDB...")
    db_instance.client = AsyncIOMotorClient(settings.MONGO_URI)
    db_instance.db = db_instance.client[settings.DATABASE_NAME]
    logger.info("Connected to MongoDB successfully.")

def disconnect_db():
    if db_instance.client:
        logger.info("Closing MongoDB connection...")
        db_instance.client.close()
        logger.info("MongoDB connection closed.")

def get_db():
    if db_instance.db is None:
        raise RuntimeError("Database not initialized. Call connect_db() first.")
    return db_instance.db
