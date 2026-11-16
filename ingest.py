"""
ingest.py - Object-Oriented Ingestion Engine for CureSee Clinic.

Employs OOP principles:
- Single Responsibility: ConditionMapper, DocumentChunker, and KnowledgeIngestor.
- Encapsulation: PDF reading, boundary-aware text chunking, and ChromaDB batch upserting.
"""

import os
from typing import List, Dict, Any, Tuple
import chromadb
from pypdf import PdfReader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_KNOWLEDGE_DIR = os.path.join(BASE_DIR, "knowledge")
DEFAULT_CHROMA_DIR = os.path.join(BASE_DIR, "chroma_db")
DEFAULT_COLLECTION_NAME = "clinic_knowledge"


class ConditionMapper:
    """Encapsulates page-to-disease and clinical body system mapping."""

    HANDBOOK_CONDITIONS: List[Tuple[int, str, str]] = [
        (4, "Dengue fever", "Infections and fever"),
        (8, "Malaria", "Infections and fever"),
        (12, "Typhoid fever", "Infections and fever"),
        (15, "Chikungunya", "Infections and fever"),
        (18, "Influenza (flu)", "Infections and fever"),
        (21, "COVID-19", "Infections and fever"),
        (24, "Chickenpox", "Infections and fever"),
        (28, "Acute gastroenteritis", "Digestive system"),
        (32, "Gastroesophageal reflux disease (GERD)", "Digestive system"),
        (36, "Peptic ulcer", "Digestive system"),
        (39, "Irritable bowel syndrome (IBS)", "Digestive system"),
        (43, "Viral hepatitis", "Digestive system"),
        (47, "Appendicitis", "Digestive system"),
        (50, "Kidney stones", "Kidney and urinary"),
        (54, "Urinary tract infection (UTI)", "Kidney and urinary"),
        (58, "Iron-deficiency anaemia", "Blood"),
        (62, "High blood pressure (hypertension)", "Heart and blood vessels"),
        (65, "Coronary artery disease (including angina and heart attack)", "Heart and blood vessels"),
        (69, "Asthma", "Lungs and breathing"),
        (72, "Chronic obstructive pulmonary disease (COPD)", "Lungs and breathing"),
        (75, "Pneumonia (lung infection)", "Lungs and breathing"),
        (78, "Tuberculosis (TB)", "Lungs and breathing"),
        (81, "Type 2 diabetes", "Hormones and metabolism"),
        (84, "Underactive thyroid (hypothyroidism)", "Hormones and metabolism"),
        (87, "Migraine", "Brain and nerves"),
        (91, "Tension-type headache", "Brain and nerves"),
        (94, "Stroke", "Brain and nerves"),
        (98, "Anxiety disorder", "Mental health"),
        (102, "Depression", "Mental health"),
        (106, "Osteoarthritis", "Bones, joints and muscles"),
        (109, "Low back pain", "Bones, joints and muscles"),
        (112, "Eczema (atopic dermatitis)", "Skin"),
        (115, "Fungal skin infection (ringworm, tinea)", "Skin"),
        (118, "Acne", "Skin"),
        (121, "Common cold", "Ear, nose and throat"),
        (124, "Allergic rhinitis (nasal allergy)", "Ear, nose and throat"),
        (127, "Sinusitis (sinus infection)", "Ear, nose and throat"),
        (130, "Ear infection (otitis media)", "Ear, nose and throat"),
        (133, "Tonsillitis", "Ear, nose and throat"),
        (136, "Conjunctivitis (pink eye)", "Eyes"),
        (140, "Polycystic ovary syndrome (PCOS)", "Women's health"),
        (143, "General Reference & Sources", "Reference")
    ]

    @classmethod
    def get_condition_for_page(cls, page_num: int) -> Tuple[str, str]:
        """Resolves condition name and body system for a given page number."""
        if page_num < 4:
            return "Handbook Overview & Contents", "Overview"
        current_cond = "General Medical Reference"
        current_system = "General"
        for start_p, cond_name, system_name in cls.HANDBOOK_CONDITIONS:
            if page_num >= start_p:
                current_cond = cond_name
                current_system = system_name
            else:
                break
        return current_cond, current_system


class DocumentChunker:
    """Encapsulates boundary-aware text splitting and chunk ID generation."""

    def __init__(self, target_size: int = 1000, overlap: int = 150):
        self._target_size = target_size
        self._overlap = overlap

    def chunk_text(self, text: str) -> List[str]:
        """Splits text into overlapping chunks respecting sentence and paragraph boundaries."""
        text = text.strip()
        if not text:
            return []
        if len(text) <= self._target_size:
            return [text]

        chunks = []
        start = 0
        total_len = len(text)

        while start < total_len:
            end = min(start + self._target_size, total_len)

            if end < total_len:
                p_break = text.rfind("\n\n", start + self._target_size // 2, end)
                if p_break != -1:
                    end = p_break + 2
                else:
                    s_break = max(
                        text.rfind(". ", start + self._target_size // 2, end),
                        text.rfind(".\n", start + self._target_size // 2, end),
                        text.rfind("? ", start + self._target_size // 2, end),
                        text.rfind(";\n", start + self._target_size // 2, end)
                    )
                    if s_break != -1:
                        end = s_break + 1
                    else:
                        space_break = text.rfind(" ", start + self._target_size // 2, end)
                        if space_break != -1:
                            end = space_break + 1

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            if end >= total_len:
                break

            start = max(start + 1, end - self._overlap)

        return chunks

    @staticmethod
    def generate_chunk_id(doc_prefix: str, page_num: int, chunk_idx: int) -> str:
        """Generates a stable, deterministic chunk ID."""
        return f"{doc_prefix}-p{page_num}-c{chunk_idx}"


class KnowledgeIngestor:
    """Coordinates PDF parsing, chunking, and persistent ChromaDB ingestion."""

    def __init__(
        self,
        knowledge_dir: str = DEFAULT_KNOWLEDGE_DIR,
        chroma_dir: str = DEFAULT_CHROMA_DIR,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        chunker: DocumentChunker = None
    ):
        self._knowledge_dir = knowledge_dir
        self._chroma_dir = chroma_dir
        self._collection_name = collection_name
        self._chunker = chunker or DocumentChunker()

    def ingest(self) -> Dict[str, Any]:
        """Parses clinic PDFs and stores embeddings in ChromaDB in batches."""
        if not os.path.exists(self._knowledge_dir):
            raise FileNotFoundError(f"Knowledge directory '{self._knowledge_dir}' not found.")

        client = chromadb.PersistentClient(path=self._chroma_dir)
        collection = client.get_or_create_collection(
            name=self._collection_name,
            metadata={"description": "Sunrise Multispeciality Clinic Medical Knowledge Base"}
        )

        pdf_files = [
            "clinic-disease-handbook.pdf",
            "symptom-terms-glossary.pdf",
            "triage-and-referral-guide.pdf"
        ]

        all_docs: List[str] = []
        all_metas: List[Dict[str, Any]] = []
        all_ids: List[str] = []
        total_pages = 0

        for filename in pdf_files:
            filepath = os.path.join(self._knowledge_dir, filename)
            if not os.path.exists(filepath):
                continue

            prefix = "handbook" if "handbook" in filename else ("glossary" if "glossary" in filename else "triage")
            reader = PdfReader(filepath)
            total_pages += len(reader.pages)

            for page_idx, page in enumerate(reader.pages):
                page_num = page_idx + 1
                raw_text = page.extract_text() or ""
                if not raw_text.strip():
                    continue

                if prefix == "handbook":
                    condition, system = ConditionMapper.get_condition_for_page(page_num)
                    category = "Disease Reference"
                elif prefix == "glossary":
                    condition = "Medical Glossary"
                    system = "Terminology"
                    category = "Symptom Glossary"
                else:
                    condition = "Triage Protocol & Red Flags"
                    system = "Emergency Triage"
                    category = "Triage Guide"

                chunks = self._chunker.chunk_text(raw_text)
                for chunk_idx, chunk in enumerate(chunks):
                    chunk_id = self._chunker.generate_chunk_id(prefix, page_num, chunk_idx + 1)
                    enriched_text = f"[{filename} | Page {page_num} | {condition}]\n{chunk}"

                    all_docs.append(enriched_text)
                    all_metas.append({
                        "source": filename,
                        "page": page_num,
                        "condition": condition,
                        "system": system,
                        "category": category,
                        "chunk_index": chunk_idx + 1
                    })
                    all_ids.append(chunk_id)

        total_chunks = len(all_docs)
        batch_size = 50
        for i in range(0, total_chunks, batch_size):
            collection.upsert(
                documents=all_docs[i:i + batch_size],
                metadatas=all_metas[i:i + batch_size],
                ids=all_ids[i:i + batch_size]
            )

        return {
            "success": True,
            "total_pages": total_pages,
            "total_chunks": total_chunks,
            "collection_count": collection.count()
        }


# Module-level convenience wrapper
def ingest_pdfs(knowledge_dir: str = DEFAULT_KNOWLEDGE_DIR, db_dir: str = DEFAULT_CHROMA_DIR) -> Dict[str, Any]:
    ingestor = KnowledgeIngestor(knowledge_dir=knowledge_dir, chroma_dir=db_dir)
    return ingestor.ingest()


if __name__ == "__main__":
    res = ingest_pdfs()
    print(f"Ingestion complete: {res['total_chunks']} chunks stored in collection.")
