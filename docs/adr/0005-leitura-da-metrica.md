# 0005. Leitura da métrica de acoplamento e exceções declaradas

- Status: aceita
- Data: 2026-11-25
- Nível: software

## Contexto

O requisito 3 fixa uma régua (Ca, Ce, I, A, D e a Main Sequence) para transformar
"está acoplado demais" em medida comparável. A régua é fixa de propósito; o script
(`metrics/measure.py`) a implementa e não pode ser ajustado ao resultado. A fórmula, porém,
coloca na "zona de dor" (A<0,5, I<0,5 e D≥0,5) componentes concretos e estáveis que **não
são um problema real** — e esses precisam ser declarados aqui, com justificativa. O próprio
enunciado proíbe usar isto como brecha: o componente que chama o gateway e os de feature
**não** podem ser exceção.

## Opções consideradas

1. **Tratar todo D alto como dívida** e refatorar até zerar: levaria a inventar abstrações
   inúteis (ex.: uma Protocol para os tipos de dados), piorando o desenho para agradar a fórmula.
2. **Ler a métrica criticamente**: refatorar o que é dor real (acoplamento volátil) e
   **declarar** como estável o que é concreto por natureza e quase nunca muda.

## Decisão

Opção 2. Exceções declaradas (concretos, estáveis por natureza, não são dor):

- **`schemas`** (D=1,00): são os tipos de valor do domínio (pydantic). São estáveis — mudam
  só quando o contrato do helpdesk muda — e é correto que muitos dependam deles. Criar uma
  abstração sobre tipos de dados seria desenho pela fórmula, não melhoria.
- **`config`** (D=1,00): só nomes de capacidade e endereço do gateway (duas variáveis de
  ambiente). É configuração, concreta e estável; na v2 seu Ca caiu de 6 para 2.

**Não são exceção** (e não estão na zona de dor): `adapters.gateway` (o componente que
chama o gateway, D=0,50) e as features `classification`, `suggestion`, `extraction`,
`report` (D entre 0,25 e 0,33). A abstração `ports` fica exatamente sobre a Main Sequence
(A=1,0, D=0,0).

## Consequências

- A comparação entre v1, v2 e main vale: mesma régua, mesmo script, exceções nomeadas.
- Qualquer avaliador que recalcular a v1 à mão chega aos mesmos números do CSV versionado.

## Evidência

Recalcular a v1 a partir de um checkout da tag reproduz o CSV versionado:

```
git worktree add ../v1 v1-coupled
python metrics/measure.py ../v1/app/helpdesk/ v1-coupled
diff <(sort metrics/results/v1-coupled.csv) ...   # igual ao versionado
```

Evolução do D nos pontos que importam: `llm` 0,80 → **eliminado**; surge `ports` com D=0,00;
`config` Ca 6 → 2. Leitura completa dos três gráficos na seção "Métrica" do README.
