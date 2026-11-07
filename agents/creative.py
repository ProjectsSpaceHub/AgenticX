
import os
import math
import json

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from core.models import AgentEvaluation


class CreativeOpinion(BaseModel):
    approved: bool
    score: float = Field(ge=0, le=100)
    reason: str


class CreativeAgent:
    name = "Creative"

    # Only these fields are visible to Creative.
    # Finance, Safety, and Operations have separate responsibilities.

    CASE_FIELDS = (
        "case_id",
        "scenario",
        "incident",
        "incident_description",
        "description",
        "event_type",
        "audience",
        "audience_size",
        "required_quality_min",
    )

    OPTION_FIELDS = (
        "option_id",
        "option_name",
        "description",
        "option_description",
        "solution_description",
        "quality_score",
        "audience_impact",
        "experience_impact",
        "creative_impact",
    )

    def __init__(self):
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError(
                "GOOGLE_API_KEY is missing. "
                "Please configure your Gemini API key."
            )

        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv(
                "AGENTICX_MODEL",
                "gemini-3.5-flash-lite"
            )
        ).with_structured_output(
            CreativeOpinion,
            method="json_schema"
        )

    @staticmethod
    def _creative_view(data, allowed_fields):
        """
        Expose only fields relevant to Creative.
        All financial and operational constraints
        remain outside this agent's observation.
        """
        return {
            field: data[field]
            for field in allowed_fields
            if field in data
            and data[field] is not None
        }

    @staticmethod
    def _valid_quality(value, field_name):
        """
        Validate quality values without silently
        replacing missing information with zero.
        """
        if value is None or isinstance(value, bool):
            raise ValueError(
                f"{field_name} must be a valid number."
            )

        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(
                f"{field_name} must be numeric."
            ) from None

        if not math.isfinite(number):
            raise ValueError(
                f"{field_name} must be finite."
            )

        return number

    def evaluate(self, case, option):
        """
        Evaluate:
        - Incident relevance
        - Creative solution suitability
        - Event quality
        - Audience experience

        Budget decisions belong to Finance.
        Safety decisions belong to Safety.
        Resource feasibility belongs to Operations.
        """

        option_id = str(option["option_id"])

        creative_case = self._creative_view(
            case,
            self.CASE_FIELDS
        )

        creative_option = self._creative_view(
            option,
            self.OPTION_FIELDS
        )

        quality_score = self._valid_quality(
            option.get("quality_score"),
            "quality_score"
        )

        required_quality = self._valid_quality(
            case.get("required_quality_min", 0),
            "required_quality_min"
        )

        quality_ok = (
            quality_score >= required_quality
        )

        prompt = (
            "You are the Creative Agent for Studio 67, "
            "a multi-agent event crisis management system.\n\n"

            "YOUR RESPONSIBILITY:\n"
            "Evaluate the proposed solution ONLY from "
            "a creative and audience-experience perspective.\n\n"

            "Evaluate:\n"
            "1. Does the solution address the incident?\n"
            "2. Does it preserve event quality?\n"
            "3. Does it maintain audience experience?\n"
            "4. Is the proposed solution appropriate "
            "for the event situation?\n\n"

            "STRICT ROLE BOUNDARIES:\n"
            "- Do NOT evaluate budgets, prices, costs, "
            "savings, or financial feasibility.\n"
            "- Do NOT make safety or permit decisions.\n"
            "- Do NOT evaluate staff, equipment availability, "
            "execution time, or operational feasibility.\n"
            "- Financial decisions belong to Finance.\n"
            "- Safety decisions belong to Safety.\n"
            "- Operational decisions belong to Operations.\n"
            "- Never invent missing information.\n"
            "- Base your decision only on the provided "
            "creative information.\n"
            "- Reject a solution if it does not adequately "
            "address the incident or preserve event quality.\n"
            "- Explain your decision using only creative "
            "or audience-experience reasons.\n\n"

            "Return structured output containing:\n"
            "- approved: boolean\n"
            "- score: number from 0 to 100\n"
            "- reason: short, clear explanation\n\n"

            "CASE:\n"
            + json.dumps(
                creative_case,
                ensure_ascii=False,
                default=str
            )
            + "\n\nOPTION:\n"
            + json.dumps(
                creative_option,
                ensure_ascii=False,
                default=str
            )
        )

        # Real Gemini evaluation
        answer = self.llm.invoke(prompt)

        # Deterministic quality requirement
        approved = bool(
            answer.approved and quality_ok
        )

        if not quality_ok:
            reason = (
                "Below minimum event quality requirement: "
                f"{quality_score:g} < {required_quality:g}."
            )
        else:
            reason = answer.reason.strip()

            if not reason:
                reason = (
                    "Creative evaluation completed "
                    "without a detailed explanation."
                )

        return AgentEvaluation(
            agent=self.name,
            option_id=option_id,
            approved=approved,
            score=float(answer.score),
            reason=reason,
            blocking=False
        )

