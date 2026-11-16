"""通用小工具：安全模板渲染、时间戳、JSON 读写。"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)[^}]*\}")


def safe_format(template: str, ctx: dict[str, Any], limit: int = 6000) -> str:
    """把 {key} 替换成 ctx[key]，缺失的键保留原样。

    不用 str.format，避免数据里出现大括号时炸掉整条流程。
    """

    def rep(m: re.Match[str]) -> str:
        key = m.group(1)
        if key not in ctx:
            return m.group(0)
        val = ctx[key]
        text = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
        if len(text) > limit:
            text = text[:limit] + f"\n…（已截断，原文 {len(text)} 字）"
        return text

    return _PLACEHOLDER.sub(rep, template)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def rid() -> str:
    return f"run-{int(time.time() * 1000)}-{int.from_bytes(__import__('os').urandom(2), 'big'):04x}"


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent
