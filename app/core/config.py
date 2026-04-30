from pathlib import Path
from typing import Tuple
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
RESULT_DIR = DATA_DIR / "results"


class Settings(BaseSettings):
    # App
    app_name: str = "Excel Parser API"
    app_version: str = "1.0.0"
    api_v1_prefix: str = "/api/v1"
    debug: bool = False

    # Excel
    allowed_extensions: Tuple[str, ...] = (".xlsx", ".xlsm", ".xltx", ".xltm")
    blank_row_tolerance: int = 1
    min_headers: int = 2

    # Database (SQL Server via SSMS)
    database_url: str = (
        "mssql+pyodbc://sa:YourStrong!Passw0rd@localhost/ExcelParserDB"
        "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)
