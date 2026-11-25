# 0001. Pôr um AI Gateway self-hosted (LiteLLM) na frente dos providers

- Status: aceita
- Data: 2026-11-25
- Nível: solução

## Contexto

Na v1, cada feature chama o SDK do provider direto do código (`app/helpdesk/llm.py`), com
duas bibliotecas (`openai` e `anthropic`), duas URLs, duas credenciais e os nomes físicos
dos modelos espalhados em `config.py`. A medição confirma o custo: `llm` com D=0,80 e
`config` com D=1,00 e Ca=6. Trocar um modelo exige mudar código e reconstruir o `app`
(dor 4 do diagnóstico). Uma instabilidade de provider derruba as features que dependem
dele (dor 3). Credencial, custo, limite e resiliência estão dentro da aplicação.

## Opções consideradas

1. **Camada de abstração só no código** (uma interface e dois adaptores de SDK, sem
   serviço): inverte a dependência no código, mas mantém credenciais, roteamento, budget e
   fallback dentro do `app` e exige deploy para trocar modelo.
2. **Gateway SaaS** (ex.: provedor gerenciado): entrega as capacidades, mas o avaliador
   precisa subir tudo localmente, sem serviço externo — proibido pelo enunciado.
3. **AI Gateway self-hosted como serviço no compose (LiteLLM Proxy)**: a aplicação pede
   uma *capacidade lógica* por uma API compatível com OpenAI; o gateway resolve modelo
   físico, provider, credencial, timeout, retry, fallback, budget e limite.

## Decisão

Opção 3: **LiteLLM Proxy** como serviço `gateway` no compose, configuração versionada em
`gateway/`. É a inversão de dependência aplicada à IA: a aplicação passa a depender de uma
abstração (capacidade lógica + `LLMPort`), e a infraestrutura decide o modelo físico.
Credencial, custo, limites e resiliência saem de cada feature e vão para um lugar só.
A aplicação fala com o gateway pelo **SDK da OpenAI** apontando a `base_url` para ele —
um único cliente, sem o SDK da Anthropic (removido de `app/requirements.txt`).

## Consequências

- Melhora: trocar modelo vira mudança de configuração do gateway (ADR 0002); governança e
  resiliência ficam centralizadas (ADR 0003, 0004); o `app` deixa de ver chaves de provider.
- Piora/novo a operar: passa a existir um serviço a mais (e o seu banco — ADR 0006), que
  precisa estar saudável para o helpdesk funcionar. É um ponto central; a resiliência dele
  (timeout, retry, fallback) é tratada no ADR 0003.
- Limitação conhecida da ferramenta: virtual keys com budget/limite exigem banco; as chaves
  precisam ser criadas sem passo manual (ADR 0004 e 0006).

## Evidência

Com o ambiente no ar, a aplicação não conhece provider nem modelo físico — só o gateway:

```
grep -rE "gpt-fake|claude-fake" app/        # (vazio)
grep -rE "FAKE_OPENAI_KEY|FAKE_ANTHROPIC_KEY" app/   # (vazio)
```

Uma chamada pela borda aparece em `/admin/calls` com o provider/modelo que o gateway
escolheu, não um escolhido pela aplicação:

```
curl -s -X POST localhost:8000/tickets/classification -H 'Content-Type: application/json' \
  -d '{"ticket_id":"TK-1","text":"Fui cobrado duas vezes"}'
curl -s localhost:8090/admin/calls   # mostra openai/gpt-fake-large (primário de classify)
```
