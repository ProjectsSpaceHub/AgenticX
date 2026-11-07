# Agentic X - Studio 67 

Python Multi-Agent System prototype for event crisis resolution. Four independent agents: Creative (LLM), Finance (deterministic), Safety (deterministic hard veto), Operations (LLM + resource tools). ACL-like messages and an engine that returns `AGREED` or `ESCALATED` from real evaluations.

## Requirements

- Python 3.10+
- A real supported LLM provider key (by default `OPENAI_API_KEY`)
- Optional LangSmith API key for tracing

```bash
python -m pip install -r requirements.txt
cp .env.example .env  # optional: configure locally; never commit .env
export OPENAI_API_KEY='YOUR_KEY'
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY='YOUR_LANGSMITH_KEY'
export LANGSMITH_PROJECT='AgenticX-Studio67'
jupyter notebook
```

Run notebooks `01` through `05` from the **repository root**. The notebooks import the shared Python modules under `core/` and `agents/`. The original Excel test set is in `data/`. Do not send model prompts any ground-truth evaluation columns. This implementation explicitly excludes the option QA-only columns in `core/environment.py`.

## Important limitations

- **No mocks**, stored answers, or faked successful LLM calls. LLM-backed cells require an actual API key and will raise an error if missing.
- This is a genuine implementation **starter**, not a claim that 150 real LLM executions or full UI integration have already succeeded. Running the full dataset requires model access, time, and possible API charges.
- The negotiation engine currently considers the supplied real options and rejects invalid ones; it **does not yet generate new replacement options** or adapt a proposal in response to a rejection. Extend this before claiming rich multi-round bargaining.
- The user interface source was not supplied in this turn. Notebook 05 exports results suitable for UI integration; the UI itself is not included.
- LangSmith tracing works when LangSmith environment variables are configured; datasets/evaluators for richer LangSmith benchmark workflow can be expanded in Notebook 05.
- The university guideline says Python only. Verify any non-Python UI separately before submission.

## Data provenance

The Excel file contains synthetic scenarios and candidate solutions. Ground-truth option fields are for evaluation only, not exposed to agents. The test set does not establish measured system performance until executed.
