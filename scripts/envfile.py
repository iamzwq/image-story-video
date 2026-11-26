"""读取项目根目录的 .env（KEY=VALUE 格式）。系统环境变量里已有的同名项优先，空值视为未设置。"""
from __future__ import annotations

import os
from pathlib import Path


def read_env(root: Path) -> dict[str, str]:
    """读出 .env 里填了值的项，不改动环境变量。同一项写了多次时以第一个有值的为准。"""
    path = root / ".env"
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        else:
            value = value.split(" #", 1)[0].strip()
        if value:
            values.setdefault(key, value)
    return values


def load_env(root: Path) -> None:
    for key, value in read_env(root).items():
        if not os.environ.get(key):
            os.environ[key] = value


def env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()
