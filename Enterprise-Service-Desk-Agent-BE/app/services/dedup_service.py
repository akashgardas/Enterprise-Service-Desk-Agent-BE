import logging
from typing import Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.models.ticket import TicketStatus

logger = logging.getLogger("enterprise_support.dedup_service")

class DedupService:
    DEDUP_THRESHOLD = 0.78
    LINK_THRESHOLD = 0.65

    @classmethod
    async def check_duplicate(cls, db, new_title: str, new_desc: str, exclude_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if there are any open tickets similar to the new ticket.
        Returns a dict indicating if a match is found.
        """
        new_text = f"{new_title} {new_desc}".strip().lower()
        if not new_text:
            return {"is_duplicate": False, "master_id": None, "similarity": 0.0}

        # Query all open/in-progress tickets from Supabase
        try:
            res = db.table("tickets").select("id, title, description").in_("status", ["Open", "Assigned", "In Progress"]).execute()
            open_tickets = res.data or []
        except Exception as e:
            logger.error(f"Failed to fetch open tickets from Supabase for dedup: {e}")
            return {"is_duplicate": False, "master_id": None, "similarity": 0.0}

        if exclude_id:
            open_tickets = [t for t in open_tickets if str(t.get("id")) != exclude_id]

        if not open_tickets:
            return {"is_duplicate": False, "master_id": None, "similarity": 0.0}

        # Vectorize using TF-IDF
        texts = [f"{t.get('title', '')} {t.get('description', '')}".strip().lower() for t in open_tickets]
        texts.append(new_text)

        try:
            vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b")
            tfidf_matrix = vectorizer.fit_transform(texts)
            
            # Compute cosine similarity between the new ticket (last item) and all existing tickets
            new_vector = tfidf_matrix[-1]
            existing_vectors = tfidf_matrix[:-1]
            
            similarities = cosine_similarity(new_vector, existing_vectors)[0]
            
            max_idx = similarities.argmax()
            max_sim = similarities[max_idx]

            logger.info(f"Similarity check complete. Max similarity: {max_sim:.4f}")

            if max_sim >= cls.DEDUP_THRESHOLD:
                matched_ticket = open_tickets[max_idx]
                return {
                    "is_duplicate": True,
                    "master_id": str(matched_ticket["id"]),
                    "similarity": float(max_sim)
                }
            elif max_sim >= cls.LINK_THRESHOLD:
                matched_ticket = open_tickets[max_idx]
                return {
                    "is_duplicate": False,
                    "linkable": True,
                    "master_id": str(matched_ticket["id"]),
                    "similarity": float(max_sim)
                }
        except Exception as e:
            logger.error(f"Error executing similarity check: {e}")

        return {"is_duplicate": False, "master_id": None, "similarity": 0.0}
