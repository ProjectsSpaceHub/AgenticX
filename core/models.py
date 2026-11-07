"""Shared schemas. No fabricated/mock agent outputs."""
from typing import Any, Literal
from pydantic import BaseModel, Field

class AgentEvaluation(BaseModel):
    agent: Literal['Creative','Finance','Safety','Operations']
    option_id: str
    approved: bool
    score: float = Field(ge=0, le=100)
    reason: str
    blocking: bool = False

class ACLMessage(BaseModel):
    message_id: str
    case_id: str
    round: int
    sender: str
    receiver: str
    performative: Literal['REQUEST','INFORM','CFP','PROPOSE','ACCEPT','REFUSE']
    content: str
    ontology: str = 'studio67.event_crisis'
    in_reply_to: str | None = None

class RunResult(BaseModel):
    case_id: str
    status: Literal['AGREED','ESCALATED','FAILED']
    selected_option_id: str | None
    rounds: int
    evaluations: list[AgentEvaluation]
    messages: list[ACLMessage]
    reason: str
    is_mock: bool = False
