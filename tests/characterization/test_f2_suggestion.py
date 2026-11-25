"""F2 — Sugerir resposta: POST /tickets/reply-suggestion.

Contrato recebido (v1): resposta SÍNCRONA (não streaming), corpo
{"ticket_id", "suggestion"} com o texto completo de uma vez. A saída do provider
simulado é determinística, então fixamos o conteúdo observado.
"""

TEXT = "Meu pedido #481516 não chegou e já passou do prazo, urgente"


def test_suggestion_shape_and_value(client):
    r = client.post(
        "/tickets/reply-suggestion", json={"ticket_id": "TK-00042", "text": TEXT}
    )
    assert r.status_code == 200
    # v1 é síncrona: JSON, não event-stream
    assert "application/json" in r.headers.get("content-type", "")
    body = r.json()
    assert set(body.keys()) == {"ticket_id", "suggestion"}
    assert body["ticket_id"] == "TK-00042"

    suggestion = body["suggestion"]
    assert isinstance(suggestion, str) and len(suggestion) > 0
    # fixa valores determinísticos do texto gerado
    assert suggestion.startswith(
        "Olá! Sinto muito pelo transtorno com a entrega do seu pedido."
    )
    assert "fazemos o reenvio sem nenhum custo adicional." in suggestion
    assert "solicitar o cancelamento com reembolso integral." in suggestion
    assert suggestion.rstrip().endswith(
        "Um abraço, equipe de atendimento."
    )


def test_suggestion_is_deterministic(client):
    r1 = client.post(
        "/tickets/reply-suggestion", json={"ticket_id": "TK-A", "text": TEXT}
    )
    r2 = client.post(
        "/tickets/reply-suggestion", json={"ticket_id": "TK-A", "text": TEXT}
    )
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["suggestion"] == r2.json()["suggestion"]


def test_suggestion_input_error_empty_text(client):
    r = client.post(
        "/tickets/reply-suggestion", json={"ticket_id": "TK-1", "text": ""}
    )
    assert r.status_code == 422
