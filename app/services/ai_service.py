import logging
import json
import re
from typing import Tuple
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from app.config import settings
from app.models.ticket import TicketCategory, TicketPriority

logger = logging.getLogger("enterprise_support.ai_service")

# Try to configure Gemini
is_gemini_active = False
if settings.GEMINI_API_KEY:
    try:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        is_gemini_active = True
        logger.info("Gemini AI API configured successfully.")
    except Exception as e:
        logger.warning(f"Failed to configure Gemini API: {e}. Falling back to rule-based engine.")

class AIService:
    @staticmethod
    def _call_gemini(prompt: str, json_mode: bool = True) -> Optional[str]:
        if not is_gemini_active:
            return None
        try:
            # Using gemini-1.5-flash or gemini-2.5-flash
            model = genai.GenerativeModel("gemini-1.5-flash")
            generation_config = {}
            if json_mode:
                generation_config = {"response_mime_type": "application/json"}
            
            response = model.generate_content(prompt, generation_config=generation_config)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini API invocation failed: {e}")
            return None

    @classmethod
    async def classify_ticket(cls, title: str, description: str) -> Dict[str, Any]:
        """Classifies a ticket's Category and Priority."""
        query = f"Title: {title}\nDescription: {description}"
        
        prompt = f"""
        You are an IT Support Analyst agent. Analyze the following support request and determine its Category and Priority.
        
        Categories: "vpn", "email", "software", "hardware", "security", "hr", "other"
        Priorities: "critical", "high", "medium", "low"
        
        Rules for Priority:
        - "critical": Entire system down, critical security breach, or ransomware.
        - "high": Department affected, major feature blocked, or unauthorized access attempts.
        - "medium": Default for individual issues, laptop/software malfunctions that block single users.
        - "low": Information requests, questions, non-blocking suggestions.
        
        Respond ONLY with a JSON object in this format:
        {{
            "category": "vpn | email | software | hardware | security | hr | other",
            "priority": "critical | high | medium | low",
            "explanation": "Brief explanation of classification decisions",
            "confidence": 0.0 to 1.0
        }}
        
        Ticket details:
        {query}
        """

        gemini_response = cls._call_gemini(prompt, json_mode=True)
        if gemini_response:
            try:
                result = json.loads(gemini_response)
                # Ensure fields exist
                return {
                    "category": TicketCategory(result.get("category", "other").lower()),
                    "priority": TicketPriority(result.get("priority", "medium").lower()),
                    "explanation": result.get("explanation", "Classified via Gemini AI."),
                    "confidence": float(result.get("confidence", 0.85))
                }
            except Exception as e:
                logger.warning(f"Error parsing Gemini classification JSON: {e}")

        # Fallback keyword-based classification
        return cls._fallback_classify(title, description)

    @classmethod
    def _fallback_classify(cls, title: str, description: str) -> Dict[str, Any]:
        text = f"{title} {description}".lower()
        
        # Categorization keywords
        category = TicketCategory.OTHER
        if any(kw in text for kw in ["vpn", "anyconnect", "forticlient", "network", "internet", "wifi", "wi-fi", "connection", "disconnected"]):
            category = TicketCategory.VPN if "vpn" in text else TicketCategory.VPN # Use VPN/Network
            # If network terms are present but not vpn, default to software/other unless it matches network specifically
            if "vpn" in text:
                category = TicketCategory.VPN
            elif any(kw in text for kw in ["wifi", "wi-fi", "internet", "connectivity"]):
                category = TicketCategory.VPN # Map network to VPN category as defined in database requirements
        if category == TicketCategory.OTHER and any(kw in text for kw in ["email", "outlook", "mail", "inbox", "exchange", "smtp"]):
            category = TicketCategory.EMAIL
        if category == TicketCategory.OTHER and any(kw in text for kw in ["laptop", "hardware", "keyboard", "mouse", "monitor", "charger", "dock"]):
            category = TicketCategory.HARDWARE
        if category == TicketCategory.OTHER and any(kw in text for kw in ["software", "app", "install", "uninstall", "crash", "freeze", "windows", "office"]):
            category = TicketCategory.SOFTWARE
        if category == TicketCategory.OTHER and any(kw in text for kw in ["security", "virus", "malware", "phishing", "hacked", "breach"]):
            category = TicketCategory.SECURITY
        if category == TicketCategory.OTHER and any(kw in text for kw in ["hr", "leave", "payroll", "payslip", "policy"]):
            category = TicketCategory.HR

        # Priority rules
        priority = TicketPriority.MEDIUM
        if any(kw in text for kw in ["system down", "outage", "entire system", "production down", "global issue", "ransomware", "hacked"]):
            priority = TicketPriority.CRITICAL
        elif any(kw in text for kw in ["department", "team blocked", "major"]):
            priority = TicketPriority.HIGH
        elif any(kw in text for kw in ["how do i", "how to", "question", "request info", "information request"]):
            priority = TicketPriority.LOW

        return {
            "category": category,
            "priority": priority,
            "explanation": "Classified via keyword-matching fallback engine.",
            "confidence": 0.60
        }

    @classmethod
    async def assess_risk(cls, title: str, description: str, category: str, priority: str) -> Dict[str, Any]:
        """Assess risk levels, business impacts, and decides on escalation flags."""
        prompt = f"""
        Perform a risk assessment on the following IT incident:
        Title: {title}
        Description: {description}
        Category: {category}
        Priority: {priority}

        Respond ONLY with a JSON object in this format:
        {{
            "risk_score": 0.0 to 1.0 (float representing security/business risk),
            "risk_level": "low | medium | high",
            "escalate": true | false,
            "explanation": "Brief explanation of risk assessment"
        }}
        """

        gemini_response = cls._call_gemini(prompt, json_mode=True)
        if gemini_response:
            try:
                result = json.loads(gemini_response)
                return {
                    "risk_score": float(result.get("risk_score", 0.3)),
                    "risk_level": result.get("risk_level", "medium").lower(),
                    "escalate": bool(result.get("escalate", False)),
                    "explanation": result.get("explanation", "Risk evaluated via Gemini AI.")
                }
            except Exception as e:
                logger.warning(f"Error parsing Gemini risk JSON: {e}")

        # Fallback risk assessment
        text = f"{title} {description}".lower()
        risk_score = 0.2
        risk_level = "low"
        escalate = False

        if priority == TicketPriority.CRITICAL:
            risk_score = 0.9
            risk_level = "high"
            escalate = True
        elif priority == TicketPriority.HIGH:
            risk_score = 0.65
            risk_level = "medium"
            escalate = True if "security" in text or "unauthorized" in text else False
        elif priority == TicketPriority.MEDIUM:
            risk_score = 0.4
            risk_level = "medium"

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "escalate": escalate,
            "explanation": "Risk assessed using static heuristic fallback rules."
        }

    @classmethod
    async def generate_rag_resolution(cls, title: str, description: str, category: str, kb_articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generates RAG-based solutions using retrieved KB articles as context."""
        if not kb_articles:
            return {
                "employee_response": f"We couldn't find a matching troubleshooting guide in our knowledge base for '{title}'. A ticket has been created and assigned to our Level-2 support team. They will look into this and get back to you shortly.",
                "admin_response": "No matching knowledge base articles found. Manual intervention required.",
                "resolution_steps": ["Review log logs", "Assign to Level-2 support representative"],
                "confidence_score": 0.3
            }

        kb_context = "\n\n".join([
            f"Article Title: {art['title']}\nCategory: {art['category']}\nContent: {art['content']}"
            for art in kb_articles
        ])

        prompt = f"""
        You are an IT Support Analyst agent. Solve this incident using the Knowledge Base (KB) Articles provided below.

        Incident:
        Title: {title}
        Description: {description}
        Category: {category}

        Available KB Articles:
        {kb_context}

        Formulate:
        1. An employee_response: A clear, polite, and reassuring response to the user with step-by-step instructions.
        2. An admin_response: A technical summary for the support agent handling the ticket.
        3. A list of resolution_steps.
        4. A confidence_score (between 0.0 and 1.0) indicating how well the articles solved the user's issue.

        Respond ONLY with a JSON object in this format:
        {{
            "employee_response": "Polite response to employee...",
            "admin_response": "Technical summary for admin...",
            "resolution_steps": ["Step 1", "Step 2", ...],
            "confidence_score": 0.95
        }}
        """

        gemini_response = cls._call_gemini(prompt, json_mode=True)
        if gemini_response:
            try:
                result = json.loads(gemini_response)
                return {
                    "employee_response": result.get("employee_response"),
                    "admin_response": result.get("admin_response"),
                    "resolution_steps": result.get("resolution_steps", []),
                    "confidence_score": float(result.get("confidence_score", 0.8))
                }
            except Exception as e:
                logger.warning(f"Error parsing Gemini RAG JSON: {e}")

        # Fallback RAG response generator using first matched article
        best_art = kb_articles[0]
        steps = [step.strip() for step in best_art["content"].split(".") if step.strip()]
        return {
            "employee_response": f"Based on our Knowledge Base article '{best_art['title']}', here is how you can resolve this:\n\n{best_art['content']}\n\nLet us know if this helps!",
            "admin_response": f"Resolved automatically using KB article: '{best_art['title']}'.",
            "resolution_steps": steps,
            "confidence_score": 0.7
        }

    @classmethod
    async def generate_chat_response(cls, messages: List[Dict[str, Any]], kb_articles: List[Dict[str, Any]], session_id: str) -> Dict[str, Any]:
        """Generates dynamic chat agent replies. Decides if ticket escalation is suggested."""
        chat_history = ""
        for msg in messages:
            chat_history += f"{msg['sender'].capitalize()}: {msg['text']}\n"

        kb_context = ""
        if kb_articles:
            kb_context = "Relevant KB Articles:\n" + "\n".join([
                f"- {art['title']}: {art['content']}" for art in kb_articles
            ])

        prompt = f"""
        You are an intelligent Enterprise IT Support Chatbot. Have a natural conversation with the employee.
        Use the provided KB Articles to troubleshoot. If the issue is resolved, conclude the chat politely.
        If the issue is NOT resolved and the user seems stuck, frustrated, or explicitly asks for a ticket, offer/suggest to create a ticket.
        
        {kb_context}

        Conversation History:
        {chat_history}

        Provide your response in a JSON structure:
        {{
            "text": "Your message reply to the user...",
            "suggest_ticket_creation": true | false,
            "ticket_template": {{
                "title": "Generated short ticket title",
                "description": "Generated ticket description summarizing the issue from conversation details",
                "category": "vpn | email | software | hardware | security | hr | other",
                "priority": "critical | high | medium | low"
            }} (Include ONLY if suggest_ticket_creation is true)
        }}
        """

        gemini_response = cls._call_gemini(prompt, json_mode=True)
        if gemini_response:
            try:
                result = json.loads(gemini_response)
                suggested_action = None
                if result.get("suggest_ticket_creation") is True:
                    template = result.get("ticket_template", {})
                    suggested_action = {
                        "action": "create_ticket",
                        "payload": {
                            "title": template.get("title", "IT Support Ticket"),
                            "description": template.get("description", "Created from chat conversation."),
                            "category": template.get("category", "other"),
                            "priority": template.get("priority", "medium")
                        }
                    }
                return {
                    "text": result.get("text", "I'm here to help you. Could you explain the issue?"),
                    "suggested_action": suggested_action,
                    "chat_session_id": session_id
                }
            except Exception as e:
                logger.warning(f"Error parsing Gemini Chat JSON: {e}")

        # Fallback chat response generator
        last_user_msg = messages[-1]["text"] if messages else ""
        lower_msg = last_user_msg.lower()
        suggested_action = None
        
        # Determine if we should offer ticket creation
        suggest_ticket = False
        if any(kw in lower_msg for kw in ["ticket", "create ticket", "raise ticket", "escalate", "help me", "not working", "fail"]):
            suggest_ticket = True

        if kb_articles:
            best_art = kb_articles[0]
            text = f"I found this article in our Knowledge Base: '{best_art['title']}'. Here is the solution:\n\n{best_art['content']}\n\nIf this doesn't help, please let me know, and I can create a ticket for you."
        else:
            text = "I'm sorry, I couldn't find a direct solution in our knowledge base. Would you like me to create a support ticket to escalate this to a specialist?"

        if suggest_ticket:
            suggested_action = {
                "action": "create_ticket",
                "payload": {
                    "title": last_user_msg[:60],
                    "description": f"User reported issue in chat: {last_user_msg}",
                    "category": "other",
                    "priority": "medium"
                }
            }

        return {
            "text": text,
            "suggested_action": suggested_action,
            "chat_session_id": session_id
        }
    @classmethod
    async def check_duplicate_with_gemini(
        cls,
        title: str,
        description: str,
        candidate_tickets: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Uses Gemini to determine whether a ticket is a duplicate
        from a small list of TF-IDF shortlisted candidates.

        Returns:
        {
            "is_duplicate": bool,
            "linkable": bool,
            "master_id": str,
            "similarity": float,
            "reason": str
        }
        """

        if not is_gemini_active:
            return None

        if not candidate_tickets:
            return None

        try:
            candidates_text = []

            for idx, ticket in enumerate(candidate_tickets):
                candidates_text.append(
                    f"""
Candidate #{idx}

Ticket ID:
{ticket.get('_id')}

Title:
{ticket.get('title', '')}

Description:
{ticket.get('description', '')}
"""
                )

            prompt = f"""
You are an IT Service Desk duplicate detection agent.

NEW TICKET

Title:
{title}

Description:
{description}

POSSIBLE MATCHES

{chr(10).join(candidates_text)}

Determine whether the new ticket is:

1. Exact Duplicate
2. Related Issue
3. Completely New Issue

Respond ONLY as JSON:

{{
    "decision": "duplicate | related | new",
    "candidate_index": 0,
    "similarity": 0.0,
    "reason": "brief explanation"
}}
"""

            response = cls._call_gemini(prompt, json_mode=True)

            if not response:
                return None

            result = json.loads(response)

            decision = str(
                result.get("decision", "new")
            ).lower()

            idx = int(result.get("candidate_index", 0))
            similarity = float(result.get("similarity", 0.0))
            reason = result.get("reason", "")

            if idx < 0 or idx >= len(candidate_tickets):
                return None

            matched_ticket = candidate_tickets[idx]

            if decision == "duplicate":
                return {
                    "is_duplicate": True,
                    "linkable": False,
                    "master_id": str(matched_ticket["_id"]),
                    "similarity": similarity,
                    "reason": reason
                }

            if decision == "related":
                return {
                    "is_duplicate": False,
                    "linkable": True,
                    "master_id": str(matched_ticket["_id"]),
                    "similarity": similarity,
                    "reason": reason
                }

            return {
                "is_duplicate": False,
                "linkable": False,
                "master_id": None,
                "similarity": similarity,
                "reason": reason
            }

        except Exception as e:
            logger.error(
                f"Gemini duplicate detection failed: {e}"
            )
            return None

    @classmethod
    async def semantic_kb_search(
        cls,
        query: str,
        candidate_articles: List[Dict[str, Any]],
        limit: int = 3
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Gemini reranks KB articles that were already shortlisted
        by TF-IDF retrieval.

        Returns ranked article list or None.
        """

        if not is_gemini_active:
            return None

        if not candidate_articles:
            return None

        try:
            articles_text = []

            for idx, article in enumerate(candidate_articles):
                articles_text.append(
                    f"""
Article #{idx}

ID:
{article.get('id')}

Title:
{article.get('title', '')}

Category:
{article.get('category', '')}

Content:
{article.get('content', '')[:2000]}
"""
                )

            prompt = f"""
You are a Knowledge Base retrieval agent.

USER QUERY

{query}

KB ARTICLES

{chr(10).join(articles_text)}

Select the most relevant articles.

Respond ONLY as JSON:

{{
  "ranked_indexes": [0,1,2]
}}
"""

            response = cls._call_gemini(prompt, json_mode=True)

            if not response:
                return None

            result = json.loads(response)

            ranked_indexes = result.get(
                "ranked_indexes",
                []
            )

            reranked_articles = []

            for idx in ranked_indexes:
                try:
                    idx = int(idx)

                    if 0 <= idx < len(candidate_articles):
                        reranked_articles.append(
                            candidate_articles[idx]
                        )
                except Exception:
                    continue

            if not reranked_articles:
                return None

            return reranked_articles[:limit]

        except Exception as e:
            logger.error(
                f"Gemini KB reranking failed: {e}"
            )
            return None
