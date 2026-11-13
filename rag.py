import os
import chromadb

def search_knowledge(query_text: str, n_results: int = 3):
    """
    Searches the local ChromaDB vector store for medical guidelines matching user symptoms.
    Returns formatted strings with file names and page numbers for AI citations.
    """
    # Connect to the local ChromaDB directory
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    collection = chroma_client.get_or_create_collection(name="clinic_knowledge")
    
    # Run similarity query against embedded document chunks
    results = collection.query(
        query_texts=[query_text],
        n_results=n_results
    )
    
    formatted_snippets = []
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    
    # Format results cleanly for the AI agent
    for doc, meta in zip(documents, metadatas):
        source = meta.get("source", "Unknown PDF")
        page = meta.get("page", 1)
        formatted_snippets.append(f"[{source}, Page {page}]: {doc}")
        
    return "\n---\n".join(formatted_snippets) if formatted_snippets else "No relevant medical guidelines found."