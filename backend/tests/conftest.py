import pytest
import asyncio
from app.config import settings

# Force test configuration
settings.DATABASE_NAME = "test_enterprise_support"
settings.MOCK_SERVICES = True
settings.JWT_SECRET_KEY = "testsecretkeyfortesting"
settings.MFA_JWT_SECRET_KEY = "testmfasecretkeyfortesting"

from app.main import app
from app.database import connect_db, disconnect_db, get_db
from httpx import AsyncClient

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def init_test_session():
    # Setup test database connection
    connect_db()
    db = get_db()
    
    # Drop existing collections to ensure a clean state
    await db.users.drop()
    await db.kb_articles.drop()
    await db.tickets.drop()
    await db.password_resets.drop()
    await db.system_counters.drop()
    
    yield
    
    # Teardown database
    db_client = db.client
    await db_client.drop_database(settings.DATABASE_NAME)
    disconnect_db()

@pytest.fixture(autouse=True)
async def clean_collections(db_session):
    # This runs before each individual test to keep them isolated
    db = get_db()
    await db.users.delete_many({})
    await db.kb_articles.delete_many({})
    await db.tickets.delete_many({})
    await db.password_resets.delete_many({})
    await db.system_counters.delete_many({})

@pytest.fixture(scope="session")
def db_session():
    return get_db()

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
