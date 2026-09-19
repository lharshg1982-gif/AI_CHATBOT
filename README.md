# Agentic Healthcare Assistant — Streamlit Capstone

This project is based on the supplied capstone problem statement:
**Agentic Healthcare Assistant for Medical Task Automation**.

The requested solution covers:
- Agent planning and goal decomposition
- Appointment discovery and demo booking
- Patient history retrieval and summarization
- Trusted medical information retrieval through PubMed/NCBI
- Separate trusted Health Consultation & Tips Knowledge Base retrieval
- Memory through a patient-history database
- Prompt engineering and task chaining
- Streamlit patient/doctor-style views
- LLMOps logs and simple evaluation metrics
- Safety gates, moderation, emergency escalation, prompt-injection resistance
- OpenAI Responses API

## Architecture

User → Streamlit UI → Safety Gate → Planner → Knowledge Base + Deterministic Tools
→ Patient DB / Appointment DB / PubMed → Answer Writer → UI + Logs

## Setup

1. Create a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. For AI-generated answers, enter a provider key in the Streamlit sidebar. OpenRouter uses `https://openrouter.ai/api/v1` and defaults to the `openrouter/free` model router; OpenAI uses the standard OpenAI API.

	If the OpenAI account has no credits, select **Local demo mode (free)** in the sidebar. This mode requires no API key and supports synthetic appointment/history workflows, but it does not generate medical answers with an AI model.

4. Start:

```bash
streamlit run app.py
```

## Example questions

- "Find a nephrologist appointment for patient P001 next week."
- "Summarize P001's previous medical history and alerts."
- "What are current evidence-based treatment approaches for chronic kidney disease?"
- "Book a suitable appointment for P001 and also summarize recent CKD information."

## Important production notes

This is an educational capstone/demo and uses synthetic patient data.
For real deployment:
- Use a compliant EHR/health-data architecture.
- Add authentication and role-based access control.
- Encrypt data at rest and in transit.
- Never put API keys in source code.
- Replace the SQLite demo database with a secured EHR/DB layer.
- Add consent, audit, retention and privacy controls appropriate to the deployment jurisdiction.
- Integrate verified doctor scheduling APIs.
- Add WHO/MedlinePlus/approved clinical knowledge connectors.
- Implement formal evaluation datasets and human review.
- Add rate limiting and abuse monitoring.
- Require explicit confirmation before real appointment writes.
