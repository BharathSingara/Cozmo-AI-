# Reference application: public-source inspection, not executed

Source: https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/voice_ai_agents/insurance_claim_live_agent_team. The README describes a Gemini 3.1 Flash Live voice-to-voice channel, an ADK `root_agent` graph in `agent.py`, Gemini 3 Flash for structured extraction, Pydantic and deterministic FNOL rules, plus an HTML/CSS/JavaScript frontend served through FastAPI. Its files include `agent.py`, `schemas.py`, `policies.py`, `examples.py`, `requirements.txt`, and `live_demo/server.py`.

It is designed to intake verbal insurance losses and hand off to an adjuster. Public documentation does not claim individual spine counting, physical measurements, room reconstruction, price-source evidence, or per-book deduplication. Its design is informative for UX only; no source was copied.

**Terminal result:** `git ls-remote https://github.com/Shubhamsaboo/awesome-llm-apps.git HEAD` failed: `Could not resolve host: github.com`. Thus dependencies were not installed, the repo was not executed, and no reference runtime results are claimed. The new project has its own testable implementation.
