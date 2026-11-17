"""模型抽象层。

所有 Agent 只认 `Backend.chat()`，不认具体厂商：
- MockBackend     : 离线确定性，无需 API key
- OpenAICompat    : 任何 OpenAI 兼容网关（DeepSeek / Qwen / 智谱 / vLLM / Ollama）

切换方式只改环境变量，改代码的地方为零：
    HARNESS_BACKEND=mock|openai
    HARNESS_BASE_URL=https://api.deepseek.com
    HARNESS_API_KEY=sk-xxx
    HARNESS_MODEL_FAST=deepseek-chat
    HARNESS_MODEL_STRONG=deepseek-chat
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

from . import mockllm


@dataclass
class Completion:
    text: str
    model: str = "mock"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class Backend:
    name = "base"

    def chat(self, messages: list[dict[str, str]], model: str, temperature: float = 0.2,
             max_tokens: int = 2400, meta: dict[str, Any] | None = None) -> Completion:
        raise NotImplementedError

    def resolve_model(self, alias: str) -> str:
        return alias


class MockBackend(Backend):
    name = "mock"

    def chat(self, messages: list[dict[str, str]], model: str, temperature: float = 0.2,
             max_tokens: int = 2400, meta: dict[str, Any] | None = None) -> Completion:
        t0 = time.time()
        meta = meta or {}
        prompt = messages[-1]["content"] if messages else ""
        text = mockllm.generate(
            role=str(meta.get("role", "generalist")),
            prompt=prompt,
            facts=meta.get("facts"),
            attempt=int(meta.get("attempt", 1)),
            meta=meta,
        )
        time.sleep(0.02)  # 让耗时指标非零，便于演示时间线
        return Completion(
            text=text,
            model=f"mock::{meta.get('role', 'generalist')}",
            prompt_tokens=max(1, len(prompt) // 2),
            completion_tokens=max(1, len(text) // 2),
            latency_ms=int((time.time() - t0) * 1000),
        )

    def resolve_model(self, alias: str) -> str:
        return f"mock::{alias}"


class OpenAICompat(Backend):
    """OpenAI 兼容网关（DeepSeek 等），只用标准库 urllib。"""

    name = "openai"

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 timeout: int = 90) -> None:
        self.base_url = (base_url or os.getenv("HARNESS_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        self.api_key = api_key or os.getenv("HARNESS_API_KEY", "")
        self.timeout = timeout
        self.fast = os.getenv("HARNESS_MODEL_FAST", "deepseek-chat")
        self.strong = os.getenv("HARNESS_MODEL_STRONG", self.fast)

    def resolve_model(self, alias: str) -> str:
        return {"fast": self.fast, "strong": self.strong}.get(alias, alias)

    def chat(self, messages: list[dict[str, str]], model: str, temperature: float = 0.2,
             max_tokens: int = 3500, meta: dict[str, Any] | None = None) -> Completion:
        t0 = time.time()
        model_id = self.resolve_model(model)
        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:300]
            return Completion(text="", model=model_id, error=f"HTTP {e.code}: {detail}",
                              latency_ms=int((time.time() - t0) * 1000))
        except Exception as e:  # noqa: BLE001
            return Completion(text="", model=model_id, error=f"请求失败: {e}",
                              latency_ms=int((time.time() - t0) * 1000))

        usage = body.get("usage", {}) or {}
        choices = body.get("choices") or [{}]
        text = (choices[0].get("message") or {}).get("content") or ""
        return Completion(
            text=text,
            model=model_id,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.time() - t0) * 1000),
            raw=body,
        )


def get_backend(name: str | None = None) -> Backend:
    kind = (name or os.getenv("HARNESS_BACKEND", "mock")).lower()
    if kind in ("openai", "deepseek", "qwen", "glm", "vllm", "ollama"):
        return OpenAICompat()
    return MockBackend()
