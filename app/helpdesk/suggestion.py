from .ports import LLMPort
from .schemas import ReplySuggestion, TicketInput


def suggest(llm: LLMPort, capability: str, ticket: TicketInput) -> ReplySuggestion:
    text = llm.generate(capability, ticket.text)
    return ReplySuggestion(ticket_id=ticket.ticket_id, suggestion=text)
