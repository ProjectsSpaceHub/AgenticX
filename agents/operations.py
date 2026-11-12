
"""Operations Agent: Gemini evaluation with mandatory resource gates."""

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
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None

    if math.isfinite(number) and number >= 0:
        return number

    return None


def is_true(value):
    if value is True:
        return True

    if isinstance(value, bool) or value is None:
        return False

    if isinstance(value, (int, float)):
        return math.isfinite(value) and value == 1

    if isinstance(value, str):
        return value.strip().lower() in (
            "true", "yes", "1"
        )

    return False


class OperationsAgent:
    name = "Operations"
    VERSION = "2026-11-operations-gemini-all-v4"

    CASE_FIELDS = (
        "case_id",
        "scenario",
        "incident",
        "severity",
        "time_left_min",
        "crew_available",
        "crew_count_available",
        "backup_available",
        "venue_access",
    )

    OPTION_FIELDS = (
        "option_id",
        "option_name",
        "duration_min",
        "needs_crew",
        "crew_required",
        "needs_backup",
        "requires_venue_access",
        "supplier_available",
    )

    def __init__(self, llm=None):
        if llm is not None:
            self.llm = llm
            return

        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError(
                "GOOGLE_API_KEY is missing"
            )

        model = os.getenv(
            "AGENTICX_MODEL",
            "gemini-3.5-flash-lite",
        )

        self.llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0,
            timeout=45,
            max_retries=1,
        ).with_structured_output(
            OperationsOpinion,
            method="json_schema",
        )

    @staticmethod
    def check_constraints(case, option):
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

        needs_backup = is_true(
            option.get("needs_backup")
        )

        needs_venue = is_true(
            option.get("requires_venue_access")
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
                not needs_backup
                or is_true(
                    case.get("backup_available")
                )
            ),

            "venue_access": (
                not needs_venue
                or is_true(
                    case.get("venue_access")
                )
            ),

            "supplier": is_true(
                option.get("supplier_available")
            ),
        }

        failed = [
            name
            for name, passed in checks.items()
            if not passed
        ]

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

    @staticmethod
    def describe_failures(failed, values):
        explanations = []

        if "time" in failed:
            explanations.append(
                "The option cannot be completed within "
                "the time currently available. "
                f"It requires {values['duration_min']} "
                f"minutes, but only "
                f"{values['time_left_min']} "
                "minutes are available."
            )

        if "crew" in failed:
            explanations.append(
                "The required operational crew is not "
                "available in sufficient numbers. "
                f"The option requires "
                f"{values['crew_required']} crew members, "
                f"while {values['crew_count_available']} "
                "are recorded as available."
            )

        if "backup" in failed:
            explanations.append(
                "This proposal depends on backup "
                "equipment, but the selected scenario "
                "states that backup equipment is "
                "unavailable."
            )

        if "venue_access" in failed:
            explanations.append(
                "The proposed work requires venue "
                "access that is not currently available."
            )

        if "supplier" in failed:
            explanations.append(
                "The solution relies on supplier "
                "availability, but the required "
                "supplier is not available."
            )

        return " ".join(explanations)

    def evaluate(self, case, option):
        passed, failed, values = self.check_constraints(
            case, option
        )

        option_id = str(option["option_id"])

        case_input = {
            key: case.get(key)
            for key in self.CASE_FIELDS
        }

        option_input = {
            key: option.get(key)
            for key in self.OPTION_FIELDS
        }

        prompt = (
            "You are the Operations Agent of Studio 67.\n"
            "You are an LLM decision-maker responsible ONLY "
            "for operational feasibility.\n\n"

            "Analyze every proposal, including proposals with "
            "failed mandatory resource checks.\n"

            "Assess the incident, implementation feasibility, "
            "time, crew, equipment, supplier and venue access.\n"

            "The Python checks below are verified constraints. "
            "You MUST NOT approve a proposal if any mandatory "
            "check failed. These checks are non-negotiable.\n"

            "If checks passed, independently assess whether "
            "the proposal is operationally practical. "
            "You may approve or reject it with justification.\n"

            "If checks failed, reject the proposal and explain "
            "the specific operational obstacles, their practical "
            "consequences, and what would need to change. "
            "Do not claim missing resources are available.\n"

            "Never judge budgets, financial cost, creative "
            "quality, safety compliance or permits.\n"

            "Give a professional, specific 2-3 sentence "
            "English explanation. Avoid generic responses, "
            "invented facts and unsupported assumptions.\n"

            "Return approved (boolean), score (0-100), "
            "and reason (English justification).\n\n"

            f"CASE: {case_input!r}\n"
            f"OPTION: {option_input!r}\n"
            f"MANDATORY_CHECKS_PASSED: {passed!r}\n"
            f"FAILED_CHECKS: {failed!r}\n"
            f"MEASUREMENTS: {values!r}\n"
            f"VERIFIED_FAILURE_DETAILS: "
            f"{self.describe_failures(failed, values)!r}"
        )

        answer = self.llm.invoke(prompt)

        if isinstance(answer, dict):
            answer = OperationsOpinion.model_validate(
                answer
            )
        elif not isinstance(answer, OperationsOpinion):
            answer = OperationsOpinion.model_validate(
                answer.model_dump()
            )

        # Gemini evaluates both accepted and rejected options.
        # Mandatory resource constraints cannot be overridden.
        approved = bool(passed and answer.approved)

        if not passed:
            reason = (
                f"{answer.reason.strip()} "
                f"Verified blocking constraints: "
                f"{self.describe_failures(failed, values)} "
                "Operations rejects this proposal."
            )
            score = min(answer.score, 49)
        else:
            decision = (
                "approves" if approved else "rejects"
            )
            reason = (
                f"{answer.reason.strip()} "
                f"All mandatory operational checks passed. "
                f"Operations {decision} this proposal."
            )
            score = answer.score

        return AgentEvaluation(
            agent=self.name,
            option_id=option_id,
            approved=approved,
            score=score,
            reason=reason,
            blocking=True,
        )
