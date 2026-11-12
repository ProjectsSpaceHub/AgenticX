
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

    # Creative only receives relevant information.
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
                "GOOGLE_API_KEY is missing."
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
        return {
            field: data[field]
            for field in allowed_fields
            if field in data
            and data[field] is not None
        }

    @staticmethod
    def _valid_quality(value, field_name):
        if value is None or isinstance(value, bool):
            raise ValueError(
                f"{field_name} must be numeric."
            )

        try:
            number = float(value)
        except (ValueError, TypeError, OverflowError):
            raise ValueError(
                f"{field_name} must be numeric."
            ) from None

        if not math.isfinite(number):
            raise ValueError(
                f"{field_name} must be finite."
            )

        if not 0 <= number <= 100:
            raise ValueError(
                f"{field_name} must be between 0 and 100."
            )

        return number

    def evaluate(self, case, option):
        option_id = str(option["option_id"])

        creative_case = self._creative_view(
            case,
            self.CASE_FIELDS
        )

        creative_option = self._creative_view(
            option,
            self.OPTION_FIELDS
        )

        quality = self._valid_quality(
            option.get("quality_score"),
            "quality_score"
        )

        minimum_quality = self._valid_quality(
            case.get("required_quality_min"),
            "required_quality_min"
        )

        quality_ok = quality >= minimum_quality

        prompt = (
            "You are the Creative Agent of Studio 67.\n"
            "Evaluate the proposed solution for the "
            "current event crisis.\n\n"

            "YOUR RESPONSIBILITIES:\n"
            "1. Incident relevance.\n"
            "2. Creative suitability.\n"
            "3. Event quality.\n"
            "4. Audience experience.\n\n"

            "DECISION RULES:\n"
            "- Assess whether the solution addresses "
            "the actual incident.\n"
            "- Consider the event and audience experience.\n"
            "- Use the provided quality information.\n"
            "- Reject solutions that do not adequately "
            "address the incident.\n"
            "- Explain acceptance or rejection clearly.\n"
            "- Do not invent missing facts.\n\n"

            "ROLE BOUNDARIES:\n"
            "- Do not assess budgets, prices or costs.\n"
            "- Do not assess safety or permits.\n"
            "- Do not assess staff, equipment or time.\n"
            "- Stay within creative responsibilities.\n\n"

            "Return:\n"
            "- approved: boolean\n"
            "- score: number between 0 and 100\n"
            "- reason: short explanation\n\n"

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

        # Genuine Gemini evaluation.
        answer = self.llm.invoke(prompt)

        # Quality is a mandatory condition.
        approved = bool(
            answer.approved and quality_ok
        )

        # Explain the actual comparison.
        comparison = (
            f"Solution quality: {quality:g}/100. "
            f"Minimum required: {minimum_quality:g}/100. "
        )

        if not quality_ok:
            reason = (
                comparison
                + "The solution is below the minimum "
                "quality requirement. Rejected."
            )

        else:
            llm_reason = (answer.reason or "").strip()

            if not llm_reason:
                llm_reason = (
                    "No detailed creative justification "
                    "was provided."
                )

            quality_status = (
                "The quality requirement is met. "
            )

            decision_status = (
                "Creative assessment approved."
                if approved
                else "Creative assessment rejected."
            )

            reason = (
                comparison
                + quality_status
                + llm_reason
                + " "
                + decision_status
            )

        return AgentEvaluation(
            agent=self.name,
            option_id=option_id,
            approved=approved,
            score=float(answer.score),
            reason=reason,
            blocking=False
        )


