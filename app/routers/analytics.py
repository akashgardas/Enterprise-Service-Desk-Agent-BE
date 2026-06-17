from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from datetime import datetime
from app.database import get_db
from app.models.user import UserRole
from app.routers.auth import get_current_user, require_roles
from app.models.ticket import TicketStatus

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

@router.get("/metrics", response_model=Dict[str, Any])
async def get_dashboard_metrics(
    current_user = Depends(require_roles([UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Calculates KPI metrics for the Service Desk."""
    
    # 1. Ticket status counts
    open_count = await db.tickets.count_documents({"status": {"$in": [TicketStatus.OPEN.value, TicketStatus.ASSIGNED.value, TicketStatus.IN_PROGRESS.value, TicketStatus.PENDING_USER.value]}})
    closed_count = await db.tickets.count_documents({"status": TicketStatus.CLOSED.value})
    resolved_count = await db.tickets.count_documents({"status": TicketStatus.RESOLVED.value})
    linked_count = await db.tickets.count_documents({"status": TicketStatus.LINKED.value})
    
    total_tickets = open_count + closed_count + resolved_count + linked_count

    # 2. Average Resolution Time (in seconds)
    avg_res_pipeline = [
        {"$match": {"resolution_time": {"$ne": None}}},
        {"$group": {"_id": None, "avg_time": {"$avg": "$resolution_time"}}}
    ]
    avg_res_cursor = db.tickets.aggregate(avg_res_pipeline)
    avg_res_result = await avg_res_cursor.to_list(length=1)
    avg_resolution_seconds = float(avg_res_result[0]["avg_time"]) if avg_res_result else 0.0

    # 3. SLA Compliance
    # Compares resolved tickets where resolution was completed before the sla_deadline
    # For resolved tickets, check if updated_at (which is resolution timestamp) <= sla_deadline
    # For open tickets that are already past sla_deadline, they are counted as breaches.
    total_sla_evaluated = await db.tickets.count_documents({
        "status": {"$in": [TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value]}
    })
    
    sla_compliant_count = 0
    if total_sla_evaluated > 0:
        # We check tickets where updated_at <= sla_deadline
        # Since we use aggregation, we can run a project expression comparison
        sla_pipeline = [
            {
                "$match": {
                    "status": {"$in": [TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value]},
                    "sla_deadline": {"$ne": None}
                }
            },
            {
                "$project": {
                    "compliant": {
                        "$cond": [{"$lte": ["$updated_at", "$sla_deadline"]}, 1, 0]
                    }
                }
            },
            {
                "$group": {
                    "_id": None,
                    "compliant_total": {"$sum": "$compliant"}
                }
            }
        ]
        sla_cursor = db.tickets.aggregate(sla_pipeline)
        sla_result = await sla_cursor.to_list(length=1)
        if sla_result:
            sla_compliant_count = sla_result[0]["compliant_total"]
            
    sla_compliance_rate = (sla_compliant_count / total_sla_evaluated * 100) if total_sla_evaluated > 0 else 100.0

    # 4. Agent Performance List
    agent_pipeline = [
        {"$match": {"assigned_to": {"$ne": None}}},
        {
            "$group": {
                "_id": "$assigned_to",
                "assigned_count": {"$sum": 1},
                "resolved_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$status", TicketStatus.RESOLVED.value]}, 1, 0]
                    }
                },
                "avg_resolution_time": {"$avg": "$resolution_time"}
            }
        }
    ]
    agent_cursor = db.tickets.aggregate(agent_pipeline)
    agent_metrics = await agent_cursor.to_list(length=100)
    
    agent_performance = []
    for am in agent_metrics:
        agent_id = am["_id"]
        # Lookup user details
        agent_user = await db.users.find_one({"_id": ObjectId(agent_id)}, {"name": 1, "email": 1})
        if agent_user:
            agent_performance.append({
                "agent_id": str(agent_id),
                "name": agent_user.get("name"),
                "email": agent_user.get("email"),
                "assigned_count": am["assigned_count"],
                "resolved_count": am["resolved_count"],
                "avg_resolution_time": float(am["avg_resolution_time"]) if am["avg_resolution_time"] is not None else 0.0
            })

    # 5. Tickets Category Breakdowns
    category_pipeline = [
        {"$group": {"_id": "$category", "count": {"$sum": 1}}}
    ]
    cat_cursor = db.tickets.aggregate(category_pipeline)
    cat_results = await cat_cursor.to_list(length=20)
    category_breakdown = {cr["_id"]: cr["count"] for cr in cat_results}

    return {
        "summary": {
            "total_tickets": total_tickets,
            "open_tickets": open_count,
            "closed_tickets": closed_count,
            "resolved_tickets": resolved_count,
            "linked_tickets": linked_count,
            "avg_resolution_time_seconds": avg_resolution_seconds,
            "sla_compliance_rate_percent": sla_compliance_rate
        },
        "agent_performance": agent_performance,
        "category_breakdown": category_breakdown
    }
