#!/usr/bin/env python3
"""Cria as virtual keys do gateway via API do LiteLLM (POST /key/generate).

Executado uma única vez pelo serviço `gateway-setup` do compose, depois que o
`gateway` fica saudável. Usa só a biblioteca padrão (urllib) para não exigir pip.

Cria duas chaves, com valores fixos vindos do ambiente para casarem com o .env:

  1. GATEWAY_API_KEY   — chave da APLICAÇÃO, com BUDGET mensal. Restrita às quatro
                         capacidades lógicas. É a única chave que o app usa.
  2. GATEWAY_LIMITED_KEY — chave de DEMONSTRAÇÃO de governança, com LIMITE DE
                         REQUISIÇÕES (rpm). Serve para provar que uma requisição
                         fora do limite é recusada pelo gateway antes de chegar
                         ao provider.

Idempotente: se a chave já existe (setup rodado antes), segue sem erro.
"""

import json
import os
import sys
import urllib.error
import urllib.request

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:4000").rstrip("/")
MASTER_KEY = os.environ["GATEWAY_MASTER_KEY"]
APP_KEY = os.environ["GATEWAY_API_KEY"]
LIMITED_KEY = os.environ.get("GATEWAY_LIMITED_KEY", "")

CAPABILITIES = ["classify", "suggest", "topics", "extract"]

# Budget da chave da aplicação (dólares por janela).
APP_MAX_BUDGET = float(os.environ.get("GATEWAY_APP_MAX_BUDGET", "50"))
APP_BUDGET_DURATION = os.environ.get("GATEWAY_APP_BUDGET_DURATION", "30d")
# Limite de requisições por minuto da chave de demonstração.
LIMITED_RPM = int(os.environ.get("GATEWAY_LIMITED_RPM", "2"))


def _post(path: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{GATEWAY_URL}{path}",
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {MASTER_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return exc.code, {"error": body}


def ensure_key(label: str, payload: dict) -> bool:
    status, body = _post("/key/generate", payload)
    if status == 200:
        print(f"[setup-keys] chave '{label}' criada ({payload.get('key', '')[:12]}...).")
        return True
    # Chave já existente é condição aceitável para um setup repetido.
    text = json.dumps(body).lower()
    if status in (400, 409) and ("already exists" in text or "duplicate" in text or "unique" in text):
        print(f"[setup-keys] chave '{label}' já existia — nada a fazer.")
        return True
    print(f"[setup-keys] FALHA ao criar '{label}': HTTP {status} {body}", file=sys.stderr)
    return False


def main() -> int:
    ok = True

    # 1) Chave da aplicação: com budget, restrita às capacidades lógicas.
    ok &= ensure_key("app (budget)", {
        "key": APP_KEY,
        "key_alias": "helpdesk-app",
        "models": CAPABILITIES,
        "max_budget": APP_MAX_BUDGET,
        "budget_duration": APP_BUDGET_DURATION,
        "metadata": {"owner": "helpdesk", "purpose": "aplicacao"},
    })

    # 2) Chave de demonstração: com limite de requisições por minuto.
    if LIMITED_KEY:
        ok &= ensure_key("limitada (rpm)", {
            "key": LIMITED_KEY,
            "key_alias": "helpdesk-rpm-demo",
            "models": CAPABILITIES,
            "rpm_limit": LIMITED_RPM,
            "metadata": {"owner": "helpdesk", "purpose": "demo-limite-requisicoes"},
        })
    else:
        print("[setup-keys] GATEWAY_LIMITED_KEY ausente — pulando a chave de demonstração.")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
