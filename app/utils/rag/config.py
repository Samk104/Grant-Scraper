from __future__ import annotations
import os
import yaml
from functools import lru_cache

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "configs", "system_prompt.yml")

@lru_cache(maxsize=1)
def load_system_prompt(path: str | None = None) -> dict:
    cfg_path = path or DEFAULT_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    data.setdefault("version", 1)
    data.setdefault("caps", {})
    data.setdefault("retrieval", {})
    if "prompt" not in data or not isinstance(data["prompt"], str) or not data["prompt"].strip():
        raise ValueError("system_prompt.yml has wrong data type or is missing a non-empty 'prompt' field.")
    return data

def get_prompt_text() -> str:
    return load_system_prompt()["prompt"].strip()

def get_caps() -> dict:
    return load_system_prompt().get("caps", {})

def get_retrieval_knobs() -> dict:
    return load_system_prompt().get("retrieval", {})

def get_keywords() -> dict:
    data = load_system_prompt()
    kw = data.get("keywords", {}) or {}
    return {
        "core": list(kw.get("core", []) or []),
        "expanded": list(kw.get("expanded", []) or []),
    }

