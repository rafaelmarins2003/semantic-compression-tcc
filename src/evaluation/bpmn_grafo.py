"""Desenha um processo BPMN em TikZ com leiaute em camadas, para as figuras qualitativas.

O `bpmn_tikz` reaproveita o BPMNDI do pipeline, que põe cada raia numa faixa e
alinha os ramos de uma decisão na mesma linha: ramos e laços ficam sobrepostos.
Aqui as posições vêm do `layered layout` do TikZ (algoritmo de Sugiyama), que
separa os ramos e trata os laços. Raias e fluxos de mensagem não são desenhados;
a figura compara a estrutura, que é o que o juiz avalia.

Gera um documento `standalone` que só compila com LuaLaTeX; a monografia inclui
o PDF resultante.

    uv run python -m src.evaluation.bpmn_grafo pmo_13 --arms A1,X-a2r,A4
    lualatex <saida>.tex
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from lxml import etree

from src.evaluation.bpmn_tikz import _escapar
from src.evaluation.render import _condition

B = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
EVENTOS = {"startEvent": "inicio", "endEvent": "fim"}
INTERMEDIARIOS = {"intermediateCatchEvent", "intermediateThrowEvent", "boundaryEvent"}
GATEWAYS = {"exclusiveGateway": r"$\times$", "parallelGateway": "+", "inclusiveGateway": "o"}
NOMES_PADRAO = {"start", "end"}  # nome que o emissor dá a evento anônimo

PREAMBULO = r"""\documentclass[tikz,border=2pt]{standalone}
\usetikzlibrary{graphs,graphdrawing,arrows.meta,shapes.geometric}
\usegdlibrary{layered}
\tikzset{
  tarefa/.style={draw, rounded corners=2pt, align=center, text width=1.7cm,
                 minimum height=0.8cm, font=\scriptsize},
  inicio/.style={circle, draw, minimum size=0.45cm, inner sep=0pt},
  fim/.style={circle, draw, very thick, minimum size=0.45cm, inner sep=0pt},
  meio/.style={circle, draw, double, minimum size=0.45cm, inner sep=0pt},
  decisao/.style={diamond, draw, minimum size=0.6cm, inner sep=0pt},
  rotulo/.style={font=\tiny\itshape, align=center},
  condicao/.style={font=\tiny\itshape, text=black, fill=white, inner sep=0.5pt},
}
"""


def _texto(nome: str, largura: int) -> str:
    return r"\\".join(_escapar(x) for x in textwrap.wrap(nome, largura)[:3])


def _no(local: str, nome: str, entradas: int) -> tuple[str, str]:
    """(estilo, conteúdo) de um nó; o rótulo de evento e decisão vai fora da forma."""
    if local in EVENTOS:
        fora = "" if nome.lower() in NOMES_PADRAO else nome
        return EVENTOS[local], fora
    if local in INTERMEDIARIOS:
        return "meio", nome
    if local in GATEWAYS:
        return "decisao", nome if entradas <= 1 else ""  # convergência fica sem nome
    return "tarefa", nome


def tikz(xml_text: str) -> str:
    """Documento LuaLaTeX com o grafo de fluxo de sequência de todos os processos."""
    raiz = etree.fromstring(xml_text.encode())
    nos, fluxos = {}, []
    for proc in raiz.iter(f"{B}process"):
        for el in proc:
            local = etree.QName(el).localname
            if local == "sequenceFlow":
                fluxos.append((el.get("sourceRef"), el.get("targetRef"), _condition(el)))
            elif el.get("id") and local not in ("laneSet", "documentation", "textAnnotation"):
                nos[el.get("id")] = (local, " ".join((el.get("name") or "").split()))
    entradas = {i: sum(1 for _, t, _ in fluxos if t == i) for i in nos}

    nomes = {ident: f"n{k}" for k, ident in enumerate(nos, 1)}
    linhas = []
    for ident, (local, nome) in nos.items():
        estilo, conteudo = _no(local, nome, entradas[ident])
        if estilo == "tarefa":
            linhas.append(f"  {nomes[ident]}[tarefa, as={{{_texto(conteudo, 22)}}}];")
        else:
            marca = GATEWAYS.get(local, "")
            extra = f", label={{[rotulo]above:{_texto(conteudo, 22)}}}" if conteudo else ""
            linhas.append(f"  {nomes[ident]}[{estilo}, as={{{marca}}}{extra}];")
    vistos: set[tuple[str, str]] = set()
    for s, t, nome in fluxos:
        if s not in nomes or t not in nomes:  # seta solta: não há o que desenhar
            continue
        opcoes = [f"edge node={{node[condicao] {{{_escapar(nome[:24])}}}}}"] if nome else []
        if (s, t) in vistos:  # dois fluxos entre o mesmo par: curva, senão se sobrepõem
            opcoes.append("bend right=35")
        vistos.add((s, t))
        rot = f"[{', '.join(opcoes)}]" if opcoes else ""
        linhas.append(f"  {nomes[s]} ->{rot} {nomes[t]};")

    corpo = "\n".join(linhas)
    return (
        PREAMBULO
        + "\\begin{document}\n\\begin{tikzpicture}[>={Latex[length=1.4mm]}]\n"
        + "\\graph[layered layout, grow=right, level distance=2.0cm, "
        + "sibling distance=1.3cm, edges={gray!70, ->}] {\n"
        + corpo
        + "\n};\n\\end{tikzpicture}\n\\end{document}\n"
    )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("sample_id")
    p.add_argument("--arms", default="A1,X-a2r,A4")
    p.add_argument("--rep", type=int, default=1)
    p.add_argument("--out", default="article/paper/figuras/bpmn")
    args = p.parse_args()

    from src.data.db import Database

    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)
    with Database(read_only=True) as db:
        gold = db.query(
            "SELECT gold_xml FROM gold_models WHERE sample_id = ? AND variant = 'primary'",
            (args.sample_id,),
        )
        fontes = [("gold", gold[0]["gold_xml"] if gold else None)]
        for arm in args.arms.split(","):
            linha = db.query(
                "SELECT output_xml FROM benchmark_eval"
                " WHERE arm = ? AND sample_id = ? AND rep = ? AND xsd_valid = 1",
                (arm, args.sample_id, args.rep),
            )
            rotulo = {"X-a2r": "A2r"}.get(arm, arm)
            fontes.append((rotulo, linha[0]["output_xml"] if linha else None))

    for nome, xml in fontes:
        if not xml:
            print(f"  {nome}: sem saída válida")
            continue
        caminho = destino / f"{args.sample_id}_{nome}.tex"
        caminho.write_text(tikz(xml), encoding="utf-8")
        print(f"  {caminho}")


if __name__ == "__main__":
    main()
