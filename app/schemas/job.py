from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# ── Parser internals ────────────────────────────────────────────────────────

class RowRecord(BaseModel):
    """A single data row — extra fields pass through as-is."""
    model_config = ConfigDict(extra="allow")


class ExtractedTable(BaseModel):
    """One detected table block within a sheet."""
    model_config = ConfigDict(extra="forbid")

    sheet_name: str
    table_id: str
    headers: list[str]
    header_signature: str
    source_range: str
    rows: list[dict[str, Any]]


class GroupedRequirement(BaseModel):
    """All tables sharing the same normalized header signature."""
    model_config = ConfigDict(extra="forbid")

    requirement_name: str
    headers: list[str]
    header_signature: str
    tables: list[ExtractedTable]
    total_rows: int = Field(default=0)


# ── API responses ────────────────────────────────────────────────────────────

class JobSubmitResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    created_at: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    created_at: str
    completed_at: str | None = None
    error: str | None = None
    result_file: str | None = None
    groups: int | None = None
    total_rows: int | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
