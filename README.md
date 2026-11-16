# CureSee / Sunrise Multispeciality Clinic AI Assistant

An intelligent, autonomous conversational clinical triage and appointment scheduling agent built for **Sunrise Multispeciality Clinic** (Bengaluru). Grounded in verified clinic manuals, this system safely triages patient symptoms, screens for emergencies, searches medical handbooks via semantic RAG, and manages real-time appointments.

---

## ⚡ Quickstart (Setup in 5 Commands)

```bash
# 1. Create and activate Python virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure API keys (Gemini or Groq)
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY (or GROQ_API_KEY)

# 4. Ingest clinic medical manuals into local ChromaDB
python3 ingest.py

# 5. Start the FastAPI WebSocket server
uvicorn app:app --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser to chat with the assistant!

---

## 🏛️ System Architecture & OOP Design

The system is engineered using strict Object-Oriented Programming (OOP) design patterns to ensure modularity, separation of concerns, and clean testability:

| Component | Design Pattern / Structure | Responsibility |
| :--- | :--- | :--- |
| **`db.py`** | **Repository & Facade Pattern** | `DatabaseConnectionManager`, `PatientRepository`, `DoctorRepository`, `AppointmentRepository`, unified under `ClinicDatabase` facade. Manages parameterized SQLite access, slot calculations, race condition recovery, and working hours constraints. |
| **`ingest.py`** | **Strategy Pattern** | `ConditionMapper`, `DocumentChunker`, and `KnowledgeIngestor`. Parses 3 clinic PDFs, extracts semantic boundaries, maps conditions, and populates persistent ChromaDB embeddings. |
| **`rag.py`** | **Composite / Strategy Pattern** | `VectorStoreClient` and `HybridKnowledgeRetriever`. Implements dense cosine similarity, lexical keyword matching, condition boosting, and diversity filtering. Always cites source file and page. |
| **`tools.py`** | **Command / Registry Pattern** | `BaseTool` (ABC) with 10 concrete clinical tool implementations registered in `ToolRegistry`. Dynamically generates OpenAI/Gemini function schemas and dispatches execution. |
| **`agent.py`** | **Factory & Polymorphism Pattern** | `BaseLLMClient` (ABC) implemented by `GeminiLLMClient` and `GroqLLMClient`, instantiated via `LLMClientFactory`. `ClinicAgentSession` encapsulates multi-turn conversation state, non-blocking tool calling loops, and event emission. |
| **`app.py`** | **Facade / Observer Pattern** | `ConnectionManager`, `SessionManager`, and `ClinicWebSocketController`. Handles `/ws/chat` protocol, multi-client session isolation, background thread execution, and real-time streaming of `status`, `booking`, and `assistant_message` events. |

---

## 📡 WebSocket Event Protocol (`/ws/chat`)

Each client communicates over WebSocket via structured JSON payloads:

### Client $\to$ Server
```json
{
  "type": "user_message",
  "text": "I have loose motions since morning and vomited twice, feeling very weak."
}
```

### Server $\to$ Client
* **Initial Greeting:** Delivered on connection.
* **`status`**: Emitted while tools run:
  ```json
  {"type": "status", "text": "Searching the clinic medical knowledge base…"}
  ```
* **`booking`**: Emitted when an appointment is booked, rescheduled, or cancelled:
  ```json
  {
    "type": "booking",
    "appointment": {
      "id": 105,
      "doctor": "Dr. Vikram Shetty",
      "specialty": "General Medicine",
      "date": "2026-11-13",
      "start_time": "15:00",
      "status": "scheduled"
    }
  }
  ```
* **`assistant_message`**: Emitted upon completion of the agent turn:
  ```json
  {
    "type": "assistant_message",
    "text": "These symptoms most often fit acute gastroenteritis... (Clinic Disease Handbook, p. 28). This is not a diagnosis; the doctor will confirm..."
  }
  ```
* **`error`**: Dispatched for invalid requests without disconnecting the client:
  ```json
  {"type": "error", "text": "Invalid JSON format."}
  ```

---

## 🛡️ Clinical Safety & Triage Rules

1. **Non-Diagnostic Policy:** The assistant never claims a definitive diagnosis; it explicitly indicates potential conditions and reminds the patient that only an examining physician can confirm.
2. **Emergency Red Flags (112/108):** Immediate triage routing for critical symptoms (e.g. chest pain radiating to arm, stroke signs, severe dyspnea, suicide ideation). Halts routine booking and directs to 112/108 or nearest emergency center.
3. **Mental Health Crisis:** Warm, caring safety guidance with Tele-MANAS (14416) and KIRAN (1800-599-0019) helplines.
4. **Bilingual Medical Logging:** Every booking records:
   - `complaint_patient_words`: Raw vernacular description from the patient.
   - `complaint_clinical`: Formal clinical terminology mapped via clinic glossary (e.g. "vomiting" $\to$ "emesis", "loose motions" $\to$ "acute diarrhea").
5. **Sunday Closure:** Strictly enforces clinic operating hours (Monday–Saturday; closed Sundays).
6. **Patient Privacy & Disambiguation:** Sessions are isolated. Ambiguous names (e.g. "Rahul Sharma") prompt for date of birth or phone number verification before disclosing records.

---

## 🧪 Testing & Evaluation

### Run Database Unit Tests
```bash
python3 test_db.py
```
*Validates all 9 CRUD operations, foreign key integrity, Sunday closure, working hours boundaries, and slot collision recovery.*

### Run the 11 Evaluation Scenarios
```bash
python3 run_scenarios.py
```
*Executes all 11 evaluation scenarios and saves full conversation transcripts with status logs and booking cards in **`TESTING.md`**.*

---

## 📁 Repository Structure

```
├── app.py                  # FastAPI WebSocket chat server and session orchestrator
├── agent.py                # OOP AI Agent, LLM client factory, and triage loop
├── db.py                   # OOP Database layer (9 clinical tools, repositories, facade)
├── ingest.py               # RAG ingestion pipeline (pypdf, semantic chunking, ChromaDB)
├── rag.py                  # Hybrid dense + lexical retrieval with source citations
├── tools.py                # Command/Registry tool definitions for LLM function calling
├── static/
│   └── index.html          # Clean, responsive single-page chat UI with booking cards
├── data/
│   └── clinic.db           # SQLite database with pre-populated clinic tables
├── knowledge/              # 3 Official clinic PDF manuals (Disease, Glossary, Triage)
├── chroma_db/              # Local persistent ChromaDB vector store
├── test_db.py              # Unit tests for database operations
├── run_scenarios.py        # Automated test harness for the 11 evaluation scenarios
├── TESTING.md              # Transcripts and verification of the 11 evaluation scenarios
├── NOTES.md                # Engineering trade-offs, chunking rationale, concurrency
└── requirements.txt        # Minimal Python dependencies
```
