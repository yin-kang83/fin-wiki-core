# -*- coding: utf-8 -*-
"""Fin-Wiki Super-agent：LLM adapter 边界层。

职责：
- 把 provider 调用封装成可替换的 adapter；
- 统一超时、重试、prompt/response 长度限制、JSON 提取；
- 不打印、不落盘 API key；
- 返回 dict，交给 Worker 再做 Pydantic 校验。

边界：
- 本文件不做真实联网测试；真实 provider 由调用方注入。
- 同步 callable 的超时只能停止等待，无法强杀底层线程（Python 限制）。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable


class AdapterError(RuntimeError):
    pass


class LLMAdapter:
    """通用 adapter：callable + 超时 + 重试 + JSON 提取。"""

    def __init__(self, call: Callable[[str], str], *,
                 timeout: float = 30.0, retries: int = 2,
                 backoff: float = 0.5,
                 max_prompt_chars: int = 20000,
                 max_response_chars: int = 200000) -> None:
        if not callable(call):
            raise TypeError("call 必须可调用")
        self.call = call
        self.timeout = float(timeout)
        self.retries = int(retries)
        self.backoff = float(backoff)
        self.max_prompt_chars = int(max_prompt_chars)
        self.max_response_chars = int(max_response_chars)

    def _call(self, text: str) -> str:
        ex = ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(self.call, text)
        try:
            return fut.result(timeout=self.timeout)
        except TimeoutError as exc:
            fut.cancel()
            raise AdapterError("LLM 调用超时") from exc
        except Exception as exc:  # noqa: BLE001
            raise AdapterError(f"LLM 调用失败: {type(exc).__name__}") from exc
        finally:
            ex.shutdown(wait=False, cancel_futures=True)

    def parse(self, text: str) -> dict[str, Any]:
        prompt = str(text)
        if not prompt.strip():
            raise AdapterError("空 prompt")
        if len(prompt) > self.max_prompt_chars:
            raise AdapterError(f"prompt 过长: {len(prompt)}")
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                raw = self._call(prompt)
                if not isinstance(raw, str):
                    raise AdapterError("LLM 返回不是文本")
                if len(raw) > self.max_response_chars:
                    raise AdapterError(f"响应过长: {len(raw)}")
                return extract_json(raw)
            except AdapterError as exc:
                last = exc
                if attempt < self.retries:
                    time.sleep(self.backoff * (attempt + 1))
        raise AdapterError(f"LLM 输出无法解析: {last}")


class CallableAdapter(LLMAdapter):
    """把普通 callable 包装成 adapter。"""


def extract_json(raw: str) -> dict[str, Any]:
    """从模型文本中提取 JSON 对象；支持 ```json fenced block。"""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise AdapterError("未找到 JSON 对象") from None
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise AdapterError(f"JSON 解析失败: {exc}") from exc
    if not isinstance(value, dict):
        raise AdapterError("LLM 输出不是 JSON 对象")
    return value


class OpenAICompatibleAdapter(LLMAdapter):
    """OpenAI-compatible Chat Completions adapter。

    密钥只从环境变量读取，不打印、不落盘：
      FINWIKI_LLM_BASE_URL
      FINWIKI_LLM_API_KEY
      FINWIKI_LLM_MODEL
    """

    def __init__(self, base_url: str, api_key: str, model: str,
                 timeout: float = 30.0, max_output_tokens: int = 2000) -> None:
        if not base_url or not model:
            raise ValueError("base_url/model 不能为空")
        if not api_key:
            raise ValueError("api_key 不能为空")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_output_tokens = int(max_output_tokens)
        super().__init__(self._post, timeout=timeout, retries=1)

    @classmethod
    def from_env(cls) -> OpenAICompatibleAdapter:
        base = os.environ.get("FINWIKI_LLM_BASE_URL", "")
        key = os.environ.get("FINWIKI_LLM_API_KEY", "")
        model = os.environ.get("FINWIKI_LLM_MODEL", "")
        if not (base and key and model):
            raise AdapterError("缺少 FINWIKI_LLM_BASE_URL/API_KEY/MODEL")
        return cls(base, key, model)

    def build_request(self, text: str) -> urllib.request.Request:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": text}],
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
        }, ensure_ascii=False).encode("utf-8")
        return urllib.request.Request(
            self.base_url + "/chat/completions", data=body, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})

    def _post(self, text: str) -> str:
        try:
            with urllib.request.urlopen(self.build_request(text), timeout=self.timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise AdapterError(f"HTTP 调用失败: {exc}") from exc
        try:
            return payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AdapterError("响应缺少 choices[0].message.content") from exc
