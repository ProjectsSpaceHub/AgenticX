
"""Operations Agent: real Gemini judgment with mandatory resource gates."""

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
    VERSION = "2026-11-operations-v3"

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
            "gemini-3.5-flash-lite"
        )

        self.llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=0,
            timeout=45,
            max_retries=1,
        ).with_structured_output(
            OperationsOpinion,
            method="json_schema"
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

        if not passed:
            reason = (
                self.describe_failures(failed, values)
                + " Operations rejects this option "
                "because these required resources "
                "or conditions are not satisfied."
            )

            return AgentEvaluation(
                agent=self.name,
                option_id=option_id,
                approved=False,
                score=0,
                blocking=True,
                reason=reason,
            )

        case_input = {
            key: case.get(key)
            for key in self.CASE_FIELDS
        }

        option_input = {
            key: option.get(key)
            for key in self.OPTION_FIELDS
        }

        prompt = (
            "You are the Operations Agent for Studio 67, "
            "an event crisis management system.\n\n"

            "All mandatory time, crew, supplier, backup "
            "equipment, and venue access checks have "
            "already passed.\n\n"

            "YOUR TASK:\n"
            "Evaluate the operational practicality "
            "of carrying out this proposed solution "
            "for the specific incident.\n\n"

            "Discuss:\n"
            "1. How the proposed response can be "
            "implemented in the event setting.\n"
            "2. Whether the known operational "
            "resources support its execution.\n"
            "3. The practical coordination "
            "required by the proposal, but only "
            "where supported by the given facts.\n"
            "4. Why you accept or reject "
            "this operational plan.\n\n"

            "IMPORTANT RULES:\n"
            "- Do not evaluate budget or cost.\n"
            "- Do not evaluate event creativity "
            "or audience quality.\n"
            "- Do not evaluate safety permits "
            "or safety compliance.\n"
            "- Do not invent extra people, "
            "equipment, resources, or suppliers.\n"
            "- Do not approve merely because "
            "the numerical resource gates passed.\n"
            "- Explain practical consequences, "
            "not only numerical comparisons.\n\n"

            "REASONING STYLE:\n"
            "Provide 2 to 3 meaningful English "
            "sentences, specific to this incident "
            "and option. Give concrete operational "
            "reasons, without generic templates "
            "or unsupported assumptions.\n\n"

            "Return structured fields:\n"
            "- approved: boolean\n"
            "- score: number from 0 to 100\n"
            "- reason: specific operational justification\n\n"

            f"CASE: {case_input!r}\n\n"
            f"OPTION: {option_input!r}"
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

        status = (
            "The Operations Agent approves "
            "this operational plan."
            if answer.approved
            else
            "The Operations Agent rejects "
            "this operational plan."
        )

        reason = (
            f"{answer.reason.strip()} "
            f"All required operational resource "
            f"checks passed. {status}"
        )

        return AgentEvaluation(
            agent=self.name,
            option_id=option_id,
            approved=answer.approved,
            score=answer.score,
            reason=reason,
            blocking=True
        )

