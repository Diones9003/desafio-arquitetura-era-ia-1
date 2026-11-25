# 0006. Serviços extras no compose: banco do gateway e provisionamento de chaves

- Status: aceita
- Data: 2026-11-25
- Nível: software

## Contexto

A restrição do desafio exige que **todo serviço** adicionado ao compose além de
`provider-fake`, `edge`, `app` e `gateway` tenha um ADR que o justifique a partir de um
requisito. A governança do ADR 0004 (virtual keys com budget e limite de requisições) é um
requisito do enunciado (requisito 5), e a ferramenta escolhida (LiteLLM, ADR 0001) impõe
duas necessidades técnicas para entregá-la.

## Opções consideradas

1. **Só budget "em memória" no gateway**, sem banco: o LiteLLM não persiste virtual keys,
   gastos nem contadores de limite sem um banco; sem ele não há como **recusar** por budget
   ou por rpm — o efeito exigido não acontece.
2. **Criar as chaves à mão** depois de subir (curl manual): quebra o critério
   "`docker compose up` sobe tudo sem passo manual adicional".
3. **Banco dedicado + serviço efêmero de provisionamento**, ambos no compose.

## Decisão

Opção 3. Dois serviços extras, cada um amarrado a um requisito:

- **`gateway-db`** (`postgres:16-alpine`): banco do gateway. **Por que existe:** virtual
  keys com budget e limite de requisições (requisito 5 / ADR 0004) exigem persistência; o
  LiteLLM usa Postgres para isso. Sem ele, o gateway não recusa por budget/limite.
- **`gateway-setup`** (`python:3.12-slim`, efêmero): roda `gateway/setup-keys.py` uma única
  vez, quando o `gateway` fica saudável, cria as duas virtual keys e termina. **Por que
  existe:** as chaves precisam ser criadas **sem passo manual** (requisito 5 + critério do
  `docker compose up` sem intervenção). Usa `depends_on: condition:
  service_completed_successfully` para o `app` só subir depois que as chaves existem.

## Consequências

- Melhora: `docker compose up -d --build --wait` entrega governança funcionando, do zero,
  sem comando manual.
- Piora/operar: mais duas peças no ambiente. O `gateway-setup` é efêmero (não fica rodando);
  o `gateway-db` é um volume a cuidar. É o custo mínimo para o efeito exigido; nenhuma das
  peças acrescenta capacidade além do que o requisito 5 pede.

## Evidência

```
docker compose up -d --build --wait     # sobe db, gateway, cria chaves, sobe app
docker compose ps gateway-setup         # estado: exited (0) -> rodou e terminou
curl -s localhost:8000/health           # 200, sem nenhum passo manual
```

O log do `gateway-setup` mostra as duas chaves criadas; o roteiro de governança do README
prova a recusa por limite, que só funciona porque o `gateway-db` persiste o contador.
