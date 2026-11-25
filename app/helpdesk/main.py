"""Ponto de composição e rotas HTTP do helpdesk.

Aqui o adaptador concreto (GatewayLLM) é criado uma vez e injetado nas features. É o
ÚNICO lugar fora de `adapters/` que conhece a implementação de `LLMPort`; as features
recebem a porta e nunca importam o SDK nem o gateway.

Modo de execução de cada feature (decidido no ADR 0007):
  F1 classification  — síncrono   (resposta curta, alguém espera agora, cabe em 3s)
  F2 reply-suggestion — streaming  (texto consumível aos poucos; primeiro trecho cedo)
  F3 reports/topics  — assíncrono (5.000 tickets, minutos; ninguém espera na linha)
  F4 extraction      — síncrono   (resposta curta, alguém espera agora)
"""

import asyncio

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse, StreamingResponse

from . import classification, config, extraction, report, suggestion
from .adapters.gateway import GatewayLLM
from .jobs import JobStore
from .schemas import (Classification, OrderData, PeriodInput, TicketInput)

app = FastAPI(title="Helpdesk")

# Ponto de composição: cria o adaptador concreto uma vez e o injeta nas features.
# Trocar o gateway por outra implementação de LLMPort é só mudar esta linha.
llm = GatewayLLM(
    base_url=config.GATEWAY_URL,
    api_key=config.GATEWAY_API_KEY,
    max_output_tokens=config.MAX_OUTPUT_TOKENS,
    default_timeout=config.SYNC_TIMEOUT,
)

# Estado das tarefas assíncronas da F3 (em memória — ver jobs.py).
jobs = JobStore()

# Teto de tempo de cada chamada de lote do relatório. Mais folgado que o síncrono:
# roda em segundo plano, ninguém está pendurado na conexão.
REPORT_CALL_TIMEOUT = 60.0


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------- F1: síncrono
@app.post("/tickets/classification")
def classify_ticket(ticket: TicketInput) -> Classification:
    return classification.classify(llm, config.CLASSIFY, ticket)


# --------------------------------------------------------------- F2: streaming
@app.post("/tickets/reply-suggestion")
def suggest_reply(ticket: TicketInput):
    # Server-Sent Events. X-Accel-Buffering: no desliga o buffer do nginx da borda
    # SÓ para esta resposta (não podemos editar edge/nginx.conf): sem isso o proxy
    # seguraria os chunks e o primeiro trecho não chegaria cedo.
    return StreamingResponse(
        suggestion.suggest_stream(llm, config.SUGGEST, ticket),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# --------------------------------------------------------------- F4: síncrono
@app.post("/tickets/extraction")
def extract_order_data(ticket: TicketInput) -> OrderData:
    return extraction.extract(llm, config.EXTRACT, ticket)


# --------------------------------------------------------------- F3: assíncrono
async def _run_report(job_id: str, period: PeriodInput) -> None:
    """Executa o relatório em segundo plano e atualiza o job conforme avança."""
    try:
        total = await asyncio.to_thread(report.count_period_tickets, period)
        jobs.set_running(job_id, total)
        result = await asyncio.to_thread(
            report.topics, llm, config.TOPICS, config.TICKETS_PER_CALL, period,
            REPORT_CALL_TIMEOUT, lambda n: jobs.set_progress(job_id, n),
        )
        jobs.set_done(job_id, result.model_dump(mode="json"))
    except Exception as exc:  # falha chega ao cliente como state=failed, com motivo
        jobs.set_failed(job_id, f"{type(exc).__name__}: {exc}")


@app.post("/reports/topics")
async def create_report(period: PeriodInput):
    # Validação de entrada é síncrona: pedido inválido recebe 422 na hora, não 202.
    report.validate_period(period)
    job = jobs.create(period.start, period.end)
    asyncio.create_task(_run_report(job.id, period))
    # Aceito; o cliente acompanha pela URL de status.
    return Response(
        status_code=202,
        headers={
            "Location": f"/reports/topics/status/{job.id}",
            "Retry-After": str(config.REPORT_RETRY_AFTER),
        },
    )


@app.get("/reports/topics/status/{job_id}")
def report_status(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    if job.state == "done":
        # Pronto: redireciona para o recurso do resultado.
        return Response(status_code=303, headers={"Location": f"/reports/topics/{job.id}"})
    if job.state == "failed":
        return JSONResponse({"state": "failed", "reason": job.reason})
    # pending ou running: devolve o andamento.
    return JSONResponse({"state": job.state, "progress": job.progress})


@app.get("/reports/topics/{job_id}")
def report_result(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
    if job.state != "done":
        # Ainda não terminou: o cliente deve consultar o status, não o resultado.
        raise HTTPException(status_code=409, detail="Relatório ainda não está pronto")
    return JSONResponse(job.result)
