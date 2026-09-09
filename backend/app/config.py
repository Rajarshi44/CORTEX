"""Application configuration (env-driven, sane defaults for local demo)."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


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
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-5"
    llm_enabled: bool = True
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
