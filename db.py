"""
db.py - Object-Oriented Database Layer for CureSee Clinic (Sunrise Multispeciality Clinic).

Employs OOP principles:
- Encapsulation: Connection management and query execution encapsulated in repositories.
- Repository Pattern: PatientRepository, DoctorRepository, AppointmentRepository.
- Facade Pattern: ClinicDatabase provides a unified interface to the database subsystem.
- Parameterized SQL and constraint enforcement for clinical integrity.
"""

import os
import re
import sqlite3
import datetime as dt
from typing import Optional, List, Dict, Any, Tuple

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "clinic.db")


# =============================================================================
# 1. Connection Manager (Encapsulation)
# =============================================================================
class DatabaseConnectionManager:
    """Manages SQLite database connections."""

    def __init__(self, db_path: Optional[str] = None):
        self._db_path = db_path or DEFAULT_DB_PATH

    @property
    def db_path(self) -> str:
        return self._db_path

    def get_connection(self) -> sqlite3.Connection:
        """Creates and configures a new database connection."""
        conn = sqlite3.connect(self._db_path, timeout=10.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn


# =============================================================================
# 2. Base Repository (Inheritance & Abstraction)
# =============================================================================
class BaseRepository:
    """Abstract base repository providing shared database utilities and helpers."""

    def __init__(self, connection_manager: DatabaseConnectionManager):
        self._conn_mgr = connection_manager

    def _get_connection(self) -> sqlite3.Connection:
        return self._conn_mgr.get_connection()

    @staticmethod
    def _time_to_minutes(time_str: str) -> int:
        hours, minutes = map(int, time_str.split(":"))
        return hours * 60 + minutes

    @staticmethod
    def _minutes_to_time(minutes: int) -> str:
        h = minutes // 60
        m = minutes % 60
        return f"{h:02d}:{m:02d}"

    @staticmethod
    def _get_current_timestamp() -> str:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _format_doctor_title(name: str) -> str:
        name = name.strip()
        return name if name.startswith("Dr.") else f"Dr. {name}"


# =============================================================================
# 3. Patient Repository (Encapsulates Patient CRUD & Disambiguation)
# =============================================================================
class PatientRepository(BaseRepository):
    """Encapsulates all patient querying, registration, and update operations."""

    def find(self, query: str, date_of_birth: Optional[str] = None) -> Dict[str, Any]:
        """
        Finds patients by phone number or name.
        Handles disambiguation if multiple patients share the same name (e.g., 'Rahul Sharma').
        """
        if not query or not query.strip():
            return {"success": False, "error": "Query cannot be empty.", "count": 0, "patients": []}

        q = query.strip()
        digits = "".join(ch for ch in q if ch.isdigit())

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            patients: List[Dict[str, Any]] = []

            # 1. Phone search if query contains 6+ digits
            if len(digits) >= 6:
                cursor.execute(
                    """
                    SELECT * FROM patients
                    WHERE REPLACE(REPLACE(phone, ' ', ''), '+', '') LIKE ?
                       OR phone LIKE ?
                    """,
                    (f"%{digits}%", f"%{q}%")
                )
                patients.extend([dict(row) for row in cursor.fetchall()])

            # 2. Name search (case-insensitive substring)
            cursor.execute(
                "SELECT * FROM patients WHERE LOWER(full_name) LIKE ?",
                (f"%{q.lower()}%",)
            )
            for row in cursor.fetchall():
                row_dict = dict(row)
                if not any(p["patient_id"] == row_dict["patient_id"] for p in patients):
                    patients.append(row_dict)

            # 3. Optional date_of_birth filter for disambiguation
            if date_of_birth:
                patients = [p for p in patients if p.get("date_of_birth") == date_of_birth.strip()]

            if not patients:
                return {
                    "success": False,
                    "error": f"No patient found matching '{query}'.",
                    "count": 0,
                    "patients": []
                }

            if len(patients) == 1:
                return {
                    "success": True,
                    "count": 1,
                    "patient": patients[0],
                    "patients": patients
                }

            return {
                "success": True,
                "count": len(patients),
                "patients": patients,
                "message": (
                    f"Found {len(patients)} patients matching '{query}'. "
                    "Please verify date of birth or full phone number to identify the exact patient."
                )
            }
        finally:
            conn.close()

    def find_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Convenience method to retrieve a single patient by phone."""
        res = self.find(phone_number)
        if res.get("success") and res.get("patients"):
            return res["patients"][0]
        return None

    def register(
        self,
        full_name: str,
        date_of_birth: str,
        gender: str,
        phone: str,
        email: Optional[str] = None,
        address: Optional[str] = None,
        blood_group: Optional[str] = None,
        allergies: str = "None known",
        chronic_conditions: str = "None",
        emergency_contact: Optional[str] = None
    ) -> Dict[str, Any]:
        """Registers a new patient with validation and unique phone enforcement."""
        if not full_name or not full_name.strip():
            return {"success": False, "error": "full_name is required."}
        if not date_of_birth or not date_of_birth.strip():
            return {"success": False, "error": "date_of_birth is required (YYYY-MM-DD)."}
        if not phone or not phone.strip():
            return {"success": False, "error": "phone is required."}

        # Normalize and validate gender
        g = gender.strip().capitalize()
        if g not in ("Female", "Male", "Other"):
            return {"success": False, "error": f"Invalid gender '{gender}'. Must be 'Female', 'Male', or 'Other'."}

        # Validate date format
        try:
            dt.date.fromisoformat(date_of_birth.strip())
        except ValueError:
            return {"success": False, "error": f"Invalid date_of_birth '{date_of_birth}'. Format must be YYYY-MM-DD."}

        clean_phone = phone.strip()
        created_at = self._get_current_timestamp()

        conn = self._get_connection()
        try:
            with conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO patients (
                        full_name, date_of_birth, gender, phone, email, address,
                        blood_group, allergies, chronic_conditions, emergency_contact, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        full_name.strip(),
                        date_of_birth.strip(),
                        g,
                        clean_phone,
                        email.strip() if email else None,
                        address.strip() if address else None,
                        blood_group.strip() if blood_group else None,
                        allergies.strip() if allergies else "None known",
                        chronic_conditions.strip() if chronic_conditions else "None",
                        emergency_contact.strip() if emergency_contact else None,
                        created_at
                    )
                )
                patient_id = cursor.lastrowid

                cursor.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,))
                new_patient = dict(cursor.fetchone())
                return {
                    "success": True,
                    "message": f"Patient {full_name} successfully registered with ID {patient_id}.",
                    "patient": new_patient
                }
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: patients.phone" in str(e):
                return {
                    "success": False,
                    "error": f"A patient with phone number '{clean_phone}' is already registered."
                }
            return {"success": False, "error": f"Database integrity error: {str(e)}"}
        finally:
            conn.close()

    def update(
        self,
        patient_id: int,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        allergies: Optional[str] = None,
        chronic_conditions: Optional[str] = None,
        emergency_contact: Optional[str] = None
    ) -> Dict[str, Any]:
        """Updates contact details, allergies, or chronic conditions for a patient."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,))
            patient = cursor.fetchone()
            if not patient:
                return {"success": False, "error": f"Patient with ID {patient_id} not found."}

            updates = []
            params = []
            if phone is not None:
                updates.append("phone = ?")
                params.append(phone.strip())
            if email is not None:
                updates.append("email = ?")
                params.append(email.strip())
            if address is not None:
                updates.append("address = ?")
                params.append(address.strip())
            if allergies is not None:
                updates.append("allergies = ?")
                params.append(allergies.strip())
            if chronic_conditions is not None:
                updates.append("chronic_conditions = ?")
                params.append(chronic_conditions.strip())
            if emergency_contact is not None:
                updates.append("emergency_contact = ?")
                params.append(emergency_contact.strip())

            if not updates:
                return {"success": True, "message": "No fields to update.", "patient": dict(patient)}

            params.append(patient_id)
            query = f"UPDATE patients SET {', '.join(updates)} WHERE patient_id = ?"

            with conn:
                cursor.execute(query, params)
                cursor.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,))
                updated_patient = dict(cursor.fetchone())

            return {
                "success": True,
                "message": f"Patient {patient_id} updated successfully.",
                "patient": updated_patient
            }
        except sqlite3.IntegrityError as e:
            if "UNIQUE constraint failed: patients.phone" in str(e):
                return {"success": False, "error": f"Phone number '{phone}' is already in use by another patient."}
            return {"success": False, "error": f"Database integrity error: {str(e)}"}
        finally:
            conn.close()


# =============================================================================
# 4. Doctor Repository (Encapsulates Doctor Metadata & Directory)
# =============================================================================
class DoctorRepository(BaseRepository):
    """Encapsulates doctor directory queries and active status verification."""

    def list_active(self, specialty: Optional[str] = None) -> Dict[str, Any]:
        """Lists all active doctors (is_active = 1), optionally filtered by specialty."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            if specialty and specialty.strip():
                cursor.execute(

                    """
                    SELECT doctor_id, full_name, specialty, qualification, experience_years,
                           languages, room, consultation_fee, working_days, start_time, end_time, slot_minutes
                    FROM doctors
                    WHERE is_active = 1 AND LOWER(specialty) = LOWER(?)
                    ORDER BY full_name
                    """,
                    (specialty.strip(),)
                )
            else:
                cursor.execute(
                    """
                    SELECT doctor_id, full_name, specialty, qualification, experience_years,
                           languages, room, consultation_fee, working_days, start_time, end_time, slot_minutes
                    FROM doctors
                    WHERE is_active = 1
                    ORDER BY specialty, full_name
                    """
                )
            doctors = [dict(row) for row in cursor.fetchall()]
            return {
                "success": True,
                "count": len(doctors),
                "doctors": doctors
            }
        finally:
            conn.close()

    def get_by_id(self, doctor_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves a single doctor by ID."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM doctors WHERE doctor_id = ?", (doctor_id,))
            doc = cursor.fetchone()
            return dict(doc) if doc else None
        finally:
            conn.close()


# =============================================================================
# 5. Appointment Repository (Encapsulates Scheduling & Operational Rules)
# =============================================================================
class AppointmentRepository(BaseRepository):
    """Encapsulates slot computation, bookings, cancellations, and reschedules."""

    def __init__(self, connection_manager: DatabaseConnectionManager, clinic_db: "ClinicDatabase"):
        super().__init__(connection_manager)
        self._clinic_db = clinic_db

    def find_free_slots(
        self,
        doctor_id: Optional[int] = None,
        specialty: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculates open consultation slots across operating hours, doctor working days,
        and slot lengths. Automatically skips Sunday dates and booked intervals.
        """
        data_today = self._clinic_db.get_data_today()

        start_str = start_date.strip() if start_date else data_today
        if start_str < data_today:
            start_str = data_today

        end_str = end_date.strip() if end_date else start_str
        if end_str < start_str:
            end_str = start_str

        try:
            start_d = dt.date.fromisoformat(start_str)
            end_d = dt.date.fromisoformat(end_str)
        except ValueError:
            return {"success": False, "error": "Invalid date format. Must be YYYY-MM-DD."}

        # Restrict date span to a maximum of 14 days
        if (end_d - start_d).days > 14:
            end_d = start_d + dt.timedelta(days=14)
            end_str = end_d.isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Filter active doctors
            if doctor_id:
                cursor.execute("SELECT * FROM doctors WHERE doctor_id = ? AND is_active = 1", (doctor_id,))
            elif specialty and specialty.strip():
                cursor.execute(
                    "SELECT * FROM doctors WHERE LOWER(specialty) = LOWER(?) AND is_active = 1",
                    (specialty.strip(),)
                )
            else:
                cursor.execute("SELECT * FROM doctors WHERE is_active = 1")

            doctors = [dict(r) for r in cursor.fetchall()]
            if not doctors:
                if doctor_id:
                    return {"success": False, "error": f"Doctor ID {doctor_id} not found or is currently inactive."}
                elif specialty:
                    return {"success": False, "error": f"No active doctors found in specialty '{specialty}'."}
                return {"success": False, "error": "No active doctors found."}

            results = []
            total_slots_count = 0

            cur_d = start_d
            while cur_d <= end_d:
                cur_date_str = cur_d.isoformat()
                weekday = cur_d.strftime("%a")

                if weekday == "Sun":
                    # Clinic is closed on Sundays
                    cur_d += dt.timedelta(days=1)
                    continue

                for doc in doctors:
                    doc_working_days = [d.strip() for d in doc["working_days"].split(",")]
                    if weekday not in doc_working_days:
                        continue

                    cursor.execute(
                        """
                        SELECT start_time FROM appointments
                        WHERE doctor_id = ? AND appointment_date = ? AND status IN ('scheduled', 'completed')
                        """,
                        (doc["doctor_id"], cur_date_str)
                    )
                    booked_slots = set(r["start_time"] for r in cursor.fetchall())

                    start_mins = self._time_to_minutes(doc["start_time"])
                    end_mins = self._time_to_minutes(doc["end_time"])
                    slot_mins = doc["slot_minutes"]

                    free_slots = []
                    cur_mins = start_mins
                    while cur_mins + slot_mins <= end_mins:
                        slot_str = self._minutes_to_time(cur_mins)
                        if slot_str not in booked_slots:
                            free_slots.append(slot_str)
                        cur_mins += slot_mins

                    if free_slots:
                        total_slots_count += len(free_slots)
                        results.append({
                            "doctor_id": doc["doctor_id"],
                            "doctor_name": doc["full_name"],
                            "specialty": doc["specialty"],
                            "room": doc["room"],
                            "date": cur_date_str,
                            "weekday": weekday,
                            "slot_duration_minutes": slot_mins,
                            "available_slots": free_slots
                        })

                cur_d += dt.timedelta(days=1)

            return {
                "success": True,
                "data_today": data_today,
                "start_date": start_str,
                "end_date": end_str,
                "total_slots": total_slots_count,
                "availability": results
            }
        finally:
            conn.close()

    def book(
        self,
        patient_id: int,
        doctor_id: int,
        appointment_date: str,
        start_time: str,
        complaint_patient_words: str,
        complaint_clinical: str,
        suspected_conditions: Optional[str] = None,
        urgency: str = "routine",
        notes: Optional[str] = None,
        booked_by: str = "ai_agent"
    ) -> Dict[str, Any]:
        """
        Books an appointment with full constraint checking:
        - Rejects past bookings
        - Rejects Sunday dates
        - Enforces doctor working days and slot boundaries
        - Catches unique slot conflicts and suggests nearby free slots
        """
        data_today = self._clinic_db.get_data_today()
        clean_date = appointment_date.strip()
        clean_time = start_time.strip()

        # 1. Past booking check
        if clean_date < data_today:
            return {
                "success": False,
                "error": f"Cannot book appointments in the past (requested: {clean_date}, clinic date: {data_today})."
            }

        # 2. Date parsing & Sunday closure check
        try:
            app_d = dt.date.fromisoformat(clean_date)
        except ValueError:
            return {"success": False, "error": f"Invalid date format '{clean_date}'. Format must be YYYY-MM-DD."}

        weekday = app_d.strftime("%a")
        if weekday == "Sun":
            return {
                "success": False,
                "error": f"The clinic is closed on Sundays ({clean_date}). Appointments are available Monday through Saturday."
            }

        if urgency not in ("routine", "soon", "emergency"):
            urgency = "routine"

        if booked_by not in ("front_desk", "ai_agent", "patient_portal"):
            booked_by = "ai_agent"

        conn = self._get_connection()
        try:
            cursor = conn.cursor()

            # Verify patient
            cursor.execute("SELECT * FROM patients WHERE patient_id = ?", (patient_id,))
            patient = cursor.fetchone()
            if not patient:
                return {"success": False, "error": f"Patient with ID {patient_id} does not exist."}

            # Verify doctor
            cursor.execute("SELECT * FROM doctors WHERE doctor_id = ?", (doctor_id,))
            doctor = cursor.fetchone()
            if not doctor:
                return {"success": False, "error": f"Doctor with ID {doctor_id} does not exist."}
            if not doctor["is_active"]:
                return {
                    "success": False,
                    "error": f"{self._format_doctor_title(doctor['full_name'])} is currently inactive and not accepting appointments."
                }

            # Verify working days
            working_days = [w.strip() for w in doctor["working_days"].split(",")]
            if weekday not in working_days:
                return {
                    "success": False,
                    "error": f"{self._format_doctor_title(doctor['full_name'])} does not consult on {weekday}s. Working days: {doctor['working_days']}."
                }

            # Verify time and slot boundaries
            start_mins = self._time_to_minutes(doctor["start_time"])
            end_mins = self._time_to_minutes(doctor["end_time"])
            slot_mins = doctor["slot_minutes"]

            try:
                req_start_mins = self._time_to_minutes(clean_time)
            except Exception:
                return {"success": False, "error": f"Invalid time format '{clean_time}'. Format must be HH:MM."}

            if req_start_mins < start_mins or (req_start_mins + slot_mins) > end_mins:
                return {
                    "success": False,
                    "error": f"Time {clean_time} is outside {self._format_doctor_title(doctor['full_name'])}'s working hours ({doctor['start_time']} to {doctor['end_time']})."
                }

            if (req_start_mins - start_mins) % slot_mins != 0:
                return {
                    "success": False,
                    "error": f"Time {clean_time} does not align with {self._format_doctor_title(doctor['full_name'])}'s {slot_mins}-minute slot intervals starting at {doctor['start_time']}."
                }

            end_time_str = self._minutes_to_time(req_start_mins + slot_mins)
            now_ts = self._get_current_timestamp()

            # Attempt insert
            try:
                with conn:
                    cursor.execute(
                        """
                        INSERT INTO appointments (
                            patient_id, doctor_id, appointment_date, start_time, end_time,
                            status, urgency, complaint_patient_words, complaint_clinical,
                            suspected_conditions, booked_by, notes, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            patient_id,
                            doctor_id,
                            clean_date,
                            clean_time,
                            end_time_str,
                            urgency,
                            complaint_patient_words.strip(),
                            complaint_clinical.strip(),
                            suspected_conditions.strip() if suspected_conditions else None,
                            booked_by,
                            notes.strip() if notes else None,
                            now_ts,
                            now_ts
                        )
                    )
                    appointment_id = cursor.lastrowid

                return {
                    "success": True,
                    "message": f"Appointment successfully booked with {self._format_doctor_title(doctor['full_name'])}.",
                    "appointment": {
                        "id": appointment_id,
                        "doctor": doctor["full_name"],
                        "specialty": doctor["specialty"],
                        "room": doctor["room"],
                        "date": clean_date,
                        "start_time": clean_time,
                        "end_time": end_time_str,
                        "status": "scheduled",
                        "urgency": urgency,
                        "patient_id": patient_id,
                        "patient_name": patient["full_name"],
                        "complaint_clinical": complaint_clinical.strip()
                    }
                }
            except sqlite3.IntegrityError:
                # Catch unique slot collision
                nearby = self.find_free_slots(
                    doctor_id=doctor_id,
                    start_date=clean_date,
                    end_date=clean_date
                )
                suggested = []
                if nearby.get("success") and nearby.get("availability"):
                    suggested = nearby["availability"][0].get("available_slots", [])[:4]

                suggest_msg = f" Free slots nearby on {clean_date} are: {', '.join(suggested)}." if suggested else ""
                return {
                    "success": False,
                    "error": f"That slot ({clean_date} at {clean_time}) was just taken.{suggest_msg}",
                    "suggested_slots": suggested
                }
        finally:
            conn.close()

    def get_by_patient(self, patient_id: int, include_past: bool = False) -> Dict[str, Any]:
        """Retrieves patient appointments from appointment_details view."""
        data_today = self._clinic_db.get_data_today()
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT full_name FROM patients WHERE patient_id = ?", (patient_id,))
            p_row = cursor.fetchone()
            if not p_row:
                return {"success": False, "error": f"Patient with ID {patient_id} not found."}

            if include_past:
                cursor.execute(
                    """
                    SELECT * FROM appointment_details
                    WHERE patient_id = ?
                    ORDER BY appointment_date DESC, start_time DESC
                    """,
                    (patient_id,)
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM appointment_details
                    WHERE patient_id = ? AND status = 'scheduled' AND appointment_date >= ?
                    ORDER BY appointment_date ASC, start_time ASC
                    """,
                    (patient_id, data_today)
                )

            appointments = [dict(r) for r in cursor.fetchall()]
            return {
                "success": True,
                "patient_id": patient_id,
                "patient_name": p_row["full_name"],
                "count": len(appointments),
                "appointments": appointments
            }
        finally:
            conn.close()

    def reschedule(self, appointment_id: int, new_date: str, new_start_time: str) -> Dict[str, Any]:
        """Moves an existing scheduled appointment to a new date and time slot."""
        data_today = self._clinic_db.get_data_today()
        clean_date = new_date.strip()
        clean_time = new_start_time.strip()

        if clean_date < data_today:
            return {
                "success": False,
                "error": f"Cannot reschedule to a past date (requested: {clean_date}, clinic date: {data_today})."
            }

        try:
            app_d = dt.date.fromisoformat(clean_date)
        except ValueError:
            return {"success": False, "error": f"Invalid date format '{clean_date}'. Format must be YYYY-MM-DD."}

        weekday = app_d.strftime("%a")
        if weekday == "Sun":
            return {"success": False, "error": f"The clinic is closed on Sundays ({clean_date})."}

        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM appointments WHERE appointment_id = ?", (appointment_id,))
            app = cursor.fetchone()
            if not app:
                return {"success": False, "error": f"Appointment with ID {appointment_id} does not exist."}

            if app["status"] != "scheduled":
                return {
                    "success": False,
                    "error": f"Cannot reschedule appointment {appointment_id} because its current status is '{app['status']}'."
                }

            doctor_id = app["doctor_id"]
            cursor.execute("SELECT * FROM doctors WHERE doctor_id = ?", (doctor_id,))
            doctor = cursor.fetchone()
            if not doctor or not doctor["is_active"]:
                return {"success": False, "error": "The assigned doctor is inactive or not found."}

            working_days = [w.strip() for w in doctor["working_days"].split(",")]
            if weekday not in working_days:
                return {
                    "success": False,
                    "error": f"{self._format_doctor_title(doctor['full_name'])} does not consult on {weekday}s. Working days: {doctor['working_days']}."
                }

            start_mins = self._time_to_minutes(doctor["start_time"])
            end_mins = self._time_to_minutes(doctor["end_time"])
            slot_mins = doctor["slot_minutes"]

            try:
                req_start_mins = self._time_to_minutes(clean_time)
            except Exception:
                return {"success": False, "error": f"Invalid time format '{clean_time}'. Format must be HH:MM."}

            if req_start_mins < start_mins or (req_start_mins + slot_mins) > end_mins:
                return {
                    "success": False,
                    "error": f"Time {clean_time} is outside {self._format_doctor_title(doctor['full_name'])}'s working hours ({doctor['start_time']} to {doctor['end_time']})."
                }

            if (req_start_mins - start_mins) % slot_mins != 0:
                return {
                    "success": False,
                    "error": f"Time {clean_time} does not align with {self._format_doctor_title(doctor['full_name'])}'s {slot_mins}-minute slot intervals."
                }

            new_end_time = self._minutes_to_time(req_start_mins + slot_mins)
            now_ts = self._get_current_timestamp()

            try:
                with conn:
                    cursor.execute(
                        """
                        UPDATE appointments
                        SET appointment_date = ?, start_time = ?, end_time = ?, updated_at = ?
                        WHERE appointment_id = ?
                        """,
                        (clean_date, clean_time, new_end_time, now_ts, appointment_id)
                    )

                return {
                    "success": True,
                    "message": f"Appointment {appointment_id} successfully rescheduled to {clean_date} at {clean_time}.",
                    "appointment": {
                        "id": appointment_id,
                        "doctor": doctor["full_name"],
                        "specialty": doctor["specialty"],
                        "date": clean_date,
                        "start_time": clean_time,
                        "end_time": new_end_time,
                        "status": "scheduled"
                    }
                }
            except sqlite3.IntegrityError:
                nearby = self.find_free_slots(
                    doctor_id=doctor_id,
                    start_date=clean_date,
                    end_date=clean_date
                )
                suggested = []
                if nearby.get("success") and nearby.get("availability"):
                    suggested = nearby["availability"][0].get("available_slots", [])[:4]

                suggest_msg = f" Free slots nearby on {clean_date} are: {', '.join(suggested)}." if suggested else ""
                return {
                    "success": False,
                    "error": f"Slot {clean_date} at {clean_time} was just taken.{suggest_msg}",
                    "suggested_slots": suggested
                }
        finally:
            conn.close()

    def cancel(self, appointment_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
        """Cancels an appointment by setting status = 'cancelled'. Never deletes rows."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT a.*, d.full_name as doctor_name, d.specialty
                FROM appointments a
                JOIN doctors d ON d.doctor_id = a.doctor_id
                WHERE a.appointment_id = ?
                """,
                (appointment_id,)
            )
            app = cursor.fetchone()
            if not app:
                return {"success": False, "error": f"Appointment with ID {appointment_id} does not exist."}

            if app["status"] == "cancelled":
                return {
                    "success": True,
                    "message": f"Appointment {appointment_id} is already cancelled.",
                    "appointment": {
                        "id": appointment_id,
                        "doctor": app["doctor_name"],
                        "specialty": app["specialty"],
                        "date": app["appointment_date"],
                        "start_time": app["start_time"],
                        "status": "cancelled"
                    }
                }

            now_ts = self._get_current_timestamp()
            old_notes = app["notes"] or ""
            cancel_note = f"Cancelled: {reason.strip()}" if reason and reason.strip() else "Cancelled by patient"
            new_notes = f"{old_notes}; {cancel_note}".strip("; ")

            with conn:
                cursor.execute(
                    """
                    UPDATE appointments
                    SET status = 'cancelled', notes = ?, updated_at = ?
                    WHERE appointment_id = ?
                    """,
                    (new_notes, now_ts, appointment_id)
                )

            return {
                "success": True,
                "message": f"Appointment {appointment_id} successfully cancelled.",
                "appointment": {
                    "id": appointment_id,
                    "doctor": app["doctor_name"],
                    "specialty": app["specialty"],
                    "date": app["appointment_date"],
                    "start_time": app["start_time"],
                    "status": "cancelled"
                }
            }
        finally:
            conn.close()


# =============================================================================
# 6. Clinic Database Facade (Coordinates Repositories & System State)
# =============================================================================
class ClinicDatabase:
    """
    Facade class managing database subsystems, repositories, and clinic metadata.
    """

    def __init__(self, db_path: Optional[str] = None):
        self._conn_mgr = DatabaseConnectionManager(db_path)
        self.patients = PatientRepository(self._conn_mgr)
        self.doctors = DoctorRepository(self._conn_mgr)
        self.appointments = AppointmentRepository(self._conn_mgr, self)

    def get_connection(self) -> sqlite3.Connection:
        """Returns a managed sqlite3 connection."""
        return self._conn_mgr.get_connection()

    def get_clinic_info(self) -> Dict[str, str]:
        """Returns key-value configuration facts from clinic_info."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM clinic_info")
            return {row["key"]: row["value"] for row in cursor.fetchall()}
        finally:
            conn.close()

    def get_data_today(self) -> str:
        """Returns the simulated clinic reference date ('YYYY-MM-DD')."""
        conn = self.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM clinic_info WHERE key = 'data_today'")
            row = cursor.fetchone()
            return row["value"] if row else dt.date.today().isoformat()
        finally:
            conn.close()


# =============================================================================
# 7. Default Singleton & Backward-Compatible Module Functions
# =============================================================================
# Default instance
clinic_db = ClinicDatabase()

# Factory/helper
def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    if db_path:
        return DatabaseConnectionManager(db_path).get_connection()
    return clinic_db.get_connection()

def get_clinic_info(db_path: Optional[str] = None) -> Dict[str, str]:
    if db_path:
        return ClinicDatabase(db_path).get_clinic_info()
    return clinic_db.get_clinic_info()

def get_data_today(db_path: Optional[str] = None) -> str:
    if db_path:
        return ClinicDatabase(db_path).get_data_today()
    return clinic_db.get_data_today()

# Tool 1: find_patient
def find_patient(query: str, date_of_birth: Optional[str] = None, db_path: Optional[str] = None) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.patients.find(query, date_of_birth=date_of_birth)

def find_patient_by_phone(phone_number: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.patients.find_by_phone(phone_number)

# Tool 2: register_patient
def register_patient(
    full_name: str,
    date_of_birth: str,
    gender: str,
    phone: str,
    email: Optional[str] = None,
    address: Optional[str] = None,
    blood_group: Optional[str] = None,
    allergies: str = "None known",
    chronic_conditions: str = "None",
    emergency_contact: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.patients.register(
        full_name=full_name,
        date_of_birth=date_of_birth,
        gender=gender,
        phone=phone,
        email=email,
        address=address,
        blood_group=blood_group,
        allergies=allergies,
        chronic_conditions=chronic_conditions,
        emergency_contact=emergency_contact
    )

create_patient = register_patient

# Tool 3: update_patient
def update_patient(
    patient_id: int,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    address: Optional[str] = None,
    allergies: Optional[str] = None,
    chronic_conditions: Optional[str] = None,
    emergency_contact: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.patients.update(
        patient_id=patient_id,
        phone=phone,
        email=email,
        address=address,
        allergies=allergies,
        chronic_conditions=chronic_conditions,
        emergency_contact=emergency_contact
    )

# Tool 4: list_doctors
def list_doctors(specialty: Optional[str] = None, db_path: Optional[str] = None) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.doctors.list_active(specialty=specialty)

# Tool 5: find_free_slots
def find_free_slots(
    doctor_id: Optional[int] = None,
    specialty: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.appointments.find_free_slots(
        doctor_id=doctor_id,
        specialty=specialty,
        start_date=start_date,
        end_date=end_date
    )

# Tool 6: book_appointment
def book_appointment(
    patient_id: int,
    doctor_id: int,
    appointment_date: str,
    start_time: str,
    complaint_patient_words: str,
    complaint_clinical: str,
    suspected_conditions: Optional[str] = None,
    urgency: str = "routine",
    notes: Optional[str] = None,
    booked_by: str = "ai_agent",
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.appointments.book(
        patient_id=patient_id,
        doctor_id=doctor_id,
        appointment_date=appointment_date,
        start_time=start_time,
        complaint_patient_words=complaint_patient_words,
        complaint_clinical=complaint_clinical,
        suspected_conditions=suspected_conditions,
        urgency=urgency,
        notes=notes,
        booked_by=booked_by
    )

# Tool 7: get_appointments
def get_appointments(patient_id: int, include_past: bool = False, db_path: Optional[str] = None) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.appointments.get_by_patient(patient_id=patient_id, include_past=include_past)

# Tool 8: reschedule_appointment
def reschedule_appointment(
    appointment_id: int,
    new_date: str,
    new_start_time: str,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.appointments.reschedule(
        appointment_id=appointment_id,
        new_date=new_date,
        new_start_time=new_start_time
    )

# Tool 9: cancel_appointment
def cancel_appointment(
    appointment_id: int,
    reason: Optional[str] = None,
    db_path: Optional[str] = None
) -> Dict[str, Any]:
    db_inst = ClinicDatabase(db_path) if db_path else clinic_db
    return db_inst.appointments.cancel(appointment_id=appointment_id, reason=reason)
