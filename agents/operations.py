"""Operations LLM plus deterministic resource gates."""
import os
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from core.models import AgentEvaluation
from agents.safety import true

class OperationsOpinion(BaseModel):
    approved: bool
    score: float = Field(ge=0,le=100)
    reason: str

class OperationsAgent:
    name='Operations'
    def __init__(self):
        if not os.getenv('OPENAI_API_KEY'):
            raise RuntimeError('Set OPENAI_API_KEY for real Operations LLM. No Mock fallback is used.')
        kwargs={'model':os.getenv('AGENTICX_MODEL','gpt-4o-mini'),'temperature':0}
        if os.getenv('OPENAI_BASE_URL'): kwargs['base_url']=os.environ['OPENAI_BASE_URL']
        self.llm=ChatOpenAI(**kwargs).with_structured_output(OperationsOpinion)

    def evaluate(self,case,option):
        checks={
          'time':float(option.get('duration_min') or 0)<=float(case.get('time_left_min') or 0),
          'backup':not true(option.get('needs_backup')) or true(case.get('backup_available')),
          'crew':not true(option.get('needs_crew')) or (true(case.get('crew_available')) and int(case.get('crew_count_available') or 0)>=int(option.get('crew_required') or 1)),
          'venue_access':not true(option.get('requires_venue_access')) or true(case.get('venue_access')),
          'supplier':true(option.get('supplier_available')),
        }
        if not all(checks.values()):
            return AgentEvaluation(agent=self.name,option_id=option['option_id'],approved=False,score=0,
                                   reason='Resource constraints failed: '+', '.join(k for k,v in checks.items() if not v),blocking=True)
        prompt=("You are Studio 67 Operations Agent. Given verified resource feasibility, assess "
                "practical logistics and identify other operational obstacles. Do not invent facts. "
                "Return structured approved/score/reason.\nCASE: " + repr(case) + '\nOPTION: '+repr(option))
        answer=self.llm.invoke(prompt)
        return AgentEvaluation(agent=self.name,option_id=option['option_id'],approved=answer.approved,
                               score=answer.score,reason=answer.reason,blocking=True)
