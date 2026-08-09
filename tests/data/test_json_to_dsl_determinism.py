"""Determinismo do `json_to_dsl` entre processos.

`_find_merge_point` escolhia o nó de menor custo iterando um `set`. Em empate, o
vencedor dependia da ordem de iteração — que varia com o hash das strings a cada
processo — e a DSL emitida mudava entre execuções para a mesma entrada.

O projeto inteiro se apoia na premissa de que a transpilação é determinística;
este teste roda o conversor em subprocessos com `PYTHONHASHSEED` distintos.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

# Fork com dois caminhos de mesmo comprimento até dois candidatos a merge —
# a condição de empate que expunha a ordenação instável.
TIED_MERGE_PAYLOAD = {
    "pool": "Tie",
    "lanes": [],
    "nodes": [
        {"id": "E01", "type": "startEvent", "name": "Start"},
        {"id": "G01", "type": "exclusiveGateway", "name": "Choice?"},
        {"id": "TA", "type": "userTask", "name": "Alpha"},
        {"id": "TB", "type": "userTask", "name": "Bravo"},
        {"id": "MA", "type": "userTask", "name": "Merge Alpha"},
        {"id": "MB", "type": "userTask", "name": "Merge Bravo"},
        {"id": "E02", "type": "endEvent", "name": "End"},
    ],
    "flows": [
        {"id": "f1", "from": "E01", "to": "G01"},
        {"id": "f2", "from": "G01", "to": "TA", "cond": "a", "label": "A"},
        {"id": "f3", "from": "G01", "to": "TB", "cond": "b", "label": "B"},
        {"id": "f4", "from": "TA", "to": "MA"},
        {"id": "f5", "from": "TB", "to": "MA"},
        {"id": "f6", "from": "MA", "to": "MB"},
        {"id": "f7", "from": "MB", "to": "E02"},
    ],
}

SCRIPT = (
    "import json,hashlib,sys;"
    "from src.data.deterministic.json_to_dsl import convert;"
    "print(hashlib.md5(convert(json.load(sys.stdin)).encode()).hexdigest())"
)


def _digest_with_seed(seed: str, payload: dict) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed}
    out = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[2],
        check=True,
    )
    return out.stdout.strip()


def test_convert_is_stable_across_hash_seeds():
    digests = {_digest_with_seed(seed, TIED_MERGE_PAYLOAD) for seed in ("0", "1", "2", "3")}

    assert len(digests) == 1, f"DSL não determinística entre processos: {digests}"


def test_convert_is_stable_within_a_process():
    from src.data.deterministic.json_to_dsl import convert

    first = convert(TIED_MERGE_PAYLOAD)
    second = convert(TIED_MERGE_PAYLOAD)

    assert hashlib.md5(first.encode()).hexdigest() == hashlib.md5(second.encode()).hexdigest()
