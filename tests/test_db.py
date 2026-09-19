from db import (
    init_db,
    seed_demo_data,
    get_patient,
    get_patient_history,
    find_patients_by_illness,
    find_doctors_for_illness,
    search_admissions,
    search_reports,
)

def test_demo_patient():
    init_db()
    seed_demo_data()
    patient = get_patient("P001")
    assert patient is not None
    assert patient["patient_id"] == "P001"

def test_history():
    init_db()
    seed_demo_data()
    history = get_patient_history("P001")
    assert isinstance(history, list)


def test_illness_search_matches_synonyms_and_specialist():
    init_db()
    seed_demo_data()
    patients = find_patients_by_illness("renal illness")
    specialist = find_doctors_for_illness("renal illness")
    assert any(patient["patient_id"] == "P001" for patient in patients)
    assert specialist["specialty"] == "Nephrology"
    assert specialist["doctors"][0]["specialization"] == "Nephrologist"


def test_records_join_current_patient_and_filter_by_reason():
    init_db()
    seed_demo_data()
    admissions = search_admissions("CKD evaluation", patient_id="P001")
    reports = search_reports("CKD", patient_id="P001")
    assert admissions[0]["patient_name"] == "Demo Patient A"
    assert admissions[0]["current_illness"] == "Chronic kidney disease"
    assert reports[0]["patient_id"] == "P001"
    assert reports[0]["patient_name"] == "Demo Patient A"
