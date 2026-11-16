"""真模型连通性自检 —— 只发一次最小请求，5 秒内告诉你能不能跑。

为什么单独做这个脚本：
接真模型失败时，90% 的人会去怀疑代码，其实问题在 key / 余额 / 网络 / 模型名。
把「模型能不能通」和「流程能不能跑」拆开测，故障定位就从 2 小时变 2 分钟。

用法：
    python check_model.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from harness.loadenv import ENV_PATH  # noqa: E402
from harness.models import get_backend  # noqa: E402

BAR = "─" * 62

HINTS = [
    ("401", "API Key 无效或已失效",
     "去 platform.deepseek.com 重新创建 key；检查是不是复制时多了空格或少了字符"),
    ("402", "账户余额不足",
     "去平台充值（10 元足够跑完全部实验）"),
    ("403", "权限不足 / 需要实名认证",
     "完成实名认证，或确认该 key 有对应模型权限"),
    ("404", "接口地址或模型名不存在",
     "检查 HARNESS_BASE_URL 是否少了 / 多了路径；检查 HARNESS_MODEL_FAST 拼写"),
    ("429", "请求太频繁被限流",
     "等 30 秒再试；或降低并发"),
    ("timeout", "网络超时",
     "检查代理设置；公司/校园网可能需要走代理"),
    ("timed out", "网络超时",
     "检查代理设置；公司/校园网可能需要走代理"),
    ("拒绝", "连接被拒绝",
     "检查网络、防火墙，或 BASE_URL 是否写错协议（http/https）"),
    ("Name or service not known", "域名解析失败",
     "DNS 或网络问题，换个网络试试"),
]


def show_config() -> None:
    print(BAR)
    print("当前配置")
    print(BAR)
    print(f"  .env 文件        : {ENV_PATH}  {'✅ 存在' if ENV_PATH.exists() else '❌ 不存在'}")
    for k in ("HARNESS_BACKEND", "HARNESS_BASE_URL", "HARNESS_MODEL_FAST",
              "HARNESS_MODEL_STRONG"):
        print(f"  {k:<17}: {os.getenv(k, '(未设置)')}")
    key = os.getenv("HARNESS_API_KEY", "")
    masked = f"{key[:6]}…{key[-4:]}(长度 {len(key)})" if len(key) > 10 else "(未设置或过短)"
    print(f"  HARNESS_API_KEY  : {masked}")
    print(BAR)


def main() -> int:
    show_config()
    backend = get_backend()
    print(f"后端类型：{backend.name}")
    if backend.name == "mock":
        print("\n⚠️  当前是 mock（离线模拟）后端，不会真正调用模型。")
        print("   要接真模型，请在 futurecup 目录下创建 .env 文件，内容参考 .env.example：")
        print("       HARNESS_BACKEND=openai")
        print("       HARNESS_BASE_URL=https://api.deepseek.com")
        print("       HARNESS_API_KEY=sk-你的key")
        print("       HARNESS_MODEL_FAST=deepseek-chat")
        print("       HARNESS_MODEL_STRONG=deepseek-chat")
        print("\n   mock 模式下系统依然可以完整演示，这一步不通过也不影响交作品。")
        return 0

    print("正在发送一次最小请求 …\n")
    comp = backend.chat(
        [{"role": "user", "content": "只回复两个字：正常"}],
        model="fast",
        max_tokens=16,
        meta={"role": "generalist"},
    )

    if comp.error:
        print("❌ 调用失败")
        print(f"   错误信息：{comp.error}")
        low = comp.error.lower()
        hit = None
        for token, cause, fix in HINTS:
            if token.lower() in low:
                hit = (cause, fix)
                break
        if hit:
            print(f"\n   最可能的原因：{hit[0]}")
            print(f"   怎么修：{hit[1]}")
        else:
            print("\n   没有匹配到已知错误类型，把上面这行完整报错发给我。")
        print("\n   提示：这一步失败不影响你继续做作品，mock 模式照样能演示。")
        return 2

    print("✅ 调用成功")
    print(f"   模型      ：{comp.model}")
    print(f"   返回内容  ：{comp.text.strip()[:60]}")
    print(f"   耗时      ：{comp.latency_ms} ms")
    print(f"   tokens    ：prompt {comp.prompt_tokens} / completion {comp.completion_tokens}")
    print(BAR)
    print("可以开始跑完整流程了：")
    print("   python -m harness.cli run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
