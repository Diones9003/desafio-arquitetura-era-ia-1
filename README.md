# Helpdesk com IA — da integração frágil à arquitetura resiliente

Fork do desafio "Arquitetura na Era da IA". A entrega está na branch `main`; as tags
`v1-coupled` e `v2-decoupled` marcam os estados reais da evolução.

> **Esta é a versão final (`main`).** A aplicação chama os modelos exclusivamente pelo
> gateway, por capacidades lógicas e sem chaves de provider, e cada feature entrega no modo
> decidido pela árvore de decisão (ADR 0007): **F1 e F4 síncronas, F2 em streaming (SSE),
> F3 assíncrona (202 + status)**. As tags `v1-coupled` (aplicação recebida + caracterização)
> e `v2-decoupled` (refatorada atrás do gateway, mesmo comportamento) marcam os estados
> anteriores — a suíte de caracterização é idêntica entre as duas tags.

## Visão geral

O helpdesk tem IA em quatro pontos (classificar ticket, sugerir resposta, relatório de
temas, extrair dados do pedido). Na v1, cada feature chamava o SDK do provider direto do
código, com os modelos físicos fixos em `config.py`, sem timeout, retry controlado nem
fallback. Esta versão aplica **inversão de dependência à IA**: a aplicação depende de uma
porta (`LLMPort`) e de **capacidades lógicas** (`classify`, `suggest`, `topics`, `extract`),
e um **AI Gateway self-hosted (LiteLLM Proxy)** decide o modelo físico, o provider, a
credencial, o timeout, o retry, o fallback, o orçamento e o limite de requisições.

**Como o sistema se comporta quando um provider cai:** cada capacidade tem um primário e um
**fallback técnico** no `large` equivalente do outro provider; o gateway faz o failover
automático (no máximo **2 tentativas por destino**). Se os **dois `large`** caírem, a
política é **por feature** (ADR 0003): F1 (classificação) cai no modelo `mini`; F2, F3 e F4
**falham explicitamente**, porque uma resposta pior é pior que nenhuma para quem as consome
(texto ao cliente, decisão de negócio, automação sem revisão humana).

## Diagnóstico da v1

Ambiente subido com `docker compose up -d --build --wait`; todas as chamadas passam pela
borda (`localhost:8000`); o `/admin/calls` do provider simulado é o instrumento de prova.
Detalhe completo (saídas de `/admin/calls`, tempos) em [`docs/diagnostico-v1.md`](docs/diagnostico-v1.md).

### Dor A — O relatório do mês nunca termina (504 da borda)

```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 60 -X POST \
  localhost:8000/reports/topics -H "Content-Type: application/json" \
  -d '{"start":"2026-08-01","end":"2026-08-31"}'
```

- **Observado:** `HTTP 504` em ~30 s (`proxy_read_timeout 30s` da borda). O mês são 5.000
  tickets em ~34 lotes síncronos (~9,8 s cada em `/admin/calls`); o corpo só sairia no fim →
  nenhum byte antes dos 30 s → `504`. **Desistir não é cancelar:** após o `504`, o
  `/admin/calls` segue crescendo — tokens gastos num relatório que ninguém espera mais.
- **Causa:** `app/helpdesk/report.py` (laço de lotes em série, resposta só no fim) +
  `main.py` (`POST /reports/topics` devolve o corpo completo).

### Dor B — A sugestão deixa o atendente esperando sem ver nada

```bash
time curl -s -X POST localhost:8000/tickets/reply-suggestion -H "Content-Type: application/json" \
  -d '{"ticket_id":"TK-00042","text":"Meu pedido #481516 não chegou, urgente"}'
```

- **Observado:** a resposta chega **inteira, de uma vez, após ~16 s**. Sem streaming, o
  atendente olha uma tela parada até o texto completo aparecer.
- **Causa:** `app/helpdesk/llm.py` chamava `messages.create(...)` **sem `stream=True`**;
  `main.py` devolvia o objeto completo em vez de `text/event-stream`.

### Dor C — Com um provider fora do ar, parte do helpdesk para junto

```bash
curl -s -X POST localhost:8090/admin/failures -H "Content-Type: application/json" \
  -d '{"provider":"anthropic","mode":"error_500"}'
curl -s -o /dev/null -w "F2 %{http_code}\n" -X POST localhost:8000/tickets/reply-suggestion \
  -H "Content-Type: application/json" -d '{"ticket_id":"TK-1","text":"teste"}'
```

- **Observado:** com `anthropic` caída, F2 e F3 devolvem `500` e F1/F4 (que usam `openai`)
  seguem `200` — **metade do helpdesk para**. Pior: **uma requisição vira 3 chamadas** ao
  provider (retries default dos SDKs em `/admin/calls`), e **não há fallback** para o outro
  provider, embora os dois `large` sejam equivalentes.
- **Causa:** `config.py` amarra F1/F4→openai, F2/F3→anthropic; `llm.py` não tem timeout,
  retry controlado nem fallback.

### Dor D — Trocar o modelo exige mudar código e reconstruir a aplicação

```bash
grep -n "MODEL" app/helpdesk/config.py   # na v1: CLASSIFICATION_MODEL = "gpt-fake-large" ...
```

- **Observado:** o nome físico do modelo estava **no código**. Trocar `gpt-fake-large` por
  `gpt-fake-mini` exigia editar `config.py`, `docker compose build app` e reiniciar o `app`.
  É deploy, não configuração.
- **Causa:** `config.py` com constantes `*_MODEL`; cada feature lia `config.*_MODEL` e
  repassava ao `llm` — o acoplamento que o gateway resolve.

## Como rodar

Pré-requisitos: Docker e Docker Compose v2.

```bash
cp .env.example .env
docker compose up -d --build --wait      # sobe provider-fake, gateway-db, gateway,
                                         # provisiona as virtual keys, sobe app e edge
curl -s localhost:8000/health            # {"status":"ok"}
```

**Testes de caracterização** (fixam o comportamento da v1; passam na `v1-coupled` e na
`v2-decoupled`), rodados contra o ambiente no ar:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r tests/characterization/requirements.txt
pytest tests/characterization/ -q
```

**Script de métrica** (régua do requisito 3; grava CSV + gráfico A×I em `metrics/results/`):

```bash
pip install -r metrics/requirements.txt    # matplotlib
python metrics/measure.py app/helpdesk/ v2-decoupled
# Para medir uma tag, rode o script da sua branch sobre um checkout dela:
#   git worktree add ../v1 v1-coupled && python metrics/measure.py ../v1/app/helpdesk/ v1-coupled
```

## Métrica

Régua do requisito 3 (Ca, Ce, I, A, D e a Main Sequence). CSVs e gráficos das **três
versões** (`v1-coupled`, `v2-decoupled`, `main`) em `metrics/results/`. O componente que
chama o gateway é **`adapters.gateway`** (único ponto que fala com o gateway; nenhuma
feature o importa — só `main.py`, o ponto de composição).

**O que saiu de onde, da v1 para a v2:**

- **`llm` (D=0,80) foi eliminado.** Era o módulo-deus: 4 features dependiam dele e ele
  concentrava os dois SDKs. No lugar surgiram **`ports`** (a `Protocol LLMPort`, **A=1,0,
  D=0,0** — exatamente sobre a Main Sequence) e **`adapters.gateway`** (adaptador concreto,
  D=0,50, importado só pelo `main`).
- **`config` encolheu:** Ca caiu de **6 → 2** (só `main` e `tickets` o importam). Continua
  com D=1,00 por ser configuração concreta e estável — exceção declarada no ADR 0005.
- **Features** (`classification`, `suggestion`, `extraction`, `report`): deixaram de importar
  `config` e `llm`; passam a receber a porta por injeção. Nenhuma está na zona de dor.
- **`schemas`** (D=1,00): tipos de valor do domínio, estáveis por natureza — exceção
  declarada no ADR 0005.

**O que muda da v2 para a `main`:** o desenho de acoplamento é o mesmo (a decisão de modo
de execução não reintroduz dependências); surge só **`jobs`** (armazém em memória das
tarefas assíncronas da F3), um módulo-folha concreto (Ca=1, Ce=0, D=1,00) do qual só o
`main` depende. `adapters.gateway` segue em D=0,50 e as features entre D=0,25 e 0,33 —
nenhuma na zona de dor.

Exceções declaradas (concretos e estáveis, não são dor real): **`schemas`**, **`config`**
e **`jobs`** (ver ADR 0005). Não são exceção e não estão na zona de dor: `adapters.gateway`
(o componente que chama o gateway) e as quatro features.

## Tabela de capacidades

| Capacidade | Feature | Modelo primário | Fallback técnico | Modelo fraco (sem `large`) | Máx. tentativas por destino |
|---|---|---|---|---|---|
| `classify` | F1 classificação | `openai/gpt-fake-large` | `anthropic/claude-fake-large` | **cai no `gpt-fake-mini`** | 2 |
| `suggest` | F2 sugestão | `anthropic/claude-fake-large` | `openai/gpt-fake-large` | **falha explícita** | 2 |
| `topics` | F3 relatório | `anthropic/claude-fake-large` | `openai/gpt-fake-large` | **falha explícita** | 2 |
| `extract` | F4 extração | `openai/gpt-fake-large` | `anthropic/claude-fake-large` | **falha explícita** | 2 |

Mapeamento em `gateway/config.yaml`. A aplicação só conhece os nomes lógicos (ADR 0002).

## Tabela de fallback

Comportamento de cada feature quando **não há nenhum modelo `large` disponível** (os dois
`large` em falha). Decisão de produto, justificada no ADR 0003 (evidência: na extração, o
`mini` perde o campo `product`).

| Feature | Sem `large` | Resposta / status |
|---|---|---|
| F1 classificação | cai no `mini` | `200` com a classificação do `gpt-fake-mini` (observado ~0,4 s) |
| F2 sugestão | falha explícita | stream abre (`200`), mas emite imediatamente `event: error`; **nenhuma** sugestão é entregue |
| F3 relatório | falha explícita | o status da tarefa chega a `{"state":"failed","reason":...}` (visível, com motivo) |
| F4 extração | falha explícita | `500` explícito; **nunca** um dado parcial para a automação |

## Fluxos

Modo de execução de cada feature (decidido pela árvore de decisão no **ADR 0007**) e como
consumir o resultado. Tempos medidos pela borda (`localhost:8000`) com o provider em modo
normal.

| Feature | Modo | Garantia medida |
|---|---|---|
| F1 classificação | **síncrono** | resultado completo em ~1,2 s (≤3 s); com primário em `timeout`, responde via fallback em ~9 s (≤15 s) |
| F2 sugestão | **streaming** (SSE) | primeiro trecho em ~0,96 s (≤1,5 s), texto fluindo até o fim |
| F3 relatório | **assíncrono** (202 + status) | `202` em ~2 ms (≤1 s); relatório dos 5.000 tickets disponível depois |
| F4 extração | **síncrono** | resultado completo em ~1,2 s; com primário em `timeout`, fallback em ~9 s (≤15 s) |

**F1 — síncrono.** Resposta inteira no corpo:

```bash
curl -s -X POST localhost:8000/tickets/classification \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id":"TK-1","text":"Fui cobrado duas vezes"}'
# {"ticket_id":"TK-1","category":"payment","priority":"medium"}
```

**F2 — streaming (Server-Sent Events).** Use `curl -N` para não bufferizar; o texto chega em
eventos `data:` e termina em `event: end`:

```bash
curl -N -X POST localhost:8000/tickets/reply-suggestion \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id":"TK-1","text":"Meu pedido não chegou"}'
# data: {"chunk": "Olá! Sinto muito"}
# data: {"chunk": " pelo transtorno..."}
# ...
# event: end
# data: {"ticket_id": "TK-1"}
```

Falha no meio do stream (o `200` já foi enviado) chega como `event: error` — reproduza com o
primário do `suggest` em `midstream_error`.

**F3 — assíncrono (Asynchronous Request-Reply).** O `POST` responde `202` com `Location`
(URL de status) e `Retry-After`; consulte o status até receber `303` para o resultado:

```bash
# 1) pede o relatório do mês inteiro -> 202 na hora
curl -si -X POST localhost:8000/reports/topics \
  -H 'Content-Type: application/json' \
  -d '{"start":"2026-08-01","end":"2026-08-31"}'
# HTTP/1.1 202 Accepted
# location: /reports/topics/status/7f3a
# retry-after: 5

# 2) acompanha o andamento (200 enquanto corre)
curl -s localhost:8000/reports/topics/status/7f3a
# {"state":"running","progress":"1800/5000"}

# 3) quando pronto, o status responde 303 -> siga o Location
curl -sL localhost:8000/reports/topics/status/7f3a
# {"start":"2026-08-01","end":"2026-08-31","total_tickets":5000,"topics":[...]}
```

Se os dois providers estiverem em `error_500`, o status chega a `{"state":"failed","reason":...}`
em poucos segundos (≤60 s) e nunca fica preso em `running`.

**F4 — síncrono.** Igual à F1:

```bash
curl -s -X POST localhost:8000/tickets/extraction \
  -H 'Content-Type: application/json' \
  -d '{"ticket_id":"TK-1","text":"Trocar o pedido #605065"}'
# {"ticket_id":"TK-1","order_number":"#605065","product":null}
```

## Troca de modelo

Trocar o modelo físico por trás de uma capacidade é mudança **só do gateway**:

1. Edite `gateway/config.yaml`: no bloco da capacidade (ex.: `model_name: classify`), troque
   `model: openai/gpt-fake-large` por `model: openai/gpt-fake-mini`.
2. Reinicie **só o gateway:** `docker compose up -d gateway` (ou `docker compose restart gateway`).
3. A próxima chamada à feature aparece em `/admin/calls` com o novo modelo. O serviço `app`
   **não** é reconstruído nem reiniciado.

## Roteiro de governança

As duas virtual keys são criadas automaticamente pelo serviço `gateway-setup` (ADR 0004/0006).
Valores padrão no `.env.example`.

**Recusa por limite de requisições** (chave de demonstração, `rpm_limit=2`): a 3ª chamada
no mesmo minuto é recusada com `429` e **não** chega ao provider (não aparece em `/admin/calls`):

```bash
for i in 1 2 3; do
  curl -s -o /dev/null -w "req $i -> %{http_code}\n" -X POST localhost:4000/chat/completions \
    -H "Authorization: Bearer sk-helpdesk-rpm-demo-0001" -H 'Content-Type: application/json' \
    -d '{"model":"classify","messages":[{"role":"user","content":"TASK: classify\nteste"}]}'
done   # -> 200, 200, 429
```

**Recusa por orçamento (budget):** a chave da aplicação tem `max_budget` mensal. Como o
gateway pode calcular custo zero para os modelos simulados (preços no README do provider),
a prova determinística de recusa usa o **limite de requisições** acima; o budget está
configurado e documentado na chave `helpdesk-app` (ver `gateway/setup-keys.py`).

## Mapa de decisões

| ADR | Nível | Resumo |
|---|---|---|
| [0001](docs/adr/0001-gateway-escolha-e-posicao.md) | solução | Pôr um AI Gateway self-hosted (LiteLLM) na frente dos providers |
| [0002](docs/adr/0002-capacidades-logicas-e-mapeamento.md) | software | Capacidades lógicas e mapeamento para modelos físicos |
| [0003](docs/adr/0003-politica-de-fallback.md) | solução | Resiliência e fallback (técnico e com modelo fraco), por feature |
| [0004](docs/adr/0004-governanca-chaves-orcamentos-limites.md) | corporativa | Governança: chaves, orçamento e limite de requisições |
| [0005](docs/adr/0005-leitura-da-metrica.md) | software | Leitura da métrica e exceções declaradas |
| [0006](docs/adr/0006-servicos-extras-compose.md) | software | Serviços extras no compose: banco do gateway e provisionamento de chaves |
| [0007](docs/adr/0007-modo-de-execucao-por-feature.md) | solução | Modo de execução por feature: F1/F4 síncronos, F2 streaming, F3 assíncrono |

Plano de refatoração (alvos, piloto, revisão e handoff para o agente):
[`docs/refactoring-plan.md`](docs/refactoring-plan.md).
