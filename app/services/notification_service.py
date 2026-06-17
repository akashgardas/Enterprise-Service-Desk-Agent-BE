import logging
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
    async def create_notification(db, user_id: str, title: str, message: str, notification_type: str) -> Dict[str, Any]:
        """Creates a notification record in the DB and broadcasts it via WebSocket + Emails."""
        notif = {
            "user_id": str(user_id),
            "title": title,
            "message": message,
            "type": notification_type,
            "is_read": False,
            "created_at": datetime.utcnow()
        }
        
        # Save to DB
        result = await db.notifications.insert_one(notif)
        notif["_id"] = str(result.inserted_id)
        
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
        user = await db.users.find_one({"_id": user_id})
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
            # Wrap standard SMTP client
            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                if settings.SMTP_USER and settings.SMTP_PASSWORD:
                    server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.sendmail(settings.EMAIL_FROM, [recipient_email], msg.as_string())
            logger.info(f"Email sent successfully to {recipient_email}")
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {e}")
            # Fallback to mock log
            logger.info(f"[Email Send Failure Fallback Log] Email subject: '{subject}' to {recipient_email}")
stream_manager = manager
