"""Shared settings loader with an ignored, machine-specific override."""
from pathlib import Path
import yaml


def load_config(config_path="config/settings.yaml"):
    cfg = {}
    paths = [Path(config_path)]
    if paths[0] == Path("config/settings.yaml"):
        paths.append(Path("config/settings.local.yaml"))
    def merge(target, values):
        for key, value in values.items():
            if isinstance(value, dict) and isinstance(target.get(key), dict):
                merge(target[key], value)
            else:
                target[key] = value
    for path in paths:
        if path.exists():
            with path.open(encoding="utf-8") as source:
                merge(cfg, yaml.safe_load(source) or {})
    return cfg
