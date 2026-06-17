import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from bson import ObjectId
from app.models.ticket import TicketStatus, TicketCategory, TicketPriority, CATEGORY_TEAM_MAP
from app.services.ai_service import AIService
from app.services.dedup_service import DedupService
from app.services.remediation_service import RemediationService
from app.services.kb_service import KbService
from app.services.notification_service import NotificationService

logger = logging.getLogger("enterprise_support.orchestrator")

class OrchestratorService:
    @staticmethod
    def sanitize_input(text: str) -> str:
        """Step 1: Sanitizes input fields to clean code injections and HTML tags."""
        if not text:
            return ""
        # Strip HTML tags
        clean_text = re.sub(r"<[^>]*>", "", text)
        # Prevent simple SQL characters or excessive scripting injection attempts
        clean_text = clean_text.replace("'", "''").strip()
        return clean_text

    @classmethod
    async def generate_ticket_number(cls, db, year: int) -> str:
        """Generates the sequential ticket number formatted as TKT-YYYY-XXXXX."""
        counter_id = f"ticket_seq_{year}"
        
        counter = await db.system_counters.find_one_and_update(
            {"_id": counter_id},
            {"$inc": {"sequence": 1}},
            upsert=True,
            return_document=True
        )
        
        seq_num = counter.get("sequence", 1)
        return f"TKT-{year}-{seq_num:05d}"

    @classmethod
    async def process_new_ticket(
        cls,
        db,
        user_id: str,
        user_email: str,
        title: str,
        description: str,
        category_input: Optional[TicketCategory] = None,
        priority_input: Optional[TicketPriority] = None,
        attachments: list = None,
        allow_ai_reset: bool = False
    ) -> Dict[str, Any]:
        """Runs the 7-step agentic support ticket pipeline."""
        logger.info(f"Starting orchestrator pipeline for new ticket submission by {user_email}")

        # --- Step 1: Sanitization & Parsing ---
        clean_title = cls.sanitize_input(title)
        clean_description = cls.sanitize_input(description)

        # --- Step 2: Deduplication Checking ---
        dedup_result = await DedupService.check_duplicate(db, clean_title, clean_description)
        is_duplicate = dedup_result.get("is_duplicate", False)
        master_id = dedup_result.get("master_id")
        similarity = dedup_result.get("similarity", 0.0)

        # --- Step 3: NLP Classification & Routing ---
        # If user provided a valid category, use it, else ask AI
        if category_input and category_input != TicketCategory.OTHER:
            category = category_input
            ai_classification = await AIService.classify_ticket(clean_title, clean_description)
            priority = priority_input or ai_classification.get("priority", TicketPriority.MEDIUM)
            explanation = f"User category selected. AI priority: {priority}."
            confidence = 1.0
        else:
            ai_classification = await AIService.classify_ticket(clean_title, clean_description)
            category = ai_classification.get("category", TicketCategory.OTHER)
            priority = priority_input or ai_classification.get("priority", TicketPriority.MEDIUM)
            explanation = ai_classification.get("explanation", "")
            confidence = ai_classification.get("confidence", 0.7)

        # Assign routing team
        assigned_team = CATEGORY_TEAM_MAP.get(category, "Support Team").value

        # --- Step 4: Risk Assessment ---
        risk_result = await AIService.assess_risk(clean_title, clean_description, category.value, priority.value)
        risk_score = risk_result.get("risk_score", 0.2)
        risk_level = risk_result.get("risk_level", "low")
        escalate = risk_result.get("escalate", False)
        risk_explanation = risk_result.get("explanation", "")

        # Adjust priority if risk assessment escalates it
        if escalate and priority != TicketPriority.CRITICAL:
            logger.info("Risk assessment escalated ticket priority to High.")
            priority = TicketPriority.HIGH

        # Calculate SLA deadline based on priority
        sla_hours = 24
        if priority == TicketPriority.CRITICAL:
            sla_hours = 2  # Critical SLA: 2 hours
        elif priority == TicketPriority.HIGH:
            sla_hours = 8  # High SLA: 8 hours
        elif priority == TicketPriority.MEDIUM:
            sla_hours = 24  # Medium SLA: 24 hours
        elif priority == TicketPriority.LOW:
            sla_hours = 72  # Low SLA: 72 hours
        
        sla_deadline = datetime.utcnow() + timedelta(hours=sla_hours)

        # Initialize responses and status variables
        status = TicketStatus.OPEN
        employee_response = None
        admin_response = f"NLP Classification: {category.value.upper()} | Priority: {priority.value.upper()}.\nRisk: {risk_level.upper()} (Score: {risk_score}).\n" + risk_explanation
        resolution_steps = []
        confidence_score = confidence

        # Handle duplicate linking immediately
        if is_duplicate and master_id:
            logger.info(f"Ticket flagged as duplicate of {master_id}. Setting status to LINKED.")
            status = TicketStatus.LINKED
            employee_response = f"This issue is a duplicate of a previously reported open ticket ({master_id}). We have linked your ticket to the master incident and will notify you when resolved."
            admin_response += f"\nLinked as duplicate of {master_id}. Cosine similarity: {similarity:.2%}"
            
            # Update master ticket records (increment linked count/affected list)
            await db.tickets.update_one(
                {"_id": ObjectId(master_id)},
                {"$addToSet": {"affected_users": user_email}}
            )

        # --- Step 5: Auto-Remediation Attempt ---
        elif allow_ai_reset and RemediationService.is_password_reset_request(clean_title, clean_description):
            logger.info("Ticket involves password reset and allowAiPasswordReset is enabled. Running remediation...")
            remediation_result = await RemediationService.run_remediation(user_email, db)
            
            if remediation_result.get("success"):
                status = TicketStatus.RESOLVED
                temp_pwd = remediation_result.get("temporary_password")
                employee_response = (
                    f"Hello. An automated password reset has been completed for your account. "
                    f"Your temporary password is: **{temp_pwd}**\n\n"
                    f"Please log in and change this password immediately. For your security, this temporary password "
                    f"complies with our corporate password strength guidelines."
                )
                admin_response += f"\nAuto-remediation successful. Temporary password generated."
                resolution_steps = ["Verify identity", "Trigger automated API reset endpoint", "Transmit secure temp credentials"]
                confidence_score = 1.0
            else:
                admin_response += f"\nAuto-remediation failed: {remediation_result.get('message')}"
                logger.warning(f"Remediation failed: {remediation_result.get('message')}. Continuing to RAG.")

        # --- Step 6: RAG Resolution Retrieval & Generation ---
        if status == TicketStatus.OPEN:
            # Look up KB articles
            kb_articles = await KbService.search_articles(db, f"{clean_title} {clean_description}", category, limit=2)
            
            # Run AI generator
            rag_result = await AIService.generate_rag_resolution(clean_title, clean_description, category.value, kb_articles)
            
            employee_response = rag_result.get("employee_response")
            admin_response += "\n" + rag_result.get("admin_response", "")
            resolution_steps = rag_result.get("resolution_steps", [])
            confidence_score = min(confidence_score, rag_result.get("confidence_score", 0.5))

            # Auto-resolve if confidence is very high, risk is low, and no escalation flagged
            if rag_result.get("confidence_score", 0.0) >= 0.85 and risk_level == "low" and not escalate:
                status = TicketStatus.RESOLVED
                admin_response += "\nTicket auto-resolved due to high KB similarity and low risk."
            else:
                # Route to queue and wait for agent assignment
                status = TicketStatus.OPEN

        # --- Step 7: Explainability & Saving ---
        current_year = datetime.now().year
        ticket_number = await cls.generate_ticket_number(db, current_year)

        ticket_doc = {
            "ticket_number": ticket_number,
            "title": clean_title,
            "description": clean_description,
            "category": category.value,
            "priority": priority.value,
            "status": status.value,
            "created_by": str(user_id),
            "assigned_to": None,
            "assigned_team": assigned_team,
            "attachments": attachments or [],
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "resolution_time": None,
            "sla_deadline": sla_deadline,
            "master_incident_id": master_id,
            "risk_score": float(risk_score),
            "confidence_score": float(confidence_score),
            "ai_explanation": explanation,
            "employee_response": employee_response,
            "admin_response": admin_response,
            "resolution_steps": resolution_steps,
            "affected_users": [user_email]
        }

        # Save to MongoDB
        insert_result = await db.tickets.insert_one(ticket_doc)
        ticket_doc["_id"] = str(insert_result.inserted_id)

        logger.info(f"Saved ticket {ticket_number} (Status: {status.value}) successfully.")

        # Trigger Notifications
        await NotificationService.create_notification(
            db,
            user_id,
            title=f"Ticket {ticket_number} Created",
            message=f"Your ticket '{clean_title}' has been logged. Status: {status.value.upper()}.",
            notification_type="ticket_created"
        )

        return ticket_doc
