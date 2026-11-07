
"""Operations Agent — Gemini LLM and validated resource checks."""

import os
import math
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from core.models import AgentEvaluation


class OperationsOpinion(BaseModel):
    approved: bool
    score: float = Field(ge=0, le=100)
    reason: str


def valid_number(value):
    """Return a non-negative finite number, or None."""
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)

        if math.isfinite(number) and number >= 0:
            return number

    except (TypeError, ValueError, OverflowError):
        pass

    return None


def is_true(value):
    """Interpret supported boolean values safely."""
    if value is True or value == 1:
        return True

    if isinstance(value, str):
        return value.strip().lower() in (
            "true", "yes", "1"
        )

    return False


class OperationsAgent:
    name = "Operations"

    def __init__(self):
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError(
                "GOOGLE_API_KEY is missing"
            )

        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv(
                "AGENTICX_MODEL",
                "gemini-3.8-flash"
            ),
            temperature=0
        ).with_structured_output(
            OperationsOpinion,
            method="json_schema"
        )

    def evaluate(self, case, option):
        duration = valid_number(
            option.get("duration_min")
        )

        time_available = valid_number(
            case.get("time_left_min")
        )

        crew_required = valid_number(
            option.get("crew_required")
        )

        crew_available = valid_number(
            case.get("crew_count_available")
        )

        needs_crew = (
            is_true(option.get("needs_crew"))
            or (
                crew_required is not None
                and crew_required > 0
            )
        )

        checks = {
            "time": (
                duration is not None
                and time_available is not None
                and duration <= time_available
            ),

            "crew": (
                not needs_crew
                or (
                    crew_required is not None
                    and crew_required.is_integer()
                    and crew_required > 0
                    and crew_available is not None
                    and crew_available.is_integer()
                    and crew_required <= crew_available
                    and is_true(
                        case.get("crew_available")
                    )
                )
            ),

            "backup": (
                not is_true(
                    option.get("needs_backup")
                )
                or is_true(
                    case.get("backup_available")
                )
            ),

            "venue_access": (
                not is_true(
                    option.get("requires_venue_access")
                )
                or is_true(
                    case.get("venue_access")
                )
            ),

            "supplier": is_true(
                option.get("supplier_available")
            )
        }

        failed = [
            name
            for name, passed in checks.items()
            if not passed
        ]

        if failed:
            return AgentEvaluation(
                agent=self.name,
                option_id=str(option["option_id"]),
                approved=False,
                score=0,
                reason=(
                    "Operational constraints failed: "
                    + ", ".join(failed)
                ),
                blocking=True
            )

        prompt = (
            "You are the Operations Agent for Studio 67. "
            "Evaluate practical operational feasibility. "
            "The resource checks have passed. "
            "Use only the provided facts. "
            "Do not invent suppliers, staff, or equipment. "
            "Return approved, score (0-100), and reason. "
            f"CASE: {case!r} OPTION: {option!r}"
        )

        answer = self.llm.invoke(prompt)

        return AgentEvaluation(
            agent=self.name,
            option_id=str(option["option_id"]),
            approved=answer.approved,
            score=answer.score,
            reason=answer.reason,
            blocking=True
        )

