import logging
from supabase import create_client, Client
from app.config import settings

logger = logging.getLogger("enterprise_support.database")

class Database:
    client: Client = None

db_instance = Database()

def connect_db():
    logger.info("Initializing Supabase Client...")
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
        try:
            db_instance.client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            logger.info("Connected to Supabase successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Supabase: {e}")
    else:
        logger.warning("Supabase URL or SERVICE_ROLE_KEY missing.")

def disconnect_db():
    db_instance.client = None

def get_db() -> Client:
    if db_instance.client is None:
        connect_db()
    return db_instance.client
