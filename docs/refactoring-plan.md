# Plano de refatoração — da v1 acoplada à v2 desacoplada

Este plano conduz a saída da `v1-coupled` para a `v2-decoupled`. O objetivo não é
estético: é quebrar o acoplamento da aplicação com os SDKs e os detalhes físicos dos
providers, usando a **métrica da Main Sequence como juiz** (requisito 3) e os **testes
de caracterização como rede de segurança** (requisito 2). O comportamento externo não
muda nesta etapa — as quatro features continuam síncronas e a suíte passa sem alteração.

## Critério de pronto (vale para todos os alvos)

Um componente só é dado como refatorado quando, **ao mesmo tempo**:

1. A suíte `tests/characterization/` continua verde pela borda (`localhost:8000`).
2. `git diff v1-coupled -- tests/characterization/` continua vazio (a rede de segurança
   não foi afrouxada para "passar").
3. A medição (`python metrics/measure.py app/helpdesk/ v2-decoupled`) mostra o efeito
   pretendido para aquele componente (ver coluna "critério" na tabela abaixo).
4. Nenhum componente de **feature** e nem o **componente que chama o gateway** ficam na
   zona de dor (A < 0,5 **e** I < 0,5 **e** D ≥ 0,5).

## Diagnóstico que motiva o plano (medição da v1-coupled)

Régua do requisito 3, saída versionada em `metrics/results/v1-coupled.csv`:

| componente | Ca | Ce | I | A | D | leitura |
|---|---|---|---|---|---|---|
| `llm` | 4 | 1 | 0,20 | 0,00 | **0,80** | módulo-deus: 4 features dependem dele; concentra os dois SDKs |
| `config` | 6 | 0 | 0,00 | 0,00 | **1,00** | todo mundo importa; carrega chaves, URLs e modelos físicos |
| `classification` | 1 | 3 | 0,75 | 0,00 | 0,25 | importa `config` + `llm` + `schemas` |
| `extraction` | 1 | 3 | 0,75 | 0,00 | 0,25 | idem |
| `suggestion` | 1 | 3 | 0,75 | 0,00 | 0,25 | idem |
| `report` | 1 | 4 | 0,80 | 0,00 | 0,20 | importa `config` + `llm` + `schemas` + `tickets` |
| `schemas` | 5 | 0 | 0,00 | 0,00 | 1,00 | tipo de valor estável (ver ADR 0005) |

O problema real é `llm` (D=0,80): é o ponto único por onde passa todo o acoplamento com
os providers, e é concreto — muda sempre que um modelo, uma URL ou um formato de API
muda. As features dependem **dele**, não de uma abstração. Não há nenhum componente com
A > 0 na v1: não existe abstração nenhuma no código.

## Componentes-alvo e estratégia

| alvo | estratégia (vocabulário do módulo 02) | critério de pronto (métrica) |
|---|---|---|
| `llm` (eliminar) | **Inverter a dependência**: criar a porta `LLMPort` (abstração) e um adaptador concreto que a implementa. As features passam a depender da porta. | Surge `ports` com **A=1,0** (sobre a Main Sequence, D≈0); `llm` deixa de existir |
| `adapters.gateway` (novo) | **Compor em vez de herdar**: o adaptador recebe URL e chave por construtor (injeção), importa só a porta + o SDK. | **Ce baixo** (só `ports`); fora da zona de dor |
| `classification`, `suggestion`, `extraction`, `report` | **Reduzir Ce**: parar de importar `config` e `llm`; receber a porta e a capacidade por argumento. | Ce cai de 3→2 (features simples) e 4→3 (`report`); deixam de importar `config`/`llm` |
| `config` (encolher) | **Reduzir Ca**: tirar de `config` tudo que não é configuração de conectividade; features não o importam mais. | Ca cai de 6→2 (só `main` e `tickets`) |
| `main` (ponto de composição) | Concentrar a montagem: é o único que instancia o adaptador e injeta nas features. | Continua I=1,0 (instável por natureza, é o topo); aceitável |

## Piloto: extrair a porta a partir de `llm` (um componente, medido antes e depois)

Antes de escalar para as quatro features, pilotamos **só** a quebra do `llm`, porque é a
decisão estruturante: se a inversão de dependência não movesse a métrica na direção certa,
o resto do plano estaria errado.

**Antes (v1-coupled):**

```
llm            Ca=4 Ce=1 I=0,20 A=0,00 D=0,80
classification Ca=1 Ce=3 I=0,75 A=0,00 D=0,25   (importa llm, config, schemas)
```

**Depois do piloto (porta extraída, 1ª tentativa):** criamos um único módulo
`gateway.py` contendo **a Protocol e a classe concreta juntas**, e apontamos as features
para ele.

```
gateway   Ca=4 Ce=1 I=0,20 A=0,50 D=0,30
```

Medição antes/depois do piloto: D caiu de 0,80 → 0,30. Melhorou, mas o componente ficou
**no meio do gráfico** (A=0,50): metade abstração, metade implementação, sem estar sobre a
Main Sequence. E o módulo que as features importam ainda carregava o SDK concreto junto —
a dependência foi reduzida, não invertida de verdade.

## Revisão do plano (o que mudou e por quê)

**Revisão 1 — separar porta de adaptador.** A medição do piloto mostrou que juntar a
Protocol com a implementação concreta no mesmo módulo trava o A em 0,50 e mantém o SDK no
caminho de import das features. O plano foi revisto: **dividir em dois componentes** —
`ports.py` (só a `Protocol LLMPort`, 100% abstrato) e `adapters/gateway.py` (só a classe
concreta). As features passam a importar **apenas `ports`**, nunca o adaptador.

Medição depois da revisão:

```
ports             Ca=5 Ce=0 I=0,00 A=1,00 D=0,00   <- exatamente sobre a Main Sequence
adapters.gateway  Ca=1 Ce=1 I=0,50 A=0,00 D=0,50   <- adaptador concreto, fora da zona de dor
```

Resultado: a abstração sobe para a Main Sequence (A=1,0, D=0,0) e o adaptador concreto
fica isolado, importado só pelo `main` (ponto de composição). Nenhuma feature importa o
adaptador — satisfaz o critério de aceite "nenhum componente de feature importa o
componente que chama o gateway; só o `main.py` pode".

## Registro do handoff para o agente de IA

- **O que foi entregue ao agente:** o diagnóstico acima, a régua da métrica
  (`metrics/measure.py`), a suíte de caracterização verde na `v1-coupled` como contrato
  imutável, e a tabela de alvos/estratégia/critério deste plano. Instrução explícita:
  evoluir o código de `app/` (proibido reescrever do zero), sem tocar em
  `tests/characterization/`, `provider-fake/`, `edge/` e `data/`.
- **Como o trabalho do agente foi aceito ou rejeitado (juízes determinísticos):**
  1. `pytest tests/characterization/` tem de ficar **verde** pela borda. Qualquer
     vermelho = rejeita e devolve com o diff do teto quebrado.
  2. `git diff v1-coupled -- tests/characterization/` tem de ficar **vazio**. Se o agente
     "consertou" um teste, rejeita.
  3. `python metrics/measure.py app/helpdesk/` tem de mostrar `llm` **eliminado**,
     `ports` com A=1,0 e nenhuma feature/adaptador na zona de dor. Caso contrário, rejeita.
- **O que foi de fato rejeitado:** a 1ª proposta do agente concentrava porta + adaptador
  num módulo só (o piloto acima). Foi rejeitada pelo critério 3 (A travado em 0,50) e
  devolvida com a Revisão 1 como instrução. A 2ª proposta passou nos três juízes.
- **Resultado final medido:** `metrics/results/v2-decoupled.csv` — ver a leitura completa
  na seção "Métrica" do README.
