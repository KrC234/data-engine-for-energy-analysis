from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parent.parent

GENERATION_FILE = BASE_DIR / "config" / "generation.yaml"
RULES_FILE = BASE_DIR / "config" / "rules.yaml"


def load_yaml(path: Path):
    if not path.exists():
        raise FileNotFoundError(
            f"No existe el archivo: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:
        data = yaml.safe_load(file)

    if not data:
        raise ValueError(
            f"Archivo YAML vacio: {path}"
        )

    return data


def load_generation_config():
    return load_yaml(GENERATION_FILE)


def load_rules():
    return load_yaml(RULES_FILE)


def load_config():
    generation = load_generation_config()
    rules = load_rules()

    return {
        "generation": generation,
        "rules": rules,
    }