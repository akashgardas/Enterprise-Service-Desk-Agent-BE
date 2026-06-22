import logging
import uuid
from typing import Dict, List, Any
from fastapi import WebSocket
from datetime import datetime
from app.config import settings

logger = logging.getLogger("enterprise_support.notification_service")

class ConnectionManager:
    def __init__(self):
        # Maps user_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"WebSocket connected for user {user_id}. Active count: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"WebSocket disconnected for user {user_id}")

    async def send_personal_message(self, message: Dict[str, Any], user_id: str):
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Error sending WebSocket message to user {user_id}: {e}")

    async def broadcast(self, message: Dict[str, Any]):
        for user_connections in self.active_connections.values():
            for connection in user_connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Error broadcasting WebSocket message: {e}")

manager = ConnectionManager()

class NotificationService:
    @staticmethod
    async def create_notification(db, user_id: str, title: str, message: str, notification_type: str, ticket_id: str = None) -> Dict[str, Any]:
        """Creates a notification record in the DB and broadcasts it via WebSocket + Emails."""
        notif = {
            "id": str(uuid.uuid4()),
            "user_id": str(user_id),
            "title": title,
            "message": message,
            "type": notification_type,
            "is_read": False,
            "ticket_id": ticket_id,
            "created_at": datetime.utcnow().isoformat()
        }
        
        # Save to DB (Supabase)
        try:
            db.table("notifications").insert(notif).execute()
        except Exception as e:
            logger.error(f"Failed to insert notification into Supabase: {e}")
        
        # Push via WebSocket
        websocket_payload = {
            "event": "notification",
            "data": notif
        }
        await manager.send_personal_message(websocket_payload, str(user_id))
        
        # Try sending email
        await NotificationService.send_email(user_id, db, title, message)
        
        return notif

    @staticmethod
    async def send_email(user_id: str, db, subject: str, message: str):
        """Dispatches an email notification (mock logs or real SMTP)."""
        try:
            response = db.table("profiles").select("*").eq("id", user_id).execute()
            user = response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Failed to fetch user from Supabase for emailing: {e}")
            return

        if not user:
            logger.warning(f"Cannot send email to user {user_id}. User not found.")
            return

        recipient_email = user.get("email")
        if not recipient_email:
            return

        if settings.MOCK_SERVICES:
            logger.info(
                f"\n--- [Mock Email Dispatched] ---\n"
                f"From: {settings.EMAIL_FROM}\n"
                f"To: {recipient_email}\n"
                f"Subject: {subject}\n"
                f"Message: {message}\n"
                f"-------------------------------\n"
            )
            return

        # Real SMTP implementation
        import smtplib
        from email.mime.text import MIMEText
        
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = settings.EMAIL_FROM
        msg['To'] = recipient_email

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM, [recipient_email], msg.as_string())
            logger.info(f"Email sent successfully to {recipient_email}")
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {e}")

    @staticmethod
    async def send_otp_email(email: str, otp_code: str):
        """Sends a login OTP verification email (calls Brevo API if key set, else SMTP relay)."""
        subject = "Your 6-Digit Login OTP Verification Code"
        message = f"Your login verification code is: {otp_code}. It is valid for 5 minutes."

        if settings.MOCK_SERVICES:
            logger.info(
                f"\n--- [Mock OTP Email Dispatched] ---\n"
                f"To: {email}\n"
                f"Subject: {subject}\n"
                f"Code: {otp_code}\n"
                f"-----------------------------------\n"
            )
            return

        # If Brevo API Key configured, call Brevo REST API
        if settings.BREVO_API_KEY:
            import httpx
            url = "https://api.brevo.com/v3/smtp/email"
            headers = {
                "api-key": settings.BREVO_API_KEY,
                "content-type": "application/json"
            }
            payload = {
                "sender": {"name": "Enterprise Support Desk", "email": settings.EMAIL_FROM},
                "to": [{"email": email}],
                "subject": subject,
                "htmlContent": f"<p>Your 6-digit OTP code is: <strong>{otp_code}</strong>. It will expire in 5 minutes.</p>"
            }
            try:
                async with httpx.AsyncClient() as client:
                    res = await client.post(url, headers=headers, json=payload)
                    if res.status_code in [200, 201, 202]:
                        logger.info(f"Brevo OTP email sent via API to {email}")
                        return
                    else:
                        logger.error(f"Brevo API error payload: {res.text}")
            except Exception as e:
                logger.error(f"Failed to send Brevo OTP email via API: {e}")

        # SMTP Relay Fallback
        import smtplib
        from email.mime.text import MIMEText
        
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = settings.EMAIL_FROM
        msg['To'] = email

        try:
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM, [email], msg.as_string())
            logger.info(f"OTP Email sent successfully via SMTP to {email}")
        except Exception as e:
            logger.error(f"Failed to send OTP email via SMTP to {email}: {e}")

stream_manager = manager
