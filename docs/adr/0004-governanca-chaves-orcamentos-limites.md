# 0004. Governança de IA: chaves, orçamento e limite de requisições

- Status: aceita
- Data: 2026-11-25
- Nível: corporativa

## Contexto

Na v1, as chaves dos providers vivem na aplicação e não há teto de gasto nem limite de uso.
Uma feature em loop, um abuso ou um pico derrubam o orçamento de IA da empresa sem que nada
recuse a chamada. A decisão de **quanto a empresa aceita gastar com IA** e **quem pode
quanto** é de nível corporativo: define política de custo, não detalhe de implementação.
O requisito 5 exige pelo menos uma chave com orçamento (budget) e uma com limite de
requisições, e que uma requisição fora do limite seja recusada **antes** de chegar ao provider.

## Opções consideradas

1. **Sem governança / só a master key**: simples, mas qualquer consumidor gasta sem teto.
2. **Controle de custo na aplicação** (contadores no código): espalha a política por cada
   serviço, difícil de auditar e fácil de furar.
3. **Virtual keys no gateway**, com budget e rpm por chave, criadas sem passo manual.

## Decisão

Opção 3. A **master key** (`GATEWAY_MASTER_KEY`) só administra o gateway e **nunca** vai à
aplicação. Duas virtual keys, criadas automaticamente pelo serviço efêmero `gateway-setup`
(ADR 0006) via `POST /key/generate`:

- **`GATEWAY_API_KEY` — chave da aplicação**, com **orçamento mensal** (`max_budget`,
  `budget_duration=30d`) e restrita às quatro capacidades lógicas. É a única chave que o
  serviço `app` recebe.
- **`GATEWAY_LIMITED_KEY` — chave de demonstração de governança**, com **limite de
  requisições** (`rpm_limit`). Prova que o gateway recusa o excedente antes do provider.

Política corporativa que isto materializa: **só providers self-hosted/aprovados** (sem SaaS
externo no fluxo), **teto de gasto por chave** e **menor privilégio** (cada chave só acessa
as capacidades de que precisa).

## Consequências

- Melhora: custo e uso ficam sob controle central e auditável; a aplicação perde o poder de
  gastar sem limite; chaves de provider somem do `app`.
- Piora/operar: virtual keys com budget/rpm exigem um banco (ADR 0006) e um passo de
  provisionamento — automatizado no compose, sem intervenção manual.
- Limitação conhecida: o gateway pode não ter preço dos modelos simulados e calcular custo
  zero; nesse caso o budget nunca estoura. Os preços do provider estão documentados; o
  roteiro de governança do README demonstra a recusa por **limite de requisições** (rpm),
  que não depende de tabela de preço, e descreve como exercitar o budget.

## Evidência

Limite de requisições (rpm=2 na chave de demonstração): a 3ª chamada é recusada com `429`
e **não** aparece em `/admin/calls` (não chegou ao provider):

```
for i in 1 2 3; do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:4000/chat/completions \
    -H "Authorization: Bearer $GATEWAY_LIMITED_KEY" -H 'Content-Type: application/json' \
    -d '{"model":"classify","messages":[{"role":"user","content":"TASK: classify\nteste"}]}'
done
# -> 200, 200, 429
```

Observado nesta entrega: `200, 200, 429`. Roteiro completo na seção "Roteiro de governança"
do README.
