# 0003. Política de resiliência e fallback (técnico e com modelo fraco)

- Status: aceita
- Data: 2026-11-25
- Nível: solução

## Contexto

Na v1, sem timeout nem retry, uma instabilidade de provider derruba a feature que depende
dele (dor 3). O requisito 5 exige, para toda capacidade: timeout explícito, retry limitado
com backoff para falhas transitórias e **fallback técnico** para um destino equivalente em
outro provider. Além disso, exige decidir, **feature por feature**, se, sem nenhum modelo
`large` disponível, vale responder com um `mini` (pior) ou **falhar explicitamente**.

O provider simulado declara que o `mini` é pior "em pelo menos uma tarefa". Medimos para
descobrir **qual** e **quanto importa** antes de decidir:

| tarefa | `large` | `mini` | diferença |
|---|---|---|---|
| `classify` | `{"category":"payment","priority":"high"}` | `{"category":"payment","priority":"high"}` | nenhuma observada |
| `topics` | 2 temas, counts e exemplos corretos | idêntico | nenhuma observada |
| `extract` (produto citado) | `{"order_number":"#481516","product":"fone de ouvido bluetooth"}` | `{"order_number":"#481516","product":null}` | **o `mini` perde o `product`** |

A degradação do `mini` é concreta na **extração** (F4): ele descarta um campo que estava no
texto. Nas demais tarefas medidas, o `mini` igualou o `large`.

## Opções consideradas

1. **Mesma política para todas** (sempre cair no `mini`, ou nunca): ignora que o impacto de
   uma resposta pior é diferente por feature.
2. **Decisão por feature**, a partir de quem consome a resposta e do dano de uma resposta
   pior vs. nenhuma resposta.

## Decisão

Opção 2. **Resiliência (igual para todas as capacidades):** timeout explícito por destino,
retry limitado **só para falhas transitórias** com backoff, e fallback técnico automático
para o `large` do outro provider. **Número máximo de tentativas por destino: 2** (1ª
tentativa + 1 retry), declarado também no README.

**Fallback com modelo fraco (por feature):**

| feature | sem nenhum `large`? | justificativa (quem consome / dano) |
|---|---|---|
| F1 `classify` | **cai no `mini`** | O cliente espera a confirmação na tela (alguém esperando agora). A classificação é tolerante e o `mini` igualou o `large` na medição. Uma categoria aproximada é melhor que erro. |
| F2 `suggest` | **falha explícita** | O texto vai, depois de edição, ao cliente. Sem garantia de qualidade, é melhor o atendente escrever do zero que partir de um rascunho possivelmente pior. |
| F3 `topics` | **falha explícita** | O relatório embasa decisão de negócio e ninguém está esperando. Contagem/exemplos errados orientam decisão errada; é preferível falhar e refazer depois. |
| F4 `extract` | **falha explícita** | Alimenta automação de troca/devolução **sem revisão humana**. Evidência: o `mini` perde o `product` → troca errada, com custo de frete, estoque e cliente. Zero tolerância. |

Onde mora cada mecanismo: timeout, retry, fallback técnico e a escala para o `mini` (só
F1) ficam **no gateway** (`gateway/config.yaml`, blocos `litellm_settings.fallbacks` e
`num_retries`). A aplicação não tem lógica de fallback.

## Consequências

- Melhora: nenhuma feature "pendura" numa instabilidade; F1 degrada com elegância; F2/F3/F4
  falham de forma visível em vez de entregar dado ruim silenciosamente.
- Piora/operar: quando os dois `large` caem, F2/F3/F4 ficam indisponíveis **por decisão** —
  é o comportamento correto, mas precisa estar claro para o time de operação (está no README,
  "Tabela de fallback").

## Evidência

Fallback técnico (primário caído, sucesso no equivalente do outro provider):

```
curl -s -X POST localhost:8090/admin/failures -d '{"provider":"openai","mode":"error_500"}'
curl -s -X POST localhost:8000/tickets/classification -H 'Content-Type: application/json' \
  -d '{"ticket_id":"TK-1","text":"Fui cobrado duas vezes"}'      # 200, via anthropic
curl -s localhost:8090/admin/calls   # tentativas no openai seguidas de sucesso no anthropic
```

Fallback com modelo fraco (os dois `large` caídos): F1 responde via `gpt-fake-mini`;
F2/F3/F4 falham explicitamente (ver status na "Tabela de fallback" do README). Reset:
`curl -s -X POST localhost:8090/admin/reset`.
