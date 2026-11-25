# 0002. Capacidades lógicas e mapeamento para modelos físicos

- Status: aceita
- Data: 2026-11-25
- Nível: software

## Contexto

Para a inversão de dependência valer (ADR 0001), a aplicação não pode conhecer nome de
modelo físico. Precisa de um vocabulário estável — *capacidades* — que descreva a tarefa,
não a implementação. O mapeamento capacidade → modelo tem de viver fora de `app/`.

## Opções consideradas

1. **Nome do modelo físico como identificador** (o `app` manda `gpt-fake-large`): é o
   acoplamento da v1; proibido na v2 (`grep gpt-fake app/` tem de ser vazio).
2. **Um nome lógico genérico único** (ex.: `chat`): esconde o modelo, mas não permite
   políticas diferentes por tarefa (primário, fallback e budget distintos por feature).
3. **Uma capacidade lógica por tarefa de negócio** (`classify`, `suggest`, `topics`,
   `extract`): a aplicação pede a capacidade; o gateway resolve o físico por capacidade.

## Decisão

Opção 3. Quatro capacidades lógicas, uma por feature, definidas em `app/helpdesk/config.py`
(só os nomes) e mapeadas em `gateway/config.yaml`. O provider simulado reconhece a tarefa
pela 1ª linha `TASK: <nome>`; como o nome lógico **é** o nome da tarefa, o adaptador
reaproveita o mesmo valor (`model=capability` e `TASK: {capability}`).

Mapeamento primário (espelha a v1: F1/F4 na OpenAI, F2/F3 na Anthropic; os dois `large`
são equivalentes, então o fallback técnico é sempre o `large` do outro provider):

| capacidade | feature | primário | fallback técnico |
|---|---|---|---|
| `classify` | F1 classificação | `openai/gpt-fake-large` | `anthropic/claude-fake-large` |
| `suggest` | F2 sugestão | `anthropic/claude-fake-large` | `openai/gpt-fake-large` |
| `topics` | F3 relatório | `anthropic/claude-fake-large` | `openai/gpt-fake-large` |
| `extract` | F4 extração | `openai/gpt-fake-large` | `anthropic/claude-fake-large` |

A política com modelo fraco (`mini`) por capacidade está no ADR 0003.

## Consequências

- Melhora: trocar o modelo físico de uma capacidade é editar uma linha do
  `gateway/config.yaml` e reiniciar só o `gateway` (ADR 0001); o `app` não muda.
- A tradução capacidade→físico passa a ser responsabilidade do gateway; a aplicação fica
  cega a provider, URL e formato de API.

## Evidência

```
grep -rE "gpt-fake|claude-fake" app/   # vazio: nenhum modelo físico no app
```

Trocar o primário de `classify` para `openai/gpt-fake-mini` em `gateway/config.yaml`,
`docker compose up -d gateway` e refazer a chamada: `/admin/calls` passa a mostrar
`gpt-fake-mini` sem reiniciar o `app` (roteiro completo na seção "Troca de modelo" do README).
