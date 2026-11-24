"""Application configuration for Neo4j and allowed LLM providers (DeepSeek / GLM / Kimi).

All credentials, endpoints, and default models are loaded strictly from standard environment
variables or a project `.env` file (see `.env.example`).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from pydantic import BaseModel
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

AllowedProvider = Literal["deepseek", "glm", "kimi"]


class ProviderSpec(BaseModel):
    id: AllowedProvider
    name: str
    base_url: str
    default_model: str
    models: list[str]
    env_keys: list[str]


def _build_models_list(default_model: str, builtins: list[str]) -> list[str]:
    out = [default_model] if default_model else []
    for m in builtins:
        if m not in out:
            out.append(m)
    return out


_DS_DEFAULT = os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip()
_GLM_DEFAULT = os.getenv("GLM_MODEL", "glm-4-plus").strip()
_KIMI_DEFAULT = os.getenv("KIMI_MODEL", "moonshot-v1-8k").strip()

ALLOWED_PROVIDERS: dict[AllowedProvider, ProviderSpec] = {
    "deepseek": ProviderSpec(
        id="deepseek",
        name="DeepSeek",
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
        default_model=_DS_DEFAULT,
        models=_build_models_list(_DS_DEFAULT, ["deepseek-chat", "deepseek-reasoner"]),
        env_keys=["DEEPSEEK_API_KEY"],
    ),
    "glm": ProviderSpec(
        id="glm",
        name="智谱 GLM",
        base_url=os.getenv("GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").strip(),
        default_model=_GLM_DEFAULT,
        models=_build_models_list(_GLM_DEFAULT, ["glm-4-plus", "glm-4-air", "glm-4-flash"]),
        env_keys=["ZHIPU_API_KEY", "GLM_API_KEY"],
    ),
    "kimi": ProviderSpec(
        id="kimi",
        name="月之暗面 Kimi",
        base_url=os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1").strip(),
        default_model=_KIMI_DEFAULT,
        models=_build_models_list(_KIMI_DEFAULT, ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0711-preview"]),
        env_keys=["KIMI_API_KEY", "MOONSHOT_API_KEY"],
    ),
}


class Settings(BaseModel):
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://62.234.93.223:30005")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "admin123")
    neo4j_browser_url: str = os.getenv("NEO4J_BROWSER_URL", "http://62.234.93.223:30002")
    query_timeout_seconds: float = float(os.getenv("QUERY_TIMEOUT_SECONDS", "15"))
    max_self_correction_retries: int = int(os.getenv("MAX_RETRIES", "5"))
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "200"))

    data_dir: Path = PROJECT_ROOT / "data"
    skills_dir: Path = PROJECT_ROOT / "skills"
    seed_kb_path: Path = PROJECT_ROOT / "data" / "seed_kb.json"
    sqlite_path: Path = PROJECT_ROOT / "data" / "app.db"

    def resolve_provider_connection(
        self, provider: AllowedProvider, model: str | None = None, api_key_override: str | None = None
    ) -> tuple[str, str, str]:
        """Return (base_url, api_key, resolved_model) for an allowed provider."""
        spec = ALLOWED_PROVIDERS[provider]
        resolved_model = (model or spec.default_model).strip()
        key = (api_key_override or self.get_provider_api_key(provider) or "").strip()
        return spec.base_url, key, resolved_model

    def get_provider_api_key(self, provider: AllowedProvider) -> str | None:
        spec = ALLOWED_PROVIDERS[provider]
        for key_name in spec.env_keys:
            val = os.getenv(key_name)
            if val and val.strip():
                return val.strip()
        return None

    def get_default_provider(self) -> AllowedProvider:
        env_pref = os.getenv("DEFAULT_LLM_PROVIDER", "").strip().lower()
        if env_pref in ALLOWED_PROVIDERS and self.get_provider_api_key(env_pref):  # type: ignore[arg-type]
            return env_pref  # type: ignore[return-value]
        for pid in ("deepseek", "glm", "kimi"):
            if self.get_provider_api_key(pid):  # type: ignore[arg-type]
                return pid  # type: ignore[return-value]
        return "deepseek"


settings = Settings()
