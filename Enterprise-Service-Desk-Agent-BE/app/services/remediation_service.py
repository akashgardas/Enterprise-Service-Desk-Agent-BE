import logging
import httpx
import re
import secrets
import string
from typing import Dict, Any, Optional
from app.config import settings

logger = logging.getLogger("enterprise_support.remediation_service")

class RemediationService:
    @staticmethod
    def is_password_reset_request(title: str, description: str) -> bool:
        """Determines if the ticket description or title asks for a password reset."""
        text = f"{title} {description}".lower()
        return any(kw in text for kw in ["reset password", "forgot password", "password reset", "change password", "recover password"])

    @classmethod
    async def run_remediation(cls, email: str, db) -> Dict[str, Any]:
        """
        Executes the password reset remediation.
        If mock is active, it modifies the user directly in Supabase or returns a generated temp password.
        Otherwise, it hits the external Web_Auth endpoint.
        """
        temp_pwd = cls.generate_secure_temp_password()

        if settings.MOCK_SERVICES:
            logger.info(f"[Mock Remediation] Simulating password reset for {email}")
            # Mock update: generate bcrypt hash for temp password and store it
            from app.utils.security import hash_password
            hashed = hash_password(temp_pwd)
            
            try:
                res = db.table("profiles").update({
                    "password_hash": hashed,
                    "failed_login_attempts": 0,
                    "lockout_until": None
                }).eq("email", email.lower()).execute()
                
                if res.data:
                    return {
                        "success": True,
                        "temporary_password": temp_pwd,
                        "message": "Password reset successfully completed locally (simulated)."
                    }
            except Exception as e:
                logger.error(f"Failed to update profile during remediation simulation: {e}")
                
            return {
                "success": False,
                "message": f"User with email {email} not found in database or update failed."
            }
        
        # Real integration with Web_Auth service
        try:
            logger.info(f"Triggering password reset at {settings.WEB_AUTH_URL}/api/password/reset for {email}")
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.WEB_AUTH_URL}/api/password/reset",
                    json={
                        "email": email.lower(),
                        "api_key": settings.RESET_API_KEY,
                        "temp_password": temp_pwd
                    },
                    timeout=5.0
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "temporary_password": temp_pwd,
                        "message": data.get("message", "Password reset successfully via Web_Auth integration.")
                    }
                else:
                    return {
                        "success": False,
                        "message": f"Integration server returned error: {response.text}"
                    }
        except Exception as e:
            logger.error(f"Remediation Web_Auth connection error: {e}")
            return {
                "success": False,
                "message": f"Failed to connect to integration server: {str(e)}"
            }

    @staticmethod
    def generate_secure_temp_password() -> str:
        """Generates a secure temporary password satisfying the password policy."""
        alphabet = string.ascii_letters + string.digits + "@$!%*?&"
        while True:
            password = ''.join(secrets.choice(alphabet) for i in range(12))
            if (any(c.islower() for c in password)
                    and any(c.isupper() for c in password)
                    and any(c.isdigit() for c in password)
                    and any(c in "@$!%*?&" for c in password)):
                return password
