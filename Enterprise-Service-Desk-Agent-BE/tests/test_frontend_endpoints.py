import pytest
from fastapi import status
from app.models.user import UserRole
from app.models.ticket import TicketStatus, TicketPriority, TicketCategory
from app.database import get_db
from datetime import datetime

pytestmark = pytest.mark.asyncio

async def test_frontend_auth_compatibility(client):
    # Register user
    email = "fe_auth@company.com"
    await client.post("/auth/register", json={
        "name": "Frontend User",
        "email": email,
        "role": "admin",
        "password": "Password@123"
    })

    # Login and verify compatibility payload structure
    login_res = await client.post("/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    assert login_res.status_code == status.HTTP_200_OK
    data = login_res.json()
    assert "token" in data
    assert "access_token" in data
    assert "user" in data
    
    user = data["user"]
    assert "id" in user
    assert "role" in user
    assert "department" in user
    assert "phone" in user
    assert "status" in user
    assert "createdAt" in user
    assert user["email"] == email

    headers = {"Authorization": f"Bearer {data['access_token']}"}

    # Change password
    change_res = await client.post("/auth/change-password", json={
        "oldPassword": "Password@123",
        "newPassword": "NewPassword@123"
    }, headers=headers)
    assert change_res.status_code == status.HTTP_200_OK
    assert change_res.json()["success"] is True

    # Logout
    logout_res = await client.post("/auth/logout", headers=headers)
    assert logout_res.status_code == status.HTTP_200_OK
    assert logout_res.json() == {"success": True, "message": "Logged out successfully"}

async def test_frontend_users_router(client):
    # Register and login admin
    email = "admin_users@company.com"
    await client.post("/auth/register", json={
        "name": "Admin Users",
        "email": email,
        "role": "admin",
        "password": "Password@123"
    })
    login_res = await client.post("/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # GET /users/me
    me_res = await client.get("/users/me", headers=headers)
    assert me_res.status_code == status.HTTP_200_OK
    assert me_res.json()["email"] == email

    # POST /users (provision user)
    new_email = "provisioned@company.com"
    provision_res = await client.post("/users", json={
        "name": "Provisioned User",
        "email": new_email,
        "role": "agent",
        "phone": "+1234567890",
        "department": "HR"
    }, headers=headers)
    assert provision_res.status_code == status.HTTP_201_CREATED
    provisioned_data = provision_res.json()
    assert provisioned_data["email"] == new_email
    assert provisioned_data["department"] == "HR"
    assert provisioned_data["phone"] == "+1234567890"
    provisioned_id = provisioned_data["id"]

    # GET /users/{id}
    get_res = await client.get(f"/users/{provisioned_id}", headers=headers)
    assert get_res.status_code == status.HTTP_200_OK
    assert get_res.json()["email"] == new_email

    # GET /users (list all)
    list_res = await client.get("/users", headers=headers)
    assert list_res.status_code == status.HTTP_200_OK
    emails = [u["email"] for u in list_res.json()]
    assert email in emails
    assert new_email in emails

async def test_frontend_tickets_router(client):
    # Register and login agent/admin
    email = "agent_tickets@company.com"
    await client.post("/auth/register", json={
        "name": "Agent Tickets",
        "email": email,
        "role": "admin",
        "password": "Password@123"
    })
    login_res = await client.post("/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Create ticket
    ticket_res = await client.post("/tickets", json={
        "title": "Email access lost",
        "description": "My corporate email access is lost after security patch."
    }, headers=headers)
    assert ticket_res.status_code == status.HTTP_201_CREATED
    t_data = ticket_res.json()
    assert "createdBy" in t_data
    assert "createdAt" in t_data
    assert "comments" in t_data
    assert "timeline" in t_data
    assert t_data["department"] == "IT"
    t_id = t_data["id"]

    # Add comment
    comment_res = await client.post(f"/tickets/{t_id}/comments", json={
        "text": "Checking exchange server logs."
    }, headers=headers)
    assert comment_res.status_code == status.HTTP_200_OK
    assert "userId" in comment_res.json()
    assert comment_res.json()["text"] == "Checking exchange server logs."

    # Verify timeline is updated on ticket retrieve
    get_ticket_res = await client.get(f"/tickets/{t_id}", headers=headers)
    assert get_ticket_res.status_code == status.HTTP_200_OK
    updated_t = get_ticket_res.json()
    assert len(updated_t["comments"]) == 1
    # Check that it contains "Comment added" in timeline
    activities = [evt["activity"] for evt in updated_t["timeline"]]
    assert any("Comment added" in act for act in activities)

    # Test filtering compatibility
    filter_res = await client.get(f"/tickets?assignedTo={updated_t.get('assignedTo') or ''}", headers=headers)
    assert filter_res.status_code == status.HTTP_200_OK

async def test_frontend_ai_router(client):
    # Register and login
    email = "ai_test@company.com"
    await client.post("/auth/register", json={
        "name": "AI User",
        "email": email,
        "role": "employee",
        "password": "Password@123"
    })
    login_res = await client.post("/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # POST /ai/chat
    chat_res = await client.post("/ai/chat", json={
        "message": "VPN connection is not starting",
        "history": []
    }, headers=headers)
    assert chat_res.status_code == status.HTTP_200_OK
    assert "text" in chat_res.json()
    assert "suggestedActions" in chat_res.json()

    # GET /ai/suggested-questions
    sq_res = await client.get("/ai/suggested-questions", headers=headers)
    assert sq_res.status_code == status.HTTP_200_OK
    assert len(sq_res.json()) > 0

async def test_frontend_kb_router(client):
    # Register and login admin
    email = "admin_kb@company.com"
    await client.post("/auth/register", json={
        "name": "Admin KB",
        "email": email,
        "role": "admin",
        "password": "Password@123"
    })
    login_res = await client.post("/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # POST /articles
    art_res = await client.post("/articles", json={
        "title": "Configuring AnyConnect VPN client",
        "category": "vpn",
        "content": "Follow these steps to connect your corporate VPN AnyConnect."
    }, headers=headers)
    assert art_res.status_code == status.HTTP_201_CREATED
    art_data = art_res.json()
    assert "authorId" in art_data
    assert "createdAt" in art_data
    art_id = art_data["id"]

    # GET /kb (compatibility check)
    kb_list_res = await client.get("/kb", headers=headers)
    assert kb_list_res.status_code == status.HTTP_200_OK
    assert len(kb_list_res.json()) > 0

    # PATCH /articles/{id}
    patch_res = await client.patch(f"/articles/{art_id}", json={
        "title": "Configuring AnyConnect VPN client - Updated"
    }, headers=headers)
    assert patch_res.status_code == status.HTTP_200_OK
    assert patch_res.json()["title"] == "Configuring AnyConnect VPN client - Updated"

    # DELETE /articles/{id}
    del_res = await client.delete(f"/articles/{art_id}", headers=headers)
    assert del_res.status_code == status.HTTP_200_OK
    assert del_res.json() == {"success": True}

async def test_frontend_notifications_router(client):
    # Register and login user
    email = "notif_user@company.com"
    await client.post("/auth/register", json={
        "name": "Notif User",
        "email": email,
        "role": "employee",
        "password": "Password@123"
    })
    login_res = await client.post("/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # Create dummy notification in database
    import uuid
    db = get_db()
    user_res = db.table("profiles").select("*").eq("email", email).execute()
    user = user_res.data[0]
    notif_id = str(uuid.uuid4())
    db.table("notifications").insert({
        "id": notif_id,
        "user_id": str(user["id"]),
        "type": "alert",
        "message": "Testing alerts",
        "is_read": False,
        "created_at": datetime.utcnow().isoformat()
    }).execute()

    # GET /notifications
    notif_res = await client.get("/notifications", headers=headers)
    assert notif_res.status_code == status.HTTP_200_OK
    assert len(notif_res.json()) == 1
    assert notif_res.json()[0]["userId"] == str(user["id"])

    # PATCH /notifications/{id}/read
    read_res = await client.patch(f"/notifications/{notif_id}/read", headers=headers)
    assert read_res.status_code == status.HTTP_200_OK
    assert read_res.json()["read"] is True

    # POST /notifications/read-all
    read_all_res = await client.post("/notifications/read-all", headers=headers)
    assert read_all_res.status_code == status.HTTP_200_OK
    assert read_all_res.json() == {"success": True}

async def test_frontend_analytics_router(client):
    # Register and login admin
    email = "admin_analytics@company.com"
    await client.post("/auth/register", json={
        "name": "Admin Analytics",
        "email": email,
        "role": "admin",
        "password": "Password@123"
    })
    login_res = await client.post("/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # GET /analytics/dashboard
    dash_res = await client.get("/analytics/dashboard", headers=headers)
    assert dash_res.status_code == status.HTTP_200_OK
    assert "ticketsByMonth" in dash_res.json()
    assert "slaCompliance" in dash_res.json()

    # GET /analytics/volume
    vol_res = await client.get("/analytics/volume", headers=headers)
    assert vol_res.status_code == status.HTTP_200_OK
    assert len(vol_res.json()) > 0

    # GET /analytics/categories
    cat_res = await client.get("/analytics/categories", headers=headers)
    assert cat_res.status_code == status.HTTP_200_OK

    # GET /analytics/performance
    perf_res = await client.get("/analytics/performance", headers=headers)
    assert perf_res.status_code == status.HTTP_200_OK

async def test_frontend_activities_router(client):
    # Register and login admin
    email = "admin_activities@company.com"
    await client.post("/auth/register", json={
        "name": "Admin Activities",
        "email": email,
        "role": "admin",
        "password": "Password@123"
    })
    login_res = await client.post("/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    # POST /activities
    act_res = await client.post("/activities", json={
        "type": "security",
        "action": "auth_login",
        "detail": "Logged in from Chrome browser",
        "user": email,
        "role": "admin",
        "status": "success"
    }, headers=headers)
    assert act_res.status_code == status.HTTP_201_CREATED
    assert act_res.json()["user"] == email

    # GET /activities
    list_res = await client.get("/activities", headers=headers)
    assert list_res.status_code == status.HTTP_200_OK
    assert len(list_res.json()) > 0
    assert list_res.json()[0]["action"] == "auth_login"
