"""多 Agent 编排调度平台（FutureCup 赛题一 参赛骨架）。"""

__version__ = "0.1.0"

from .loadenv import load_env  # noqa: F401

# 导入 harness 包时自动加载项目根目录的 .env（若存在），命令行已设置的变量优先。
load_env()
