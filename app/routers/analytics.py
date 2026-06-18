from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from datetime import datetime
from bson import ObjectId
from app.database import get_db
from app.models.user import UserRole
from app.routers.auth import get_current_user, require_roles
from app.models.ticket import TicketStatus, TicketPriority

router = APIRouter(prefix="/analytics", tags=["Analytics"])

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

@router.get("/metrics", response_model=Dict[str, Any])
async def get_dashboard_metrics(
    current_user = Depends(require_roles([UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Calculates legacy KPI metrics for backward compatibility."""
    open_count = await db.tickets.count_documents({"status": {"$in": [TicketStatus.OPEN.value, TicketStatus.ASSIGNED.value, TicketStatus.IN_PROGRESS.value, TicketStatus.PENDING_USER.value]}})
    closed_count = await db.tickets.count_documents({"status": TicketStatus.CLOSED.value})
    resolved_count = await db.tickets.count_documents({"status": TicketStatus.RESOLVED.value})
    linked_count = await db.tickets.count_documents({"status": TicketStatus.LINKED.value})
    
    total_tickets = open_count + closed_count + resolved_count + linked_count

    avg_res_pipeline = [
        {"$match": {"resolution_time": {"$ne": None}}},
        {"$group": {"_id": None, "avg_time": {"$avg": "$resolution_time"}}}
    ]
    avg_res_cursor = db.tickets.aggregate(avg_res_pipeline)
    avg_res_result = await avg_res_cursor.to_list(length=1)
    avg_resolution_seconds = float(avg_res_result[0]["avg_time"]) if avg_res_result else 0.0

    total_sla_evaluated = await db.tickets.count_documents({
        "status": {"$in": [TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value]}
    })
    
    sla_compliant_count = 0
    if total_sla_evaluated > 0:
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

@router.get("/dashboard", response_model=Any)
async def get_dashboard_data(
    current_user = Depends(require_roles([UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Retrieves analytics summary details for frontend dashboard widgets."""
    tickets_by_month = {}
    tickets_by_category = {}
    tickets_by_priority = {}
    
    # Initialize month counts
    for m in MONTH_NAMES:
        tickets_by_month[m] = 0
        
    cursor = db.tickets.find({})
    total_sla_evaluated = 0
    sla_compliant_count = 0
    
    async for ticket in cursor:
        # 1. Month classification
        dt = ticket.get("created_at")
        if isinstance(dt, datetime):
            m_name = MONTH_NAMES[dt.month - 1]
            tickets_by_month[m_name] = tickets_by_month.get(m_name, 0) + 1
            
        # 2. Category classification
        cat = ticket.get("category", "other")
        tickets_by_category[cat] = tickets_by_category.get(cat, 0) + 1
        
        # 3. Priority classification
        pri = ticket.get("priority", "medium")
        tickets_by_priority[pri] = tickets_by_priority.get(pri, 0) + 1
        
        # 4. SLA calculation
        status_val = ticket.get("status")
        if status_val in [TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value]:
            total_sla_evaluated += 1
            updated_dt = ticket.get("updated_at")
            sla_dt = ticket.get("sla_deadline")
            if updated_dt and sla_dt and updated_dt <= sla_dt:
                sla_compliant_count += 1

    sla_percentage = (sla_compliant_count / total_sla_evaluated * 100) if total_sla_evaluated > 0 else 100.0
    
    return {
        "ticketsByMonth": [{"month": m, "count": count} for m, count in tickets_by_month.items()],
        "ticketsByCategory": [{"category": c, "count": count} for c, count in tickets_by_category.items()],
        "ticketsByPriority": [{"priority": p, "count": count} for p, count in tickets_by_priority.items()],
        "slaCompliance": {
            "percentage": round(sla_percentage, 1),
            "trend": "up"
        }
    }

@router.get("/volume", response_model=List[Any])
async def get_ticket_volume(
    current_user = Depends(require_roles([UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Retrieves created, resolved, and closed counts grouped monthly."""
    volume_by_month = {}
    for m in MONTH_NAMES:
        volume_by_month[m] = {"month": m, "created": 0, "resolved": 0, "closed": 0}
        
    cursor = db.tickets.find({})
    async for ticket in cursor:
        dt = ticket.get("created_at")
        if not isinstance(dt, datetime):
            continue
        m_name = MONTH_NAMES[dt.month - 1]
        volume_by_month[m_name]["created"] += 1
        
        status_val = ticket.get("status")
        if status_val == TicketStatus.RESOLVED.value:
            volume_by_month[m_name]["resolved"] += 1
        elif status_val == TicketStatus.CLOSED.value:
            volume_by_month[m_name]["closed"] += 1
            
    return [volume_by_month[m] for m in MONTH_NAMES]

@router.get("/categories", response_model=List[Any])
async def get_categories_distribution(
    current_user = Depends(require_roles([UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Retrieves tickets count and percentage across categories."""
    category_counts = {}
    total_tickets = 0
    
    cursor = db.tickets.find({})
    async for ticket in cursor:
        cat = ticket.get("category", "other")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        total_tickets += 1
        
    results = []
    for cat, count in category_counts.items():
        pct = (count / total_tickets * 100) if total_tickets > 0 else 0.0
        results.append({
            "category": cat,
            "count": count,
            "percentage": round(pct, 1)
        })
    return results

@router.get("/performance", response_model=List[Any])
async def get_agents_performance(
    current_user = Depends(require_roles([UserRole.MANAGER, UserRole.ADMIN])),
    db = Depends(get_db)
):
    """Retrieves agent scorecard data (resolved count, average duration, rating)."""
    agent_pipeline = [
        {"$match": {"assigned_to": {"$ne": None}}},
        {
            "$group": {
                "_id": "$assigned_to",
                "assigned_count": {"$sum": 1},
                "resolved_count": {
                    "$sum": {
                        "$cond": [{"$in": ["$status", [TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value]]}, 1, 0]
                    }
                },
                "avg_resolution_time": {"$avg": "$resolution_time"}
            }
        }
    ]
    agent_cursor = db.tickets.aggregate(agent_pipeline)
    agent_metrics = await agent_cursor.to_list(length=100)
    
    performance = []
    for am in agent_metrics:
        agent_id = am["_id"]
        agent_user = await db.users.find_one({"_id": ObjectId(agent_id)}, {"name": 1, "email": 1})
        if agent_user:
            performance.append({
                "agentId": str(agent_id),
                "name": agent_user.get("name"),
                "email": agent_user.get("email"),
                "resolvedTickets": am["resolved_count"],
                "avgResolutionTime": round(float(am["avg_resolution_time"]), 1) if am["avg_resolution_time"] is not None else 0.0,
                "rating": 4.8
            })
    return performance
