"""零依赖 .env 加载器。

目的：不用每次开新终端都重新 $env: 一遍，也不会因为手抖打错变量名而白折腾半小时。
只用标准库，不引入 python-dotenv。

规则：
- 逐行读 KEY=VALUE
- 跳过空行与 # 注释
- 去掉值两端可能存在的引号
- 已经存在的环境变量不覆盖（命令行显式设置的优先）
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def load_env(path: Path | None = None) -> dict[str, str]:
    p = path or ENV_PATH
    loaded: dict[str, str] = {}
    if not p.exists():
        return loaded
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key:
            continue
        loaded[key] = val
        os.environ.setdefault(key, val)
    return loaded
