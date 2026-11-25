# 0007. Modo de execução de cada feature (síncrono, streaming ou assíncrono)

- Status: aceita
- Data: 2026-11-25
- Nível: solução

## Contexto

Uma chamada a LLM não se comporta como uma chamada HTTP comum: demora segundos, chega
aos poucos e prende a conexão. Escolher o modo de resposta de cada feature é decisão
arquitetural. A pergunta não é "qual modo adotar", é "qual modo para cada caso de uso".
Usamos a mesma árvore de decisão para as quatro features, com três perguntas:

1. **Alguém está esperando a resposta agora?** (humano no fluxo, aguardando)
2. **O resultado cabe no orçamento de latência?** (dá para entregar inteiro a tempo?)
3. **O resultado é consumível aos poucos?** (texto que pode ser lido enquanto chega)

Os limites de experiência (medidos pela borda, `localhost:8000`) são: F1 ≤3 s; F2
primeiro trecho ≤1,5 s; F3 responde ≤1 s e o relatório completo fica disponível depois;
nenhuma requisição pode terminar em `504`; feature síncrona tem timeout explícito e
responde (sucesso via fallback ou erro) em ≤15 s.

## Opções consideradas

Para cada feature: **síncrono** (resposta inteira no corpo), **streaming** (SSE, bytes
fluindo) ou **assíncrono** (Asynchronous Request-Reply: `202` + URL de status).

## Decisão

### F1 — Classificação (`POST /tickets/classification`): SÍNCRONO

- Alguém espera agora? **Sim** — a triagem acontece com o atendente na tela.
- Cabe no orçamento de latência? **Sim** — a saída é minúscula (categoria + prioridade),
  medida em ~1,2 s normal, bem dentro dos 3 s.
- Consumível aos poucos? **Não** — é um JSON atômico; meio JSON não serve.

Síncrono é o modo certo: resposta inteira, imediata. Timeout explícito de 15 s no cliente
(`config.SYNC_TIMEOUT`) e timeout de 8 s por modelo no gateway, que, com `TimeoutErrorRetries: 0`,
cai direto no fallback — garante resposta em ≤15 s mesmo com o primário travado (medido 9,2 s).

### F2 — Sugestão de resposta (`POST /tickets/reply-suggestion`): STREAMING

- Alguém espera agora? **Sim** — o atendente quer começar a ler/editar a sugestão já.
- Consumível aos poucos? **Sim** — é texto corrido; as primeiras palavras já têm valor.
- Cabe inteiro no orçamento? Não precisa caber: a resposta completa leva ~16 s, mas o
  **primeiro trecho** chega em ~0,96 s (≤1,5 s) e o texto segue fluindo.

Streaming (SSE) é o modo certo: o primeiro trecho cedo mata a dor da "tela congelada", e
como os bytes fluem continuamente a borda nunca atinge os 30 s sem dados (sem `504`). O
cabeçalho `X-Accel-Buffering: no` desliga o buffer do nginx só para esta resposta (não
podemos editar `edge/`). Falha no meio (`midstream_error`) chega como evento `error` no
stream — o `200` já foi enviado, então não há como trocar o status nem cair em fallback.

### F3 — Relatório de temas (`POST /reports/topics`): ASSÍNCRONO

- Alguém espera agora? **Não** — é um relatório do mês (5.000 tickets); quem pede volta
  depois para buscar.
- Cabe no orçamento de latência? **Não, de jeito nenhum** — processar 5.000 tickets em
  lotes leva minutos; síncrono dá `504` na borda (é a dor A do diagnóstico).
- Consumível aos poucos? **Não** — só o relatório agregado completo tem sentido.

Assíncrono (Asynchronous Request-Reply) é o modo certo: o `POST` aceita e responde `202`
em ~2 ms (≤1 s) com `Location` + `Retry-After`; a tarefa roda em segundo plano; a URL de
status devolve `200` com `progress` enquanto corre e `303` para o resultado quando pronto.
Como a conexão do `POST` não fica presa, não há `504`. Falha (dois providers em `error_500`)
chega a `failed` com motivo em ~5 s (≤60 s) e nunca fica presa em `running`. Custo assumido:
estado distribuído e uma peça a mais para operar (o armazém de jobs, hoje em memória —
persistência fica fora de escopo).

### F4 — Extração de dados (`POST /tickets/extraction`): SÍNCRONO

- Alguém espera agora? **Sim** — a extração alimenta o próximo passo do atendimento.
- Cabe no orçamento de latência? **Sim** — a saída é pequena (número do pedido + produto),
  medida em ~1,2 s normal.
- Consumível aos poucos? **Não** — é um JSON atômico que passa por validação de formato.

Síncrono, pelas mesmas razões da F1 e com a mesma proteção de timeout (medido 9,1 s com o
primário em `timeout`, caindo no fallback).

## Consequências

- Cada modo segue o contrato do requisito 6 e dos "Contratos sugeridos". Os testes na
  `main` foram atualizados para os contratos novos de F2 (streaming) e F3 (assíncrono).
- A régua de tempo é atendida sem `504` em nenhum cenário, inclusive nas falhas.
- O assíncrono da F3 traz estado em memória; sobreviver a reinício com tarefas em
  andamento está fora de escopo (enunciado), então não foi implementado.
