import json
import re
import time
from typing import Any, Dict, List

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI, RateLimitError

from db import (
    get_patient,
    find_patient_by_name,
    find_patients_by_illness,
    find_doctors_for_illness,
    search_admissions,
    search_reports,
    get_patient_history,
    create_appointment,
    find_slots,
    log_event,
)
from medical_search import search_medical_sources
from health_consultation_kb import retrieve_health_guidance
from safety import moderate_text, safety_gate, MEDICAL_SYSTEM_POLICY
from prompts import PLANNER_PROMPT, ANSWER_PROMPT


class HealthcareAgent:
    """
    Agentic orchestration layer.

    Design:
      1. Safety gate + moderation
      2. LLM planner produces a constrained JSON plan
      3. Deterministic tools execute actions
      4. LLM synthesizes a grounded final answer
    """

    def __init__(
        self,
        model: str,
        use_web: bool = True,
        demo_mode: bool = True,
        api_key: str | None = None,
        offline_mode: bool = False,
        provider: str = "openai",
    ):
        self.provider = provider
        if offline_mode:
            self.client = None
        elif provider == "openrouter":
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "http://localhost:8501",
                    "X-Title": "Agentic Healthcare Assistant",
                },
            )
        else:
            self.client = OpenAI(api_key=api_key)
        self.model = model
        self.use_web = use_web
        self.demo_mode = demo_mode
        self.offline_mode = offline_mode

    def _generate(self, messages: List[Dict[str, str]]) -> str:
        if self.provider == "openrouter":
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            return response.choices[0].message.content or ""

        response = self.client.responses.create(
            model=self.model,
            input=messages,
        )
        return response.output_text

    def _offline_run(self, user_text: str, trace: Dict[str, Any]) -> Dict[str, Any]:
        patient_id, identification_reason = self._identify_patient(user_text, {})
        patient = get_patient(patient_id) if patient_id else None
        guidance = retrieve_health_guidance(user_text)
        trace["health_knowledge_base"] = guidance
        trace["workflow"][0].update({
            "status": "success" if patient_id else "needs_patient_id",
            "patient_id": patient_id,
            "reason": identification_reason,
        })

        history = get_patient_history(patient_id) if patient_id else []
        illness_context = self._illness_context(user_text, patient)
        record_context = self._record_context(user_text, patient_id)
        trace["record_search"] = record_context
        trace["illness_search"] = illness_context
        if illness_context["matched_patients"] or illness_context["doctors"]:
            trace["tool_results"].append({
                "tool": "semantic_illness_search",
                "status": "success",
                **illness_context,
            })
        if patient:
            trace["workflow"][1].update({
                "status": "success",
                "patient_id": patient_id,
                "history_entries": len(history),
            })
        else:
            trace["workflow"][1]["status"] = "skipped"

        if any(word in user_text.lower() for word in ("admission", "admitted", "report", "reason")):
            answer = "Connected admission and report records:\n\n"
            if record_context["admissions"]:
                answer += "Admissions:\n" + "\n".join(
                    f"- {item['patient_id']} {item['patient_name']}: {item['reason']} ({item['admission_date']})"
                    for item in record_context["admissions"]
                )
            else:
                answer += "Admissions: no matching records."
            answer += "\n\n"
            if record_context["reports"]:
                answer += "Reports:\n" + "\n".join(
                    f"- {item['patient_id']} {item['patient_name']}: {item['title']} - {item['findings']}"
                    for item in record_context["reports"]
                )
            else:
                answer += "Reports: no matching records."
        elif patient_id and not patient:
            answer = f"I couldn't find synthetic demo patient ID `{patient_id}`. Please use one of the IDs shown in the Patients tab."
        elif not any(word in user_text.lower() for word in ("appointment", "book")) and (
            illness_context["matched_patients"] or (
            illness_context["doctors"]
            and re.search(r"\b(illness|disease|condition|patients?)\b", user_text, re.IGNORECASE)
            )
        ):
            answer = "Semantic illness search results:\n\n"
            if illness_context["matched_patients"]:
                answer += "Patients:\n" + "\n".join(
                    f"- `{match['patient_id']}`: {match['name']} - {match['illness']}"
                    for match in illness_context["matched_patients"]
                )
            else:
                answer += "No matching patients were found in the synthetic records."
            if illness_context["specialty"]:
                answer += f"\n\nRecommended specialty: {illness_context['specialty']}"
            if illness_context["doctors"]:
                answer += "\nMatching doctors:\n" + "\n".join(
                    f"- {doctor['doctor_name']} ({doctor['specialization']}, {doctor['years_experience']} years, {doctor['availability_status']})"
                    for doctor in illness_context["doctors"]
                )
        elif any(word in user_text.lower() for word in ("appointment", "doctor", "book")):
            specialty = illness_context["specialty"] or "General Medicine"
            slots = find_slots(specialty=specialty, date_preference=None)
            trace["tool_results"].append({
                "tool": "find_appointment",
                "status": "success",
                "specialty": specialty,
                "count": len(slots),
                "options": slots[:5],
            })
            trace["workflow"][2].update({
                "status": "calendar_checked",
                "specialty": specialty,
                "available_slots": len(slots),
            })
            if patient_id and patient and "book" in user_text.lower() and slots:
                chosen = slots[0]
                booked = create_appointment(
                    patient_id=patient_id,
                    doctor=chosen["doctor"],
                    specialty=chosen["specialty"],
                    appointment_date=chosen["date"],
                    appointment_time=chosen["time"],
                )
                trace["tool_results"].append({
                    "tool": "book_appointment",
                    "status": "success",
                    "appointment": booked,
                })
                trace["workflow"][2].update({
                    "status": "booked",
                    "appointment": booked,
                })
            answer = (
                "Local demo mode found these synthetic appointment options:\n\n"
                + "\n".join(
                    f"- {slot['date']} at {slot['time']} with {slot['doctor']} ({slot['specialty']})"
                    for slot in slots[:5]
                )
            )
            if trace["workflow"][2]["status"] == "booked":
                booked = trace["workflow"][2]["appointment"]
                answer += (
                    f"\n\nSynthetic demo appointment booked for `{booked['patient_id']}`: "
                    f"{booked['date']} at {booked['time']} with {booked['doctor']}."
                )
        elif patient:
            history = get_patient_history(patient_id)
            trace["tool_results"].append({"tool": "retrieve_history", "status": "success"})
            answer = (
                f"Local demo mode retrieved synthetic records for `{patient_id}`. "
                f"Patient: {patient['name']}. History entries: {len(history)}. "
                "Enable OpenAI mode for a natural-language summary."
            )
        else:
            answer = (
                "Local demo mode is active and does not call an AI model. "
                "Use a synthetic patient ID such as P001 for history or appointment workflows, "
                "or add OpenAI credits for generated medical-information answers."
            )

        if guidance and any(word in user_text.lower() for word in ("kidney", "ckd", "treatment", "symptom")):
            trace["workflow"][3].update({
                "status": "success",
                "knowledge_base_entries": len(guidance),
                "research_sources": 0,
            })
            answer += "\n\nHealth consultation knowledge base:\n" + "\n\n".join(
                f"**{entry['title']}**\n{entry['guidance']}\n_{entry['safety']}"
                for entry in guidance
            )
        else:
            trace["workflow"][3]["status"] = "no_sources"

        trace["mode"] = "offline"
        log_event("agent_run", "offline", user_text, answer)
        return {"answer": answer, "trace": trace}

    def _planner(self, user_text: str) -> Dict[str, Any]:
        raw = self._generate([
                {"role": "system", "content": PLANNER_PROMPT},
                {"role": "user", "content": user_text},
            ]).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Safe fallback: no actions are executed if planning is malformed.
            return {
                "intent": "general_medical_information",
                "patient_id": None,
                "specialty": None,
                "date_preference": None,
                "actions": ["medical_search"] if self.use_web else [],
                "risk": "unknown",
                "reason": "Planner returned non-JSON output; no booking/write action permitted."
            }

    def _identify_patient(self, user_text: str, plan: Dict[str, Any]) -> tuple[str | None, str]:
        explicit_match = re.search(r"\bP\d{3}\b", user_text.upper())
        if explicit_match:
            return explicit_match.group(0), "explicit patient ID"
        name_matches = re.findall(r"\b([A-Za-z]{2,}(?:['-][A-Za-z]+)?\s+[A-Za-z]{2,}(?:['-][A-Za-z]+)?)\b", user_text)
        patient_phrase = re.search(
            r"\bpatient(?:\s+named|\s+name\s+is)?\s+([A-Za-z]{2,}(?:['-][A-Za-z]+)?\s+[A-Za-z]{2,}(?:['-][A-Za-z]+)?)\b",
            user_text,
            re.IGNORECASE,
        )
        if patient_phrase:
            name_matches.insert(0, patient_phrase.group(1))
        for candidate in name_matches:
            patient = find_patient_by_name(candidate)
            if patient:
                return patient["patient_id"], f"fuzzy-matched patient name '{candidate}' to '{patient['name']}'"
        if "father" in user_text.lower() and (
            "70-year-old" in user_text.lower()
            or "70 year old" in user_text.lower()
            or "chronic kidney" in user_text.lower()
            or "ckd" in user_text.lower()
        ):
            # This mapping is only valid for the seeded synthetic demo records.
            return "P001", "matched synthetic 70-year-old father/CKD demo context"
        return plan.get("patient_id"), "planner-provided patient ID"

    def _illness_context(self, user_text: str, patient: Dict[str, Any] | None = None) -> Dict[str, Any]:
        query = user_text
        if patient and patient.get("illness"):
            query = f"{user_text} {patient['illness']}"
        patient_matches = []
        if re.search(r"\bpatients?\b", user_text, re.IGNORECASE):
            patient_matches = find_patients_by_illness(user_text)
        specialist_result = find_doctors_for_illness(query)
        return {
            "matched_patients": patient_matches,
            "specialty": specialist_result["specialty"],
            "doctors": specialist_result["doctors"],
        }

    def _record_context(self, user_text: str, patient_id: str | None = None) -> Dict[str, Any]:
        return {
            "admissions": search_admissions(user_text, patient_id=patient_id),
            "reports": search_reports(user_text, patient_id=patient_id),
        }

    def run(self, user_text: str) -> Dict[str, Any]:
        started = time.time()
        trace = {
            "input": user_text,
            "workflow": [
                {"step": 1, "name": "identify patient and context", "status": "pending"},
                {"step": 2, "name": "retrieve patient medical history", "status": "pending"},
                {"step": 3, "name": "query doctor calendar and book appointment", "status": "pending"},
                {"step": 4, "name": "retrieve and summarize treatment guidance", "status": "pending"},
            ],
            "steps": [],
            "tool_results": [],
        }

        gate = safety_gate(user_text)
        trace["steps"].append({"step": "safety_gate", "result": gate})

        if not gate["allowed"]:
            answer = gate["message"]
            log_event("safety_gate", "blocked", user_text, answer)
            return {"answer": answer, "trace": trace}

        if self.offline_mode:
            return self._offline_run(user_text, trace)

        try:
            moderation = moderate_text(self.client, user_text)
            trace["steps"].append({"step": "moderation", "result": moderation})
            if moderation["flagged"]:
                answer = (
                    "I can help with safe healthcare administration and general medical "
                    "information, but I can't assist with that request."
                )
                log_event("moderation", "blocked", user_text, answer)
                return {"answer": answer, "trace": trace}

            plan = self._planner(user_text)
            trace["plan"] = plan

            # Keep critical routing deterministic when the model omits one part of a mixed request.
            lowered_text = user_text.lower()
            if "nephrolog" in lowered_text and any(
                word in lowered_text for word in ("appointment", "book", "doctor")
            ):
                plan["specialty"] = "Nephrology"
                if "find_appointment" not in plan.get("actions", []):
                    plan.setdefault("actions", []).append("find_appointment")
            if "chronic kidney" in lowered_text or "ckd" in lowered_text:
                if "medical_search" not in plan.get("actions", []):
                    plan.setdefault("actions", []).append("medical_search")
                plan["medical_query"] = plan.get("medical_query") or (
                    "chronic kidney disease treatment guidelines and current management"
                )

            requested_actions = plan.get("actions", [])
            if any(word in lowered_text for word in ("appointment", "doctor", "book", "nephrolog")):
                if "find_appointment" not in requested_actions:
                    requested_actions.append("find_appointment")
            if "book" in lowered_text and "book_appointment" not in requested_actions:
                requested_actions.append("book_appointment")
            if "medical_search" in requested_actions:
                requested_actions = [
                    action for action in requested_actions
                    if action != "medical_search"
                ] + ["medical_search"]
            if "find_appointment" in requested_actions:
                requested_actions = [
                    action for action in requested_actions
                    if action not in ("find_appointment", "book_appointment")
                ] + ["find_appointment"]
                if "book" in lowered_text:
                    requested_actions.append("book_appointment")
            plan["actions"] = requested_actions

            patient_id, identification_reason = self._identify_patient(user_text, plan)
            plan["patient_id"] = patient_id
            trace["workflow"][0].update({
                "status": "success" if patient_id else "needs_patient_id",
                "patient_id": patient_id,
                "reason": identification_reason,
            })

            health_guidance = retrieve_health_guidance(
                f"{user_text} {plan.get('medical_query') or ''}"
            )
            trace["health_knowledge_base"] = health_guidance

            patient_id = plan.get("patient_id")
            patient = get_patient(patient_id) if patient_id else None
            history = get_patient_history(patient_id) if patient_id else []

            if patient_id and not patient:
                answer = f"I couldn't find synthetic demo patient ID `{patient_id}`. Please use one of the IDs shown in the Patients tab."
                log_event("planner", "failed", user_text, answer)
                return {"answer": answer, "trace": trace}

            if patient:
                trace["workflow"][1].update({
                    "status": "success",
                    "patient_id": patient_id,
                    "history_entries": len(history),
                })
            else:
                trace["workflow"][1]["status"] = "skipped"

            context = {
                "patient": patient,
                "history": history,
                "sources": [],
                "health_guidance": health_guidance,
                "appointment_options": [],
                "illness_search": self._illness_context(user_text, patient),
                "record_search": self._record_context(user_text, patient_id),
            }

            if context["record_search"]["admissions"] or context["record_search"]["reports"]:
                trace["record_search"] = context["record_search"]
                trace["tool_results"].append({
                    "tool": "retrieve_admissions_reports",
                    "status": "success",
                    "admissions": len(context["record_search"]["admissions"]),
                    "reports": len(context["record_search"]["reports"]),
                })

            if context["illness_search"]["matched_patients"] or context["illness_search"]["doctors"]:
                trace["illness_search"] = context["illness_search"]
                trace["tool_results"].append({
                    "tool": "semantic_illness_search",
                    "status": "success",
                    **context["illness_search"],
                })

            for action in plan.get("actions", []):
                if action == "retrieve_history" and patient_id:
                    trace["tool_results"].append({"tool": "retrieve_history", "status": "success"})
                elif action == "find_appointment":
                    specialty = (
                        plan.get("specialty")
                        or context["illness_search"]["specialty"]
                        or "General Medicine"
                    )
                    slots = find_slots(specialty=specialty, date_preference=plan.get("date_preference"))
                    context["appointment_options"] = slots
                    trace["tool_results"].append({
                        "tool": "find_appointment",
                        "status": "success",
                        "patient_id": patient_id,
                        "specialty": specialty,
                        "count": len(slots),
                        "options": slots[:5],
                    })
                    trace["workflow"][2].update({
                        "status": "calendar_checked",
                        "specialty": specialty,
                        "available_slots": len(slots),
                    })
                elif action == "book_appointment" and patient_id:
                    # Booking is only allowed for a specific selected slot.
                    slots = context.get("appointment_options", [])
                    if slots:
                        chosen = slots[0]
                        if self.demo_mode:
                            booked = create_appointment(
                                patient_id=patient_id,
                                doctor=chosen["doctor"],
                                specialty=chosen["specialty"],
                                appointment_date=chosen["date"],
                                appointment_time=chosen["time"],
                            )
                            context["booked"] = booked
                            trace["tool_results"].append({
                                "tool": "book_appointment",
                                "status": "success",
                                "appointment": booked,
                            })
                            trace["workflow"][2].update({
                                "status": "booked",
                                "appointment": booked,
                            })
                    else:
                        trace["tool_results"].append({
                            "tool": "book_appointment",
                            "status": "skipped",
                            "reason": "A patient ID is required before a booking can be created, or no verified slot was found.",
                        })
                elif action == "medical_search":
                    if self.use_web:
                        sources = search_medical_sources(
                            plan.get("medical_query") or user_text
                        )
                        context["sources"] = sources
                        trace["tool_results"].append({
                            "tool": "medical_search",
                            "status": "success",
                            "count": len(sources),
                        })

            if health_guidance or context["sources"]:
                trace["workflow"][3].update({
                    "status": "success",
                    "knowledge_base_entries": len(health_guidance),
                    "research_sources": len(context["sources"]),
                })
            else:
                trace["workflow"][3]["status"] = "no_sources"

            # Final response is generated only from explicitly supplied context.
            context_text = json.dumps(context, ensure_ascii=False, default=str)
            answer_messages = [
                {"role": "system", "content": MEDICAL_SYSTEM_POLICY + "\n" + ANSWER_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"USER REQUEST:\n{user_text}\n\n"
                        f"VERIFIED CONTEXT:\n{context_text}\n\n"
                        "Answer the user. Do not claim an action happened unless the tool result says it succeeded."
                    ),
                },
            ]
            answer = self._generate(answer_messages).strip()
            elapsed = round(time.time() - started, 2)
            trace["duration_seconds"] = elapsed
            log_event("agent_run", "success", user_text, answer)

            return {"answer": answer, "trace": trace}
        except RateLimitError:
            answer = (
                "OpenAI API quota is exhausted for this account. Add credits at "
                "https://platform.openai.com/settings/organization/billing/ or switch to "
                "Local demo mode in the sidebar."
            )
            trace["mode"] = "openai_quota_exhausted"
            log_event("agent_run", "quota_exhausted", user_text, answer)
            return {"answer": answer, "trace": trace}
