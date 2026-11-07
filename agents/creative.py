"""Genuine LLM-based Creative Agent. Requires a configured API key."""
import os
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from core.models import AgentEvaluation

class CreativeOpinion(BaseModel):
    approved: bool
    score: float = Field(ge=0,le=100)
    reason: str

class CreativeAgent:
    name='Creative'
    def __init__(self):
        if not os.getenv('OPENAI_API_KEY'):
            raise RuntimeError('Set OPENAI_API_KEY for real Creative LLM. No Mock fallback is used.')
        kwargs={'model':os.getenv('AGENTICX_MODEL','gpt-4o-mini'),'temperature':0}
        if os.getenv('OPENAI_BASE_URL'): kwargs['base_url']=os.environ['OPENAI_BASE_URL']
        self.llm=ChatOpenAI(**kwargs).with_structured_output(CreativeOpinion)

    def evaluate(self, case, option):
        prompt=("You are Studio 67 Creative Agent. Independently assess whether this option "
                "addresses the stated event incident and protects audience experience/quality. "
                "Reject irrelevant alternatives. Do not invent equipment or facts. "
                "Return structured approved/score/reason.\nCASE: " + repr(case) + '\nOPTION: ' + repr(option))
        answer=self.llm.invoke(prompt)
        meets_quality = float(option.get('quality_score') or 0) >= float(case.get('required_quality_min') or 0)
        return AgentEvaluation(agent=self.name,option_id=option['option_id'], approved=answer.approved and meets_quality,
                               score=float(answer.score),reason=answer.reason if meets_quality else 'Below minimum quality requirement',blocking=False)
