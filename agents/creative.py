
"""Studio 67 Creative Agent — Gemini-based quality evaluation."""

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
    VERSION = "2026-11-creative-evidence-v3"

    CASE_FIELDS = (
        "case_id",
        "scenario",
        "incident",
        "required_quality_min",
    )

    OPTION_FIELDS = (
        "option_id",
        "option_name",
        "quality_score",
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
                "gemini-3.5-flash-lite",
            ),
            temperature=0,
            timeout=45,
            max_retries=1,
        ).with_structured_output(
            CreativeOpinion,
            method="json_schema",
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
            "quality_score",
        )

        minimum = self.valid_quality(
            case.get("required_quality_min"),
            "required_quality_min",
        )

        context = {
            key: case.get(key)
            for key in self.CASE_FIELDS
        }

        proposal = {
            key: option.get(key)
            for key in self.OPTION_FIELDS
        }

        prompt = f"""CREATIVE_LLM_QUALITY_V2
CREATIVE_EVIDENCE_GROUNDED_V3

You are the Creative Quality Expert in Studio 67,
an event crisis management multi-agent system.

YOUR RESPONSIBILITY:
Evaluate the proposed solution exclusively from the
perspective of creative quality, event presentation,
and preservation of the intended event experience.

YOU ARE THE DECISION-MAKER:
Use your own LLM reasoning to produce the approval
decision, quality score, and explanation.
The Python application must not calculate approval
on your behalf.

EVALUATION GUIDELINES:

1. Understand the incident and proposed option.

2. Assess whether the option offers a credible
   creative or presentation-quality response to
   the incident, based on supplied evidence.

3. Treat the provided quality_score as evidence
   of expected quality, not as a complete
   substitute for your own reasoning.

4. Respect required_quality_min as a mandatory
   quality standard. Reject options below it.
   Meeting the minimum does not automatically
   guarantee creative approval.

5. STRICT ROLE SEPARATION:
   Your authority is limited to creative quality,
   visual presentation and event experience.

   Safety, emergency access, permits, staffing,
   resources, budgets and logistics are exclusively
   evaluated by other agents.

6. If an incident concerns safety or operations,
   evaluate ONLY the creative presentation aspects
   of the proposed solution.

   Do not reject a proposal because it creates a
   safety risk, blocks emergency access, lacks crew,
   or fails an operational requirement.

   Do not infer poor creative quality merely from
   those non-creative problems.

7. Your approval is a CREATIVE approval only.
   It does NOT mean the proposal is safe,
   affordable or operationally feasible.

8. The minimum quality requirement is mandatory,
   but meeting it does not automatically guarantee
   creative approval. Use LLM reasoning to assess
   presentation suitability based on supplied facts.

9. In your explanation, discuss only creative
   quality and presentation-related evidence.
   Do not mention safety compliance, emergency
   access restrictions, staffing or budgets.

10. Never invent presentation benefits or visual
    characteristics that are not supported by
    the provided information.

EVIDENCE-BASED CREATIVE REASONING:

- Make the creative approval decision yourself using
  the LLM, option description and quality evidence.

- Explain the specific creative implications of the
  option, not just its numerical quality score.

- Distinguish recorded facts from reasonable
  interpretations.

- Never claim that visual coherence, design
  integrity, audience satisfaction or presentation
  quality is guaranteed without supporting evidence.

- Avoid absolute claims such as "ensures",
  "guarantees", "all expectations are met",
  or "no negative impacts".

- Do not invent visual features, event outcomes,
  or performance improvements.

- If detailed design evidence is unavailable,
  base your assessment on the supplied quality
  score and option description, acknowledging
  uncertainty naturally.

- Make a clear APPROVE or REJECT decision based
  only on creative-quality considerations.

- Respect the minimum quality standard, but do not
  treat meeting it as automatic approval.

- Never evaluate budget, staffing, logistics,
  execution time, equipment availability,
  emergency access, permits or safety.

- Your decision is a creative-quality judgment only,
  not an overall feasibility or safety approval.

SCORING:
Return a score between 0 and 100 supported by the
supplied quality evidence.
Do not introduce unsupported scoring criteria.

RESPONSE:
Return a structured result containing:
- approved: your quality-focused decision
- score: your quality assessment from 0 to 100
- reason: 2-3 concise, professional English sentences

Your explanation must:
- Address the specific option and incident.
- Explain the creative-quality reasoning.
- Avoid merely repeating the quality numbers.
- Avoid unsupported assumptions or exaggeration.
- Stay strictly within Creative responsibilities.

CASE: {context!r}

OPTION: {proposal!r}

VERIFIED QUALITY SCORE: {quality:g}
MINIMUM REQUIRED QUALITY: {minimum:g}
"""

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
