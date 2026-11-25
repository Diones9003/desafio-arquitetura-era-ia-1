"""Feature F3 — relatório de tópicos do período.

A lógica de agregação (varrer os tickets do período em lotes, somar as contagens por
tópico e guardar exemplos) é a mesma da v1. O que muda na `main` é QUEM a executa e
QUANDO: agora ela roda em segundo plano, dirigida por `main.py`, que reporta o
progresso e guarda o resultado no `JobStore`. Esta função não conhece HTTP nem o job —
recebe um callback de progresso e devolve o relatório pronto.
"""

import json
from datetime import date
from typing import Callable

from fastapi import HTTPException

from . import tickets
from .ports import LLMPort
from .schemas import PeriodInput, Topic, TopicsReport


def count_period_tickets(period: PeriodInput) -> int:
    """Quantos tickets caem no período — usado para validar e dimensionar o progresso."""
    return len(tickets.in_period(period.start, period.end))


def validate_period(period: PeriodInput) -> None:
    if period.start > period.end:
        raise HTTPException(status_code=422, detail="A data inicial é posterior à data final")


def topics(
    llm: LLMPort,
    capability: str,
    batch_size: int,
    period: PeriodInput,
    call_timeout: float,
    on_progress: Callable[[int], None] | None = None,
) -> TopicsReport:
    """Produz o relatório de tópicos do período, em lotes.

    `call_timeout` é o teto de cada chamada ao gateway. `on_progress(n)` é chamado após
    cada lote com o total de tickets já processados — é assim que o job expõe o andamento.
    """
    selected = tickets.in_period(period.start, period.end)

    # O mês inteiro não cabe numa chamada: processa em lotes, um depois do outro.
    totals: dict[str, dict] = {}
    processed = 0
    for first in range(0, len(selected), batch_size):
        batch = selected[first:first + batch_size]
        content = "\n".join(f"[{t['id']}] {t['text']}" for t in batch)
        answer = json.loads(llm.generate(capability, content, timeout=call_timeout))
        for item in answer["topics"]:
            current = totals.setdefault(item["topic"], {"count": 0, "examples": []})
            current["count"] += item["count"]
            current["examples"] = (current["examples"] + item["examples"])[:3]
        processed += len(batch)
        if on_progress is not None:
            on_progress(processed)

    items = [Topic(topic=name, **data) for name, data in totals.items()]
    items.sort(key=lambda t: (-t.count, t.topic))
    return TopicsReport(start=period.start, end=period.end, total_tickets=len(selected), topics=items)
