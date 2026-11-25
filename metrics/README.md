# Métrica de acoplamento (Main Sequence)

`measure.py` calcula, por componente do `helpdesk`, as métricas **Ca, Ce, I, A, D**
segundo a régua fixa do requisito 3, gravando um CSV e um gráfico A × I.

## Rodar

```bash
pip install matplotlib
python metrics/measure.py app/helpdesk/ v1-coupled
```

- 1º argumento: caminho da pasta `helpdesk` a medir.
- 2º argumento (opcional): nome de saída. Sem ele, é derivado do caminho se contiver
  `v1-coupled`, `v2-decoupled` ou `main`; senão usa `measure`.

Saídas em `metrics/results/`: `<nome>.csv` (cabeçalho `component,ca,ce,i,a,d`) e
`<nome>.png`.

## Medir uma tag

O script nasce depois da tag `v1-coupled`. Para medir uma tag, rode o script da sua
branch sobre um checkout dela:

```bash
git worktree add ../v1 v1-coupled
python metrics/measure.py ../v1/app/helpdesk/ v1-coupled
git worktree remove ../v1
```

## Régua (fixa)

- **Componente**: cada módulo `.py` do helpdesk (incl. subpastas), identificado pelo
  caminho com pontos (ex.: `adapters.gateway`), exceto `__init__.py`.
- **Dependência**: import (relativo ou absoluto) que resolve para outro componente do
  mesmo helpdesk. Libs externas e stdlib não contam.
- **Ca** = quantos componentes importam este. **Ce** = quantos este importa.
- **I** = Ce / (Ce + Ca), ou 0 se ambos zero.
- **A** = nº de classes abstratas (herdam de `typing.Protocol` ou `abc.ABC`) / total de
  classes do módulo, ou 0 se não houver classes.
- **D** = |A + I − 1|.
- Todos arredondados para 2 casas.
