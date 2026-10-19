"""Perturbações controladas de modelos BPMN, para validar o juiz sem avaliador humano.

Casos em que a resposta certa é conhecida por construção. Um gold do PMo recebe
defeitos de gravidade conhecida (mutantes) ou tem os rótulos reescritos sem mudar o
sentido (paráfrase). Uma medida de fidelidade válida dá ao gold nota maior que aos
mutantes, menor quanto mais defeitos, e a mesma nota à paráfrase.

Todos os casos, inclusive o gold intacto, passam pela mesma serialização (`to_xml`):
a única diferença entre eles é a perturbação. Fluxos de mensagem não são
serializados (2 dos 53 golds os têm), igualmente para todos os casos.
"""

from __future__ import annotations

import copy
import random

from lxml import etree

from src.evaluation.render import BPMN_NS, parse

_Q = f"{{{BPMN_NS}}}"
OPERATORS = ("drop_task", "add_task", "swap_tasks", "parallel_to_exclusive", "swap_branches")
# Etapas administrativas plausíveis que nenhum texto do PMo descreve; a escolhida é a
# primeira cujas palavras não aparecem na descrição.
INVENTED = (
    "Notify the regional office",
    "Print a paper copy for the archive",
    "Request approval from the board",
    "Schedule a follow-up survey",
    "Update the company newsletter",
)


def graph(xml_text: str) -> dict:
    dados = parse(xml_text)
    return {"nodes": copy.deepcopy(dados["nodes"]), "flows": list(dados["flows"])}


def to_xml(g: dict) -> str:
    """BPMN mínimo: nós, fluxos de sequência e uma lane por ator."""
    root = etree.Element(
        f"{_Q}definitions",
        nsmap={None: BPMN_NS},
        id="Definitions_p",
        targetNamespace="http://example.org/perturbation",
    )
    proc = etree.SubElement(root, f"{_Q}process", id="Process_p", isExecutable="false")
    atores = sorted({n["actor"] for n in g["nodes"].values() if n["actor"]})
    if atores:
        lane_set = etree.SubElement(proc, f"{_Q}laneSet", id="LaneSet_p")
        for i, ator in enumerate(atores):
            lane = etree.SubElement(lane_set, f"{_Q}lane", id=f"Lane_{i}", name=ator)
            for nid, no in g["nodes"].items():
                if no["actor"] == ator:
                    etree.SubElement(lane, f"{_Q}flowNodeRef").text = nid
    for nid, no in g["nodes"].items():
        el = etree.SubElement(proc, f"{_Q}{no['local']}", id=nid)
        if no["name"]:
            el.set("name", no["name"])
        if no["trigger"]:
            etree.SubElement(el, f"{_Q}{no['trigger']}EventDefinition")
    for i, (a, b, cond) in enumerate(g["flows"]):
        fluxo = etree.SubElement(proc, f"{_Q}sequenceFlow", id=f"Flow_{i}", sourceRef=a)
        fluxo.set("targetRef", b)
        if cond:
            fluxo.set("name", cond)
    return etree.tostring(root, encoding="unicode")


def _simple_tasks(g: dict) -> list[str]:
    """Atividades com exatamente uma entrada e uma saída, em ordem estável."""
    return sorted(
        n
        for n, no in g["nodes"].items()
        if no["kind"] == "activity"
        and sum(f[1] == n for f in g["flows"]) == 1
        and sum(f[0] == n for f in g["flows"]) == 1
    )


def drop_task(g: dict, rng: random.Random, description: str) -> bool:
    candidatas = _simple_tasks(g)
    if not candidatas:
        return False
    alvo = rng.choice(candidatas)
    entra = next(f for f in g["flows"] if f[1] == alvo)
    sai = next(f for f in g["flows"] if f[0] == alvo)
    g["flows"] = [f for f in g["flows"] if alvo not in f[:2]] + [(entra[0], sai[1], entra[2])]
    del g["nodes"][alvo]
    return True


def add_task(g: dict, rng: random.Random, description: str) -> bool:
    candidatos = sorted(f for f in g["flows"] if g["nodes"][f[0]]["kind"] == "activity")
    texto = set(description.lower().split())
    rotulo = next(
        (r for r in INVENTED if not {w for w in r.lower().split() if len(w) > 3} & texto), None
    )
    if not candidatos or rotulo is None:
        return False
    a, b, cond = rng.choice(candidatos)
    novo = f"Invented_{len(g['nodes'])}"
    g["nodes"][novo] = {
        "kind": "activity", "local": "task", "name": rotulo, "trigger": "",
        "pool": g["nodes"][a]["pool"], "actor": g["nodes"][a]["actor"],
    }  # fmt: skip
    g["flows"].remove((a, b, cond))
    g["flows"] += [(a, novo, cond), (novo, b, "")]
    return True


def swap_tasks(g: dict, rng: random.Random, description: str) -> bool:
    """Troca os rótulos de duas atividades: a ordem (ou o ramo) fica errada."""
    candidatas = _simple_tasks(g)
    pares = [(a, b) for a in candidatas for b in candidatas if a < b]
    pares = [(a, b) for a, b in pares if g["nodes"][a]["name"] != g["nodes"][b]["name"]]
    if not pares:
        return False
    a, b = rng.choice(pares)
    nos = g["nodes"]
    nos[a]["name"], nos[b]["name"] = nos[b]["name"], nos[a]["name"]
    return True


def parallel_to_exclusive(g: dict, rng: random.Random, description: str) -> bool:
    """Todo paralelismo vira escolha exclusiva."""
    paralelos = [n for n, no in g["nodes"].items() if no["local"] == "parallelGateway"]
    if not any(sum(f[0] == n for f in g["flows"]) > 1 for n in paralelos):
        return False
    for n in paralelos:
        g["nodes"][n]["local"] = "exclusiveGateway"
    return True


def swap_branches(g: dict, rng: random.Random, description: str) -> bool:
    """Numa decisão com ramos rotulados, troca os destinos de dois ramos."""
    opcoes = []
    for n, no in sorted(g["nodes"].items()):
        if no["local"] != "exclusiveGateway":
            continue
        ramos = [f for f in g["flows"] if f[0] == n and f[2]]
        opcoes += [(r, s) for r in ramos for s in ramos if r < s and r[1] != s[1]]
    if not opcoes:
        return False
    r, s = rng.choice(opcoes)
    g["flows"] = [f for f in g["flows"] if f not in (r, s)] + [
        (r[0], s[1], r[2]),
        (s[0], r[1], s[2]),
    ]
    return True


_FUNCS = {
    f.__name__: f for f in (drop_task, add_task, swap_tasks, parallel_to_exclusive, swap_branches)
}


def mutate(g: dict, operator: str, rng: random.Random, description: str) -> bool:
    """Aplica o operador em `g` (no lugar). False se não se aplica a este modelo."""
    return _FUNCS[operator](g, rng, description)


def mutate_many(g: dict, n: int, rng: random.Random, description: str) -> list[str]:
    """Aplica até `n` operadores distintos, sorteados; devolve os que se aplicaram."""
    aplicados = []
    for op in rng.sample(OPERATORS, len(OPERATORS)):
        if len(aplicados) == n:
            break
        if mutate(g, op, rng, description):
            aplicados.append(op)
    return aplicados


def labels(g: dict) -> list[str]:
    """Rótulos que a paráfrase reescreve: atividades e eventos nomeados."""
    return sorted(
        {no["name"] for no in g["nodes"].values() if no["name"] and no["kind"] != "gateway"}
    )


def paraphrased(g: dict, mapping: dict[str, str]) -> dict:
    novo = copy.deepcopy(g)
    for no in novo["nodes"].values():
        if no["kind"] != "gateway" and no["name"] in mapping:
            no["name"] = mapping[no["name"]]
    return novo
