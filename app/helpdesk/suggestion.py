"""Feature F2 — sugestão de resposta ao ticket, em streaming.

O texto da sugestão é consumível aos poucos: quem atende quer ver as primeiras
palavras já, não esperar o parágrafo inteiro. Por isso a feature vira streaming
(Server-Sent Events). Esta função pede o texto em pedaços pela porta `LLMPort.stream`
e os reemite no formato de eventos do contrato. Ela não conhece FastAPI; devolve um
gerador de linhas SSE que `main.py` embrulha numa resposta de streaming.

Contrato (ver README / Contratos sugeridos):
  data: {"chunk": "..."}            # um ou mais, conforme o texto chega
  event: end\ndata: {"ticket_id": "..."}             # fim normal
  event: error\ndata: {"ticket_id": "...", "message": "..."}   # falha no meio
Quando há falha no meio, o status HTTP 200 já foi enviado: o erro só pode chegar como
um evento dentro do próprio stream.
"""

import json
from typing import Iterator

from .ports import LLMPort
from .schemas import TicketInput


def suggest_stream(llm: LLMPort, capability: str, ticket: TicketInput) -> Iterator[str]:
    try:
        for piece in llm.stream(capability, ticket.text):
            yield f"data: {json.dumps({'chunk': piece}, ensure_ascii=False)}\n\n"
    except Exception:
        # O provider interrompeu no meio (ou o stream caiu). O 200 e vários chunks já
        # foram enviados, então não dá para trocar o status nem cair em fallback: o
        # cliente é avisado por um evento `error` dentro do próprio stream.
        error = {"ticket_id": ticket.ticket_id, "message": "A geração foi interrompida"}
        yield f"event: error\ndata: {json.dumps(error, ensure_ascii=False)}\n\n"
        return
    end = {"ticket_id": ticket.ticket_id}
    yield f"event: end\ndata: {json.dumps(end, ensure_ascii=False)}\n\n"
