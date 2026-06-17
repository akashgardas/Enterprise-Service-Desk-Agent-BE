import logging
from typing import List, Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.models.ticket import TicketCategory

logger = logging.getLogger("enterprise_support.kb_service")

class KbService:
    @classmethod
    async def search_articles(cls, db, query: str, category: Optional[TicketCategory] = None, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Searches KB articles using TF-IDF cosine similarity.
        Optionally pre-filters by category.
        """
        query_text = query.strip().lower()
        if not query_text:
            return []

        # Build filter query
        filter_query = {}
        if category:
            filter_query["category"] = category

        # Fetch articles
        cursor = db.kb_articles.find(filter_query)
        articles = []
        async for doc in cursor:
            articles.append({
                "id": str(doc["_id"]),
                "title": doc.get("title", ""),
                "content": doc.get("content", ""),
                "category": doc.get("category", "other"),
                "tags": doc.get("tags", [])
            })

        if not articles:
            return []

        # Calculate similarity using TF-IDF
        corpus = [f"{art['title']} {art['content']} {' '.join(art['tags'])}".lower() for art in articles]
        corpus.append(query_text)

        try:
            vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b")
            tfidf_matrix = vectorizer.fit_transform(corpus)
            
            query_vector = tfidf_matrix[-1]
            article_vectors = tfidf_matrix[:-1]
            
            similarities = cosine_similarity(query_vector, article_vectors)[0]
            
            # Pair article index with similarity score
            results = []
            for i, sim in enumerate(similarities):
                if sim > 0.1:  # Only return articles with some relevance
                    results.append((articles[i], sim))
            
            # Sort by similarity score in descending order
            results.sort(key=lambda x: x[1], reverse=True)
            
            # Format and limit output
            sorted_articles = []
            for art, score in results[:limit]:
                art_copy = art.copy()
                art_copy["similarity_score"] = float(score)
                sorted_articles.append(art_copy)
                
            return sorted_articles
        except Exception as e:
            logger.error(f"Error performing KB search vectorization: {e}")
            # Fallback to simple keyword filtering if tf-idf fails
            fallback_matches = []
            for art in articles:
                score = 0
                if any(word in art['title'].lower() for word in query_text.split()):
                    score += 0.5
                if any(word in art['content'].lower() for word in query_text.split()):
                    score += 0.2
                if score > 0:
                    art_copy = art.copy()
                    art_copy["similarity_score"] = score
                    fallback_matches.append(art_copy)
            fallback_matches.sort(key=lambda x: x["similarity_score"], reverse=True)
            return fallback_matches[:limit]
