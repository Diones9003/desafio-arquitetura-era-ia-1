# Diagnóstico da v1 (aplicação recebida)

> Fonte das evidências: ambiente subido com `docker compose up -d --build --wait`
> (provider-fake:8090, app:8080, borda/edge:8000). Todas as requisições das features
> passam pela borda `localhost:8000`, como faz o avaliador. O `/admin/calls` do
> provider simulado é o instrumento de prova.

A aplicação recebida (`app/helpdesk/`) chama os SDKs `openai` e `anthropic`
diretamente de dentro de cada feature, de forma **síncrona**, com os **nomes
físicos dos modelos fixos em `config.py`** e **sem timeout nem política de retry
própria** (valem os padrões dos SDKs, que fazem novas tentativas sozinhos).

As quatro dores do cenário foram reproduzidas:

## Dor A — O relatório do mês nunca termina (504 da borda)

**Comando**

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 60 -X POST \
  localhost:8000/reports/topics -H "Content-Type: application/json" \
  -d '{"start":"2026-08-01","end":"2026-08-31"}'
```

**Observado**

- A borda devolveu **`HTTP 504` em exatos ~30 s** (`proxy_read_timeout 30s` em
  `edge/nginx.conf`).
- O mês são 5.000 tickets. A F3 divide em lotes de 150 (`TICKETS_PER_CALL=150`),
  ~34 lotes, e chama o modelo **um lote depois do outro, de forma síncrona**. Cada
  chamada `topics` ao `claude-fake-large` leva ~9,8 s (`/admin/calls`:
  `duration_ms: 9827`, `input_tokens: ~6600`, `output_tokens: 361`). O corpo só
  seria devolvido no fim → nenhum byte é enviado antes dos 30 s → `504`.
- **Desistir não é cancelar:** depois do `504` entregue ao cliente, o
  `/admin/calls` continuou crescendo (4 → 6 chamadas em +15 s). A aplicação segue
  gastando tokens em um relatório que ninguém está mais esperando.

**Causa no código**

- `app/helpdesk/report.py` → laço `for first in range(0, len(selected), config.TICKETS_PER_CALL)`
  processando lotes em série, resposta só no fim (modo síncrono).
- `app/helpdesk/main.py` → `POST /reports/topics` responde com o corpo completo
  (`def topics_report(...) -> TopicsReport`).
- `edge/nginx.conf` → `proxy_read_timeout 30s` (a borda não pode ser alterada; a
  fricção se resolve mudando o modo de execução da feature).

## Dor B — A sugestão deixa o atendente esperando sem ver nada

**Comando**

```bash
time curl -s -X POST localhost:8000/tickets/reply-suggestion \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"TK-00042","text":"Meu pedido #481516 não chegou e já passou do prazo, urgente"}'
```

**Observado**

- A resposta chegou **inteira, de uma vez, após ~16 s** (`real 0m15.9s`). O
  atendente fica olhando para uma tela parada até o texto completo aparecer — não
  há streaming. A saída da tarefa `suggest` é longa (texto completo de sugestão).

**Causa no código**

- `app/helpdesk/suggestion.py` → `llm.call_anthropic(...)` espera a geração inteira.
- `app/helpdesk/llm.py` → `anthropic_client.messages.create(...)` **sem `stream=True`**;
  retorna `response.content[0].text` só no fim.
- `app/helpdesk/main.py` → `POST /tickets/reply-suggestion` devolve o objeto
  completo (resposta síncrona), em vez de `text/event-stream`.

## Dor C — Com um provider fora do ar, parte do helpdesk para junto

**Comando**

```bash
curl -s -X POST localhost:8090/admin/failures -H "Content-Type: application/json" \
  -d '{"provider":"anthropic","mode":"error_500"}'
curl -s -o /dev/null -w "F2 %{http_code}\n" -X POST localhost:8000/tickets/reply-suggestion \
  -H "Content-Type: application/json" -d '{"ticket_id":"TK-1","text":"teste"}'
curl -s -o /dev/null -w "F1 %{http_code}\n" -X POST localhost:8000/tickets/classification \
  -H "Content-Type: application/json" -d '{"ticket_id":"TK-1","text":"pedido nao chegou"}'
```

**Observado**

- Com **anthropic em `error_500`**: F2 (sugestão) e F3 (relatório) devolvem
  **`HTTP 500`**; F1 (classificação) e F4 (extração), que usam `openai`, seguem em
  **`200`**. Ou seja, **metade do helpdesk para**.
- Com **openai em `error_500`**: F4 (extração) devolve **`HTTP 500`**.
- Além disso, **uma única requisição vira 3 chamadas ao provider**
  (`/admin/calls` mostra 3× `status: 500` para o mesmo pedido): os SDKs repetem a
  falha sozinhos (padrão de ~2 retries). Não há fallback para o outro provider:
  os dois `large` são equivalentes, mas a aplicação está presa a um provider por
  feature, sem inversão de dependência.

**Causa no código**

- `app/helpdesk/config.py` → acoplamento rígido: F1/F4 → `openai`, F2/F3 → `anthropic`.
- `app/helpdesk/llm.py` → um cliente por provider, **sem timeout, retry controlado
  ou fallback**; propaga a exceção do SDK, que vira `500` na borda.

## Dor D — Trocar o modelo exige mudar código e reconstruir a aplicação

**Comando**

```bash
grep -n "MODEL" app/helpdesk/config.py
```

**Observado**

```
10:CLASSIFICATION_MODEL = "gpt-fake-large"
11:EXTRACTION_MODEL = "gpt-fake-large"
12:SUGGESTION_MODEL = "claude-fake-large"
13:REPORT_MODEL = "claude-fake-large"
```

- O **nome físico do modelo está no código** (`config.py`). Trocar
  `gpt-fake-large` por `gpt-fake-mini` exige editar o arquivo, reconstruir a
  imagem (`docker compose build app`) e reiniciar o serviço `app`. Não é
  configuração: é deploy.

**Causa no código**

- `app/helpdesk/config.py` → constantes com nomes físicos dos modelos.
- `app/helpdesk/{classification,suggestion,extraction,report}.py` → cada feature
  lê `config.*_MODEL` e repassa ao `llm`, amarrando a feature ao provider e ao
  modelo concretos. É o acoplamento que o gateway (inversão de dependência) vem
  resolver nas fases seguintes.

## Síntese

| Dor | Sintoma | Modo correto (fases seguintes) |
|---|---|---|
| A | Relatório do mês → `504`, tokens gastos após desistência | Assíncrono (Request-Reply 202→303) |
| B | Atendente espera ~16 s sem ver nada | Streaming (SSE) |
| C | Provider fora do ar derruba metade do helpdesk; sem fallback | Gateway com fallback técnico + timeout/retry controlado |
| D | Nome do modelo no código → troca exige deploy | Capacidade lógica no gateway; troca por configuração |
