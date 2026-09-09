"""Application configuration (env-driven, sane defaults for local demo)."""
from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv_into_environ(*paths: Path) -> None:
    """Put every key in these .env files onto `os.environ` (without overriding a real env var).

    pydantic-settings reads a .env file into `Settings` only, and only under the `CNA_` prefix.
    Third-party libraries and the provider layer look at `os.environ` for their own conventional
    names, so a key someone pastes in as `GEMINI_API_KEY` or `FIRECRAWL_API_KEY` would otherwise
    be silently ignored. This closes that gap for the one file `Settings` already reads.

    Deliberately only `backend/.env`. The repo root holds its own .env for other tooling, and
    hoovering that up would let an unrelated `CNA_DATABASE_URL` there quietly repoint the running
    app at a different database. A real environment variable still wins over the file.
    """
    for path in paths:
        try:
            if not path.is_file():
                continue
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip().lstrip("﻿")
                if key.lower().startswith("export "):
                    key = key[7:].strip()
                value = value.strip().strip('"').strip("'")
                if key and value:
                    os.environ.setdefault(key, value)
        except OSError:
            continue


_load_dotenv_into_environ(BASE_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CNA_", env_file=BASE_DIR / ".env", extra="ignore")

    app_name: str = "Criminal Network Analysis System"
    environment: str = "development"
    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'cna.db').as_posix()}"
    data_dir: Path = BASE_DIR / "data"
    samples_dir: Path = BASE_DIR / "data" / "samples"

    # What an empty database is filled with at startup: "real" chains the public-record connectors
    # (ICIJ, OpenSanctions, INTERPOL, GLEIF, NIA, Supreme Court, news), "demo" loads the synthetic
    # Operation Saltwater corpus, "none" leaves it empty. Real needs network for most sources; if
    # nothing loads it falls back to the demo so the console is never blank.
    default_corpus: str = "real"

    # Security
    jwt_secret: str = "change-me-in-production-please-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173"]
    bootstrap_admin_user: str = "admin"
    bootstrap_admin_password: str = "admin@123"
    bootstrap_analyst_user: str = "analyst"
    bootstrap_analyst_password: str = "analyst@123"

    # AI (optional; system is fully functional without any of it)
    # LLM tier. Served through OpenRouter (OpenAI-compatible) by default; "anthropic" is still
    # accepted for a direct Claude key. The system is fully functional with no key at all.
    llm_provider: str = "openrouter"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    anthropic_api_key: str | None = None
    llm_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    llm_enabled: bool = True
    # Tier-3 extraction over every ingested document. Off by default: a call costs tens of seconds,
    # so a few hundred documents would turn a routine harvest into hours. Narration and the
    # investigator run on `llm_enabled` alone and are unaffected by this.
    llm_extraction_enabled: bool = False
    # The default model reasons before answering, and reasoning tokens come out of max_tokens.
    # "none" keeps the budget for the tool call itself; raise to "low"/"medium" for harder text.
    llm_reasoning_effort: str = "none"
    llm_max_tokens: int = 8000
    llm_narrate_tokens: int = 1200
    llm_max_input_chars: int = 12000
    llm_timeout: float = 240.0
    llm_max_retries: int = 3
    # Extraction is cached by (model, text) so a document is read once and re-runs are
    # reproducible; the graph must not drift between two runs over the same corpus.
    llm_cache_enabled: bool = True

    # Investigator agent providers, tried in this order; the first that answers takes the turn.
    llm_providers: str = "gemini,nvidia,anthropic"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    nvidia_api_key: str | None = None
    nvidia_model: str = "meta/llama-3.3-70b-instruct"
    nvidia_base_url: str | None = None
    # Open-web tier for the agent: with a key, Firecrawl renders JS and returns clean markdown;
    # without one it falls back to the keyless DuckDuckGo + HTTP path.
    firecrawl_api_key: str | None = None
    # zero-shot transformer NER (GLiNER). Requires the "neural" extra; off by default so the
    # default install stays small and offline-friendly.
    neural_ner_enabled: bool = False
    # 0.40 keeps high-value offence context (drug/weapon/quantity score 0.81-0.94); precision is
    # enforced by pattern validation in neural_ner._valid rather than by a blunt threshold.
    neural_ner_threshold: float = 0.40
    # semantic search over documents (fastembed / ONNX)
    semantic_search_enabled: bool = True
    # tamper-evident hash chain sealing every ingested document at collection time
    evidence_ledger_enabled: bool = True

    # Analytics tuning
    fuzzy_name_threshold: int = 88
    anomaly_contamination: float = 0.06
    structuring_threshold_inr: float = 50_000.0


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.samples_dir.mkdir(parents=True, exist_ok=True)
