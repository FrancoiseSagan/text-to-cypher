"""Unified OpenAI-compatible LLM client strictly restricted to DeepSeek / GLM / Kimi.

Supports configurable reasoning_effort (none / low / medium / high) and normalizes both
plain-string and structured thinking/text content block responses.
"""
from __future__ import annotations

import json
import re
from typing import Any
from openai import OpenAI

from .config import ALLOWED_PROVIDERS, AllowedProvider, settings


def _extract_message_text(content: Any) -> str:
    """Normalize string or list-of-blocks (e.g. Mistral/DeepSeek thinking blocks) into clean text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for blk in content:
            if isinstance(blk, str):
                parts.append(blk)
            elif isinstance(blk, dict):
                if blk.get("type") == "text" and isinstance(blk.get("text"), str):
                    parts.append(blk["text"])
            else:
                btype = getattr(blk, "type", None)
                btext = getattr(blk, "text", None)
                if btype == "text" and isinstance(btext, str):
                    parts.append(btext)
        return "\n".join(parts).strip()
    return str(content).strip()


def extract_cypher(text: str) -> str:
    """Extract clean Cypher statement from LLM output."""
    if not text:
        return ""
    fenced = re.findall(r"```(?:cypher|sql|neo4j)?\s*\n(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    candidate = fenced[0].strip() if fenced else text.strip()
    candidate = candidate.strip("`").strip()
    if candidate.endswith(";"):
        candidate = candidate[:-1].strip()
    return candidate


def extract_json_block(text: str) -> Any:
    """Extract JSON object/array from LLM response."""
    if not text:
        return None
    fenced = re.findall(r"```(?:json)?\s*\n(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    raw = fenced[0].strip() if fenced else text.strip()
    start_obj = raw.find("{")
    start_arr = raw.find("[")
    starts = [i for i in (start_obj, start_arr) if i != -1]
    if not starts:
        return None
    raw = raw[min(starts):]
    try:
        return json.loads(raw)
    except Exception:
        end = max(raw.rfind("}"), raw.rfind("]"))
        if end != -1:
            try:
                return json.loads(raw[: end + 1])
            except Exception:
                return None
        return None


class LLMClient:
    def chat(
        self,
        messages: list[dict[str, str]],
        provider: AllowedProvider | None = None,
        model: str | None = None,
        api_key: str | None = None,
        reasoning_effort: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> tuple[str, str, str]:
        """Call an allowed LLM provider and return (content, resolved_provider, resolved_model)."""
        resolved_provider: AllowedProvider = provider or settings.get_default_provider()
        if resolved_provider not in ALLOWED_PROVIDERS:
            raise ValueError(
                f"不允许的大模型提供商: {resolved_provider}。仅允许使用 DeepSeek、GLM 或 Kimi。"
            )

        base_url, key, resolved_model = settings.resolve_provider_connection(
            resolved_provider, model=model, api_key_override=api_key
        )
        if not key:
            spec = ALLOWED_PROVIDERS[resolved_provider]
            raise RuntimeError(
                f"未配置 {spec.name} 的 API Key（环境变量 {', '.join(spec.env_keys)} 或前端手动填入）。"
            )

        client = OpenAI(base_url=base_url, api_key=key, timeout=60.0)
        kwargs: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if reasoning_effort and reasoning_effort != "none":
            kwargs["reasoning_effort"] = reasoning_effort

        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:
            # Graceful fallback if a specific endpoint/model does not accept reasoning_effort
            if "reasoning_effort" in kwargs:
                kwargs.pop("reasoning_effort", None)
                resp = client.chat.completions.create(**kwargs)
            else:
                raise

        raw_content = resp.choices[0].message.content if resp.choices else ""
        content = _extract_message_text(raw_content)
        return content, resolved_provider, resolved_model


llm_client = LLMClient()
