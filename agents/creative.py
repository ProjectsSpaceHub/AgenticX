
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field
from core.models import AgentEvaluation


# Structured output returned by Gemini
class CreativeOpinion(BaseModel):
    approved: bool
    score: float = Field(ge=0, le=100)
    reason: str


# Creative LLM Agent
class CreativeAgent:
    name = "Creative"

    def __init__(self):
        if not os.getenv("GOOGLE_API_KEY"):
            raise RuntimeError(
                "GOOGLE_API_KEY is missing. "
                "Please configure your Gemini API key."
            )

        self.llm = ChatGoogleGenerativeAI(
            model=os.getenv(
                "AGENTICX_MODEL",
                "gemini-3.8-flash"
            ),
            temperature=0
        ).with_structured_output(
            CreativeOpinion,
            method="json_schema"
        )

    def evaluate(self, case, option):
        """
        Evaluate incident relevance, event quality,
        and audience experience using Gemini.
        """

        prompt = (
            "You are the Creative Agent for Studio 67, "
            "an event crisis management system.\n"

            "Evaluate whether the proposed solution "
            "addresses the incident and maintains "
            "event quality and audience experience.\n"

            "Reject irrelevant solutions.\n"

            "Use only the provided information. "
            "Do not invent facts.\n"

            "Return approved, score (0-100), "
            "and a short explanation.\n\n"

            f"CASE:\n{case}\n\n"

            f"OPTION:\n{option}"
        )

        # Real Gemini LLM evaluation
        answer = self.llm.invoke(prompt)

        # Deterministic quality requirement
        quality_score = float(
            option.get("quality_score") or 0
        )

        required_quality = float(
            case.get("required_quality_min") or 0
        )

        quality_ok = (
            quality_score >= required_quality
        )

        approved = bool(
            answer.approved and quality_ok
        )

        if quality_ok:
            reason = answer.reason
        else:
            reason = (
                "Below minimum quality requirement: "
                f"{quality_score} < {required_quality}"
            )

        return AgentEvaluation(
            agent=self.name,
            option_id=str(option["option_id"]),
            approved=approved,
            score=float(answer.score),
            reason=reason,
            blocking=False
        )
