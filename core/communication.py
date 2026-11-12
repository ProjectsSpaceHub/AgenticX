
"""Structured, traceable FIPA-style ACL messages for Studio 67.

Uses the project's shared ACLMessage schema and consistent ontology.
"""

from core.models import ACLMessage

VALID_PERFORMATIVES = frozenset({
    "REQUEST", "INFORM", "CFP", "PROPOSE", "ACCEPT", "REFUSE"
})
ONTOLOGY = "studio67.event_crisis"


class MessageBus:
    def __init__(self, case_id):
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("case_id must be a non-empty string")
        self.case_id = case_id
        self.messages = []

    def send(self, round, sender, receiver, performative, content,
             in_reply_to=None):
        if type(round) is not int or round < 1:
            raise ValueError("Round must be a positive integer")
        for name, value in (
            ("sender", sender), ("receiver", receiver), ("content", content)
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-empty string")
        if performative not in VALID_PERFORMATIVES:
            raise ValueError("Invalid ACL performative")
        if self.messages and round < self.messages[-1].round:
            raise ValueError("Message rounds must not decrease")

        if in_reply_to is not None:
            referenced = next(
                (m for m in self.messages if m.message_id == in_reply_to),
                None,
            )
            if referenced is None:
                raise ValueError("Referenced message does not exist")
            if referenced.round > round:
                raise ValueError("Cannot reply to a future round")
            if referenced.receiver != "ALL" and sender != referenced.receiver:
                raise ValueError("Reply sender must match original receiver")
            if referenced.sender != receiver:
                raise ValueError("Reply receiver must match original sender")

        message = ACLMessage(
            message_id=f"{self.case_id}-M{len(self.messages)+1:04d}",
            case_id=self.case_id, round=round, sender=sender,
            receiver=receiver, performative=performative,
            content=content, ontology=ONTOLOGY, in_reply_to=in_reply_to,
        )
        self.messages.append(message)
        return message

    def history(self, agent=None, performative=None):
        messages = self.messages
        if agent is not None:
            messages = [
                m for m in messages
                if m.sender == agent or m.receiver in (agent, "ALL")
            ]
        if performative is not None:
            if performative not in VALID_PERFORMATIVES:
                raise ValueError("Invalid ACL performative filter")
            messages = [m for m in messages if m.performative == performative]
        return messages

    def to_records(self):
        return [m.model_dump() for m in self.messages]
