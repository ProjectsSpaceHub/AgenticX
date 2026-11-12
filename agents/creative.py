
"""Studio 67 Creative Agent: Gemini-powered, quality-focused evaluation."""

import math
import os
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from core.models import AgentEvaluation


class CreativeOpinion(BaseModel):
    approved: bool
    score: float = Field(ge=0, le=100)
    reason: str = Field(min_length=1)


class CreativeAgent:
    name = "Creative"
    VERSION = "2026-11-creative-gemini-quality-v1"

    CASE_FIELDS = (
        "case_id",
        "scenario",
        "incident",
        "required_quality_min"
    )

    OPTION_FIELDS = (
        "option_id",
        "option_name",
        "quality_score"
    )

    def __init__(self, llm=None):
        if llm is not None:
            self.llm = llm
            return

        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError("GOOGLE_API_KEY is missing")

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
    def valid_quality(value, field):
        if value is None or isinstance(value, bool):
            raise ValueError(
                f"{field} must be numeric"
            )

        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(
                f"{field} must be numeric"
            ) from None

        if not math.isfinite(number) or not 0 <= number <= 100:
            raise ValueError(
                f"{field} must be between 0 and 100"
            )

        return number

    def evaluate(self, case, option):
        quality = self.valid_quality(
            option.get("quality_score"),
            "quality_score"
        )

        minimum = self.valid_quality(
            case.get("required_quality_min"),
            "required_quality_min"
        )

        context = {
            key: case.get(key)
            for key in self.CASE_FIELDS
        }

        proposal = {
            key: option.get(key)
            for key in self.OPTION_FIELDS
        }

        prompt = (
            "You are the Creative Agent in Studio 67, "
            "an event-crisis multi-agent system.\n"

            "You alone decide whether to approve this "
            "proposed solution and explain your "
            "quality-focused assessment. The decision "
            "and justification must come from your "
            "reasoning, not from a Python-computed "
            "approval.\n\n"

            "YOUR ONLY RESPONSIBILITY: "
            "Assess the option's event quality and its "
            "relevance to the incident, using ONLY "
            "the supplied incident, option name, "
            "quality_score and required_quality_min.\n"

            "The required minimum quality is a "
            "mandatory quality standard. Reject any "
            "option with quality_score below "
            "required_quality_min. Meeting the "
            "threshold does not by itself guarantee "
            "acceptance when the described option "
            "clearly does not address the specific "
            "incident. Do not speculate about "
            "unspecified visual features, audience "
            "reactions, or capabilities.\n"

            "Do NOT judge cost, budgets, staffing, "
            "timing, logistics, permits or safety; "
            "these belong to other agents.\n"

            "Return a structured approved boolean, "
            "a score from 0 to 100 reflecting "
            "the supplied quality evidence, and a "
            "meaningful 2-3 sentence English reason "
            "specific to the incident and solution. "
            "State how the quality compares to the "
            "minimum requirement, and if relevant "
            "explain why the solution does or does "
            "not address the incident. Avoid generic "
            "or invented claims.\n\n"

            f"CASE: {context!r}\n"
            f"OPTION: {proposal!r}\n"
            f"Verified quality_score: {quality:g}; "
            f"verified minimum: {minimum:g}."
        )

        answer = self.llm.invoke(prompt)

        if isinstance(answer, dict):
            opinion = CreativeOpinion.model_validate(
                answer
            )
        elif isinstance(answer, CreativeOpinion):
            opinion = answer
        else:
            opinion = CreativeOpinion.model_validate(
                answer.model_dump()
            )

        return AgentEvaluation(
            agent=self.name,
            option_id=str(option["option_id"]),
            approved=opinion.approved,
            score=opinion.score,
            reason=opinion.reason.strip(),
            blocking=not opinion.approved,
        )


