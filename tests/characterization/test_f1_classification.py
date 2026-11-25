"""F1 — Classificar ticket: POST /tickets/classification.

Contrato recebido (v1): resposta síncrona com o corpo
{"ticket_id", "category", "priority"}.
"""

CATEGORIES = {"delivery", "payment", "exchange_return", "product_defect", "other"}
PRIORITIES = {"low", "medium", "high"}


def test_classification_delivery_high(client):
    r = client.post(
        "/tickets/classification",
        json={
            "ticket_id": "TK-00042",
            "text": "Meu pedido #481516 não chegou e já passou do prazo, urgente",
        },
    )
    assert r.status_code == 200
    body = r.json()
    # fixa campos E valores
    assert body == {"ticket_id": "TK-00042", "category": "delivery", "priority": "high"}


def test_classification_payment_high(client):
    r = client.post(
        "/tickets/classification",
        json={"ticket_id": "TK-X", "text": "Fui cobrado duas vezes no cartão"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"ticket_id": "TK-X", "category": "payment", "priority": "high"}


def test_classification_fields_and_domain(client):
    r = client.post(
        "/tickets/classification",
        json={"ticket_id": "TK-7", "text": "O produto chegou com a tela trincada"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"ticket_id", "category", "priority"}
    assert body["ticket_id"] == "TK-7"
    assert body["category"] in CATEGORIES
    assert body["priority"] in PRIORITIES


def test_classification_input_error_empty_text(client):
    # caso de erro de entrada: text vazio viola min_length=1 -> 422
    r = client.post(
        "/tickets/classification", json={"ticket_id": "TK-1", "text": ""}
    )
    assert r.status_code == 422


def test_classification_input_error_missing_field(client):
    r = client.post("/tickets/classification", json={"ticket_id": "TK-1"})
    assert r.status_code == 422
