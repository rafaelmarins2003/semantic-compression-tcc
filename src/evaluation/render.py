from __future__ import annotations

from collections import deque

from lxml import etree

BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_Q = f"{{{BPMN_NS}}}"

_GATEWAYS = {
    "exclusiveGateway": "exclusive",
    "parallelGateway": "parallel",
    "inclusiveGateway": "inclusive",
    "eventBasedGateway": "event-based",
    "complexGateway": "complex",
}
_EVENTS = {
    "startEvent": "start event",
    "endEvent": "end event",
    "intermediateCatchEvent": "intermediate event (catch)",
    "intermediateThrowEvent": "intermediate event (throw)",
    "boundaryEvent": "boundary event",
}
_SUBPROCESSES = {"subProcess", "callActivity", "transaction", "adHocSubProcess"}

# Nome que o emissor XML atribui a evento anônimo: não é denominação do modelo.
_DEFAULT_EVENT_NAMES = {"start", "end"}


def _local(el: etree._Element) -> str | None:
    if not isinstance(el.tag, str) or not el.tag.startswith(_Q):
        return None
    return el.tag[len(_Q) :]


def _kind(local: str) -> str | None:
    """Categoria neutra do nó, ou None se não for nó de fluxo."""
    if local in _GATEWAYS:
        return "gateway"
    if local in _EVENTS:
        return "event"
    if local in _SUBPROCESSES:
        return "subprocess"
    if local == "task" or local.endswith("Task"):
        return "activity"
    return None


def _clean(texto: str | None) -> str:
    return " ".join((texto or "").split()).strip().strip('"').strip()


def _event_trigger(el: etree._Element) -> str:
    for filho in el:
        local = _local(filho)
        if local and local.endswith("EventDefinition"):
            return local.removesuffix("EventDefinition")
    return ""


def _condition(flow: etree._Element) -> str:
    nome = _clean(flow.get("name"))
    if nome:
        return nome
    expr = flow.find(f"{_Q}conditionExpression")
    return _clean(expr.text if expr is not None else "")


def parse(xml_text: str) -> dict:
    """Extrai nós, fluxos, atores e mensagens, já sem convenções de origem."""
    root = etree.fromstring(xml_text.encode("utf-8"))
    nos: dict[str, dict] = {}
    fluxos: list[tuple[str, str, str]] = []
    mensagens: list[tuple[str, str, str]] = []
    ator: dict[str, str] = {}
    pool_do_processo: dict[str, str] = {}
    participantes: dict[str, str] = {}  # id do participant -> nome do pool

    for part in root.iter(f"{_Q}participant"):
        participantes[part.get("id")] = _clean(part.get("name"))
        if part.get("processRef"):
            pool_do_processo[part.get("processRef")] = _clean(part.get("name"))

    for proc in root.iter(f"{_Q}process"):
        pool = pool_do_processo.get(proc.get("id"), "")
        for el in proc.iter():
            local = _local(el)
            if local is None:
                continue
            if local == "sequenceFlow":
                if el.get("sourceRef") and el.get("targetRef"):
                    fluxos.append((el.get("sourceRef"), el.get("targetRef"), _condition(el)))
                continue
            if local == "lane":
                nome = _clean(el.get("name"))
                for ref in el.iter(f"{_Q}flowNodeRef"):
                    if ref.text and nome:
                        ator[ref.text.strip()] = nome
                continue
            tipo = _kind(local)
            if tipo is None or el.get("id") is None:
                continue
            nome = _clean(el.get("name"))
            if tipo == "event" and nome.lower() in _DEFAULT_EVENT_NAMES:
                nome = ""
            nos[el.get("id")] = {
                "kind": tipo,
                "local": local,
                "name": nome,
                "trigger": _event_trigger(el) if tipo == "event" else "",
                "pool": pool,
            }

    for el in root.iter(f"{_Q}messageFlow"):
        if el.get("sourceRef") and el.get("targetRef"):
            mensagens.append((el.get("sourceRef"), el.get("targetRef"), _clean(el.get("name"))))

    for nid, no in nos.items():
        no["actor"] = ator.get(nid) or no["pool"]
    fluxos = [f for f in fluxos if f[0] in nos and f[1] in nos]
    return {"nodes": nos, "flows": fluxos, "messages": mensagens, "pools": participantes}


def _bypass_passthrough(nos: dict, fluxos: list) -> list:
    """Remove gateway com uma entrada e uma saída: não roteia nada.

    O transpilador e alguns modeladores deixam gateways degenerados; mostrá-los
    ao juiz seria ruído de convenção, não de processo.
    """
    while True:
        entra = {n: [f for f in fluxos if f[1] == n] for n in nos}
        sai = {n: [f for f in fluxos if f[0] == n] for n in nos}
        alvo = next(
            (
                n
                for n, no in nos.items()
                if no["kind"] == "gateway" and len(entra[n]) == 1 and len(sai[n]) == 1
            ),
            None,
        )
        if alvo is None:
            return fluxos
        (origem, _, cond_in), (_, destino, cond_out) = entra[alvo][0], sai[alvo][0]
        fluxos = [f for f in fluxos if alvo not in f[:2]]
        fluxos.append((origem, destino, cond_in or cond_out))
        del nos[alvo]


def _neutral_ids(nos: dict, fluxos: list) -> dict[str, str]:
    """N1, N2... em busca em largura a partir dos inícios; desempate por rótulo."""
    succ: dict[str, list[str]] = {n: [] for n in nos}
    entra = {n: 0 for n in nos}
    for a, b, _ in fluxos:
        succ[a].append(b)
        entra[b] += 1
    chave = lambda n: (nos[n]["name"], nos[n]["local"])  # noqa: E731
    inicios = sorted((n for n in nos if nos[n]["local"] == "startEvent"), key=chave)
    inicios += sorted((n for n in nos if entra[n] == 0 and n not in inicios), key=chave)
    ordem: list[str] = []
    vistos: set[str] = set()
    pendentes = list(inicios) + sorted(nos, key=chave)
    for semente in pendentes:
        if semente in vistos:
            continue
        fila = deque([semente])
        while fila:
            n = fila.popleft()
            if n in vistos:
                continue
            vistos.add(n)
            ordem.append(n)
            fila.extend(sorted(succ[n], key=chave))
    return {n: f"N{i}" for i, n in enumerate(ordem, 1)}


def _describe(no: dict, entradas: int, saidas: int) -> str:
    if no["kind"] == "gateway":
        tipo = _GATEWAYS.get(no["local"], "")
        if entradas > 1 and saidas <= 1:
            return f"merge ({tipo})"  # junção: o nome do merge é convenção, não conteúdo
        base = f"decision ({tipo})" if tipo != "parallel" else "parallel split"
        return f'{base} "{no["name"]}"' if no["name"] else base
    if no["kind"] == "event":
        base = _EVENTS[no["local"]]
        if no["trigger"]:
            base += f" [{no['trigger']}]"
        return f'{base} "{no["name"]}"' if no["name"] else base
    base = "subprocess" if no["kind"] == "subprocess" else "activity"
    return f'{base} "{no["name"]}"' if no["name"] else base


def render(xml_text: str) -> str:
    """Texto neutro do modelo. Mesma saída para o mesmo processo, venha de onde vier."""
    dados = parse(xml_text)
    nos, fluxos = dados["nodes"], _bypass_passthrough(dados["nodes"], dados["flows"])
    ids = _neutral_ids(nos, fluxos)
    entra = {n: sum(f[1] == n for f in fluxos) for n in nos}
    sai = {n: sum(f[0] == n for f in fluxos) for n in nos}

    atores = sorted({no["actor"] for no in nos.values() if no["actor"]})
    linhas = []
    if atores:
        linhas.append("Actors: " + ", ".join(atores))
    linhas.append("Elements:")
    for n in sorted(nos, key=lambda n: int(ids[n][1:])):
        no = nos[n]
        sufixo = f" (by {no['actor']})" if no["actor"] else ""
        linhas.append(f"  {ids[n]}: {_describe(no, entra[n], sai[n])}{sufixo}")
    linhas.append("Sequence flows:")
    for a, b, cond in sorted(fluxos, key=lambda f: (int(ids[f[0]][1:]), int(ids[f[1]][1:]))):
        linhas.append(f"  {ids[a]} -> {ids[b]}" + (f'  [if "{cond}"]' if cond else ""))
    mensagens = [
        (ids.get(a, dados["pools"].get(a, a)), ids.get(b, dados["pools"].get(b, b)), nome)
        for a, b, nome in dados["messages"]
    ]
    if mensagens:
        linhas.append("Message flows:")
        for a, b, nome in sorted(mensagens):
            linhas.append(f"  {a} -> {b}" + (f'  "{nome}"' if nome else ""))
    return "\n".join(linhas)
