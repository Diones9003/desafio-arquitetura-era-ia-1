# Testes de caracterização

Fixam o comportamento observável da aplicação recebida (**v1-coupled**): as 4
features exercitadas pela borda oficial (`localhost:8000`), com os **campos e os
valores** do corpo das respostas fixados (não só o status HTTP), e pelo menos um
caso de erro de entrada por feature.

## Pré-requisito

Ambiente no ar:

```bash
cp .env.example .env
docker compose up -d --build --wait
curl -s localhost:8000/health   # {"status":"ok"}
```

## Rodar

```bash
pip install -r tests/characterization/requirements.txt
pytest tests/characterization/ -v
```

A borda pode ser trocada por variável de ambiente (padrão `http://localhost:8000`):

```bash
HELPDESK_BASE_URL=http://localhost:8000 pytest tests/characterization/ -v
```

## Cobertura

| Arquivo | Feature | Rota | Fixa |
|---|---|---|---|
| `test_f1_classification.py` | F1 Classificar | `POST /tickets/classification` | `category`/`priority` exatos + domínio + 2 erros (422) |
| `test_f2_suggestion.py` | F2 Sugerir | `POST /tickets/reply-suggestion` | resposta síncrona (JSON), trechos determinísticos do texto, determinismo + erro (422) |
| `test_f3_report.py` | F3 Relatório | `POST /reports/topics` | `total_tickets`=137 e temas de topo (período de 1 dia) + 2 erros (422) |
| `test_f4_extraction.py` | F4 Extrair | `POST /tickets/extraction` | `order_number`/`product` exatos + formato + erro (422) |

> A mesma suíte roda e passa nas tags `v1-coupled` e `v2-decoupled` (comportamento
> externo idêntico). Na `main` ela é atualizada para o novo contrato das features
> que mudarem de modo de execução (requisito 6).
