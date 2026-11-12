
"""Operations Agent for Studio 67: deterministic gates plus Gemini judgment.

Only operational evidence reaches the LLM. Finance, Creative, and Safety make
separate decisions; an Operations approval does not replace their vetoes.
"""

import math
import os

from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from core.models import AgentEvaluation


class OperationsOpinion(BaseModel):
    approved: bool
    score: float = Field(ge=0, le=100)
    reason: str = Field(min_length=1)


def valid_number(value):
    """Non-negative finite number, or None for missing/invalid inputs."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def is_true(value):
    """Require an explicit true, without treating nonempty strings as truthy."""
    if value is True:
        return True
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(value) and value == 1
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return False


class OperationsAgent:
    name = "Operations"
    VERSION = "2026-11-operations-v2"

    CASE_FIELDS = (
        "case_id", "scenario", "incident", "severity", "time_left_min",
        "crew_available", "crew_count_available", "backup_available",
        "venue_access",
    )
    OPTION_FIELDS = (
        "option_id", "option_name", "duration_min", "needs_crew",
        "crew_required", "needs_backup", "requires_venue_access",
        "supplier_available",
    )

    def __init__(self, llm=None):
        """Provide an LLM only for isolated testing; live use requires Gemini."""
        if llm is not None:
            self.llm = llm
            return
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY is missing")
        model = os.getenv("AGENTICX_MODEL", "gemini-3.5-flash-lite")
        self.llm = ChatGoogleGenerativeAI(
            model=model, temperature=0
        ).with_structured_output(OperationsOpinion, method="json_schema")

    @staticmethod
    def check_constraints(case, option):
        """Return (passed, failed_checks, measured_values); no LLM call."""
        duration = valid_number(option.get("duration_min"))
        time_available = valid_number(case.get("time_left_min"))
        crew_required = valid_number(option.get("crew_required"))
        crew_available = valid_number(case.get("crew_count_available"))

        needs_crew = is_true(option.get("needs_crew")) or (
            crew_required is not None and crew_required > 0
        )
        needs_backup = is_true(option.get("needs_backup"))
        needs_venue = is_true(option.get("requires_venue_access"))

        checks = {
            "time": (
                duration is not None and time_available is not None
                and duration <= time_available
            ),
            "crew": (
                not needs_crew or (
                    crew_required is not None
                    and crew_required.is_integer()
                    and crew_required > 0
                    and crew_available is not None
                    and crew_available.is_integer()
                    and crew_required <= crew_available
                    and is_true(case.get("crew_available"))
                )
            ),
            "backup": (
                not needs_backup or is_true(case.get("backup_available"))
            ),
            "venue_access": (
                not needs_venue or is_true(case.get("venue_access"))
            ),
            "supplier": is_true(option.get("supplier_available")),
        }
        failed = [name for name, passed in checks.items() if not passed]
        measurements = {
            "duration_min": duration,
            "time_left_min": time_available,
            "crew_required": crew_required,
            "crew_count_available": crew_available,
            "needs_crew": needs_crew,
            "needs_backup": needs_backup,
            "requires_venue_access": needs_venue,
        }
        return not failed, failed, measurements

    def evaluate(self, case, option):
        passed, failed, values = self.check_constraints(case, option)
        option_id = str(option["option_id"])
        if not passed:
            return AgentEvaluation(
                agent=self.name, option_id=option_id, approved=False,
                score=0, blocking=True,
                reason=(
                    "Operational constraints failed: " + ", ".join(failed)
                    + ". Duration: " + str(values["duration_min"])
                    + " min; available time: " + str(values["time_left_min"])
                    + " min; crew required: " + str(values["crew_required"])
                    + "; crew available: " + str(values["crew_count_available"])
                    + ". Rejected."
                ),
            )

        case_input = {k: case.get(k) for k in self.CASE_FIELDS}
        option_input = {k: option.get(k) for k in self.OPTION_FIELDS}
        prompt = (
            "You are the Operations Agent for Studio 67. All deterministic "
            "time, crew, supplier, backup, and venue resource gates passed. "
            "Assess practical execution feasibility and logistical coordination "
            "for this incident using ONLY the operational facts given. "
            "Do not evaluate financial budget, audience quality, permits, or "
            "safety compliance; other agents own those judgments. "
            "Do not invent additional crew, equipment or suppliers. "
            "Return approved, score 0-100, and a concise evidence-based reason. "
            f"CASE: {case_input!r}; OPTION: {option_input!r}"
        )
        # Any API/schema failure must propagate to the coordinator, not masquerade
        # as a real approved/rejected LLM assessment.
        answer = self.llm.invoke(prompt)
        if isinstance(answer, dict):
            answer = OperationsOpinion.model_validate(answer)
        elif not isinstance(answer, OperationsOpinion):
            answer = OperationsOpinion.model_validate(answer.model_dump())
        return AgentEvaluation(
            agent=self.name, option_id=option_id,
            approved=answer.approved, score=answer.score,
            reason=(
                f"Operational gates passed (duration {values['duration_min']:g} "
                f"min / available {values['time_left_min']:g} min). "
                f"Gemini assessment: {answer.reason.strip()}"
            ),
            blocking=True,
        )

