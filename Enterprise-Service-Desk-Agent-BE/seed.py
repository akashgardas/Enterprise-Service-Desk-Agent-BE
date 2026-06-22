import logging
from datetime import datetime, timedelta
from app.config import settings
from app.database import get_db as get_supabase
from app.utils.security import hash_password

# Configure logging
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("seed")

def seed_data():
    logger.info("Initializing Supabase Client for seeding...")
    supabase = get_supabase()

    # Clear existing data from tables (PostgREST equivalent of drops/truncates)
    # We delete all records. To bypass API limitations, we filter by non-empty conditions.
    logger.info("Cleaning up existing data in Supabase tables...")
    try:
        supabase.table("tickets").delete().neq("id", "").execute()
        supabase.table("kb_articles").delete().neq("title", "").execute()
        supabase.table("profiles").delete().neq("email", "").execute()
        supabase.table("chat_sessions").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        supabase.table("notifications").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        logger.info("Tables cleared successfully.")
    except Exception as e:
        logger.warning(f"Error clearing some tables (they might not exist yet or are empty): {e}")

    # 1. Seed Profiles (Users)
    logger.info("Seeding user profiles...")
    default_password_hash = hash_password("Welcome@123")
    
    admin_id = "00000000-0000-4000-a000-000000000001"
    manager_id = "00000000-0000-4000-a000-000000000002"
    agent_id = "00000000-0000-4000-a000-000000000003"
    employee_id = "00000000-0000-4000-a000-000000000004"

    profiles = [
        {
            "id": admin_id,
            "name": "Super Administrator",
            "email": "admin@company.com",
            "role": "admin",
            "password_hash": default_password_hash,
            "mfa_secret": None,
            "mfa_enabled": False,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "id": manager_id,
            "name": "Service Desk Manager",
            "email": "manager@company.com",
            "role": "manager",
            "password_hash": default_password_hash,
            "mfa_secret": None,
            "mfa_enabled": False,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "id": agent_id,
            "name": "Support Agent Level 1",
            "email": "agent@company.com",
            "role": "agent",
            "password_hash": default_password_hash,
            "mfa_secret": None,
            "mfa_enabled": False,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "id": employee_id,
            "name": "Jane Employee",
            "email": "employee@company.com",
            "role": "employee",
            "password_hash": default_password_hash,
            "mfa_secret": None,
            "mfa_enabled": False,
            "failed_login_attempts": 0,
            "lockout_until": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    ]
    
    try:
        supabase.table("profiles").insert(profiles).execute()
        logger.info("Successfully seeded user profiles.")
    except Exception as e:
        logger.error(f"Failed to seed user profiles: {e}")
        return

    # 2. Seed Knowledge Base Articles
    logger.info("Seeding knowledge base articles...")
    kb_articles = [
        {
            "title": "VPN Connecting Issues & GlobalProtect Troubleshoot",
            "content": "If your VPN connection fails or disconnects repeatedly, follow these steps: "
                       "1. Disconnect and re-establish your local Wi-Fi router. "
                       "2. Open GlobalProtect settings, go to Portal, and verify portal address is vpn.company.com. "
                       "3. Clear credentials cache by clicking settings -> Sign Out. "
                       "4. Restart the GlobalProtect service from Task Manager services. "
                       "5. Verify your internet connection is active outside GlobalProtect.",
            "category": "VPN",
            "tags": ["vpn", "globalprotect", "network", "remote access"],
            "created_by": admin_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "title": "Corporate Outlook Email Setup & Sync Errors",
            "content": "To fix Outlook mail client synchronization and connection faults: "
                       "1. Ensure you have an active network connection. "
                       "2. Go to Outlook File -> Account Settings -> Reset Account settings. "
                       "3. If prompted with credentials, check your email address and enter corporate SSO password. "
                       "4. Check for disk storage limits. Archiving old folders frees up space for incoming mail syncs. "
                       "5. Restart your computer and reopen Outlook in safe mode by running 'outlook /safe'.",
            "category": "Email",
            "tags": ["email", "outlook", "exchange", "sync"],
            "created_by": admin_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "title": "Corporate Software Installation Guide & License Keys",
            "content": "For installing standard software apps (e.g. Docker, Slack, Zoom, VS Code): "
                       "1. Open the Company Portal application on your computer. "
                       "2. Search for the requested software in the app catalog. "
                       "3. Click Install. Admin credentials are pre-packaged. "
                       "4. For licenses, open a software request and enter your department billing code. "
                       "5. Restart your application after installation to apply license activations.",
            "category": "Software",
            "tags": ["software", "install", "docker", "slack", "license"],
            "created_by": admin_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "title": "External Monitor and Laptop Dock Troubleshooting",
            "content": "If external monitors connected to your laptop dock are not displaying: "
                       "1. Disconnect the USB-C/Thunderbolt cable from your laptop. "
                       "2. Unplug power source to the docking station, wait 15 seconds, and replug. "
                       "3. Check HDMI and DisplayPort cable seating on both monitor and dock ends. "
                       "4. Connect dock back to laptop. Update Intel Graphics driver via device manager. "
                       "5. Press Win+P and verify that Extend Display mode is active.",
            "category": "Hardware",
            "tags": ["monitor", "hardware", "dock", "screen", "display"],
            "created_by": admin_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "title": "Reporting Suspicious Phishing Emails",
            "content": "If you receive a suspicious email in your inbox: "
                       "1. Do NOT click any links, open attachments, or input passwords. "
                       "2. Select the email in Outlook and click the PhishAlarm button in the ribbon menu. "
                       "3. If the button is missing, forward the email as an attachment to security@company.com. "
                       "4. Delete the email from your inbox and deleted items. "
                       "5. If you already clicked a link, immediately change your corporate password.",
            "category": "Security",
            "tags": ["phishing", "security", "email", "malware"],
            "created_by": admin_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        },
        {
            "title": "Accessing Payroll Pay Slips and Leave Policies",
            "content": "To check your monthly payslips or request vacation leave: "
                       "1. Access the Workday corporate portal at hr.company.com. "
                       "2. Log in using your Single Sign-On (SSO) email credentials. "
                       "3. For payslips: Click Pay -> Pay Slips -> Select Year. "
                       "4. For leaves: Go to Time Off -> Request Time Off. Select start/end dates. "
                       "5. Submit for your direct manager's review. Managers receive notifications in Workday.",
            "category": "HR",
            "tags": ["payroll", "hr", "leave", "payslip", "workday"],
            "created_by": admin_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
    ]

    try:
        supabase.table("kb_articles").insert(kb_articles).execute()
        logger.info("Successfully seeded Knowledge Base articles.")
    except Exception as e:
        logger.error(f"Failed to seed KB articles: {e}")

    # 3. Seed Default Tickets
    logger.info("Seeding default tickets...")
    default_tickets = [
        {
            "id": f"TKT-{datetime.now().year}-00001",
            "title": "VPN GlobalProtect Connection Failure",
            "description": "Getting error 'Cannot connect to gateway' when trying to connect to GlobalProtect VPN. Checked wifi connection, it works fine.",
            "category": "VPN",
            "priority": "High",
            "status": "Open",
            "department": "Network Team",
            "assigned_to": agent_id,
            "created_by": employee_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "sla_deadline": (datetime.utcnow() + timedelta(hours=8)).isoformat(),
            "comments": [],
            "timeline": [
                {"action": "Ticket Created (Auto-categorized)", "by": "Jane Employee", "at": datetime.utcnow().isoformat()},
                {"action": "Auto-routed to Network Team", "by": "System", "at": datetime.utcnow().isoformat()}
            ],
            "stage_outputs": {}
        },
        {
            "id": f"TKT-{datetime.now().year}-00002",
            "title": "Laptop Docking Station Display Outage",
            "description": "My external monitors are black and not receiving any signal when my laptop is plugged into the dock. Tried replugging everything.",
            "category": "Hardware",
            "priority": "Medium",
            "status": "In Progress",
            "department": "Hardware Team",
            "assigned_to": agent_id,
            "created_by": employee_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "sla_deadline": (datetime.utcnow() + timedelta(hours=24)).isoformat(),
            "comments": [
                {"id": "c1", "userId": agent_id, "userName": "Support Agent Level 1", "text": "I am looking into this display driver issue.", "createdAt": datetime.utcnow().isoformat()}
            ],
            "timeline": [
                {"action": "Ticket Created", "by": "Jane Employee", "at": datetime.utcnow().isoformat()},
                {"action": "Status updated to In Progress", "by": "Support Agent Level 1", "at": datetime.utcnow().isoformat()}
            ],
            "stage_outputs": {}
        }
    ]

    try:
        supabase.table("tickets").insert(default_tickets).execute()
        logger.info("Successfully seeded default tickets.")
    except Exception as e:
        logger.error(f"Failed to seed default tickets: {e}")

    logger.info("Database seeding successfully completed!")

if __name__ == "__main__":
    seed_data()
