# clinic.db: the clinic's database

`clinic.db` is a SQLite file for **Sunrise Multispeciality Clinic**, a made-up clinic in Bengaluru. Every person, phone number and address in it is fictional.

Open it with Python's built-in `sqlite3` module, the `sqlite3` command line, or a viewer such as DB Browser for SQLite.

**First, run this once** so the appointment dates match this week:

```
python3 tools/refresh_dates.py data/clinic.db
```

It moves every date forward by whole weeks. The data's "today" is stored in `clinic_info`, under the key `data_today`.

## Tables

### doctors (17 rows)

| Column | Type | Meaning |
| --- | --- | --- |
| doctor_id | INTEGER | Primary key |
| full_name | TEXT | e.g. Dr. Ananya Rao |
| specialty | TEXT | One of 14 departments, such as General Medicine, Pediatrics, Cardiology, ENT |
| qualification | TEXT | e.g. MBBS, MD (General Medicine) |
| experience_years | INTEGER | Years of practice |
| languages | TEXT | Comma-separated, e.g. English,Kannada,Hindi |
| room | TEXT | Consulting room |
| phone, email | TEXT | Contact details |
| consultation_fee | INTEGER | In rupees |
| working_days | TEXT | Comma-separated weekdays, e.g. Mon,Wed,Fri |
| start_time, end_time | TEXT | 'HH:MM'. The first slot starts at start_time, and the last slot must end by end_time. |
| slot_minutes | INTEGER | Length of one appointment: 15, 20 or 30 |
| is_active | INTEGER | 1 if taking appointments, 0 if not. One doctor is inactive. |

### patients (60 rows)

| Column | Type | Meaning |
| --- | --- | --- |
| patient_id | INTEGER | Primary key |
| full_name | TEXT | Two patients share the name "Rahul Sharma" |
| date_of_birth | TEXT | 'YYYY-MM-DD'. Some patients are children. |
| gender | TEXT | Female, Male or Other |
| phone | TEXT | Unique. The best way to find a returning patient. |
| email, address, blood_group | TEXT | May be empty |
| allergies | TEXT | 'None known' if none |
| chronic_conditions | TEXT | 'None' if none, e.g. 'Type 2 diabetes; Hypertension' |
| emergency_contact | TEXT | Name, relation and phone |
| created_at | TEXT | 'YYYY-MM-DD HH:MM:SS' |

### appointments (about 200 rows)

| Column | Type | Meaning |
| --- | --- | --- |
| appointment_id | INTEGER | Primary key |
| patient_id | INTEGER | Points to patients |
| doctor_id | INTEGER | Points to doctors |
| appointment_date | TEXT | 'YYYY-MM-DD' |
| start_time, end_time | TEXT | 'HH:MM'. end_time is start_time plus the doctor's slot_minutes. |
| status | TEXT | scheduled, completed, cancelled or no_show |
| urgency | TEXT | routine, soon (within 24 to 48 hours) or emergency |
| complaint_patient_words | TEXT | What the patient said, in their own words |
| complaint_clinical | TEXT | The same complaint in clinical terms |
| suspected_conditions | TEXT | Possibilities, separated by '; '. Not a diagnosis. |
| booked_by | TEXT | front_desk, ai_agent or patient_portal. Your agent uses ai_agent. |
| notes | TEXT | The doctor's notes after a visit, or why an appointment was cancelled |
| created_at, updated_at | TEXT | 'YYYY-MM-DD HH:MM:SS' |

### clinic_info

Key-value facts about the clinic: name, address, phone, opening hours, `emergency_note` and `data_today`.

### appointment_details (a view)

Appointments joined with the patient's and doctor's names, which is handy for reading.

## Rules the data follows (your code must keep them)

1. **One live booking per slot.** A unique index allows only one `scheduled` or `completed` appointment per doctor, date and start time. Booking a taken slot raises `sqlite3.IntegrityError`. A `cancelled` appointment frees its slot.
2. **Inside working hours only.** A booking must be on one of the doctor's `working_days`, between `start_time` and `end_time`, on a slot boundary. For a 20-minute doctor starting at 10:00, the slots are 10:00, 10:20, 10:40 and so on.
3. **Never delete an appointment.** Cancelling sets `status = 'cancelled'` and updates `updated_at`.
4. **No bookings in the past, none on Sundays (the clinic is closed), and none with inactive doctors.**
5. Turn on foreign keys in every connection: `PRAGMA foreign_keys = ON;`

## Example rows

What a good booking looks like. The patient's words are kept as they were said, and the clinical version is written for the doctor:

| complaint_patient_words | complaint_clinical | suspected_conditions |
| --- | --- | --- |
| loose motions 6 times since morning and vomiting twice | Acute diarrhea (6 episodes) with emesis x2 since morning | Acute gastroenteritis |
| one side of my head throbs, I vomit and light hurts my eyes | Unilateral pulsatile headache with vomiting and photophobia | Migraine |
| chest feels heavy when I walk fast, goes away when I rest | Exertional chest heaviness relieved by rest, query stable angina | Coronary artery disease; Stable angina |

## Handy queries

```sql
-- Active doctors in a department
SELECT doctor_id, full_name, working_days, start_time, end_time, slot_minutes
FROM doctors WHERE specialty = 'Pediatrics' AND is_active = 1;

-- Slots already taken for a doctor on a day
SELECT start_time FROM appointments
WHERE doctor_id = ? AND appointment_date = ? AND status IN ('scheduled', 'completed');

-- A patient's upcoming appointments
SELECT * FROM appointment_details
WHERE patient_id = ? AND status = 'scheduled'
  AND appointment_date >= (SELECT value FROM clinic_info WHERE key = 'data_today')
ORDER BY appointment_date, start_time;
```
