#!/usr/bin/env python3
"""Mede o acoplamento de um pacote helpdesk segundo a régua do requisito 3.

Uso:
    python metrics/measure.py <caminho/para/helpdesk> [nome]

Exemplos:
    python metrics/measure.py app/helpdesk/ v1-coupled
    python metrics/measure.py ../v1/app/helpdesk/        # nome derivado do caminho

Saídas (em metrics/results/):
    <nome>.csv   cabeçalho exato: component,ca,ce,i,a,d
    <nome>.png   gráfico A × I com a Main Sequence traçada

RÉGUA (fixa, igual para as três medições):
- Componente = cada módulo .py do helpdesk, incluindo subpastas, identificado pelo
  caminho com pontos (ex.: adapters.gateway), EXCETO os __init__.py.
- Dependência = um import (relativo ou absoluto) que resolve para outro componente
  do mesmo helpdesk. Bibliotecas externas e da biblioteca padrão NÃO contam.
- Ca = quantos componentes importam este. Ce = quantos este importa.
- I  = Ce / (Ce + Ca), ou 0 quando ambos são zero.
- A  = nº de classes abstratas (herdam de typing.Protocol ou abc.ABC) / total de
  classes do módulo, ou 0 quando o módulo não tem classes.
- D  = |A + I - 1|.
- Todos os valores arredondados para 2 casas.
"""

import ast
import csv
import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


# --------------------------------------------------------------------------- #
# Descoberta de componentes
# --------------------------------------------------------------------------- #
def discover_components(root: Path) -> dict[str, Path]:
    """Mapeia id-de-componente (dotted) -> arquivo .py, exceto __init__.py."""
    components: dict[str, Path] = {}
    for path in sorted(root.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(root).with_suffix("")
        dotted = ".".join(rel.parts)
        components[dotted] = path
    return components


# --------------------------------------------------------------------------- #
# Resolução de imports para componentes internos
# --------------------------------------------------------------------------- #
def resolve_dependencies(
    component: str, tree: ast.AST, known: set[str], root_pkg: str
) -> set[str]:
    """Conjunto de componentes internos importados por `component`."""
    deps: set[str] = set()
    pkg_parts = component.split(".")[:-1]  # pacote que contém o módulo atual

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # import relativo: sobe (level-1) níveis a partir do pacote atual
                base = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                prefix = base + (node.module.split(".") if node.module else [])
                _add_candidates(prefix, node.names, known, deps)
            else:
                # import absoluto
                mod_parts = node.module.split(".") if node.module else []
                stripped = _strip_root(mod_parts, root_pkg)
                if stripped is not None:
                    _add_candidates(stripped, node.names, known, deps)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                mod_parts = alias.name.split(".")
                stripped = _strip_root(mod_parts, root_pkg)
                if stripped is not None:
                    cand = ".".join(stripped)
                    if cand in known:
                        deps.add(cand)

    deps.discard(component)  # auto-import não conta
    return deps


def _add_candidates(prefix_parts, names, known: set[str], deps: set[str]) -> None:
    """Avalia `from <prefix> import name1, name2` resolvendo cada alvo possível."""
    # 1) o próprio prefixo pode ser um componente (from .schemas import X)
    prefix_dotted = ".".join(prefix_parts)
    if prefix_dotted in known:
        deps.add(prefix_dotted)
    # 2) cada nome importado pode ser um submódulo/componente
    #    (from . import config, llm) ou (from .adapters import gateway)
    for alias in names:
        if alias.name == "*":
            continue
        cand = ".".join([p for p in prefix_parts + [alias.name] if p])
        if cand in known:
            deps.add(cand)


def _strip_root(mod_parts, root_pkg: str):
    """Remove o nome do pacote raiz de um import absoluto; None se não pertence."""
    if not mod_parts:
        return None
    if mod_parts[0] == root_pkg:
        return mod_parts[1:]
    return None


# --------------------------------------------------------------------------- #
# Abstração (A)
# --------------------------------------------------------------------------- #
ABSTRACT_BASES = {"Protocol", "ABC"}


def _base_name(base: ast.expr) -> str:
    if isinstance(base, ast.Name):
        return base.id
    if isinstance(base, ast.Attribute):
        return base.attr  # typing.Protocol -> "Protocol", abc.ABC -> "ABC"
    if isinstance(base, ast.Subscript):  # ex.: Protocol[...]
        return _base_name(base.value)
    return ""


def abstraction(tree: ast.AST) -> tuple[int, int]:
    """(classes_abstratas, total_de_classes) considerando classes de topo do módulo."""
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    total = len(classes)
    abstract = 0
    for cls in classes:
        base_names = {_base_name(b) for b in cls.bases}
        if base_names & ABSTRACT_BASES:
            abstract += 1
    return abstract, total


# --------------------------------------------------------------------------- #
# Medição
# --------------------------------------------------------------------------- #
def measure(root: Path):
    components = discover_components(root)
    root_pkg = root.name
    known = set(components)

    ce_map: dict[str, set[str]] = {}
    abs_map: dict[str, tuple[int, int]] = {}

    for comp, path in components.items():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        ce_map[comp] = resolve_dependencies(comp, tree, known, root_pkg)
        abs_map[comp] = abstraction(tree)

    # Ca = quantos componentes importam este
    ca_count: dict[str, int] = {c: 0 for c in components}
    for comp, deps in ce_map.items():
        for dep in deps:
            ca_count[dep] += 1

    rows = []
    for comp in sorted(components):
        ce = len(ce_map[comp])
        ca = ca_count[comp]
        inst = round(ce / (ce + ca), 2) if (ce + ca) > 0 else 0.0
        abstract, total = abs_map[comp]
        a = round(abstract / total, 2) if total > 0 else 0.0
        d = round(abs(a + inst - 1), 2)
        rows.append({"component": comp, "ca": ca, "ce": ce, "i": inst, "a": a, "d": d})
    return rows


# --------------------------------------------------------------------------- #
# Saídas
# --------------------------------------------------------------------------- #
def write_csv(rows, out_csv: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["component", "ca", "ce", "i", "a", "d"])
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_plot(rows, out_png: Path, name: str) -> None:
    fig, ax = plt.subplots(figsize=(9, 8))
    # Main Sequence: A + I = 1
    ax.plot([0, 1], [1, 0], "--", color="gray", label="Main Sequence (A + I = 1)")
    # zona de dor (I<0.5, A<0.5) e zona de inutilidade (I>0.5, A>0.5)
    ax.add_patch(plt.Rectangle((0, 0), 0.5, 0.5, color="red", alpha=0.06))
    ax.text(0.02, 0.02, "Zona de dor", color="red", fontsize=9, alpha=0.7)
    ax.add_patch(plt.Rectangle((0.5, 0.5), 0.5, 0.5, color="blue", alpha=0.06))
    ax.text(0.72, 0.95, "Zona de inutilidade", color="blue", fontsize=9, alpha=0.7)

    for row in rows:
        x, y = row["i"], row["a"]
        ax.scatter(x, y, s=70, color="#1f77b4", zorder=3)
        ax.annotate(
            f"{row['component']}\n(D={row['d']})",
            (x, y),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=8,
        )

    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.set_xlabel("Instabilidade (I)")
    ax.set_ylabel("Abstração (A)")
    ax.set_title(f"Main Sequence — {name}")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=120)
    plt.close(fig)


def derive_name(path_arg: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    known_tags = ("v1-coupled", "v2-decoupled", "main")
    parts = Path(path_arg).resolve().parts
    for token in known_tags:
        if token in parts:
            return token
    return "measure"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    helpdesk_path = Path(sys.argv[1]).resolve()
    if not helpdesk_path.is_dir():
        print(f"Caminho inválido: {helpdesk_path}")
        return 2
    name = derive_name(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)

    rows = measure(helpdesk_path)

    results_dir = Path(__file__).resolve().parent / "results"
    out_csv = results_dir / f"{name}.csv"
    out_png = results_dir / f"{name}.png"
    write_csv(rows, out_csv)
    write_plot(rows, out_png, name)

    print(f"Medição '{name}' em {helpdesk_path}")
    print(f"  componentes: {len(rows)}")
    print("component,ca,ce,i,a,d")
    for row in rows:
        print(f"{row['component']},{row['ca']},{row['ce']},{row['i']},{row['a']},{row['d']}")
    print(f"CSV: {out_csv}")
    print(f"PNG: {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
