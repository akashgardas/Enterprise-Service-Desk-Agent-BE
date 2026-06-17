import pytest
from fastapi import status
from app.utils.security import hash_password
from app.utils.mfa import generate_mfa_secret, verify_totp_code
import pyotp

pytestmark = pytest.mark.asyncio

async def test_user_registration(client):
    # Test valid registration
    res = await client.post("/api/auth/register", json={
        "name": "Alex Support",
        "email": "alex@company.com",
        "role": "employee",
        "password": "Password@123"
    })
    assert res.status_code == status.HTTP_201_CREATED
    assert res.json() == {"message": "User registered successfully"}

    # Test invalid password policy registration (missing uppercase)
    res_bad = await client.post("/api/auth/register", json={
        "name": "Bad Pass",
        "email": "bad@company.com",
        "role": "employee",
        "password": "password@123"
    })
    assert res_bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # Test duplicate registration
    res_dup = await client.post("/api/auth/register", json={
        "name": "Alex Support",
        "email": "alex@company.com",
        "role": "employee",
        "password": "Password@123"
    })
    assert res_dup.status_code == status.HTTP_400_BAD_REQUEST

async def test_login_invalid_credentials(client):
    # Register user
    await client.post("/api/auth/register", json={
        "name": "Bob Agent",
        "email": "bob@company.com",
        "role": "agent",
        "password": "Password@123"
    })

    # Login with wrong password
    res = await client.post("/api/auth/login", json={
        "email": "bob@company.com",
        "password": "WrongPassword@123"
    })
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Attempt 1 of 5" in res.json()["detail"]

async def test_account_lockout_policy(client):
    email = "lockout_test@company.com"
    await client.post("/api/auth/register", json={
        "name": "Lock Tester",
        "email": email,
        "role": "employee",
        "password": "Password@123"
    })

    # Fail login 5 times
    for i in range(1, 6):
        res = await client.post("/api/auth/login", json={
            "email": email,
            "password": "WrongPassword@123"
        })
        if i < 5:
            assert res.status_code == status.HTTP_401_UNAUTHORIZED
            assert f"Attempt {i} of 5" in res.json()["detail"]
        else:
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            assert "Too many failed attempts. Account locked" in res.json()["detail"]

    # Sixth login should directly state account is locked
    res_locked = await client.post("/api/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    assert res_locked.status_code == status.HTTP_400_BAD_REQUEST
    assert "Account locked due to too many failed attempts" in res_locked.json()["detail"]

async def test_mfa_setup_and_verification(client, db_session):
    # Register user
    email = "mfa@company.com"
    await client.post("/api/auth/register", json={
        "name": "Mfa User",
        "email": email,
        "role": "employee",
        "password": "Password@123"
    })

    # Login to get basic token
    login_res = await client.post("/api/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Setup MFA
    setup_res = await client.post("/api/auth/mfa/setup", headers=headers)
    assert setup_res.status_code == status.HTTP_200_OK
    setup_data = setup_res.json()
    assert "secret" in setup_data
    assert "qr_code_url" in setup_data

    # Generate TOTP Code using setup secret
    totp = pyotp.TOTP(setup_data["secret"])
    code = totp.now()

    # Enable MFA with verification token
    # We need a temp validation session, but since we are setup, enable_mfa uses temporary validation token
    # Let's request it: wait, our enable endpoint decodes mfa_token to get email.
    from app.utils.security import create_mfa_token
    mfa_token = create_mfa_token(email)
    
    enable_res = await client.post("/api/auth/mfa/enable", json={
        "mfa_token": mfa_token,
        "code": code
    })
    assert enable_res.status_code == status.HTTP_200_OK
    assert enable_res.json() == {"message": "MFA enabled successfully"}

    # Next login should return mfa_required
    login_mfa_res = await client.post("/api/auth/login", json={
        "email": email,
        "password": "Password@123"
    })
    assert login_mfa_res.status_code == status.HTTP_200_OK
    login_data = login_mfa_res.json()
    assert login_data["status"] == "mfa_required"
    assert "mfa_token" in login_data

    # Verify MFA code to get final token
    verify_code = totp.now()
    verify_res = await client.post("/api/auth/mfa/verify", json={
        "mfa_token": login_data["mfa_token"],
        "code": verify_code
    })
    assert verify_res.status_code == status.HTTP_200_OK
    assert "access_token" in verify_res.json()
    assert verify_res.json()["email"] == email
