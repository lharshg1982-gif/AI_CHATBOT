import streamlit as st
from pathlib import Path
from agent import HealthcareAgent
from health_consultation_kb import load_knowledge_base
from db import (
    init_db,
    seed_demo_data,
    get_dashboard_stats,
    list_appointments,
    list_patients,
    list_logs,
    list_admissions,
    list_reports,
    search_admissions,
    search_reports,
    list_doctors,
)

st.set_page_config(
    page_title="Agentic Healthcare Assistant",
    page_icon="🩺",
    layout="wide",
)

init_db()
seed_demo_data()

st.title("🩺 Agentic Healthcare Assistant")
st.caption("Capstone implementation: planning • memory • medical information retrieval • appointment automation • LLMOps")

with st.sidebar:
    st.header("Configuration")
    provider = st.selectbox(
        "AI provider",
        ["OpenRouter API", "OpenAI API", "Local demo mode (free)"],
    )
    api_key = ""
    if provider in ("OpenAI API", "OpenRouter API"):
        api_key = st.text_input(
            f"{provider.split()[0]} API key",
            type="password",
            help="Your key is used for this Streamlit session and is not written to the project files.",
        )
    else:
        st.caption("Uses synthetic database workflows without an API key. No AI-generated medical answers.")
    default_model = "openrouter/free" if provider == "OpenRouter API" else "gpt-5.6-terra"
    model = st.text_input("Model", value=default_model)
    use_web = st.toggle("Use trusted medical web retrieval", value=True)
    demo_mode = st.toggle("Demo / mock appointment booking", value=True)

    st.divider()
    st.markdown(
        """
        **Safety**
        - Educational/administrative assistant, not a doctor.
        - No diagnosis or prescription generation.
        - Emergency symptoms should be handled by local emergency services.
        - Demo records contain synthetic data only.
        """
    )

offline_mode = provider == "Local demo mode (free)"
if not offline_mode and not api_key.strip():
    st.info("Enter your OpenAI API key in the sidebar to enable the assistant.")
    st.stop()

agent = HealthcareAgent(
    model=model,
    use_web=use_web,
    demo_mode=demo_mode,
    api_key=api_key.strip(),
    offline_mode=offline_mode,
    provider="openrouter" if provider == "OpenRouter API" else "openai",
)

tabs = st.tabs([
    "💬 Assistant",
    "👤 Patients",
    "📅 Appointments",
    "🏥 Admissions & Reports",
    "👨‍⚕️ Doctors",
    "📊 LLMOps",
    "🧠 Agent Trace",
    "📚 Health KB",
])

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_trace" not in st.session_state:
    st.session_state.last_trace = {}

with tabs[0]:
    st.subheader("Ask the assistant")
    examples = [
        "Find a nephrologist appointment for patient P001 next week.",
        "Summarize P001's previous medical history and alerts.",
        "What are current evidence-based treatment approaches for chronic kidney disease?",
        "Book a suitable appointment for P001 and also summarize recent CKD information.",
        "My 70-year-old father has chronic kidney disease. I want to book a nephrologist for him. Also, can you summarize latest treatment methods?",
    ]
    st.write("Try:")
    for ex in examples:
        if st.button(ex, key=f"ex_{ex}"):
            st.session_state["pending_prompt"] = ex

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prompt = st.chat_input("Ask about appointments, records, or medical information…")
    prompt = prompt or st.session_state.pop("pending_prompt", None)

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Planning and executing…"):
                result = agent.run(prompt)
            st.markdown(result["answer"])

        st.session_state.messages.append({"role": "assistant", "content": result["answer"]})
        st.session_state.last_trace = result["trace"]

with tabs[1]:
    st.subheader("Patient view")
    patients = list_patients()
    st.dataframe(patients, width="stretch", hide_index=True)

with tabs[2]:
    st.subheader("Appointment tracking")
    appointments = list_appointments()
    st.dataframe(appointments, width="stretch", hide_index=True)

with tabs[3]:
    st.subheader("Synthetic admissions and reports")
    st.caption("All records shown here are randomized synthetic demo data.")
    record_reason = st.text_input(
        "Filter by admission/report reason",
        placeholder="Example: CKD evaluation or pneumonia",
    )
    st.write("Admissions")
    st.dataframe(
        search_admissions(record_reason or None),
        width="stretch",
        hide_index=True,
    )
    st.write("Reports")
    st.dataframe(
        search_reports(record_reason or None),
        width="stretch",
        hide_index=True,
    )

with tabs[4]:
    st.subheader("Doctor directory")
    st.caption("Synthetic doctor directory with specialties and experience. Availability is for demo scheduling only.")
    st.dataframe(list_doctors(), width="stretch", hide_index=True)

with tabs[5]:
    st.subheader("LLMOps dashboard")
    stats = get_dashboard_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Requests", stats["requests"])
    c2.metric("Tool calls", stats["tool_calls"])
    c3.metric("Successful tools", stats["successful_tools"])
    c4.metric("Success rate", f'{stats["tool_success_rate"]:.1f}%')

    logs = list_logs(limit=100)
    st.dataframe(logs, width="stretch", hide_index=True)

with tabs[6]:
    st.subheader("Agent planning / execution trace")
    trace = st.session_state.last_trace
    if not trace:
        st.info("Run a request in the Assistant tab to see the trace.")
    else:
        st.json(trace)

with tabs[7]:
    st.subheader("Health consultation and tips knowledge base")
    st.caption("Curated educational guidance used for retrieval. It is not a clinical guideline or personalized medical advice.")
    for entry in load_knowledge_base():
        with st.expander(entry["title"]):
            st.write(entry["guidance"])
            st.warning(entry["safety"])
            st.caption(entry["source"])
