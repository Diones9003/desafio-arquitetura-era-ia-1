import json

from fastapi import HTTPException

from . import tickets
from .ports import LLMPort
from .schemas import PeriodInput, Topic, TopicsReport


def topics(llm: LLMPort, capability: str, batch_size: int, period: PeriodInput) -> TopicsReport:
    if period.start > period.end:
        raise HTTPException(status_code=422, detail="A data inicial é posterior à data final")

    selected = tickets.in_period(period.start, period.end)

    # O mês inteiro não cabe numa chamada: processa em lotes, um depois do outro.
    totals: dict[str, dict] = {}
    for first in range(0, len(selected), batch_size):
        batch = selected[first:first + batch_size]
        content = "\n".join(f"[{t['id']}] {t['text']}" for t in batch)
        answer = json.loads(llm.generate(capability, content))
        for item in answer["topics"]:
            current = totals.setdefault(item["topic"], {"count": 0, "examples": []})
            current["count"] += item["count"]
            current["examples"] = (current["examples"] + item["examples"])[:3]

    items = [Topic(topic=name, **data) for name, data in totals.items()]
    items.sort(key=lambda t: (-t.count, t.topic))
    return TopicsReport(start=period.start, end=period.end, total_tickets=len(selected), topics=items)
