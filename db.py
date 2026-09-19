import sqlite3
import random
import re
from difflib import SequenceMatcher
from pathlib import Path
from datetime import date, timedelta
import pandas as pd

DB_PATH = Path("healthcare_demo.db")

ILLNESS_ALIASES = {
    "ckd": "kidney",
    "renal": "kidney",
    "nephropathy": "kidney",
    "kidneys": "kidney",
    "hypertensive": "hypertension",
    "cardiac": "heart",
    "cardiovascular": "heart",
    "migraine": "neurology",
    "neurological": "neurology",
    "arthritis": "orthopedics",
    "joint": "orthopedics",
    "lung": "pulmonology",
    "respiratory": "pulmonology",
}

ILLNESS_SPECIALTIES = {
    "kidney": "Nephrology",
    "liver": "Hepatology",
    "heart": "Cardiology",
    "hypertension": "Cardiology",
    "diabetes": "Endocrinology",
    "asthma": "Pulmonology",
    "pneumonia": "Pulmonology",
    "orthopedics": "Orthopedics",
    "neurology": "Neurology",
    "anemia": "Hematology",
}


def _illness_terms(value):
    ignored = {"the", "and", "with", "find", "show", "patient", "patients", "illness", "disease"}
    terms = set()
    for raw_term in value.casefold().replace("-", " ").split():
        term = ILLNESS_ALIASES.get(raw_term, raw_term)
        if len(term) > 2 and term not in ignored:
            terms.add(term)
    return terms


def infer_specialty_from_illness(illness):
    terms = _illness_terms(illness)
    for illness_term, specialty in ILLNESS_SPECIALTIES.items():
        if illness_term in terms:
            return specialty
    return None

def connect():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = connect()
    cur = con.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS patients (
        patient_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        age INTEGER,
        allergies TEXT,
        alerts TEXT,
        illness TEXT,
        treatment_taken TEXT,
        treatment_taken_date TEXT
    );

    CREATE TABLE IF NOT EXISTS medical_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT,
        entry_date TEXT,
        diagnosis TEXT,
        treatment TEXT,
        notes TEXT
    );

    CREATE TABLE IF NOT EXISTS appointments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT,
        doctor TEXT,
        specialty TEXT,
        appointment_date TEXT,
        appointment_time TEXT,
        status TEXT
    );

    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        event_type TEXT,
        status TEXT,
        request_text TEXT,
        response_text TEXT
    );

    CREATE TABLE IF NOT EXISTS admissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        admission_date TEXT NOT NULL,
        discharge_date TEXT,
        reason TEXT NOT NULL,
        ward TEXT NOT NULL,
        status TEXT NOT NULL,
        severity TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id TEXT NOT NULL,
        report_date TEXT NOT NULL,
        report_type TEXT NOT NULL,
        title TEXT NOT NULL,
        findings TEXT NOT NULL,
        status TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS doctors (
        doctor_id TEXT PRIMARY KEY,
        doctor_name TEXT NOT NULL,
        specialization TEXT NOT NULL,
        category TEXT NOT NULL,
        years_experience INTEGER NOT NULL,
        availability_status TEXT NOT NULL
    );
    """)
    patient_columns = {
        row[1] for row in cur.execute("PRAGMA table_info(patients)").fetchall()
    }
    for column, definition in (
        ("illness", "TEXT"),
        ("treatment_taken", "TEXT"),
        ("treatment_taken_date", "TEXT"),
    ):
        if column not in patient_columns:
            cur.execute(f"ALTER TABLE patients ADD COLUMN {column} {definition}")
    con.commit()
    con.close()

def seed_demo_data():
    con = connect()
    cur = con.cursor()
    doctor_catalog = [
        ("D001", "Dr. Anil Rao", "Nephrologist", "Kidney", 18),
        ("D002", "Dr. Kavita Mehta", "Hepatologist", "Liver", 16),
        ("D003", "Dr. Priya Shah", "Pediatrician", "Pediatrics / Child", 12),
        ("D004", "Dr. Rohan Iyer", "Cardiologist", "Heart", 21),
        ("D005", "Dr. Sameer Patel", "Orthopedic Surgeon", "Orthopedics", 19),
        ("D006", "Dr. Neha Singh", "ENT Specialist", "ENT", 14),
        ("D007", "Dr. Arjun Das", "General Physician", "General Medicine", 11),
        ("D008", "Dr. Vikram Nair", "General Surgeon", "Surgery", 22),
        ("D009", "Dr. Meera Kulkarni", "Anesthesiologist", "Anesthesia", 17),
        ("D010", "Dr. Farah Khan", "Neurologist", "Brain / Neurology", 15),
        ("D011", "Dr. Tara Wilson", "Ophthalmologist", "Eye", 13),
        ("D012", "Dr. Daniel Brown", "Dentist", "Dental", 10),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO doctors(doctor_id, doctor_name, specialization, category, years_experience, availability_status) VALUES (?, ?, ?, ?, ?, ?)",
        [doctor + ("Available",) for doctor in doctor_catalog],
    )
    cur.execute("SELECT COUNT(*) FROM patients")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            """
            INSERT INTO patients
            (patient_id, name, age, allergies, alerts, illness, treatment_taken, treatment_taken_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("P001", "Demo Patient A", 70, "None recorded", "Chronic kidney disease", "Chronic kidney disease", "Clinician-managed treatment", "2026-05-18"),
                ("P002", "Demo Patient B", 45, "Penicillin (demo)", "Hypertension", "Hypertension", "Clinician-managed treatment", "2026-03-12"),
            ],
        )
        cur.executemany(
            "INSERT INTO medical_history(patient_id, entry_date, diagnosis, treatment, notes) VALUES (?, ?, ?, ?, ?)",
            [
                ("P001", "2026-01-10", "Chronic kidney disease", "Clinician-managed treatment", "Synthetic demo record."),
                ("P001", "2026-05-18", "CKD follow-up", "Monitoring", "Synthetic demo record."),
                ("P002", "2026-03-12", "Hypertension", "Clinician-managed treatment", "Synthetic demo record."),
            ],
        )

    randomizer = random.Random(20260906)
    conditions = [
        ("Chronic kidney disease", "Nephrology", "critical"),
        ("Heart failure", "Cardiology", "critical"),
        ("Type 2 diabetes", "Endocrinology", "normal"),
        ("Hypertension", "General Medicine", "normal"),
        ("Asthma", "Pulmonology", "normal"),
        ("Pneumonia", "Pulmonology", "critical"),
        ("Coronary artery disease", "Cardiology", "critical"),
        ("Osteoarthritis", "Orthopedics", "normal"),
        ("Migraine", "Neurology", "normal"),
        ("Iron-deficiency anemia", "Hematology", "normal"),
    ]
    first_names = ["Aarav", "Maya", "Noah", "Anika", "Liam", "Sara", "Ethan", "Isha", "Oliver", "Nora"]
    last_names = ["Patel", "Shah", "Rao", "Mehta", "Singh", "Iyer", "Khan", "Das", "Brown", "Wilson"]
    allergy_options = ["None recorded", "Penicillin", "Sulfa drugs", "Latex", "Aspirin"]
    existing_ids = {row[0] for row in cur.execute("SELECT patient_id FROM patients").fetchall()}
    next_number = 1
    while f"P{next_number:03d}" in existing_ids:
        next_number += 1

    patients_to_add = []
    history_to_add = []
    admissions_to_add = []
    reports_to_add = []
    target_count = 150
    while len(existing_ids) < target_count:
        patient_id = f"P{next_number:03d}"
        next_number += 1
        if patient_id in existing_ids:
            continue
        condition, specialty, severity = randomizer.choice(conditions)
        age = randomizer.randint(18, 88)
        patient_name = f"{randomizer.choice(first_names)} {randomizer.choice(last_names)} {patient_id}"
        alert = condition if severity == "critical" else "Routine follow-up"

        record_count = randomizer.randint(2, 4)
        history_dates = []
        for record_index in range(record_count):
            record_date = date(2025, 1, 1) + timedelta(days=randomizer.randint(0, 610))
            history_dates.append(record_date)
            treatment = "Specialist-managed care" if severity == "critical" else "Routine clinician-managed care"
            history_to_add.append((
                patient_id,
                record_date.isoformat(),
                condition if record_index == 0 else f"{condition} follow-up",
                treatment,
                f"Synthetic {severity} demo record; specialty: {specialty}.",
            ))
        latest_date = max(history_dates)
        patients_to_add.append((
            patient_id,
            patient_name,
            age,
            randomizer.choice(allergy_options),
            alert,
            condition,
            treatment,
            latest_date.isoformat(),
        ))

        if severity == "critical" or randomizer.random() < 0.35:
            admission_date = date(2025, 1, 1) + timedelta(days=randomizer.randint(0, 610))
            length_of_stay = randomizer.randint(1, 14)
            discharge_date = admission_date + timedelta(days=length_of_stay)
            admissions_to_add.append((
                patient_id,
                admission_date.isoformat(),
                discharge_date.isoformat(),
                condition,
                f"{specialty} ward",
                "Discharged",
                severity,
            ))

        report_date = date(2025, 1, 1) + timedelta(days=randomizer.randint(0, 610))
        reports_to_add.append((
            patient_id,
            report_date.isoformat(),
            randomizer.choice(["Lab report", "Imaging report", "Specialist report"]),
            f"{condition} assessment",
            f"Synthetic report for {condition}; review with the {specialty} team.",
            "Reviewed",
        ))
        existing_ids.add(patient_id)

    if patients_to_add:
        cur.executemany(
            "INSERT INTO patients(patient_id, name, age, allergies, alerts, illness, treatment_taken, treatment_taken_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            patients_to_add,
        )
        cur.executemany(
            "INSERT INTO medical_history(patient_id, entry_date, diagnosis, treatment, notes) VALUES (?, ?, ?, ?, ?)",
            history_to_add,
        )
        cur.executemany(
            "INSERT INTO admissions(patient_id, admission_date, discharge_date, reason, ward, status, severity) VALUES (?, ?, ?, ?, ?, ?, ?)",
            admissions_to_add,
        )
        cur.executemany(
            "INSERT INTO reports(patient_id, report_date, report_type, title, findings, status) VALUES (?, ?, ?, ?, ?, ?)",
            reports_to_add,
        )

    # Ensure the two original demo patients also have admission/report records.
    cur.execute("SELECT COUNT(*) FROM admissions WHERE patient_id='P001'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO admissions(patient_id, admission_date, discharge_date, reason, ward, status, severity) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("P001", "2026-02-03", "2026-02-08", "CKD evaluation", "Nephrology ward", "Discharged", "critical"),
        )
    cur.execute("SELECT COUNT(*) FROM reports WHERE patient_id='P001'")
    if cur.fetchone()[0] == 0:
        cur.execute(
            "INSERT INTO reports(patient_id, report_date, report_type, title, findings, status) VALUES (?, ?, ?, ?, ?, ?)",
            ("P001", "2026-05-18", "Specialist report", "CKD follow-up", "Synthetic nephrology follow-up report.", "Reviewed"),
        )
    missing_reports = cur.execute(
        """
        SELECT p.patient_id, p.alerts
        FROM patients p
        LEFT JOIN reports r ON r.patient_id = p.patient_id
        WHERE r.patient_id IS NULL
        """
    ).fetchall()
    cur.executemany(
        "INSERT INTO reports(patient_id, report_date, report_type, title, findings, status) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (
                patient_id,
                "2026-06-01",
                "General report",
                f"{alerts} review",
                "Synthetic follow-up report; review with the care team.",
                "Reviewed",
            )
            for patient_id, alerts in missing_reports
        ],
    )
    cur.execute(
        """
        UPDATE patients
        SET illness = COALESCE(illness, (
                SELECT diagnosis FROM medical_history h
                WHERE h.patient_id = patients.patient_id
                ORDER BY entry_date DESC, id DESC LIMIT 1
            )),
            treatment_taken = COALESCE(treatment_taken, (
                SELECT treatment FROM medical_history h
                WHERE h.patient_id = patients.patient_id
                ORDER BY entry_date DESC, id DESC LIMIT 1
            )),
            treatment_taken_date = COALESCE(treatment_taken_date, (
                SELECT entry_date FROM medical_history h
                WHERE h.patient_id = patients.patient_id
                ORDER BY entry_date DESC, id DESC LIMIT 1
            ))
        WHERE illness IS NULL OR treatment_taken IS NULL OR treatment_taken_date IS NULL
        """
    )
    cur.execute(
        """
        UPDATE patients
        SET illness = alerts
        WHERE alerts IS NOT NULL
          AND alerts <> 'Routine follow-up'
          AND illness LIKE '%follow-up'
        """
    )
    con.commit()
    con.close()

def get_patient(patient_id):
    con = connect()
    row = con.execute("SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
    con.close()
    if not row:
        return None
    return {
        "patient_id": row[0],
        "name": row[1],
        "age": row[2],
        "allergies": row[3],
        "alerts": row[4],
        "illness": row[5],
        "treatment_taken": row[6],
        "treatment_taken_date": row[7],
    }

def _name_similarity(query, candidate):
    query_tokens = set(query.lower().split())
    candidate_tokens = set(candidate.lower().split())
    token_score = len(query_tokens & candidate_tokens) / max(len(query_tokens), len(candidate_tokens))
    text_score = SequenceMatcher(None, query.lower(), candidate.lower()).ratio()
    return max(text_score, (text_score + token_score) / 2)

def find_patient_by_name(name, minimum_score=0.58):
    search_name = " ".join(name.strip().split())
    con = connect()
    rows = con.execute("SELECT * FROM patients").fetchall()
    con.close()
    normalized_search = search_name.casefold()
    exact_rows = [
        row for row in rows
        if normalized_search == " ".join(row[1].split()).casefold()
        or normalized_search in " ".join(row[1].split()).casefold()
    ]
    if exact_rows:
        return _patient_from_row(exact_rows[0])
    row = max(rows, key=lambda item: _name_similarity(search_name, item[1]), default=None)
    if row is None or _name_similarity(search_name, row[1]) < minimum_score:
        return None
    return _patient_from_row(row)


def find_patients_by_illness(illness_query, limit=20):
    query_terms = _illness_terms(illness_query)
    if not query_terms:
        return []
    con = connect()
    rows = con.execute("SELECT * FROM patients").fetchall()
    con.close()
    matches = []
    for row in rows:
        searchable = " ".join(str(value or "") for value in (row[4], row[5]))
        patient_terms = _illness_terms(searchable)
        score = len(query_terms & patient_terms)
        if score:
            patient = _patient_from_row(row)
            patient["illness_match_score"] = score / max(len(query_terms), 1)
            matches.append((score, patient))
    matches.sort(key=lambda item: (-item[0], item[1]["patient_id"]))
    return [patient for _, patient in matches[:limit]]

def _patient_from_row(row):
    if not row:
        return None
    return {
        "patient_id": row[0],
        "name": row[1],
        "age": row[2],
        "allergies": row[3],
        "alerts": row[4],
        "illness": row[5],
        "treatment_taken": row[6],
        "treatment_taken_date": row[7],
    }

def find_doctor_by_name(name, minimum_score=0.58):
    search_name = " ".join(name.strip().split())
    con = connect()
    rows = con.execute(
        "SELECT doctor_id, doctor_name, specialization, category, years_experience, availability_status FROM doctors"
    ).fetchall()
    con.close()
    row = max(rows, key=lambda item: _name_similarity(search_name, item[1]), default=None)
    if row is None or _name_similarity(search_name, row[1]) < minimum_score:
        return None
    return {
        "doctor_id": row[0],
        "doctor_name": row[1],
        "specialization": row[2],
        "category": row[3],
        "years_experience": row[4],
        "availability_status": row[5],
    }


def find_doctors_for_illness(illness_query):
    specialty = infer_specialty_from_illness(illness_query)
    if not specialty:
        return {"illness": illness_query, "specialty": None, "doctors": []}
    specialty_terms = {
        "Nephrology": ("Kidney", "Nephrologist"),
        "Hepatology": ("Liver", "Hepatologist"),
        "Cardiology": ("Heart", "Cardiologist"),
        "Pediatrics": ("Pediatrics / Child", "Pediatrician"),
        "Orthopedics": ("Orthopedics", "Orthopedic Surgeon"),
        "ENT": ("ENT", "ENT Specialist"),
        "General Medicine": ("General Medicine", "General Physician"),
        "Surgery": ("Surgery", "General Surgeon"),
        "Anesthesia": ("Anesthesia", "Anesthesiologist"),
        "Neurology": ("Brain / Neurology", "Neurologist"),
        "Ophthalmology": ("Eye", "Ophthalmologist"),
        "Dental": ("Dental", "Dentist"),
    }
    category, specialization = specialty_terms.get(specialty, (specialty, specialty))
    con = connect()
    rows = con.execute(
        """
        SELECT doctor_id, doctor_name, specialization, category,
               years_experience, availability_status
        FROM doctors
        WHERE category=? OR specialization=?
        ORDER BY availability_status DESC, years_experience DESC
        """,
        (category, specialization),
    ).fetchall()
    con.close()
    return {
        "illness": illness_query,
        "specialty": specialty,
        "doctors": [
            {
                "doctor_id": row[0],
                "doctor_name": row[1],
                "specialization": row[2],
                "category": row[3],
                "years_experience": row[4],
                "availability_status": row[5],
            }
            for row in rows
        ],
    }

def get_patient_history(patient_id):
    con = connect()
    rows = con.execute(
        "SELECT entry_date, diagnosis, treatment, notes FROM medical_history WHERE patient_id=? ORDER BY entry_date DESC",
        (patient_id,),
    ).fetchall()
    con.close()
    return [
        {
            "date": r[0],
            "diagnosis": r[1],
            "treatment": r[2],
            "notes": r[3],
        }
        for r in rows
    ]


def _search_terms(value):
    return {
        term for term in re.sub(r"[^a-z0-9 ]", " ", value.casefold()).split()
        if len(term) > 2
    }


def _reason_matches(query, value):
    query_terms = _search_terms(query)
    value_terms = _search_terms(value)
    return bool(query_terms and query_terms & value_terms)


def search_admissions(reason=None, patient_id=None, limit=100):
    con = connect()
    rows = con.execute(
        """
        SELECT a.id, a.patient_id, p.name, p.age, p.illness,
               a.admission_date, a.discharge_date, a.reason,
               a.ward, a.status, a.severity
        FROM admissions a
        JOIN patients p ON p.patient_id = a.patient_id
        WHERE (? IS NULL OR a.patient_id = ?)
        ORDER BY a.admission_date DESC, a.id DESC
        """,
        (patient_id, patient_id),
    ).fetchall()
    con.close()
    if reason:
        rows = [row for row in rows if _reason_matches(reason, row[7])]
    return [
        {
            "admission_id": row[0],
            "patient_id": row[1],
            "patient_name": row[2],
            "patient_age": row[3],
            "current_illness": row[4],
            "admission_date": row[5],
            "discharge_date": row[6],
            "reason": row[7],
            "ward": row[8],
            "status": row[9],
            "severity": row[10],
        }
        for row in rows[:limit]
    ]


def search_reports(reason=None, patient_id=None, limit=100):
    con = connect()
    rows = con.execute(
        """
        SELECT r.id, r.patient_id, p.name, p.age, p.illness,
               r.report_date, r.report_type, r.title,
               r.findings, r.status
        FROM reports r
        JOIN patients p ON p.patient_id = r.patient_id
        WHERE (? IS NULL OR r.patient_id = ?)
        ORDER BY r.report_date DESC, r.id DESC
        """,
        (patient_id, patient_id),
    ).fetchall()
    con.close()
    if reason:
        rows = [
            row for row in rows
            if _reason_matches(reason, " ".join(str(value or "") for value in (row[7], row[8])))
        ]
    return [
        {
            "report_id": row[0],
            "patient_id": row[1],
            "patient_name": row[2],
            "patient_age": row[3],
            "current_illness": row[4],
            "report_date": row[5],
            "report_type": row[6],
            "title": row[7],
            "findings": row[8],
            "status": row[9],
        }
        for row in rows[:limit]
    ]

def find_slots(specialty: str, date_preference=None):
    base = date.today()
    specialty_terms = {
        "Nephrology": ("Kidney", "Nephrologist"),
        "Hepatology": ("Liver", "Hepatologist"),
        "Pediatrics": ("Pediatrics / Child", "Pediatrician"),
        "Cardiology": ("Heart", "Cardiologist"),
        "Orthopedics": ("Orthopedics", "Orthopedic Surgeon"),
        "ENT": ("ENT", "ENT Specialist"),
        "General Medicine": ("General Medicine", "General Physician"),
        "Surgery": ("Surgery", "General Surgeon"),
        "Anesthesia": ("Anesthesia", "Anesthesiologist"),
        "Neurology": ("Brain / Neurology", "Neurologist"),
        "Ophthalmology": ("Eye", "Ophthalmologist"),
        "Dental": ("Dental", "Dentist"),
    }
    category, specialization = specialty_terms.get(
        specialty, ("General Medicine", "General Physician")
    )
    con = connect()
    doctor_rows = con.execute(
        "SELECT doctor_name, specialization, years_experience FROM doctors WHERE category=? OR specialization=? ORDER BY doctor_id",
        (category, specialization),
    ).fetchall()
    con.close()
    if not doctor_rows:
        doctor_rows = [("Dr. Arjun Das", "General Physician", 11)]

    slots = []
    for i in range(1, 6):
        d = base + timedelta(days=i)
        for t in ["10:00", "14:00", "16:30"]:
            doctor_name, doctor_specialization, years_experience = doctor_rows[(i - 1) % len(doctor_rows)]
            slots.append({
                "doctor": doctor_name,
                "specialty": specialty,
                "specialization": doctor_specialization,
                "years_experience": years_experience,
                "date": d.isoformat(),
                "time": t,
            })
    return slots

def create_appointment(patient_id, doctor, specialty, appointment_date, appointment_time):
    con = connect()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO appointments
        (patient_id, doctor, specialty, appointment_date, appointment_time, status)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (patient_id, doctor, specialty, appointment_date, appointment_time, "Booked"),
    )
    appointment_id = cur.lastrowid
    con.commit()
    con.close()
    return {
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "doctor": doctor,
        "specialty": specialty,
        "date": appointment_date,
        "time": appointment_time,
        "status": "Booked",
    }

def log_event(event_type, status, request_text, response_text):
    con = connect()
    con.execute(
        "INSERT INTO logs(event_type, status, request_text, response_text) VALUES (?, ?, ?, ?)",
        (event_type, status, request_text[:4000], response_text[:4000]),
    )
    con.commit()
    con.close()

def list_patients():
    con = connect()
    df = pd.read_sql_query(
        "SELECT patient_id, name, age, allergies, alerts, illness, treatment_taken, treatment_taken_date FROM patients",
        con,
    )
    con.close()
    return df

def list_appointments():
    con = connect()
    df = pd.read_sql_query("SELECT * FROM appointments ORDER BY id DESC", con)
    con.close()
    return df

def list_logs(limit=100):
    con = connect()
    df = pd.read_sql_query(
        f"SELECT created_at, event_type, status, request_text, response_text FROM logs ORDER BY id DESC LIMIT {int(limit)}",
        con,
    )
    con.close()
    return df

def list_admissions(limit=500):
    return pd.DataFrame(search_admissions(limit=limit))

def list_reports(limit=500):
    return pd.DataFrame(search_reports(limit=limit))

def list_doctors():
    con = connect()
    df = pd.read_sql_query(
        "SELECT doctor_id, doctor_name, specialization, category, years_experience, availability_status FROM doctors ORDER BY category, doctor_name",
        con,
    )
    con.close()
    return df

def get_dashboard_stats():
    con = connect()
    requests = con.execute("SELECT COUNT(*) FROM logs WHERE event_type='agent_run'").fetchone()[0]
    tool_calls = con.execute("SELECT COUNT(*) FROM logs").fetchone()[0]
    successful = con.execute("SELECT COUNT(*) FROM logs WHERE status='success'").fetchone()[0]
    con.close()
    return {
        "requests": requests,
        "tool_calls": tool_calls,
        "successful_tools": successful,
        "tool_success_rate": (successful / tool_calls * 100) if tool_calls else 0,
    }
