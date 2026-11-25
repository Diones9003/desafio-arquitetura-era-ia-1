"""F3 — Relatório de temas: POST /reports/topics.

Contrato recebido (v1): resposta SÍNCRONA com o corpo
{"start", "end", "total_tickets", "topics": [{"topic", "count", "examples"}]}.

Para fixar valores sem estourar os 30 s da borda (o mês inteiro são 5.000 tickets
e, na v1 síncrona, dá 504), caracterizamos um período curto e determinístico:
um único dia (2026-08-01), que a v1 responde em ~10 s.
"""

PERIOD = {"start": "2026-08-01", "end": "2026-08-01"}


def test_report_shape_and_total(client):
    r = client.post("/reports/topics", json=PERIOD)
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"start", "end", "total_tickets", "topics"}
    assert body["start"] == "2026-08-01"
    assert body["end"] == "2026-08-01"
    # valor fixado: 137 tickets no dia
    assert body["total_tickets"] == 137


def test_report_topics_values(client):
    r = client.post("/reports/topics", json=PERIOD)
    assert r.status_code == 200
    topics = r.json()["topics"]

    # ordenado por count desc; temas em português
    counts = [t["count"] for t in topics]
    assert counts == sorted(counts, reverse=True)

    # cada tema tem a forma esperada e no máximo 3 exemplos
    for t in topics:
        assert set(t.keys()) == {"topic", "count", "examples"}
        assert isinstance(t["topic"], str) and t["topic"]
        assert isinstance(t["count"], int) and t["count"] > 0
        assert isinstance(t["examples"], list) and len(t["examples"]) <= 3

    # fixa os três temas de topo (valores determinísticos observados na v1)
    top3 = [(t["topic"], t["count"]) for t in topics[:3]]
    assert top3 == [
        ("Problema no rastreio", 20),
        ("Pedido extraviado", 15),
        ("Troca por tamanho", 11),
    ]
    assert topics[0]["examples"] == ["TK-00001", "TK-00007", "TK-00008"]


def test_report_input_error_start_after_end(client):
    # caso de erro de entrada: início depois do fim -> 422
    r = client.post(
        "/reports/topics", json={"start": "2026-08-31", "end": "2026-08-01"}
    )
    assert r.status_code == 422


def test_report_input_error_bad_date(client):
    r = client.post(
        "/reports/topics", json={"start": "not-a-date", "end": "2026-08-01"}
    )
    assert r.status_code == 422
