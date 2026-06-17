import asyncio
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from app.utils.security import hash_password
from app.models.user import UserRole
from app.models.ticket import TicketCategory

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("seed")

async def seed_data():
    logger.info(f"Connecting to MongoDB at {settings.MONGO_URI}...")
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.DATABASE_NAME]

    # Clean existing indexes and prepare clean tables
    await db.users.drop()
    await db.kb_articles.drop()
    await db.tickets.drop()
    await db.chat_sessions.drop()
    await db.notifications.drop()
    await db.system_counters.drop()

    # Create Indexes
    await db.users.create_index("email", unique=True)
    await db.kb_articles.create_index("title")

    # 1. Seed Users
    logger.info("Seeding user accounts...")
    default_password_hash = hash_password("Welcome@123")
    
    users = [
        {
            "name": "Super Administrator",
            "email": "admin@company.com",
            "role": UserRole.ADMIN.value,
            "password_hash": default_password_hash,
            "mfa_secret": None,
            "mfa_enabled": False,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "name": "Service Desk Manager",
            "email": "manager@company.com",
            "role": UserRole.MANAGER.value,
            "password_hash": default_password_hash,
            "mfa_secret": None,
            "mfa_enabled": False,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "name": "Support Agent Level 1",
            "email": "agent@company.com",
            "role": UserRole.AGENT.value,
            "password_hash": default_password_hash,
            "mfa_secret": None,
            "mfa_enabled": False,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "name": "Jane Employee",
            "email": "employee@company.com",
            "role": UserRole.EMPLOYEE.value,
            "password_hash": default_password_hash,
            "mfa_secret": None,
            "mfa_enabled": False,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    ]
    
    # Store users and log IDs
    users_insert = await db.users.insert_many(users)
    logger.info(f"Successfully seeded {len(users)} users.")

    # 2. Seed Knowledge Base Articles
    logger.info("Seeding knowledge base articles...")
    
    admin_id = str(users_insert.inserted_ids[0])
    
    kb_articles = [
        {
            "title": "VPN Connecting Issues & GlobalProtect Troubleshoot",
            "content": "If your VPN connection fails or disconnects repeatedly, follow these steps: "
                       "1. Disconnect and re-establish your local Wi-Fi router. "
                       "2. Open GlobalProtect settings, go to Portal, and verify portal address is vpn.company.com. "
                       "3. Clear credentials cache by clicking settings -> Sign Out. "
                       "4. Restart the GlobalProtect service from Task Manager services. "
                       "5. Verify your internet connection is active outside GlobalProtect.",
            "category": TicketCategory.VPN.value,
            "tags": ["vpn", "globalprotect", "network", "remote access"],
            "created_by": admin_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "title": "Corporate Outlook Email Setup & Sync Errors",
            "content": "To fix Outlook mail client synchronization and connection faults: "
                       "1. Ensure you have an active network connection. "
                       "2. Go to Outlook File -> Account Settings -> Reset Account settings. "
                       "3. If prompted with credentials, check your email address and enter corporate SSO password. "
                       "4. Check for disk storage limits. Archiving old folders frees up space for incoming mail syncs. "
                       "5. Restart your computer and reopen Outlook in safe mode by running 'outlook /safe'.",
            "category": TicketCategory.EMAIL.value,
            "tags": ["email", "outlook", "exchange", "sync"],
            "created_by": admin_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "title": "Corporate Software Installation Guide & License Keys",
            "content": "For installing standard software apps (e.g. Docker, Slack, Zoom, VS Code): "
                       "1. Open the Company Portal application on your computer. "
                       "2. Search for the requested software in the app catalog. "
                       "3. Click Install. Admin credentials are pre-packaged. "
                       "4. For licenses, open a software request and enter your department billing code. "
                       "5. Restart your application after installation to apply license activations.",
            "category": TicketCategory.SOFTWARE.value,
            "tags": ["software", "install", "docker", "slack", "license"],
            "created_by": admin_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "title": "External Monitor and Laptop Dock Troubleshooting",
            "content": "If external monitors connected to your laptop dock are not displaying: "
                       "1. Disconnect the USB-C/Thunderbolt cable from your laptop. "
                       "2. Unplug power source to the docking station, wait 15 seconds, and replug. "
                       "3. Check HDMI and DisplayPort cable seating on both monitor and dock ends. "
                       "4. Connect dock back to laptop. Update Intel Graphics driver via device manager. "
                       "5. Press Win+P and verify that Extend Display mode is active.",
            "category": TicketCategory.HARDWARE.value,
            "tags": ["monitor", "hardware", "dock", "screen", "display"],
            "created_by": admin_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "title": "Reporting Suspicious Phishing Emails",
            "content": "If you receive a suspicious email in your inbox: "
                       "1. Do NOT click any links, open attachments, or input passwords. "
                       "2. Select the email in Outlook and click the PhishAlarm button in the ribbon menu. "
                       "3. If the button is missing, forward the email as an attachment to security@company.com. "
                       "4. Delete the email from your inbox and deleted items. "
                       "5. If you already clicked a link, immediately change your corporate password.",
            "category": TicketCategory.SECURITY.value,
            "tags": ["phishing", "security", "email", "malware"],
            "created_by": admin_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "title": "Accessing Payroll Pay Slips and Leave Policies",
            "content": "To check your monthly payslips or request vacation leave: "
                       "1. Access the Workday corporate portal at hr.company.com. "
                       "2. Log in using your Single Sign-On (SSO) email credentials. "
                       "3. For payslips: Click Pay -> Pay Slips -> Select Year. "
                       "4. For leaves: Go to Time Off -> Request Time Off. Select start/end dates. "
                       "5. Submit for your direct manager's review. Managers receive notifications in Workday.",
            "category": TicketCategory.HR.value,
            "tags": ["payroll", "hr", "leave", "payslip", "workday"],
            "created_by": admin_id,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    ]

    await db.kb_articles.insert_many(kb_articles)
    logger.info(f"Successfully seeded {len(kb_articles)} Knowledge Base articles.")
    
    # Initialize sequential counters
    current_year = datetime.now().year
    await db.system_counters.insert_one({"_id": f"ticket_seq_{current_year}", "sequence": 0})
    logger.info(f"Counter initialized for ticket sequence in {current_year}.")

    client.close()
    logger.info("Database seeding successfully completed!")

if __name__ == "__main__":
    asyncio.run(seed_data())
