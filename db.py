import sqlite3
import os

DB_PATH = os.path.join("data", "clinic.db")

def get_connection():
    """Establishes a connection to the SQLite database file."""
    conn = sqlite3.connect(DB_PATH)
    # This row factory allows us to access columns by name (e.g., patient['name'])
    conn.row_factory = sqlite3.Row
    return conn

def find_patient_by_phone(phone_number: str):
    """Searches the database to see if a patient already exists by phone number."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM patients WHERE phone = ?", (phone_number,))
    patient = cursor.fetchone()
    
    conn.close()
    return dict(patient) if patient else None

def find_free_slots(department_name: str, date_str: str):
    """
    Finds available appointment slots for a specific medical department on a given date.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Query doctors in the given department and check unbooked slots
    query = """
        D
    """
    # We will expand this query to match the exact schema in data/README.md
    conn.close()