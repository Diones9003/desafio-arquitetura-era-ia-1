from fastapi import FastAPI

from . import classification, config, extraction, report, suggestion
from .adapters.gateway import GatewayLLM
from .schemas import (Classification, OrderData, PeriodInput, ReplySuggestion, TicketInput,
                      TopicsReport)

app = FastAPI(title="Helpdesk")

# Ponto de composição: cria o adaptador concreto uma vez e o injeta nas features.
# Trocar o gateway por outra implementação de LLMPort é só mudar esta linha.
llm = GatewayLLM(
    base_url=config.GATEWAY_URL,
    api_key=config.GATEWAY_API_KEY,
    max_output_tokens=config.MAX_OUTPUT_TOKENS,
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tickets/classification")
def classify_ticket(ticket: TicketInput) -> Classification:
    return classification.classify(llm, config.CLASSIFY, ticket)


@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput) -> ReplySuggestion:
    return suggestion.suggest(llm, config.SUGGEST, ticket)


@app.post("/tickets/extraction")
def extract_order_data(ticket: TicketInput) -> OrderData:
    return extraction.extract(llm, config.EXTRACT, ticket)


@app.post("/reports/topics")
def topics_report(period: PeriodInput) -> TopicsReport:
    return report.topics(llm, config.TOPICS, config.TICKETS_PER_CALL, period)
