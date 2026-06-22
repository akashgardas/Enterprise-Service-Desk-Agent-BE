import pytest
import asyncio
import copy
import re
from app.config import settings

# Force test configuration BEFORE importing app
settings.DATABASE_NAME = "test_enterprise_support"
settings.MOCK_SERVICES = True
settings.JWT_SECRET_KEY = "testsecretkeyfortesting"
settings.MFA_JWT_SECRET_KEY = "testmfasecretkeyfortesting"

class MockSupabaseTable:
    def __init__(self, name, db_dict):
        self.name = name
        self.db_dict = db_dict
        if name not in self.db_dict:
            self.db_dict[name] = []
        self.current_list = list(self.db_dict[name])

    def select(self, columns="*"):
        self.current_list = list(self.db_dict[self.name])
        return self

    def eq(self, column, value):
        self.current_list = [r for r in self.current_list if r.get(column) == value]
        return self

    def neq(self, column, value):
        self.current_list = [r for r in self.current_list if r.get(column) != value]
        return self

    def gte(self, column, value):
        self.current_list = [r for r in self.current_list if r.get(column) >= value]
        return self

    def lte(self, column, value):
        self.current_list = [r for r in self.current_list if r.get(column) <= value]
        return self

    def in_(self, column, values):
        self.current_list = [r for r in self.current_list if r.get(column) in values]
        return self

    def or_(self, filter_str):
        parts = filter_str.split(",")
        matched = []
        for p in parts:
            m = re.match(r"(\w+)\.eq\.(.+)", p)
            if m:
                col, val = m.groups()
                for r in self.db_dict[self.name]:
                    if r.get(col) == val and r not in matched:
                        matched.append(r)
        self.current_list = matched
        return self

    def order(self, column, desc=False):
        self.current_list.sort(key=lambda x: x.get(column, ""), reverse=desc)
        return self

    def limit(self, val):
        self.current_list = self.current_list[:val]
        return self

    def insert(self, data):
        if isinstance(data, list):
            self.db_dict[self.name].extend(data)
            self.current_list = data
        else:
            self.db_dict[self.name].append(data)
            self.current_list = [data]
        return self

    def update(self, data):
        updated_items = []
        for r in self.current_list:
            for db_r in self.db_dict[self.name]:
                if db_r.get("id") == r.get("id") or db_r.get("_id") == r.get("_id"):
                    db_r.update(data)
                    updated_items.append(db_r)
        self.current_list = updated_items
        return self

    def upsert(self, data, on_conflict=None):
        if not isinstance(data, list):
            data = [data]
        for item in data:
            conflict_val = item.get(on_conflict)
            found = False
            for db_r in self.db_dict[self.name]:
                if db_r.get(on_conflict) == conflict_val:
                    db_r.update(item)
                    found = True
                    break
            if not found:
                self.db_dict[self.name].append(item)
        self.current_list = data
        return self

    def delete(self):
        for r in list(self.current_list):
            for db_r in list(self.db_dict[self.name]):
                if db_r.get("id") == r.get("id") or db_r.get("_id") == r.get("_id"):
                    self.db_dict[self.name].remove(db_r)
        return self

    def execute(self):
        class APIResponse:
            def __init__(self, data):
                self.data = data
        return APIResponse(copy.deepcopy(self.current_list))

class MockSupabaseClient:
    def __init__(self):
        self.db_dict = {}

    def table(self, name):
        return MockSupabaseTable(name, self.db_dict)

from app.database import db_instance
import app.database

mock_client = MockSupabaseClient()
db_instance.client = mock_client

# Override database lifecycle methods to prevent Atlas connection attempts
app.database.connect_db = lambda: None
app.database.disconnect_db = lambda: None

from app.main import app
from app.database import connect_db, disconnect_db, get_db
from httpx import AsyncClient

# Pytest-asyncio needs asyncio_mode configured in pytest.ini or via marker
pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def init_test_session():
    connect_db()
    yield
    disconnect_db()

@pytest.fixture(autouse=True)
async def clean_collections():
    """Clean tables before each individual test to keep them isolated."""
    db = get_db()
    db.db_dict.clear()

@pytest.fixture(scope="session")
def db_session():
    return get_db()

@pytest.fixture
async def client():
    from httpx import ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
