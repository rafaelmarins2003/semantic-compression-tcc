"""Converte BPMN com BPMNDI em TikZ, para as figuras qualitativas da monografia.

Reaproveita as coordenadas de `transpiler.layout` em vez de recalcular posições:
a figura mostra o mesmo leiaute que o pipeline produz, e não uma versão
arrumada à mão para a publicação.

Uso:
    uv run python -m src.evaluation.bpmn_tikz pmo_52
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

from lxml import etree

NS = {
    "b": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "di": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "dd": "http://www.omg.org/spec/DD/20100524/DI",
}
EVENTOS = {"startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent"}
GATEWAYS = {"exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway"}
ESCALA = 0.012  # unidades BPMN → cm no TikZ
LARGURA_TEXTO = 20  # caracteres por linha dentro da caixa


def _escapar(texto: str) -> str:
    for de, para in (("\\", r"\textbackslash "), ("&", r"\&"), ("%", r"\%"), ("_", r"\_"),
                     ("#", r"\#"), ("$", r"\$"), ("{", r"\{"), ("}", r"\}")):  # fmt: skip
        texto = texto.replace(de, para)
    return texto


def _rotulo(nome: str, largura: int = LARGURA_TEXTO) -> str:
    if not nome:
        return ""
    linhas = textwrap.wrap(nome, largura) or [nome]
    return r"\\".join(_escapar(x) for x in linhas[:3])


def elementos(raiz: etree._Element) -> dict[str, tuple[str, str]]:
    """id -> (tag local, nome). Cobre todos os processos do documento."""
    saida: dict[str, tuple[str, str]] = {}
    for proc in raiz.findall(".//b:process", NS):
        for no in proc:
            ident = no.get("id")
            if ident:
                saida[ident] = (etree.QName(no).localname, no.get("name") or "")
    return saida


def gerar(xml_text: str, *, titulo: str, escala: float = ESCALA, yescala: float = 1.0) -> str:
    """TikZ de um diagrama BPMN. Requer que o XML já tenha BPMNDI.

    `yescala` amplia só o eixo vertical. As referências do PMo nomeiam
    atividades como orações inteiras, que quebram em quatro ou cinco linhas e
    estouram a altura de 80 unidades que o BPMNDI reserva ao nó, fazendo caixas
    empilhadas se sobreporem. A ampliação afasta as linhas sem alterar a ordem
    nem a topologia; a legenda da figura declara o ajuste.
    """
    raiz = etree.fromstring(xml_text.encode())
    mapa = elementos(raiz)
    formas = [
        f
        for f in raiz.findall(".//di:BPMNShape", NS)
        if mapa.get(f.get("bpmnElement"), ("lane", ""))[0] not in ("lane", "laneSet")
    ]
    if not formas:
        return f"% sem formas para {titulo}\n"

    caixas = []
    for f in formas:
        b = f.find("dc:Bounds", NS)
        caixas.append(
            (
                f.get("bpmnElement"),
                float(b.get("x")),
                float(b.get("y")),
                float(b.get("width")),
                float(b.get("height")),
            )
        )
    x0 = min(c[1] for c in caixas)
    y0 = min(c[2] for c in caixas)
    # y invertido: BPMN cresce para baixo, TikZ para cima
    px = lambda x: (x - x0) * escala  # noqa: E731
    py = lambda y: -(y - y0) * escala * yescala  # noqa: E731

    linhas = [f"% {titulo}", r"\begin{tikzpicture}[x=1cm, y=1cm, font=\tiny]"]
    for e in raiz.findall(".//di:BPMNEdge", NS):
        pts = [
            (px(float(w.get("x"))), py(float(w.get("y")))) for w in e.findall("dd:waypoint", NS)
        ]
        if len(pts) >= 2:
            caminho = " -- ".join(f"({a:.2f},{b:.2f})" for a, b in pts)
            linhas.append(f"  \\draw[-{{Latex[length=1.4mm]}}, gray!70] {caminho};")

    for ident, x, y, w, h in caixas:
        tag, nome = mapa.get(ident, ("task", ""))
        cx, cy = px(x + w / 2), py(y + h / 2)
        if tag in EVENTOS:
            grosso = "very thick" if tag == "endEvent" else "thin"
            linhas.append(f"  \\node[circle, draw, {grosso}, minimum size=0.42cm, "
                          f"inner sep=0pt, fill=white] at ({cx:.2f},{cy:.2f}) {{}};")  # fmt: skip
            if nome:
                linhas.append(
                    f"  \\node[anchor=north, font=\\tiny] at ({cx:.2f},{cy - 0.28:.2f}) "
                    f"{{{_escapar(nome[:18])}}};"
                )
        elif tag in GATEWAYS:
            marca = "+" if tag == "parallelGateway" else r"$\times$"
            linhas.append(f"  \\node[diamond, draw, thin, minimum size=0.52cm, inner sep=0pt, "
                          f"fill=white] at ({cx:.2f},{cy:.2f}) {{{marca}}};")  # fmt: skip
            if nome:
                linhas.append(
                    f"  \\node[anchor=south, font=\\tiny] at ({cx:.2f},{cy + 0.32:.2f}) "
                    f"{{{_escapar(nome[:20])}}};"
                )
        else:
            linhas.append(
                f"  \\node[rounded corners=2pt, draw, thin, fill=white, align=center, "
                f"text width={w * escala * 1.15:.2f}cm, minimum height={h * escala:.2f}cm, "
                f"inner sep=1pt] at ({cx:.2f},{cy:.2f}) {{{_rotulo(nome)}}};"
            )
    linhas.append(r"\end{tikzpicture}")
    return "\n".join(linhas) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("sample_id")
    p.add_argument("--arms", default="A1,A2,A4")
    p.add_argument("--out", default="article/Atualização Template TCC Unifor 2022.2/figuras/tikz")
    p.add_argument("--yescala", type=float, default=1.9)
    args = p.parse_args()

    from src.data.db import Database
    from src.transpiler.layout import add_layout

    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)

    with Database() as db:
        gold = db.query(
            "SELECT gold_xml FROM gold_models WHERE sample_id = ? AND variant = 'primary'",
            (args.sample_id,),
        )
        fontes = [("gold", gold[0]["gold_xml"] if gold else None)]
        for arm in args.arms.split(","):
            linha = db.query(
                "SELECT output_xml FROM benchmark_eval WHERE arm = ? AND sample_id = ? AND rep = 1",
                (arm, args.sample_id),
            )
            fontes.append((arm, linha[0]["output_xml"] if linha else None))

    for nome, xml in fontes:
        if not xml:
            print(f"  {nome}: sem saída")
            continue
        try:
            corpo = gerar(
                add_layout(xml), titulo=f"{args.sample_id} — {nome}", yescala=args.yescala
            )
        except Exception as exc:
            print(f"  {nome}: falhou ({type(exc).__name__}: {exc})")
            continue
        caminho = destino / f"{args.sample_id}_{nome}.tex"
        caminho.write_text(corpo, encoding="utf-8")
        print(f"  {caminho.name}: {corpo.count(chr(10))} linhas")


if __name__ == "__main__":
    main()
