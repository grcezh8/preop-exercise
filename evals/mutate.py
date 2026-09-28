"""small edit language for building a scenario from a seed case, e.g. set("vitals[2].value_f", 100.5)
edits run in order, so a delete shifts the positions of later items
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any

_TOKEN = re.compile(r"([a-z_]+)|\[(\d+)\]")


@dataclass(frozen=True)
class Edit:
    op: str  # set | delete | append
    path: str
    value: Any = None


def set_(path: str, value: Any) -> Edit:
    return Edit("set", path, value)


def delete(path: str) -> Edit:
    return Edit("delete", path)


def append(path: str, value: Any) -> Edit:
    return Edit("append", path, value)


def apply_edits(submission: dict[str, Any], edits: list[Edit]) -> dict[str, Any]:
    # returns an edited copy, raises if a path doesn't exist so a typo in a scenario can't pass silently
    result = copy.deepcopy(submission)
    for edit in edits:
        keys = _parse(edit.path)
        parent = result
        for key in keys[:-1]:
            parent = parent[key]
        last = keys[-1]
        if edit.op == "set":
            if isinstance(parent, list):
                parent[last]  # must exist
            parent[last] = copy.deepcopy(edit.value)
        elif edit.op == "delete":
            del parent[last]
        elif edit.op == "append":
            parent[last].append(copy.deepcopy(edit.value))
        else:
            raise ValueError(f"unknown op {edit.op}")
    return result


def _parse(path: str) -> list[str | int]:
    keys: list[str | int] = []
    for name, index in _TOKEN.findall(path):
        keys.append(name if name else int(index))
    if not keys:
        raise ValueError(f"bad path {path!r}")
    return keys
