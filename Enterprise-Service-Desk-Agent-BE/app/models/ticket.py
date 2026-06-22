from enum import Enum

class TicketStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PENDING_USER = "pending_user"
    RESOLVED = "resolved"
    CLOSED = "closed"
    LINKED = "linked"

class TicketCategory(str, Enum):
    VPN = "vpn"
    EMAIL = "email"
    SOFTWARE = "software"
    HARDWARE = "hardware"
    SECURITY = "security"
    HR = "hr"
    OTHER = "other"

class TicketPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class RoutingTeam(str, Enum):
    NETWORK = "Network Team"
    MESSAGING = "Messaging Team"
    HARDWARE = "Hardware Team"
    APPLICATION = "Application Team"
    SUPPORT = "Support Team"

CATEGORY_TEAM_MAP = {
    TicketCategory.VPN: RoutingTeam.NETWORK,
    TicketCategory.EMAIL: RoutingTeam.MESSAGING,
    TicketCategory.HARDWARE: RoutingTeam.HARDWARE,
    TicketCategory.SOFTWARE: RoutingTeam.APPLICATION,
    TicketCategory.SECURITY: RoutingTeam.SUPPORT,
    TicketCategory.HR: RoutingTeam.SUPPORT,
    TicketCategory.OTHER: RoutingTeam.SUPPORT
}
