"""ACL router. Each message has a real reason from a specific agent evaluation."""
from core.models import ACLMessage

class MessageBus:
    def __init__(self,case_id):
        self.case_id=case_id
        self.messages=[]

    def send(self, round, sender, receiver, performative, content, in_reply_to=None):
        msg=ACLMessage(message_id=f'{self.case_id}-M{len(self.messages)+1:04d}',case_id=self.case_id,
                       round=round,sender=sender,receiver=receiver,performative=performative,
                       content=str(content),in_reply_to=in_reply_to)
        self.messages.append(msg)
        return msg
