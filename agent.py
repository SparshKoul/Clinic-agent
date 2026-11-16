"""
agent.py - Object-Oriented AI Agent Architecture for CureSee Clinic.

Employs OOP principles:
- Abstraction: BaseLLMClient (ABC) defining the provider inference contract.
- Polymorphism: GroqLLMClient and GeminiLLMClient implement specialized tool-calling.
- Factory Pattern: LLMClientFactory instantiates the appropriate LLM provider.
- Encapsulation: ClinicAgentSession encapsulates conversation state, tool loops, and event callbacks.
"""

import os
import json
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from dotenv import load_dotenv

import tools

# Load environment configuration
load_dotenv()

DEFAULT_SYSTEM_PROMPT = """You are the AI Clinic Assistant for Sunrise Multispeciality Clinic in Bengaluru.
Your role is to assist patients by listening to their symptoms, conducting clinical follow-up triage, screening for emergency red flags, consulting clinic manuals via the search tool, and booking appointments with the appropriate doctor.

Current clinic context:
- Clinic opening days: Monday through Saturday. The clinic is CLOSED on Sundays.
- Clinic reference date (today): Use the simulated date from database/clinic_info.
- National emergency helpline: 112 (or 108 for ambulance).
- Mental health crisis helplines: Tele-MANAS (14416) or KIRAN (1800-599-0019).

Strict 7-Step Workflow:
1. Greet and Identify:
   - Ask if the patient is a returning visitor or a new patient.
   - For returning patients, ask for their phone number and call `find_patient`.
   - If multiple patients match a name (e.g., 'Rahul Sharma'), DO NOT disclose private records or book until you ask for their phone number or date of birth to disambiguate.
   - For new patients, register them with `register_patient`, asking only for required details (Full Name, Date of Birth, Gender, Phone).
2. Listen and Ask Follow-ups:
   - Allow patients to explain their condition in their own words.
   - Ask 1 to 2 targeted follow-up questions at a time: onset/duration, severity, accompanying symptoms, existing chronic conditions, and known allergies.
3. Check for Emergencies First:
   - Immediately screen for red flags (e.g. chest pain radiating to left arm/jaw, sudden weakness or numbness on one side of face/body [stroke], severe sudden shortness of breath, heavy uncontrolled bleeding, or suicidal ideation).
   - If ANY emergency sign is detected: Direct them immediately to call 112 or 108 or go to the nearest emergency room. STOP the routine booking flow. For mental health distress/suicidal ideation, give a warm, supportive crisis message with Tele-MANAS (14416) / 112 before offering a Psychiatry consultation.
4. Search Knowledge Base:
   - Call `search_knowledge` with the patient's symptoms to ground your responses in official clinic manuals.
5. Suggest Possibilities (Non-Diagnostic):
   - Name up to 3 possible conditions indicated by the clinic manuals.
   - For each condition, give a one-line reason and cite the source manual and page number (e.g., 'Clinic Disease Handbook, p. 28').
   - ALWAYS include the mandatory disclaimer: 'This is not a diagnosis. The doctor will examine you in person to confirm.'
   - Never prescribe medication or dosages. General self-care from clinic guidelines (e.g. oral rehydration salts, rest) is permitted.
6. Match Department & Free Slots:
   - Route to the correct department (e.g., children under 14 to Pediatrics; skin to Dermatology; heart to Cardiology; ear/nose/throat to ENT; digestive issues or general fever to General Medicine).
   - Sunday rule: If a user asks for Sunday, explain the clinic is closed on Sundays and offer the doctor's next working weekday slots.
   - Call `find_free_slots` and offer 2 to 3 available times.
7. Book & Save Bilingual Medical Records:
   - Once the patient selects a slot, call `book_appointment`.
   - `complaint_patient_words`: Capture exactly what the patient described in everyday words.
   - `complaint_clinical`: Translate their complaint into proper medical terminology using the clinic glossary (e.g. 'loose motions' -> 'Acute diarrhea', 'vomiting' -> 'emesis', 'pain behind eyes' -> 'retro-orbital pain').
   - Set `booked_by` = 'ai_agent'.

Appointment Management:
- Also assist with 'show my appointments' (`get_appointments`), 'reschedule my appointment' (`reschedule_appointment`), and 'cancel my appointment' (`cancel_appointment`). Always confirm before cancelling.
"""


# =============================================================================
# 1. Base LLM Client Contract (Abstraction)
# =============================================================================
class BaseLLMClient(ABC):
    """Abstract base class defining the provider-agnostic LLM interface."""

    def __init__(self, model_name: str, api_key: str):
        self.model_name = model_name
        self.api_key = api_key

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Executes a chat completion with function calling capability."""
        pass


# =============================================================================
# 2. Concrete LLM Implementations (Polymorphism)
# =============================================================================
class GroqLLMClient(BaseLLMClient):
    """Encapsulates interaction with Groq API and Llama 3 models."""

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        from groq import Groq
        client = Groq(api_key=self.api_key)

        completion = client.chat.completions.create(
            model=self.model_name or "llama-3.3-70b-versatile",
            messages=messages,
            tools=tools_schema,
            tool_choice="auto",
            temperature=0.2,
            max_tokens=1024
        )

        msg = completion.choices[0].message
        res: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            res["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                }
                for tc in msg.tool_calls
            ]
        return res


class GeminiLLMClient(BaseLLMClient):
    """Encapsulates interaction with Google GenAI / Gemini models."""

    def complete(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)

        # Convert tool schemas to Gemini FunctionDeclarations
        gemini_tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=t["function"]["name"],
                        description=t["function"]["description"],
                        parameters=t["function"].get("parameters")
                    )
                    for t in tools_schema
                ]
            )
        ]

        # Extract system prompt and contents
        system_instruction = DEFAULT_SYSTEM_PROMPT
        formatted_contents = []

        for m in messages:
            role = m["role"]
            if role == "system":
                system_instruction = m["content"]
            elif role == "user":
                formatted_contents.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=m["content"])])
                )
            elif role == "assistant":
                if m.get("_raw_candidate_content"):
                    formatted_contents.append(m["_raw_candidate_content"])
                else:
                    parts = []
                    if m.get("content"):
                        parts.append(types.Part.from_text(text=m["content"]))
                    if m.get("tool_calls"):
                        for tc in m["tool_calls"]:
                            fn_args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                            parts.append(
                                types.Part.from_function_call(name=tc["function"]["name"], args=fn_args)
                            )
                    if parts:
                        formatted_contents.append(types.Content(role="model", parts=parts))
            elif role == "tool":
                try:
                    resp_dict = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
                except Exception:
                    resp_dict = {"output": m["content"]}
                formatted_contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=m["name"],
                                response={"result": resp_dict}
                            )
                        ]
                    )
                )

        response = client.models.generate_content(
            model=self.model_name or "gemini-3.1-flash-lite",
            contents=formatted_contents,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=gemini_tools,
                temperature=0.2
            )
        )

        text_parts = []
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for p in response.candidates[0].content.parts:
                if getattr(p, "text", None):
                    text_parts.append(p.text)
        model_text = "".join(text_parts)

        res: Dict[str, Any] = {"role": "assistant", "content": model_text}
        if response.candidates and response.candidates[0].content:
            res["_raw_candidate_content"] = response.candidates[0].content
        if response.function_calls:
            res["tool_calls"] = [
                {
                    "id": f"call_{fc.name}",
                    "type": "function",
                    "function": {
                        "name": fc.name,
                        "arguments": json.dumps(fc.args)
                    }
                }
                for fc in response.function_calls
            ]
        return res


# =============================================================================
# 3. LLM Client Factory (Factory Pattern)
# =============================================================================
class LLMClientFactory:
    """Factory responsible for instantiating the appropriate LLM client."""

    @staticmethod
    def create_client(
        provider: Optional[str] = None,
        model: Optional[str] = None
    ) -> Optional[BaseLLMClient]:
        groq_key = os.getenv("GROQ_API_KEY")
        gemini_key = os.getenv("GEMINI_API_KEY")

        chosen_provider = provider or os.getenv("LLM_PROVIDER")
        if not chosen_provider:
            chosen_provider = "groq" if groq_key else ("gemini" if gemini_key else "groq")

        if chosen_provider == "groq" and groq_key:
            return GroqLLMClient(
                model_name=model or os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"),
                api_key=groq_key
            )
        elif chosen_provider == "gemini" and gemini_key:
            return GeminiLLMClient(
                model_name=model or os.getenv("LLM_MODEL", "gemini-3.1-flash-lite"),
                api_key=gemini_key
            )
        elif groq_key:
            return GroqLLMClient(
                model_name=model or "llama-3.3-70b-versatile",
                api_key=groq_key
            )
        elif gemini_key:
            return GeminiLLMClient(
                model_name=model or "gemini-3.1-flash-lite",
                api_key=gemini_key
            )

        return None


# =============================================================================
# 4. Clinic Agent Session (Encapsulation of Conversation & Triage Lifecycle)
# =============================================================================
class ClinicAgentSession:
    """Manages multi-turn conversation state, autonomous tool calling, and event dispatching."""

    def __init__(
        self,
        session_id: str,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        tool_registry: Optional[tools.ToolRegistry] = None,
        llm_client: Optional[BaseLLMClient] = None
    ):
        self.session_id = session_id
        self._tool_registry = tool_registry or tools.tool_registry
        self._llm_client = llm_client or LLMClientFactory.create_client()
        self.messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_prompt}
        ]
        self.identified_patient: Optional[Dict[str, Any]] = None

    def add_user_message(self, text: str) -> None:
        """Appends user message to session history."""
        self.messages.append({"role": "user", "content": text})

    async def run_turn(
        self,
        on_status: Optional[Callable[[str], None]] = None,
        on_booking: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_token: Optional[Callable[[str], None]] = None
    ) -> str:
        """
        Executes one complete conversational turn with tool calling loops in threadpool.
        """
        if not self._llm_client:
            # Recheck factory in case environment variables were loaded late
            self._llm_client = LLMClientFactory.create_client()
            if not self._llm_client:
                return (
                    "API key required: Please set GROQ_API_KEY or GEMINI_API_KEY in your .env file "
                    "to enable live AI reasoning."
                )

        max_tool_iterations = 6
        iteration = 0

        while iteration < max_tool_iterations:
            iteration += 1

            # Execute LLM call in non-blocking threadpool
            response_msg = await asyncio.to_thread(
                self._llm_client.complete,
                self.messages,
                self._tool_registry.get_schemas()
            )

            tool_calls = response_msg.get("tool_calls")
            if not tool_calls:
                final_content = response_msg.get("content") or ""
                self.messages.append({"role": "assistant", "content": final_content})
                return final_content

            self.messages.append(response_msg)

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                raw_args = tc["function"].get("arguments", "{}")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    args = {}

                # Emit user-facing status indicator
                status_text = self._format_status_message(fn_name, args)
                if on_status and status_text:
                    on_status(status_text)

                # Dispatch tool execution
                tool_output = await asyncio.to_thread(self._tool_registry.execute, fn_name, args)

                # Booking event notification
                if fn_name in ("book_appointment", "reschedule_appointment", "cancel_appointment"):
                    if isinstance(tool_output, dict) and tool_output.get("success") and tool_output.get("appointment"):
                        if on_booking:
                            on_booking(tool_output["appointment"])

                if fn_name == "find_patient" and isinstance(tool_output, dict):
                    if tool_output.get("success") and tool_output.get("count") == 1:
                        self.identified_patient = tool_output.get("patient")

                tool_output_str = json.dumps(tool_output) if isinstance(tool_output, (dict, list)) else str(tool_output)
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{fn_name}"),
                    "name": fn_name,
                    "content": tool_output_str
                })

        return "I apologize, but I encountered an issue processing your request. Please try again."

    @staticmethod
    def _format_status_message(tool_name: str, args: Dict[str, Any]) -> str:
        """Translates tool names to user-friendly status updates."""
        if tool_name == "find_free_slots":
            spec = args.get("specialty")
            return f"Checking free slots for {spec}…" if spec else "Checking free slots…"

        status_map = {
            "search_knowledge": "Searching the clinic medical knowledge base…",
            "book_appointment": "Booking your appointment…",
            "reschedule_appointment": "Rescheduling your appointment…",
            "cancel_appointment": "Updating appointment status…",
            "find_patient": "Looking up patient records…",
            "register_patient": "Registering new patient…",
            "get_appointments": "Fetching appointment history…",
            "list_doctors": "Checking doctor directories…"
        }
        return status_map.get(tool_name, f"Executing {tool_name}…")


if __name__ == "__main__":
    print("Testing ClinicAgentSession initialization...")
    session = ClinicAgentSession("cli-test")
    print(f"Session initialized with ID: {session.session_id}")
    print(f"LLM Client configured: {session._llm_client.__class__.__name__ if session._llm_client else 'None (Missing API Keys)'}")
