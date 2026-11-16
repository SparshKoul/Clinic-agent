"""
tools.py - Object-Oriented Tool Architecture for CureSee Clinic.

Employs OOP principles:
- Abstraction: BaseTool (ABC) defines the tool contract (name, description, schema, execution).
- Inheritance: 10 concrete Tool classes encapsulate specific database and knowledge base actions.
- Command / Registry Pattern: ToolRegistry manages registration, schema generation, and dispatching.
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import db
import rag


# =============================================================================
# 1. Base Tool Contract (Abstract Base Class)
# =============================================================================
class BaseTool(ABC):
    """Abstract base class representing an autonomous agent tool."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier of the tool."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Clear description of what the tool accomplishes."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> Dict[str, Any]:
        """JSON Schema parameter definitions."""
        pass

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Executes the tool with provided arguments."""
        pass

    def to_schema(self) -> Dict[str, Any]:
        """Generates OpenAI / Groq / Gemini compatible function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }


# =============================================================================
# 2. Concrete Database & Knowledge Base Tools (Inheritance)
# =============================================================================
class SearchKnowledgeTool(BaseTool):
    """Tool for querying the clinic disease handbook, glossary, and triage guides."""

    @property
    def name(self) -> str:
        return "search_knowledge"

    @property
    def description(self) -> str:
        return (
            "Searches the official clinic medical handbook, triage guide, and symptom glossary "
            "for symptoms, diseases, warning signs, recommended departments, or patient care questions."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The symptom or medical query (e.g. 'pain behind eyes high fever', 'loose motions vomiting')."
                },
                "k": {
                    "type": "integer",
                    "description": "Number of relevant chunks to retrieve (default: 3).",
                    "default": 3
                }
            },
            "required": ["query"]
        }

    def execute(self, **kwargs) -> Any:
        query = kwargs.get("query") or kwargs.get("query_text", "")
        k = int(kwargs.get("k") or kwargs.get("n_results", 3))
        return rag.search_knowledge(query=query, k=k)


class FindPatientTool(BaseTool):
    """Tool for looking up registered patients by phone number or name."""

    @property
    def name(self) -> str:
        return "find_patient"

    @property
    def description(self) -> str:
        return (
            "Searches for registered patients by phone number or full name. "
            "If duplicate names exist, returns all matches so the patient can be disambiguated."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Patient's phone number (e.g. '+91 90000 10111' or '9000010111') or full name."
                },
                "date_of_birth": {
                    "type": "string",
                    "description": "Optional date of birth (YYYY-MM-DD) to disambiguate patients sharing the same name."
                }
            },
            "required": ["query"]
        }

    def execute(self, **kwargs) -> Any:
        return db.find_patient(
            query=kwargs.get("query", ""),
            date_of_birth=kwargs.get("date_of_birth")
        )


class RegisterPatientTool(BaseTool):
    """Tool for registering new patients."""

    @property
    def name(self) -> str:
        return "register_patient"

    @property
    def description(self) -> str:
        return "Registers a new patient in clinic records."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "full_name": {"type": "string", "description": "Patient's full legal name."},
                "date_of_birth": {"type": "string", "description": "Date of birth in YYYY-MM-DD format."},
                "gender": {"type": "string", "enum": ["Female", "Male", "Other"], "description": "Gender."},
                "phone": {"type": "string", "description": "Phone number (must be unique)."},
                "email": {"type": "string", "description": "Optional email."},
                "address": {"type": "string", "description": "Optional home address."},
                "blood_group": {"type": "string", "description": "Optional blood group."},
                "allergies": {"type": "string", "description": "Known allergies.", "default": "None known"},
                "chronic_conditions": {"type": "string", "description": "Chronic conditions.", "default": "None"},
                "emergency_contact": {"type": "string", "description": "Optional emergency contact."}
            },
            "required": ["full_name", "date_of_birth", "gender", "phone"]
        }

    def execute(self, **kwargs) -> Any:
        return db.register_patient(
            full_name=kwargs.get("full_name", ""),
            date_of_birth=kwargs.get("date_of_birth", ""),
            gender=kwargs.get("gender", "Other"),
            phone=kwargs.get("phone", ""),
            email=kwargs.get("email"),
            address=kwargs.get("address"),
            blood_group=kwargs.get("blood_group"),
            allergies=kwargs.get("allergies", "None known"),
            chronic_conditions=kwargs.get("chronic_conditions", "None"),
            emergency_contact=kwargs.get("emergency_contact")
        )


class UpdatePatientTool(BaseTool):
    """Tool for updating existing patient records."""

    @property
    def name(self) -> str:
        return "update_patient"

    @property
    def description(self) -> str:
        return "Updates contact details, allergies, or chronic conditions for an existing patient."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer", "description": "Patient ID."},
                "phone": {"type": "string", "description": "New phone number."},
                "email": {"type": "string", "description": "New email address."},
                "address": {"type": "string", "description": "New address."},
                "allergies": {"type": "string", "description": "Updated allergies."},
                "chronic_conditions": {"type": "string", "description": "Updated chronic conditions."},
                "emergency_contact": {"type": "string", "description": "Updated emergency contact."}
            },
            "required": ["patient_id"]
        }

    def execute(self, **kwargs) -> Any:
        return db.update_patient(
            patient_id=int(kwargs["patient_id"]),
            phone=kwargs.get("phone"),
            email=kwargs.get("email"),
            address=kwargs.get("address"),
            allergies=kwargs.get("allergies"),
            chronic_conditions=kwargs.get("chronic_conditions"),
            emergency_contact=kwargs.get("emergency_contact")
        )


class ListDoctorsTool(BaseTool):
    """Tool for retrieving active doctor directory."""

    @property
    def name(self) -> str:
        return "list_doctors"

    @property
    def description(self) -> str:
        return "Lists active clinic doctors, optionally filtered by medical specialty (e.g. Pediatrics, Cardiology)."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "specialty": {"type": "string", "description": "Specialty name (e.g. 'Pediatrics', 'General Medicine')."}
            }
        }

    def execute(self, **kwargs) -> Any:
        return db.list_doctors(specialty=kwargs.get("specialty"))


class FindFreeSlotsTool(BaseTool):
    """Tool for locating open consultation slots."""

    @property
    def name(self) -> str:
        return "find_free_slots"

    @property
    def description(self) -> str:
        return (
            "Finds available appointment slots for a specific doctor or medical specialty between two dates (inclusive). "
            "Automatically enforces working days, slot lengths, and skips Sunday dates."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "doctor_id": {"type": "integer", "description": "Optional specific doctor ID."},
                "specialty": {"type": "string", "description": "Optional medical specialty."},
                "start_date": {"type": "string", "description": "Start date (YYYY-MM-DD)."},
                "end_date": {"type": "string", "description": "End date (YYYY-MM-DD)."}
            }
        }

    def execute(self, **kwargs) -> Any:
        doc_id = int(kwargs["doctor_id"]) if kwargs.get("doctor_id") else None
        return db.find_free_slots(
            doctor_id=doc_id,
            specialty=kwargs.get("specialty"),
            start_date=kwargs.get("start_date"),
            end_date=kwargs.get("end_date")
        )


class BookAppointmentTool(BaseTool):
    """Tool for booking a verified consultation slot."""

    @property
    def name(self) -> str:
        return "book_appointment"

    @property
    def description(self) -> str:
        return (
            "Books an appointment slot for a patient with a doctor. "
            "Saves the symptom complaint in both patient words and clinical terminology."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer", "description": "Registered patient ID."},
                "doctor_id": {"type": "integer", "description": "Doctor ID to book."},
                "appointment_date": {"type": "string", "description": "Appointment date (YYYY-MM-DD)."},
                "start_time": {"type": "string", "description": "Slot start time (HH:MM)."},
                "complaint_patient_words": {"type": "string", "description": "Complaint in patient's everyday words."},
                "complaint_clinical": {"type": "string", "description": "Complaint translated into clinical terms."},
                "suspected_conditions": {"type": "string", "description": "Suspected conditions (not a diagnosis)."},
                "urgency": {"type": "string", "enum": ["routine", "soon", "emergency"], "default": "routine"},
                "notes": {"type": "string", "description": "Optional scheduling notes."}
            },
            "required": ["patient_id", "doctor_id", "appointment_date", "start_time", "complaint_patient_words", "complaint_clinical"]
        }

    def execute(self, **kwargs) -> Any:
        return db.book_appointment(
            patient_id=int(kwargs["patient_id"]),
            doctor_id=int(kwargs["doctor_id"]),
            appointment_date=kwargs["appointment_date"],
            start_time=kwargs["start_time"],
            complaint_patient_words=kwargs["complaint_patient_words"],
            complaint_clinical=kwargs["complaint_clinical"],
            suspected_conditions=kwargs.get("suspected_conditions"),
            urgency=kwargs.get("urgency", "routine"),
            notes=kwargs.get("notes")
        )


class GetAppointmentsTool(BaseTool):
    """Tool for querying patient appointments."""

    @property
    def name(self) -> str:
        return "get_appointments"

    @property
    def description(self) -> str:
        return "Retrieves appointments for a patient (defaults to upcoming scheduled visits)."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patient_id": {"type": "integer", "description": "Patient ID."},
                "include_past": {"type": "boolean", "description": "True to include past/cancelled appointments.", "default": False}
            },
            "required": ["patient_id"]
        }

    def execute(self, **kwargs) -> Any:
        return db.get_appointments(
            patient_id=int(kwargs["patient_id"]),
            include_past=bool(kwargs.get("include_past", False))
        )


class RescheduleAppointmentTool(BaseTool):
    """Tool for rescheduling an existing appointment."""

    @property
    def name(self) -> str:
        return "reschedule_appointment"

    @property
    def description(self) -> str:
        return "Moves an existing scheduled appointment to a new date and time slot."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "integer", "description": "Appointment ID."},
                "new_date": {"type": "string", "description": "New date (YYYY-MM-DD)."},
                "new_start_time": {"type": "string", "description": "New time (HH:MM)."}
            },
            "required": ["appointment_id", "new_date", "new_start_time"]
        }

    def execute(self, **kwargs) -> Any:
        return db.reschedule_appointment(
            appointment_id=int(kwargs["appointment_id"]),
            new_date=kwargs["new_date"],
            new_start_time=kwargs["new_start_time"]
        )


class CancelAppointmentTool(BaseTool):
    """Tool for softly cancelling an appointment."""

    @property
    def name(self) -> str:
        return "cancel_appointment"

    @property
    def description(self) -> str:
        return "Cancels an appointment by setting its status to 'cancelled'. Never deletes rows."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "appointment_id": {"type": "integer", "description": "Appointment ID."},
                "reason": {"type": "string", "description": "Optional cancellation reason."}
            },
            "required": ["appointment_id"]
        }

    def execute(self, **kwargs) -> Any:
        return db.cancel_appointment(
            appointment_id=int(kwargs["appointment_id"]),
            reason=kwargs.get("reason")
        )


# =============================================================================
# 3. Tool Registry (Command / Registry Pattern)
# =============================================================================
class ToolRegistry:
    """Manages tool registration, schema export, and dynamic dispatching."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        """Instantiates and registers the 10 core clinical tools."""
        default_tools = [
            SearchKnowledgeTool(),
            FindPatientTool(),
            RegisterPatientTool(),
            UpdatePatientTool(),
            ListDoctorsTool(),
            FindFreeSlotsTool(),
            BookAppointmentTool(),
            GetAppointmentsTool(),
            RescheduleAppointmentTool(),
            CancelAppointmentTool()
        ]
        for tool in default_tools:
            self.register(tool)

    def register(self, tool: BaseTool) -> None:
        """Registers a tool instance."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        """Retrieves a registered tool by name."""
        return self._tools.get(name)

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Returns JSON function schemas for all registered tools."""
        return [tool.to_schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Dispatches execution to the corresponding tool instance."""
        tool = self.get(name)
        if not tool:
            # Check create_patient alias
            if name == "create_patient":
                tool = self.get("register_patient")
            if not tool:
                return {"success": False, "error": f"Unknown tool: '{name}'"}
        try:
            return tool.execute(**arguments)
        except Exception as e:
            return {"success": False, "error": f"Error executing tool '{name}': {str(e)}"}


# Singleton instance
tool_registry = ToolRegistry()

# Backward-compatible exports
TOOL_DEFINITIONS = tool_registry.get_schemas()
execute_tool = tool_registry.execute
