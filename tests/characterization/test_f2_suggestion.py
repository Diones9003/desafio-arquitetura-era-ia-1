"""F2 — Sugerir resposta: POST /tickets/reply-suggestion.

Contrato da `main` (requisito 6): resposta em STREAMING (Server-Sent Events),
`Content-Type: text/event-stream`. O texto chega em eventos `data: {"chunk": "..."}`
e termina com um evento `end` (`data: {"ticket_id": "..."}`). Uma falha no meio do
stream chega como evento `error` dentro do próprio stream (o status 200 já foi enviado).

O conteúdo gerado é determinístico, então reconstruímos o texto completo a partir dos
chunks e fixamos os mesmos valores observados na v1 — o contrato mudou de FORMA
(streaming), não de CONTEÚDO.
"""

import json

import httpx

TEXT = "Meu pedido #481516 não chegou e já passou do prazo, urgente"


def _consume_sse(response):
    """Lê um stream SSE e devolve (texto_reconstruido, lista_de_eventos_nomeados)."""
    chunks = []
    events = []  # tuplas (nome_do_evento, dados)
    current_event = None
    for line in response.iter_lines():
        if not line:
            current_event = None
            continue
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = json.loads(line.split(":", 1)[1])
            if current_event in ("end", "error"):
                events.append((current_event, data))
            else:
                chunks.append(data["chunk"])
    return "".join(chunks), events


def test_suggestion_is_streaming(client):
    with client.stream(
        "POST", "/tickets/reply-suggestion", json={"ticket_id": "TK-00042", "text": TEXT}
    ) as r:
        assert r.status_code == 200
        # o contrato novo é streaming, não JSON
        assert "text/event-stream" in r.headers.get("content-type", "")
        full, events = _consume_sse(r)

    # termina com um evento `end` carregando o ticket_id
    assert events[-1][0] == "end"
    assert events[-1][1] == {"ticket_id": "TK-00042"}

    # conteúdo determinístico reconstruído (mesmos valores da v1)
    assert full.startswith("Olá! Sinto muito pelo transtorno com a entrega do seu pedido.")
    assert "fazemos o reenvio sem nenhum custo adicional." in full
    assert "solicitar o cancelamento com reembolso integral." in full
    assert full.rstrip().endswith("Um abraço, equipe de atendimento.")


def test_suggestion_is_deterministic(client):
    def collect(ticket_id):
        with client.stream(
            "POST", "/tickets/reply-suggestion", json={"ticket_id": ticket_id, "text": TEXT}
        ) as r:
            assert r.status_code == 200
            full, _ = _consume_sse(r)
            return full

    assert collect("TK-A") == collect("TK-A")


def test_suggestion_input_error_empty_text(client):
    # validação de entrada acontece ANTES do stream: pedido inválido recebe 422
    r = client.post("/tickets/reply-suggestion", json={"ticket_id": "TK-1", "text": ""})
    assert r.status_code == 422


def test_suggestion_midstream_error_arrives_as_event(client, provider_url, reset_provider):
    """Com o primário do suggest em `midstream_error`, o cliente recebe evento `error`.

    O status 200 e os primeiros chunks já foram enviados, então o erro não pode virar
    um status HTTP — chega como evento `error` dentro do stream, no formato do contrato.
    """
    # primário do suggest é o claude large (anthropic). Força falha no meio.
    httpx.post(
        f"{provider_url}/admin/failures",
        json={"provider": "anthropic", "model": "claude-fake-large", "mode": "midstream_error"},
        timeout=10,
    )
    with client.stream(
        "POST", "/tickets/reply-suggestion", json={"ticket_id": "TK-ERR", "text": TEXT}
    ) as r:
        assert r.status_code == 200  # o status já havia sido enviado antes da falha
        assert "text/event-stream" in r.headers.get("content-type", "")
        _, events = _consume_sse(r)

    assert events[-1][0] == "error"
    assert events[-1][1]["ticket_id"] == "TK-ERR"
    assert "message" in events[-1][1]
