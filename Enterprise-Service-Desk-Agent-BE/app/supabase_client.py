import logging
from supabase import create_client, Client
from app.config import settings

logger = logging.getLogger("enterprise_support.supabase_client")

supabase: Client = None

def init_supabase():
    global supabase
    logger.info("Initializing Supabase Client...")
    if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
        try:
            supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            logger.info("Supabase Client initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase Client: {e}")
    else:
        logger.warning("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not configured. Supabase operations will fail.")

def get_supabase() -> Client:
    global supabase
    if supabase is None:
        init_supabase()
    return supabase
