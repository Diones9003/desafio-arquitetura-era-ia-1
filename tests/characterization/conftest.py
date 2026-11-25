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
    # timeout generoso: a sugestão (F2) em streaming leva ~16 s até o fim; o relatório
    # de 1 dia (F3) roda assíncrono e é consultado por polling. Ainda abaixo da borda.
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as c:
        yield c


@pytest.fixture
def provider_url():
    """URL do provider simulado, para os testes que exercitam o /admin (falhas)."""
    return PROVIDER_URL


@pytest.fixture
def reset_provider():
    """Reseta o provider para modo normal antes e depois de um teste de falha."""
    def _reset():
        try:
            httpx.post(f"{PROVIDER_URL}/admin/reset", timeout=10)
        except httpx.HTTPError:
            pass
    _reset()
    yield
    _reset()
