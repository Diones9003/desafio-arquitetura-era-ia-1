"""F3 — Relatório de temas: POST /reports/topics.

Contrato da `main` (requisito 6): Asynchronous Request-Reply. O POST aceita o pedido
e responde `202 Accepted` com os headers `Location` (URL de status) e `Retry-After`.
A URL de status responde `200` com o estado (`pending`/`running` + `progress`, ou
`failed` + `reason`) enquanto a tarefa não termina, e `303 See Other` apontando para o
resultado quando ela conclui. O resultado tem o corpo
{"start", "end", "total_tickets", "topics": [{"topic", "count", "examples"}]}.

O conteúdo é determinístico: caracterizamos um dia (2026-08-01, 137 tickets), que fica
pronto em ~10 s, e fixamos os mesmos valores observados na v1 — mudou o MODO de entrega
(assíncrono), não o conteúdo do relatório.
"""

import time

import httpx

ONE_DAY = {"start": "2026-08-01", "end": "2026-08-01"}


def _wait_for_result(client, status_url, timeout_s=50):
    """Faz polling do status até `303` (pronto) e devolve o corpo do resultado.

    Enquanto corre, valida o contrato do status: `200` com estado e progresso.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        # follow_redirects desligado: queremos VER o 303 e o Location, não segui-lo.
        s = client.get(status_url, follow_redirects=False)
        if s.status_code == 303:
            result_url = s.headers["location"]
            r = client.get(result_url)
            assert r.status_code == 200
            return r.json()
        assert s.status_code == 200
        body = s.json()
        assert body["state"] in ("pending", "running")
        assert "progress" in body and body["progress"].endswith("/137")
        time.sleep(2)
    raise AssertionError("relatório não ficou pronto a tempo")


def test_report_accepts_async_and_returns_202(client):
    r = client.post("/reports/topics", json=ONE_DAY)
    assert r.status_code == 202
    # headers obrigatórios do padrão Asynchronous Request-Reply
    assert r.headers.get("location")
    assert r.headers.get("retry-after")


def test_report_result_shape_and_total(client):
    r = client.post("/reports/topics", json=ONE_DAY)
    assert r.status_code == 202
    body = _wait_for_result(client, r.headers["location"])

    assert set(body.keys()) == {"start", "end", "total_tickets", "topics"}
    assert body["start"] == "2026-08-01"
    assert body["end"] == "2026-08-01"
    # valor fixado: 137 tickets no dia
    assert body["total_tickets"] == 137


def test_report_topics_values(client):
    r = client.post("/reports/topics", json=ONE_DAY)
    assert r.status_code == 202
    body = _wait_for_result(client, r.headers["location"])
    topics = body["topics"]

    # ordenado por count desc
    counts = [t["count"] for t in topics]
    assert counts == sorted(counts, reverse=True)

    for t in topics:
        assert set(t.keys()) == {"topic", "count", "examples"}
        assert isinstance(t["topic"], str) and t["topic"]
        assert isinstance(t["count"], int) and t["count"] > 0
        assert isinstance(t["examples"], list) and len(t["examples"]) <= 3

    # fixa os três temas de topo (mesmos valores determinísticos da v1)
    top3 = [(t["topic"], t["count"]) for t in topics[:3]]
    assert top3 == [
        ("Problema no rastreio", 20),
        ("Pedido extraviado", 15),
        ("Troca por tamanho", 11),
    ]
    assert topics[0]["examples"] == ["TK-00001", "TK-00007", "TK-00008"]


def test_report_input_error_start_after_end(client):
    # validação síncrona: início depois do fim -> 422, antes de aceitar a tarefa
    r = client.post("/reports/topics", json={"start": "2026-08-31", "end": "2026-08-01"})
    assert r.status_code == 422


def test_report_input_error_bad_date(client):
    r = client.post("/reports/topics", json={"start": "not-a-date", "end": "2026-08-01"})
    assert r.status_code == 422


def test_report_failure_reaches_failed_state(client, provider_url, reset_provider):
    """Com os dois providers em `error_500`, a tarefa chega a `failed` com motivo.

    O cliente nunca fica preso em `running`: o estado de falha fica visível na URL de
    status, com o motivo, bem dentro dos 60 s exigidos.
    """
    for provider in ("openai", "anthropic"):
        httpx.post(
            f"{provider_url}/admin/failures",
            json={"provider": provider, "mode": "error_500"},
            timeout=10,
        )

    r = client.post("/reports/topics", json=ONE_DAY)
    assert r.status_code == 202
    status_url = r.headers["location"]

    deadline = time.time() + 60
    state = None
    while time.time() < deadline:
        s = client.get(status_url, follow_redirects=False)
        assert s.status_code == 200  # nunca vira 303 (não conclui com sucesso)
        body = s.json()
        state = body["state"]
        if state == "failed":
            assert body.get("reason")  # o motivo da falha fica visível
            break
        time.sleep(2)
    assert state == "failed"
