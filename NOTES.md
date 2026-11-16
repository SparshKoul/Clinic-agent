# Engineering Notes - CureSee / Sunrise Multispeciality Clinic AI Assistant

### 1. Chunk Size & Retrieval Strategy
- **Chunk Size Rationale:** Document chunks are sized between **800 and 1,100 characters** with a **150-character sliding overlap**. 
  - *Why this size?* The clinic manuals (`clinic-disease-handbook.pdf`, `symptom-terms-glossary.pdf`, `triage-and-referral-guide.pdf`) are structured around distinct clinical sections: *Overview, Clinical Presentation, Emergency Red Flags, Triage/Referral Guidance, and Home Care*. Smaller chunks (<500 characters) sever related symptoms from red flags. Larger chunks (>1,500 characters) dilute dense sentence embeddings and introduce noise.
  - *Boundary-Aware Chunking:* The chunker (`DocumentChunker`) respects paragraph breaks (`\n\n`) and sentence boundaries rather than cutting arbitrarily mid-sentence, preserving clinical coherence.
  - *Hybrid Ranking:* Retrieval combines dense vector cosine similarity (via local `all-MiniLM-L6-v2`) with lexical keyword/phrase matching, condition page indexing, and metadata filtering. Every result returns exact `source` and `page` references for strict AI grounding.

---

### 2. WebSocket Concurrency & Multi-Conversation Architecture
- **Session Isolation:** The WebSocket server (`app.py`) leverages FastAPI and `uvicorn` on an asynchronous event loop. Each connection is assigned an isolated `session_id` mapped inside `SessionManager`. State, conversation history, and identified patient identity are encapsulated within that session's `ClinicAgentSession` instance, preventing state leakage across tabs or users.
- **Non-Blocking Asynchronous Concurrency:** LLM API calls, SQLite transactions, and ChromaDB vector embeddings are executed within non-blocking worker threads using `asyncio.to_thread()`. This ensures that slow external network calls or database operations in one patient's session never stall the event loop or increase latency for other connected clients.
- **Resilient Protocol:** The `/ws/chat` endpoint handles client disconnects cleanly without crashing the server, supports auto-reconnection via session query parameters, and rejects malformed JSON with non-fatal `error` events.

---

### 3. What Worked and What Didn't
- **What Worked Well:**
  - **OOP Design Patterns:** Repository and Facade patterns in `db.py` made slot calculation, working hours validation, and race condition handling clean and testable. Command/Registry pattern in `tools.py` decoupled tool execution from schema generation.
  - **Slot Collision Recovery:** Atomic SQLite transactions with `sqlite3.IntegrityError` capture reliably detected simultaneous booking conflicts and suggested alternative free slots on the same day.
  - **Clinical Safety Rules:** Emergency red flag detection immediately halted routine booking flows and directed critical patients to 112/108, while mental health crises routed to Tele-MANAS (14416).
  - **Bilingual Term Mapping:** Automated translation of patient colloquial descriptions (e.g. "vomiting twice and loose motions") into standardized medical records (`complaint_clinical: Acute diarrhea with emesis x2`).
- **Challenges & Solutions:**
  - *Gemini 3 Thought Signatures:* In Google GenAI SDK (`google-genai`), multi-turn tool calling with Gemini 3 requires preserving the raw candidate content (`thought_signature`). We addressed this by retaining raw candidate objects in `GeminiLLMClient` across function call iterations.
  - *Model Deprecation:* Google AI Studio deprecated older models (`gemini-2.5-flash`) for new API keys. We dynamically adapted to `gemini-3.1-flash-lite`, which delivered sub-second responses and strong tool adherence.
  - *Offline Embeddings:* Sandboxed environments restrict downloading model weights from S3. Pre-caching ONNX weights for `all-MiniLM-L6-v2` locally enabled 100% offline, reproducible vector store operations.

---

### 4. What I Would Do With More Time
1. **Token-Level Streaming (`assistant_token`):** Enable streaming token generator yielding chunks over WebSocket for instantaneous typing animations.
2. **Vernacular Voice Triage:** Integrate Whisper and TTS for real-time Kannada, Hindi, and Tamil voice conversations for patients who cannot type.
3. **FHIR / EHR Interoperability:** Export completed bookings as HL7 / FHIR `Appointment` and `Encounter` JSON resources for integration into hospital management systems (HMS).
4. **Automated Patient Notifications:** Send immediate SMS / WhatsApp booking confirmations with clinic address and doctor details.

---

### 5. How AI Tools Were Used
- **Architecture Blueprints & Scaffolding:** Used to structure OOP interfaces, database repository contracts, and schema definitions.
- **Clinical Glossary Review:** Assisted in auditing medical terminology mappings between colloquial Indian patient expressions and clinical terminology.
- **Rigorous Verification:** All business logic, slot boundaries, database constraints, and scenario outputs were verified with automated test suites (`test_db.py`, `run_scenarios.py`).
