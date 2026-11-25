"""F4 — Extrair dados do pedido: POST /tickets/extraction.

Contrato recebido (v1): resposta síncrona com o corpo
{"ticket_id", "order_number", "product"}. order_number no formato #NNNNNN ou null.
"""

import re

ORDER_FORMAT = re.compile(r"^#\d{6}$")


def test_extraction_with_order_number(client):
    r = client.post(
        "/tickets/extraction",
        json={"ticket_id": "TK-00042", "text": "Quero trocar o pedido #605065 que veio quebrado"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"ticket_id": "TK-00042", "order_number": "#605065", "product": None}


def test_extraction_without_order_number(client):
    r = client.post(
        "/tickets/extraction",
        json={"ticket_id": "TK-Y", "text": "Produto chegou com defeito mas nao lembro o numero"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"ticket_id": "TK-Y", "order_number": None, "product": None}


def test_extraction_fields_and_format(client):
    r = client.post(
        "/tickets/extraction",
        json={"ticket_id": "TK-Z", "text": "O pedido #123456 chegou errado"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"ticket_id", "order_number", "product"}
    assert body["ticket_id"] == "TK-Z"
    if body["order_number"] is not None:
        assert ORDER_FORMAT.match(body["order_number"])


def test_extraction_input_error_empty_text(client):
    r = client.post("/tickets/extraction", json={"ticket_id": "TK-1", "text": ""})
    assert r.status_code == 422
