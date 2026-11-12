
import os
import math
import json

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from core.models import AgentEvaluation


class CreativeOpinion(BaseModel):
    approved: bool
    score: float = Field(ge=0, le=100)
    reason: str = Field(min_length=1)


class CreativeAgent:
    name = "Creative"
    VERSION = "2026-11-creative-v3"

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

    def __init__(self, llm=None):
        if llm is not None:
            self.llm = llm
            return

        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY is missing.")

        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv(
                "AGENTICX_MODEL",
                "gemini-3.5-flash-lite"
            ),
            temperature=0,
            timeout=45,
            max_retries=1,
        ).with_structured_output(
            CreativeOpinion,
            method="json_schema"
        )

    @staticmethod
    def _creative_view(data, allowed_fields):
        return {
            field: data[field]
            for field in allowed_fields
            if field in data and data[field] is not None
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
            case, self.CASE_FIELDS
        )

        creative_option = self._creative_view(
            option, self.OPTION_FIELDS
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
            "You are the Creative Agent of Studio 67, "
            "a multi-agent event crisis management system.\n\n"

            "YOUR RESPONSIBILITIES:\n"
            "Evaluate incident relevance, creative suitability, "
            "event quality, and audience experience.\n\n"

            "REQUIRED ANALYSIS:\n"
            "1. INCIDENT RELEVANCE: Explain how the proposed "
            "solution addresses the specific event crisis.\n"
            "2. AUDIENCE EXPERIENCE: Explain its effect on "
            "the event experience using only available evidence.\n"
            "3. QUALITY: Discuss whether the proposed solution "
            "is suitable for the event quality expectations. "
            f"The solution quality score is {quality:g}/100 "
            f"and the minimum required is {minimum_quality:g}/100. "
            "Do not confuse the numerical threshold with "
            "overall creative suitability.\n"
            "4. DECISION: Accept or reject based on the actual "
            "creative suitability and incident relevance.\n\n"

            "MANDATORY DECISION RULES:\n"
            "- A high quality score alone is NOT sufficient "
            "for acceptance.\n"
            "- Reject solutions that fail to address the "
            "incident appropriately.\n"
            "- Do not invent details about the audience, "
            "event, or implementation.\n"
            "- Explain meaningful limitations when supported.\n\n"

            "STRICT ROLE BOUNDARIES:\n"
            "- Do not assess budgets, prices, or costs.\n"
            "- Do not assess safety, risks, or permits.\n"
            "- Do not assess staff, resource availability, "
            "equipment availability, or execution time.\n"
            "- Only evaluate creative and experience factors.\n\n"

            "EXPLANATION STYLE:\n"
            "Write 2 to 3 clear, specific English sentences. "
            "Include how the solution addresses the incident, "
            "its effect on event or audience experience, "
            "and why it is creatively suitable or unsuitable. "
            "Explain meaningful reasons rather than "
            "only restating numbers. Avoid generic praise.\n\n"

            "Return structured fields:\n"
            "- approved: boolean\n"
            "- score: number between 0 and 100\n"
            "- reason: evidence-based creative justification\n\n"

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

        # Real Gemini assessment
        answer = self.llm.invoke(prompt)

        if isinstance(answer, dict):
            answer = CreativeOpinion.model_validate(answer)
        elif not isinstance(answer, CreativeOpinion):
            answer = CreativeOpinion.model_validate(
                answer.model_dump()
            )

        llm_reason = answer.reason.strip()

        # Both requirements must pass:
        # Gemini's creative judgment and the quality gate.
        approved = bool(answer.approved and quality_ok)

        # Verified numerical comparison from Python.
        if quality_ok:
            quality_explanation = (
                f"Quality assessment: {quality:g}/100 exceeds "
                f"or meets the required minimum of "
                f"{minimum_quality:g}/100. "
                f"The quality threshold is satisfied."
            )
        else:
            quality_explanation = (
                f"Quality assessment: {quality:g}/100 is below "
                f"the required minimum of "
                f"{minimum_quality:g}/100. "
                f"The quality threshold is not satisfied."
            )

        # Combine real Gemini reasoning with verified data.
        if not quality_ok:
            decision_explanation = (
                "The solution is rejected because it does "
                "not meet the mandatory quality requirement, "
                "regardless of the creative assessment."
            )
        elif approved:
            decision_explanation = (
                "The Creative Agent accepts the solution "
                "because the creative assessment and "
                "the minimum quality requirement both pass."
            )
        else:
            decision_explanation = (
                "The Creative Agent rejects the solution "
                "because Gemini found it creatively "
                "unsuitable despite meeting the "
                "minimum quality requirement."
            )

        reason = (
            f"{llm_reason} "
            f"{quality_explanation} "
            f"{decision_explanation}"
        )

        return AgentEvaluation(
            agent=self.name,
            option_id=option_id,
            approved=approved,
            score=float(answer.score),
            reason=reason,
            blocking=False
        )


