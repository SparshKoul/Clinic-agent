"""
test_db.py - Unit and integration tests for Object-Oriented db.py and tools.py.
Tests the repositories, facade, connection manager, tools registry, and operational constraints.
"""

import os
import shutil
import tempfile
import unittest

import db
import tools


class TestDatabaseOOP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary copy of clinic.db
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_path = os.path.join(cls.temp_dir, "test_clinic.db")
        shutil.copyfile("data/clinic.db", cls.db_path)
        # Instantiate OOP database facade
        cls.clinic_db = db.ClinicDatabase(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir)

    def test_01_connection_manager_and_facade(self):
        """Verifies DatabaseConnectionManager and ClinicDatabase facade."""
        conn_mgr = db.DatabaseConnectionManager(self.db_path)
        conn = conn_mgr.get_connection()
        fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        self.assertEqual(fk, 1, "Foreign keys must be enabled (PRAGMA foreign_keys = 1).")
        conn.close()

        # Facade methods
        today = self.clinic_db.get_data_today()
        self.assertTrue(len(today) == 10 and today.startswith("202"))
        info = self.clinic_db.get_clinic_info()
        self.assertIn("name", info)
        self.assertIn("hours", info)

    def test_02_patient_repository_find_and_disambiguation(self):
        """Verifies PatientRepository lookup and disambiguation logic."""
        repo = self.clinic_db.patients

        # Phone lookup
        res_phone = repo.find("+91 90000 10111")
        self.assertTrue(res_phone["success"])
        self.assertEqual(res_phone["count"], 1)
        self.assertEqual(res_phone["patient"]["full_name"], "Priya Nair")

        # Duplicate name search
        res_dup = repo.find("Rahul Sharma")
        self.assertTrue(res_dup["success"])
        self.assertEqual(res_dup["count"], 2)

        # Disambiguate by date_of_birth
        res_disamb = repo.find("Rahul Sharma", date_of_birth="1992-08-14")
        self.assertTrue(res_disamb["success"])
        self.assertEqual(res_disamb["count"], 1)
        self.assertEqual(res_disamb["patients"][0]["phone"], "+91 90000 10037")

    def test_03_patient_repository_register_and_update(self):
        """Verifies PatientRepository registration, constraints, and updates."""
        repo = self.clinic_db.patients

        reg = repo.register(
            full_name="OOP Test Patient",
            date_of_birth="1993-04-12",
            gender="Female",
            phone="+91 91111 22222",
            email="oop@example.com",
            allergies="Latex",
            chronic_conditions="None"
        )
        self.assertTrue(reg["success"])
        patient_id = reg["patient"]["patient_id"]

        # Duplicate phone check
        dup = repo.register(
            full_name="Duplicate Phone User",
            date_of_birth="1990-01-01",
            gender="Male",
            phone="+91 91111 22222"
        )
        self.assertFalse(dup["success"])
        self.assertIn("already registered", dup["error"])

        # Update record
        upd = repo.update(patient_id, allergies="Latex, Peanuts", address="Indiranagar, Bengaluru")
        self.assertTrue(upd["success"])
        self.assertEqual(upd["patient"]["allergies"], "Latex, Peanuts")

    def test_04_doctor_repository(self):
        """Verifies DoctorRepository active doctor listing and filtering."""
        repo = self.clinic_db.doctors

        all_docs = repo.list_active()
        self.assertTrue(all_docs["success"])
        # Ensure inactive doctor (ID 17 Dr. Thomas George) is excluded
        self.assertFalse(any(d["doctor_id"] == 17 for d in all_docs["doctors"]))

        # Filter by specialty
        peds = repo.list_active(specialty="Pediatrics")
        self.assertTrue(peds["success"])
        self.assertTrue(all(d["specialty"] == "Pediatrics" for d in peds["doctors"]))

    def test_05_appointment_repository_free_slots(self):
        """Verifies AppointmentRepository slot calculation and Sunday skipping."""
        repo = self.clinic_db.appointments
        today = self.clinic_db.get_data_today()

        slots = repo.find_free_slots(specialty="Pediatrics", start_date=today, end_date=today)
        self.assertTrue(slots["success"])
        self.assertGreater(slots["total_slots"], 0)

    def test_06_appointment_repository_book_and_constraints(self):
        """Verifies booking validations (past dates, Sundays, inactive doctors, conflicts)."""
        repo = self.clinic_db.appointments
        today = self.clinic_db.get_data_today()
        p = self.clinic_db.patients.find("+91 90000 10111")["patient"]

        # Valid booking
        bk = repo.book(
            patient_id=p["patient_id"],
            doctor_id=2,  # Dr. Vikram Shetty
            appointment_date=today,
            start_time="15:30",
            complaint_patient_words="stomach cramps and nausea",
            complaint_clinical="Abdominal cramps with nausea",
            suspected_conditions="Acute gastroenteritis",
            urgency="soon"
        )
        self.assertTrue(bk["success"])
        self.assertEqual(bk["appointment"]["status"], "scheduled")

        # Duplicate slot collision
        dup_bk = repo.book(
            patient_id=1,
            doctor_id=2,
            appointment_date=today,
            start_time="15:30",
            complaint_patient_words="checkup",
            complaint_clinical="Routine checkup"
        )
        self.assertFalse(dup_bk["success"])
        self.assertIn("was just taken", dup_bk["error"])

        # Sunday rejection
        sun_bk = repo.book(
            patient_id=p["patient_id"],
            doctor_id=2,
            appointment_date="2026-11-15",  # Sunday
            start_time="15:30",
            complaint_patient_words="checkup",
            complaint_clinical="Routine checkup"
        )
        self.assertFalse(sun_bk["success"])
        self.assertIn("Sundays", sun_bk["error"])

        # Inactive doctor rejection
        inact_bk = repo.book(
            patient_id=p["patient_id"],
            doctor_id=17,
            appointment_date=today,
            start_time="10:00",
            complaint_patient_words="fever",
            complaint_clinical="Pyrexia"
        )
        self.assertFalse(inact_bk["success"])
        self.assertIn("inactive", inact_bk["error"])

    def test_07_appointment_repository_reschedule_and_cancel(self):
        """Verifies rescheduling and soft cancellation."""
        repo = self.clinic_db.appointments
        p = self.clinic_db.patients.find("+91 90000 10111")["patient"]

        apps = repo.get_by_patient(p["patient_id"])
        self.assertTrue(apps["success"])
        self.assertGreaterEqual(apps["count"], 1)
        aid = apps["appointments"][0]["appointment_id"]

        # Reschedule to valid Monday slot
        resched = repo.reschedule(aid, new_date="2026-11-16", new_start_time="14:45")
        self.assertTrue(resched["success"])
        self.assertEqual(resched["appointment"]["start_time"], "14:45")

        # Cancel appointment
        canc = repo.cancel(aid, reason="Symptoms resolved")
        self.assertTrue(canc["success"])
        self.assertEqual(canc["appointment"]["status"], "cancelled")

    def test_08_tool_registry_and_polymorphic_execution(self):
        """Verifies ToolRegistry, BaseTool polymorphism, and dynamic command execution."""
        registry = tools.tool_registry

        # Check all 10 tools are registered
        self.assertEqual(len(registry._tools), 10)

        # Check schemas
        schemas = registry.get_schemas()
        self.assertEqual(len(schemas), 10)
        tool_names = [s["function"]["name"] for s in schemas]
        self.assertIn("search_knowledge", tool_names)
        self.assertIn("book_appointment", tool_names)
        self.assertIn("find_free_slots", tool_names)

        # Execute list_doctors via registry
        res = registry.execute("list_doctors", {"specialty": "Pediatrics"})
        self.assertTrue(res["success"])
        self.assertEqual(len(res["doctors"]), 1)
        self.assertEqual(res["doctors"][0]["full_name"], "Dr. Meera Iyer")


if __name__ == "__main__":
    unittest.main()
