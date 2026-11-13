import os
import chromadb
from pypdf import PdfReader

# Initialize local ChromaDB client (stores files in ./chroma_db folder)
chroma_client = chromadb.PersistentClient(path="./chroma_db")
collection = chroma_client.get_or_create_collection(name="clinic_knowledge")

KNOWLEDGE_DIR = "knowledge"

def ingest_pdfs():
    """Reads all PDFs in the knowledge folder, chunks them, and stores them in ChromaDB."""
    if not os.path.exists(KNOWLEDGE_DIR):
        print(f"Directory '{KNOWLEDGE_DIR}' not found.")
        return

    for filename in os.listdir(KNOWLEDGE_DIR):
        if filename.endswith(".pdf"):
            pdf_path = os.path.join(KNOWLEDGE_DIR, filename)
            reader = PdfReader(pdf_path)
            
            print(f"Processing {filename}...")
            
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text.strip():
                    continue
                
                # Simple chunking: split text into blocks of ~1000 characters
                chunk_size = 1000
                overlap = 150
                for i in range(0, len(text), chunk_size - overlap):
                    chunk = text[i:i + chunk_size]
                    chunk_id = f"{filename}-p{page_num}-c{i}"
                    
                    # Upsert chunk into ChromaDB with metadata for source tracking
                    collection.upsert(
                        documents=[chunk],
                        metadatas=[{"source": filename, "page": page_num + 1}],
                        ids=[chunk_id]
                    )
    print("Ingestion complete! Knowledge base is ready.")

if __name__ == "__main__":
    ingest_pdfs()