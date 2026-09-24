import os
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


class Settings:

    APP_NAME = os.getenv(
        "APP_NAME",
        "HyperDataSynthetic"
    )

    APP_ENV = os.getenv(
        "APP_ENV",
        "development"
    )

    DB_HOST = os.getenv(
        "DB_HOST",
        "localhost"
    )

    DB_PORT = int(
        os.getenv("DB_PORT", "5432")
    )

    DB_NAME = os.getenv(
        "DB_NAME",
        "energia_hsd"
    )

    DB_USER = os.getenv(
        "DB_USER",
        "equipo_hsd"
    )

    DB_PASSWORD = os.getenv(
        "DB_PASSWORD"
    )

    DB_SCHEMA = os.getenv(
        "DB_SCHEMA",
        "energia"
    )

    DB_CONNECT_TIMEOUT = int(
        os.getenv("DB_CONNECT_TIMEOUT", "10")
    )

    @classmethod
    def validate(cls):
        required = {
            "DB_HOST": cls.DB_HOST,
            "DB_NAME": cls.DB_NAME,
            "DB_USER": cls.DB_USER,
            "DB_PASSWORD": cls.DB_PASSWORD,
            "DB_SCHEMA": cls.DB_SCHEMA,
        }

        missing = [
            key
            for key, value in required.items()
            if not value
        ]

        if missing:
            raise RuntimeError(
                "Configuracion faltante: "
                + ", ".join(missing)
            )


settings = Settings()
