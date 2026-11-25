"""Fixtures da suíte de caracterização.

A suíte exercita as 4 features pela borda oficial (`localhost:8000`) e fixa o
comportamento observado da aplicação recebida (v1-coupled): campos E valores do
corpo das respostas, não só o status HTTP.

Pré-requisito: o ambiente no ar (`docker compose up -d --build --wait`).
A URL da borda pode ser trocada por `HELPDESK_BASE_URL` e a do provider simulado
por `PROVIDER_BASE_URL` (usada só para garantir modo `normal` antes dos testes).
"""

import os

import httpx
import pytest

BASE_URL = os.environ.get("HELPDESK_BASE_URL", "http://localhost:8000")
PROVIDER_URL = os.environ.get("PROVIDER_BASE_URL", "http://localhost:8090")


@pytest.fixture(scope="session", autouse=True)
def provider_normal():
    """Garante o provider simulado em modo normal e sem ruído de chamadas antigas."""
    try:
        httpx.post(f"{PROVIDER_URL}/admin/reset", timeout=10)
    except httpx.HTTPError:
        # Sem acesso ao /admin (ex.: provider atrás de rede fechada): segue mesmo
        # assim; os testes só dependem da borda.
        pass
    yield


@pytest.fixture(scope="session")
def client():
    # timeout generoso: na v1 a sugestão (F2) é síncrona e leva ~16 s; o relatório
    # de 1 dia, ~10 s. Ainda abaixo dos 30 s da borda.
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as c:
        yield c
