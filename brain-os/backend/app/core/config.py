"""Load and validate BrainOS config from YAML. No hardcoded defaults for business logic."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(config_dir: str | Path | None = None) -> dict[str, Any]:
    _default = Path(__file__).parent.parent.parent / "config"
    config_dir = Path(config_dir or os.environ.get("BRAINOS_CONFIG_DIR", _default))
    schema_path = config_dir / "schema.yaml"
    if not schema_path.exists():
        raise FileNotFoundError(f"Config not found: {schema_path}")

    with open(schema_path) as f:
        config = yaml.safe_load(f) or {}

    # Resolve env vars for secrets / URLs (values like ${ENV_VAR})
    def resolve_env(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: resolve_env(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [resolve_env(x) for x in obj]
        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            key = obj[2:-1].strip()
            return os.environ.get(key, obj)
        return obj

    config = resolve_env(config)
    config["_config_dir"] = str(config_dir)
    return config


def get_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("llm", {})


def get_embedding_config(config: dict[str, Any]) -> dict[str, Any]:
    return config.get("embedding", {})


def get_intent_prompt(config: dict[str, Any], intent: str) -> dict[str, str] | None:
    intents = config.get("intents", {})
    spec = intents.get(intent)
    if not spec:
        return None
    path = spec.get("prompts_path")
    if not path:
        return None
    config_dir = Path(config.get("_config_dir", "."))
    full_path = (config_dir / path).resolve()
    if not full_path.exists():
        return None
    with open(full_path) as f:
        data = yaml.safe_load(f) or {}
    return {"system": data.get("system", ""), "user_template": data.get("user_template", "")}
