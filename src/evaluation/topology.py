"""Eixo 2 — equivalência topológica JSON (original) ↔ XML (gerado).

Prova que o pipeline determinístico json_to_dsl → dsl_to_xml preserva a lógica
de fluxo, e não só a contagem de nós.

O transpiler transforma o grafo de propósito (gateways de join sumem, cada fork
vira par split+join, convergências viram refs). Então NÃO comparamos iso
nó-a-nó. Comparamos a relação **direct-follows projetada sobre nós emitíveis**
(tasks/eventos/subprocess), pulando gateways: "qual atividade segue qual",
ignorando a representação de roteamento. É o que captura preservação de lógica.

Identidade de nó = rótulo (nome). Eventos sem nome usam `<categoria>` derivada
do tipo, idêntico nos dois lados (neutraliza os nomes-default "start"/"end" que
o emissor XML coloca em eventos anônimos).
"""

from __future__ import annotations

import json
from collections import Counter, deque

from lxml import etree

from src.data.deterministic.graph import ProcessGraph, load_llm
from src.data.deterministic.json_to_dsl import _wrapped_processes

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"

_EVENT_CAT = {
    "startEvent": "start",
    "startMessageEvent": "start",
    "endEvent": "end",
    "endMessageEvent": "end",
    "endErrorEvent": "end",
    "intermediateCatchEvent": "catch",
    "catchEvent": "catch",
    "catchMessageEvent": "catch",
    "catchTimerEvent": "catch",
    "catchSignalEvent": "catch",
    "catchErrorEvent": "catch",
    "catchEscalationEvent": "catch",
    "intermediateThrowEvent": "throw",
    "throwEvent": "throw",
    "throwMessageEvent": "throw",
    "throwSignalEvent": "throw",
}
_DEFAULT_EVENT_NAMES = {"start", "end"}  # nomes que o emissor XML usa p/ eventos anônimos

# Atividades que encapsulam outro comportamento — contam como um nó só.
_SUBPROCESS_LIKE = {"subProcess", "callActivity", "transaction", "adHocSubProcess"}

# Categoria de nó de fluxo cuja tag não conhecemos. Contar como atividade é mais
# seguro que atravessar: um nó a mais aparece em `node_delta`, um nó a menos
# reescreve as arestas em silêncio.
UNKNOWN_ACTIVITY = "activity"


def _category(node_type: str) -> str | None:
    """Map a node type/tag to 'task' | 'event:<kind>' | 'subprocess' | None (gateway/other)."""
    if "Gateway" in node_type:
        return None
    if node_type in _EVENT_CAT:
        return f"event:{_EVENT_CAT[node_type]}"
    if node_type in _SUBPROCESS_LIKE:
        return "subprocess"
    if node_type == "task" or node_type.endswith("Task"):
        return "task"
    return None


def _label(category: str, name: str) -> str:
    """Stable cross-format label. Anonymous events collapse to their category."""
    n = (name or "").strip()
    if category.startswith("event:"):
        if not n or n in _DEFAULT_EVENT_NAMES:
            return f"<{category.split(':', 1)[1]}>"
        return n
    return n or f"<{category}>"


def _direct_follows(
    nodes: dict[str, tuple[str, str]],  # id -> (category|None, label)
    succs: dict[str, list[str]],
) -> Counter:
    """Direct-follows multiset over emittable nodes, skipping routing gateways.

    For each emittable node `a`, walk forward through non-emittable nodes until
    the first emittable node(s) `b` are reached; record edge (label_a, label_b).
    """
    df: Counter = Counter()
    emittable = [nid for nid, (cat, _) in nodes.items() if cat is not None]
    for a in emittable:
        a_label = nodes[a][1]
        seen: set[str] = set()
        queue = deque(succs.get(a, []))
        while queue:
            n = queue.popleft()
            if n in seen:
                continue
            seen.add(n)
            cat = nodes.get(n, (None, ""))[0]
            if cat is not None:
                df[(a_label, nodes[n][1])] += 1
            else:
                queue.extend(succs.get(n, []))  # routing node: traverse through
    return df


def _node_multiset(nodes: dict[str, tuple[str, str]]) -> Counter:
    """Multiset of emittable node categories (gateways excluded)."""
    return Counter(cat for cat, _ in nodes.values() if cat is not None)


def _json_graph_nodes(graph: ProcessGraph) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for nid, node in graph.nodes.items():
        cat = _category(node.type)
        out[nid] = (cat, _label(cat, node.name) if cat else "")
    return out


def json_direct_follows(data: dict) -> tuple[Counter, Counter]:
    """Return (direct_follows, node_multiset) for the original JSON.

    Aggregates across wrapped multi-process payloads (processos/processes).
    """
    procs = _wrapped_processes(data) or [data]
    df: Counter = Counter()
    nm: Counter = Counter()
    for p in procs:
        graph = load_llm(p)
        nodes = _json_graph_nodes(graph)
        df += _direct_follows(nodes, graph.succs)
        nm += _node_multiset(nodes)
    return df, nm


def xml_direct_follows(xml_text: str) -> tuple[Counter, Counter]:
    """Return (direct_follows, node_multiset) for generated BPMN XML.

    Aggregates across all <process> elements in the document.

    Nó com tag desconhecida que seja **extremidade de sequenceFlow** conta como
    atividade, não como roteamento. Antes, qualquer tag fora do mapa (por
    exemplo `callActivity`) era atravessada em silêncio: o nó sumia do
    multiconjunto e uma aresta espúria aparecia no lugar. Isso era inofensivo
    enquanto os dois lados vinham do nosso emissor; deixou de ser quando o
    candidato passou a ser saída livre de LLM.
    """
    root = etree.fromstring(xml_text.encode("utf-8"))
    elements: dict[str, tuple[str, str]] = {}
    succs: dict[str, list[str]] = {}
    endpoints: set[str] = set()
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.tag.startswith(f"{{{BPMN_NS}}}"):
            continue
        local = el.tag.split("}", 1)[1]
        nid = el.get("id")
        if local == "sequenceFlow":
            src, tgt = el.get("sourceRef"), el.get("targetRef")
            if src and tgt:
                succs.setdefault(src, []).append(tgt)
                endpoints.update((src, tgt))
            continue
        if nid is not None:
            elements[nid] = (local, el.get("name", ""))

    nodes: dict[str, tuple[str, str]] = {}
    for nid, (local, name) in elements.items():
        cat = _category(local)
        if cat is None and "Gateway" not in local:
            if nid not in endpoints:
                continue  # não é nó de fluxo (definitions, laneSet, eventDefinition…)
            cat = UNKNOWN_ACTIVITY
        nodes[nid] = (cat, _label(cat, name) if cat else "")
    return _direct_follows(nodes, succs), _node_multiset(nodes)


def message_flows(xml_text: str) -> Counter:
    """Multiconjunto de mensagens `(rótulo_origem, rótulo_destino)`.

    Métrica **separada** do DF-F1 de propósito. `messageFlow` é comunicação entre
    participantes, não ordem de execução; fundir as duas relações produziria
    casamento falso — uma mensagem no candidato valendo por uma sequência no
    gold. Separar também expõe uma assimetria real entre os braços em vez de
    escondê-la: o transpiler tem código para emitir mensagens mas não as produz
    na prática (0 em 1021 amostras), então contá-las no DF-F1 daria vantagem
    estrutural aos braços de XML direto.

    Extremidades podem ser nós de fluxo **ou participantes** (pools) — no gold
    do PMo as duas formas aparecem.
    """
    root = etree.fromstring(xml_text.encode("utf-8"))
    rotulos: dict[str, str] = {}
    mensagens: list[tuple[str, str]] = []
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.tag.startswith(f"{{{BPMN_NS}}}"):
            continue
        local = el.tag.split("}", 1)[1]
        if local == "messageFlow":
            src, tgt = el.get("sourceRef"), el.get("targetRef")
            if src and tgt:
                mensagens.append((src, tgt))
            continue
        nid = el.get("id")
        if nid is not None:
            cat = _category(local)
            rotulos[nid] = _label(cat, el.get("name", "")) if cat else (el.get("name") or nid)
    return Counter((rotulos.get(s, s), rotulos.get(t, t)) for s, t in mensagens)


def _prf(reference: Counter, candidate: Counter) -> tuple[float, float, float]:
    """Precision/recall/F1 of candidate vs reference, over multisets.

    Candidato vazio contra referência não-vazia dá precisão **0**, não 1. Um
    documento estruturalmente vazio é XSD-válido e antes reportava precisão
    perfeita, o que contaminaria a precisão média por braço na monografia — só
    o F1 denunciava.
    """
    inter = sum((reference & candidate).values())
    p = (1.0 if not reference else 0.0) if not candidate else inter / sum(candidate.values())
    r = (1.0 if not candidate else 0.0) if not reference else inter / sum(reference.values())
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f1


def _result(df_ref: Counter, nm_ref: Counter, df_cand: Counter, nm_cand: Counter) -> dict:
    """Resultado comum a `compare` e `compare_xml` — um só formato de saída.

    `df_ref_size`/`df_cand_size` valem para os dois: quem consome não precisa
    saber qual comparador produziu o dicionário.
    """
    p, r, f1 = _prf(df_ref, df_cand)
    return {
        "nodes_match": nm_ref == nm_cand,
        "node_delta": dict((nm_cand - nm_ref) + (nm_ref - nm_cand)),
        "df_exact": df_ref == df_cand,
        "df_precision": p,
        "df_recall": r,
        "df_f1": f1,
        "df_ref_size": sum(df_ref.values()),
        "df_cand_size": sum(df_cand.values()),
        "df_missing": dict(df_ref - df_cand),  # na referência e ausentes no candidato
        "df_extra": dict(df_cand - df_ref),  # inventadas pelo candidato
        "parse_error": None,
    }


def compare(data: dict, xml_text: str) -> dict:
    """Compare original JSON vs generated XML topology. Higher is better."""
    df_json, nm_json = json_direct_follows(data)
    df_xml, nm_xml = xml_direct_follows(xml_text)
    return _result(df_json, nm_json, df_xml, nm_xml)


def compare_json_text(json_text: str, xml_text: str) -> dict:
    return compare(json.loads(json_text), xml_text)


def compare_xml(gold_xml: str, candidate_xml: str) -> dict:
    """Compare gold BPMN XML vs generated BPMN XML. Higher is better.

    Mesma projeção direct-follows de `compare()`, com XML nos dois lados — é a
    forma usada contra o gold do PMo (`data/raw/pmo/bpmn_process/*.bpmn`), que é
    BPMN lógico e não JSON canônico.

    Chaves idênticas às de `compare()` — o harness trata os dois casos igual.

    **Candidato malformado não levanta exceção**: devolve resultado zerado com
    `parse_error` preenchido. A spec 003 AC-2 exige linha gravada, nunca exceção,
    e truncamento em A1/A1g é modo de falha orçado em §6.2. Mesma convenção de
    `validate_bpmn_xsd`, que reporta erro de sintaxe em vez de propagar.

    Acrescenta as chaves `mf_*` — F1 de `messageFlow`, **reportado ao lado e
    nunca somado** ao DF-F1 (ver `message_flows`).
    """
    df_gold, nm_gold = xml_direct_follows(gold_xml)
    mf_gold = message_flows(gold_xml)
    try:
        df_cand, nm_cand = xml_direct_follows(candidate_xml)
        mf_cand = message_flows(candidate_xml)
    except etree.XMLSyntaxError as exc:
        resultado = _result(df_gold, nm_gold, Counter(), Counter())
        resultado.update(_message_result(mf_gold, Counter()))
        # Spec 003 §3.1: XML inválido é **falha total**, não dado ausente. Sem
        # isto, um gold sem arestas casaria com o candidato ilegível por vacuidade
        # e reportaria F1 = 1,0 para um documento que sequer parseia.
        resultado.update(
            {
                "nodes_match": False,
                "df_exact": False,
                "df_precision": 0.0,
                "df_recall": 0.0,
                "df_f1": 0.0,
                "mf_precision": 0.0,
                "mf_recall": 0.0,
                "mf_f1": 0.0,
                "parse_error": f"XMLSyntaxError: {exc}",
            }
        )
        return resultado
    resultado = _result(df_gold, nm_gold, df_cand, nm_cand)
    resultado.update(_message_result(mf_gold, mf_cand))
    return resultado


def _message_result(mf_ref: Counter, mf_cand: Counter) -> dict:
    """Métrica de mensagens, prefixada `mf_` para nunca se confundir com o DF."""
    p, r, f1 = _prf(mf_ref, mf_cand)
    return {
        "mf_precision": p,
        "mf_recall": r,
        "mf_f1": f1,
        "mf_ref_size": sum(mf_ref.values()),
        "mf_cand_size": sum(mf_cand.values()),
        "mf_missing": dict(mf_ref - mf_cand),
        "mf_extra": dict(mf_cand - mf_ref),
    }
