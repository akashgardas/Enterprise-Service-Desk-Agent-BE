import pytest
from fastapi import status
from app.models.ticket import TicketStatus, TicketPriority, TicketCategory
from app.database import get_db

pytestmark = pytest.mark.asyncio

async def test_ticket_creation_and_ai_fallback(client, db_session):
    # Register user
    email = "employee_test@company.com"
    reg_res = await client.post("/api/auth/register", json={
        "name": "Jane Employee",
        "email": email,
        "role": "employee",
        "password": "Password@123"
    })
    
    # Login to get token
    login_res = await client.post("/api/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Submit a VPN ticket (checks category and priority mapping fallback)
    ticket_res = await client.post("/api/auth/tickets", json={
        "title": "VPN AnyConnect is disconnected",
        "description": "My AnyConnect secure portal client is disconnected since morning. I cannot work."
    }, headers=headers)

    assert ticket_res.status_code == status.HTTP_201_CREATED
    ticket_data = ticket_res.json()
    assert ticket_data["category"] == TicketCategory.VPN.value
    assert ticket_data["priority"] == TicketPriority.MEDIUM.value
    assert ticket_data["status"] == TicketStatus.OPEN.value
    assert ticket_data["assigned_team"] == "Network Team"
    assert ticket_data["sla_deadline"] is not None

async def test_ticket_deduplication(client, db_session):
    # Register employee
    email = "emp@company.com"
    await client.post("/api/auth/register", json={
        "name": "Emp Tester",
        "email": email,
        "role": "employee",
        "password": "Password@123"
    })
    login_res = await client.post("/api/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create first ticket
    t1 = await client.post("/api/auth/tickets", json={
        "title": "Outlook calendar is sync error",
        "description": "My corporate Outlook calendar is throwing sync errors and events are missing."
    }, headers=headers)
    assert t1.status_code == status.HTTP_201_CREATED
    t1_id = t1.json()["_id"]

    # 2. Create second ticket with highly similar contents (should trigger duplicate logic)
    t2 = await client.post("/api/auth/tickets", json={
        "title": "Outlook calendar sync error events missing",
        "description": "My corporate Outlook calendar is throwing sync errors and events are missing."
    }, headers=headers)
    assert t2.status_code == status.HTTP_201_CREATED
    t2_data = t2.json()
    
    assert t2_data["status"] == TicketStatus.LINKED.value
    assert t2_data["master_incident_id"] == t1_id
    assert "Linked as duplicate" in t2_data["admin_response"]

async def test_password_reset_auto_remediation(client, db_session):
    # Register employee
    email = "pwd_rem@company.com"
    await client.post("/api/auth/register", json={
        "name": "Rem User",
        "email": email,
        "role": "employee",
        "password": "Password@123"
    })
    login_res = await client.post("/api/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Submit ticket asking for password reset with allowAiPasswordReset = True
    t_res = await client.post("/api/auth/tickets", json={
        "title": "Forgot password reset account",
        "description": "I forgot my password. Can you reset my password please?",
        "allowAiPasswordReset": True
    }, headers=headers)

    assert t_res.status_code == status.HTTP_201_CREATED
    t_data = t_res.json()
    assert t_data["status"] == TicketStatus.RESOLVED.value
    assert "temporary password is:" in t_data["employee_response"]

    # Verify that the user can now log in with the new temp password
    # Extract password from text
    import re
    match = re.search(r"temporary password is: \*\*([^*]+)\*\*", t_data["employee_response"])
    assert match is not None
    temp_pwd = match.group(1)

    login_temp = await client.post("/api/auth/login", json={
        "email": email,
        "password": temp_pwd
    })
    assert login_temp.status_code == status.HTTP_200_OK

async def test_ticket_workflow_transitions(client, db_session):
    # Setup test users: Employee, Agent
    emp_email = "emp_flow@company.com"
    agent_email = "agent_flow@company.com"
    
    await client.post("/api/auth/register", json={
        "name": "Emp Flow",
        "email": emp_email,
        "role": "employee",
        "password": "Password@123"
    })
    await client.post("/api/auth/register", json={
        "name": "Agent Flow",
        "email": agent_email,
        "role": "agent",
        "password": "Password@123"
    })

    # Login both
    login_emp = await client.post("/api/auth/login", json={"email": emp_email, "password": "Password@123"})
    login_agt = await client.post("/api/auth/login", json={"email": agent_email, "password": "Password@123"})
    
    emp_token = login_emp.json()["access_token"]
    agt_token = login_agt.json()["access_token"]
    
    # Store agent ID
    db = get_db()
    agent_res = db.table("profiles").select("*").eq("email", agent_email).execute()
    agent_user = agent_res.data[0]
    agent_id = str(agent_user["id"])

    # Create ticket as employee
    t_create = await client.post("/api/auth/tickets", json={
        "title": "Monitor is blinking black",
        "description": "My external desktop screen keeps flickering black every few seconds."
    }, headers={"Authorization": f"Bearer {emp_token}"})
    
    t_id = t_create.json()["_id"]

    # 1. Try invalid transition: OPEN -> IN_PROGRESS directly (not allowed, must be Assigned first)
    bad_res = await client.patch(f"/api/auth/tickets/{t_id}", json={
        "status": "in_progress"
    }, headers={"Authorization": f"Bearer {agt_token}"})
    assert bad_res.status_code == status.HTTP_400_BAD_REQUEST

    # 2. Correct transition: assign agent (OPEN -> ASSIGNED)
    assign_res = await client.patch(f"/api/auth/tickets/{t_id}", json={
        "assigned_to": agent_id
    }, headers={"Authorization": f"Bearer {agt_token}"})
    assert assign_res.status_code == status.HTTP_200_OK
    assert assign_res.json()["status"] == TicketStatus.ASSIGNED.value
    assert assign_res.json()["assigned_to"] == agent_id

    # 3. Transition: ASSIGNED -> IN_PROGRESS
    prog_res = await client.patch(f"/api/auth/tickets/{t_id}", json={
        "status": "in_progress"
    }, headers={"Authorization": f"Bearer {agt_token}"})
    assert prog_res.status_code == status.HTTP_200_OK
    assert prog_res.json()["status"] == TicketStatus.IN_PROGRESS.value

    # 4. Transition: IN_PROGRESS -> RESOLVED
    res_res = await client.patch(f"/api/auth/tickets/{t_id}", json={
        "status": "resolved"
    }, headers={"Authorization": f"Bearer {agt_token}"})
    assert res_res.status_code == status.HTTP_200_OK
    assert res_res.json()["status"] == TicketStatus.RESOLVED.value
    assert res_res.json()["resolution_time"] is not None

    # 5. Transition: RESOLVED -> CLOSED
    close_res = await client.patch(f"/api/auth/tickets/{t_id}", json={
        "status": "closed"
    }, headers={"Authorization": f"Bearer {emp_token}"})
    assert close_res.status_code == status.HTTP_200_OK
    assert close_res.json()["status"] == TicketStatus.CLOSED.value
