
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
            "You are the Creative Agent in Studio 67, "
            "a multi-agent event crisis management system.\n\n"

            "YOUR ROLE:\n"
            "You are responsible for incident relevance, "
            "creative suitability, event quality, "
            "and audience experience.\n\n"

            "EVALUATION TASK:\n"
            "1. Explain the actual incident and how the "
            "proposed solution addresses it.\n"
            "2. Evaluate whether this response preserves "
            "the event experience and event quality.\n"
            "3. Assess how appropriate the solution is "
            "for the stated audience and event context.\n"
            "4. Identify a meaningful creative limitation "
            "or tradeoff if one is supported by the data.\n"
            "5. Decide whether to ACCEPT or REJECT.\n\n"

            "DECISION RULES:\n"
            "- Reject solutions that fail to address "
            "the actual incident.\n"
            "- Consider the provided quality score "
            "and minimum required quality.\n"
            "- Do not approve solely because the "
            "quality score is high.\n"
            "- Base the decision only on the case "
            "and option evidence.\n"
            "- Do not invent missing context.\n\n"

            "ROLE BOUNDARIES:\n"
            "- Do not assess budget, price, or cost.\n"
            "- Do not assess safety, risk, or permits.\n"
            "- Do not assess staff, equipment, "
            "resource availability, or execution time.\n"
            "- Focus strictly on the creative role.\n\n"

            "REASONING STYLE:\n"
            "Write 2 to 3 meaningful English sentences "
            "that explain WHY the solution is accepted "
            "or rejected in this specific incident. "
            "Connect the proposed action to the event "
            "experience and audience impact. "
            "Avoid generic statements, numerical-only "
            "comparisons, repetitive templates, "
            "and unsupported claims.\n\n"

            "Return structured fields:\n"
            "- approved: boolean\n"
            "- score: number from 0 to 100\n"
            "- reason: detailed but concise justification\n\n"

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

        answer = self.llm.invoke(prompt)

        if isinstance(answer, dict):
            answer = CreativeOpinion.model_validate(answer)
        elif not isinstance(answer, CreativeOpinion):
            answer = CreativeOpinion.model_validate(
                answer.model_dump()
            )

        approved = bool(answer.approved and quality_ok)
        llm_reason = answer.reason.strip()

        if not quality_ok:
            reason = (
                f"The proposed solution does not meet "
                f"the minimum event quality requirement "
                f"({quality:g} compared with "
                f"{minimum_quality:g}). "
                f"Gemini's creative assessment: "
                f"{llm_reason} "
                f"The mandatory quality gate therefore "
                f"rejects this option."
            )
        else:
            status = (
                "The Creative Agent approves this option."
                if approved
                else "The Creative Agent rejects this option."
            )

            reason = (
                f"{llm_reason} "
                f"The minimum quality requirement is met. "
                f"{status}"
            )

        return AgentEvaluation(
            agent=self.name,
            option_id=option_id,
            approved=approved,
            score=float(answer.score),
            reason=reason,
            blocking=False
        )



