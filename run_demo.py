"""一键运行入口 —— 给 PyCharm 的 ▶ 按钮、以及录视频时用。

用法：
    # 默认跑一次"故障演练"（注入一次输出截断，会看到验证抓错 → 自动返修）
    python run_demo.py

    # 也可以传参数，等价于 python -m harness.cli xxx
    python run_demo.py run
    python run_demo.py run --fault
    python run_demo.py run --dataset data/demo_second.csv
    python run_demo.py eval
    python run_demo.py replay run-xxxxx
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.cli import main  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:] or ["run", "--fault"]
    raise SystemExit(main(argv))
