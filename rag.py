"""
rag.py - Object-Oriented Retrieval Layer (RAG) for CureSee Clinic.

Employs OOP principles:
- Encapsulation: VectorStoreClient manages ChromaDB connection.
- Polymorphic / Strategy retrieval: HybridKnowledgeRetriever implements semantic + lexical scoring.
- High cohesion: Clean formatting and structured match representations.
"""

import os
import re
from typing import Optional, List, Dict, Any, Tuple
import chromadb

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
DEFAULT_COLLECTION_NAME = "clinic_knowledge"


class VectorStoreClient:
    """Encapsulates ChromaDB persistent client and collection lifecycle."""

    def __init__(self, db_dir: Optional[str] = None, collection_name: str = DEFAULT_COLLECTION_NAME):
        self._db_dir = db_dir or DEFAULT_CHROMA_DIR
        self._collection_name = collection_name
        self._client = chromadb.PersistentClient(path=self._db_dir)

    def get_collection(self):
        """Returns the ChromaDB collection."""
        return self._client.get_or_create_collection(name=self._collection_name)

    @property
    def count(self) -> int:
        """Returns number of chunks in the collection."""
        return self.get_collection().count()


class HybridKnowledgeRetriever:
    """
    Implements hybrid retrieval combining dense vector similarity with
    lexical keyword matching, phrase boosting, and diversity filtering.
    """

    def __init__(self, vector_store: Optional[VectorStoreClient] = None):
        self._store = vector_store or VectorStoreClient()

    def search_structured(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        """
        Executes hybrid search and returns a ranked list of structured match dictionaries.
        """
        search_q = query.strip()
        if not search_q:
            return []

        collection = self._store.get_collection()
        total_count = collection.count()
        if total_count == 0:
            return []

        # Query a larger candidate pool for re-ranking
        candidate_k = min(max(k * 5, 20), total_count)
        results = collection.query(
            query_texts=[search_q],
            n_results=candidate_k
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] if "distances" in results else [0.5] * len(documents)

        if not documents:
            return []

        # Compute hybrid relevance scores
        terms = [w for w in re.split(r"\W+", search_q.lower()) if len(w) > 2]
        scored_items = []

        for doc, meta, dist in zip(documents, metadatas, distances):
            doc_lower = doc.lower()
            vec_score = max(0.0, 1.0 - (dist / 2.0))

            term_hits = sum(1 for t in terms if t in doc_lower)
            phrase_bonus = 0.0
            if len(terms) >= 2:
                for i in range(len(terms) - 1):
                    phrase = f"{terms[i]} {terms[i+1]}"
                    if phrase in doc_lower:
                        phrase_bonus += 0.5

            cond_bonus = 0.0
            cond_name = (meta.get("condition") or "").lower()
            if any(t in cond_name for t in terms):
                cond_bonus += 0.3

            total_score = vec_score + (0.15 * term_hits) + phrase_bonus + cond_bonus
            scored_items.append((total_score, doc, meta, dist))

        # Sort descending by hybrid score
        scored_items.sort(key=lambda x: x[0], reverse=True)

        # Apply diversity filter to prevent identical pages from crowding the results
        selected = []
        seen_pages = set()
        for score, doc, meta, dist in scored_items:
            page_key = (meta.get("source"), meta.get("page"))
            if list(seen_pages).count(page_key) >= 2:
                continue
            seen_pages.add(page_key)

            clean_text = doc
            if clean_text.startswith("[") and "]\n" in clean_text[:140]:
                clean_text = clean_text.split("]\n", 1)[1]

            selected.append({
                "source": meta.get("source", "Clinic Manual"),
                "page": meta.get("page", 1),
                "condition": meta.get("condition", "General"),
                "category": meta.get("category", "Medical Reference"),
                "text": clean_text.strip(),
                "score": score,
                "distance": dist
            })
            if len(selected) >= k:
                break

        return selected

    def search_formatted(self, query: str, k: int = 3) -> str:
        """
        Executes hybrid search and returns formatted citations for LLM grounding.
        """
        matches = self.search_structured(query, k=k)
        if not matches:
            if self._store.count == 0:
                return "Knowledge base is currently empty. Please run 'python ingest.py' first."
            return "No relevant medical guidelines found in clinic records."

        formatted_snippets = []
        for m in matches:
            snippet = (
                f"Source: {m['source']} (Page {m['page']})\n"
                f"Topic / Condition: {m['condition']}\n"
                f"Excerpt:\n{m['text']}"
            )
            formatted_snippets.append(snippet)

        return "\n\n---\n\n".join(formatted_snippets)


# Default singleton instance
retriever = HybridKnowledgeRetriever()

# Module-level convenience functions
def get_chroma_collection(db_dir: Optional[str] = None):
    return VectorStoreClient(db_dir).get_collection()

def search_knowledge(
    query: str,
    k: int = 3,
    query_text: Optional[str] = None,
    n_results: Optional[int] = None,
    db_dir: Optional[str] = None
) -> str:
    active_retriever = HybridKnowledgeRetriever(VectorStoreClient(db_dir)) if db_dir else retriever
    effective_q = query_text or query or ""
    effective_k = n_results or k or 3
    return active_retriever.search_formatted(effective_q, k=effective_k)

def search_knowledge_structured(
    query: str,
    k: int = 3,
    db_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    active_retriever = HybridKnowledgeRetriever(VectorStoreClient(db_dir)) if db_dir else retriever
    return active_retriever.search_structured(query, k=k)


if __name__ == "__main__":
    print("Testing OOP knowledge retrieval for: 'pain behind the eyes and high fever'...")
    res = search_knowledge("pain behind the eyes and high fever", k=3)
    print("\nSearch Results:")
    print(res)
