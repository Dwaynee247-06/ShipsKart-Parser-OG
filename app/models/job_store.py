from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.job import ParseJob


class SqlServerJobStore:
    """Thin repository layer over ParseJob; all DB calls go through here."""

    def create(self, db: Session, payload: dict[str, Any]) -> None:
        db.add(ParseJob(**payload))
        db.commit()

    def get(self, db: Session, job_id: str) -> dict[str, Any] | None:
        job = db.execute(select(ParseJob).where(ParseJob.job_id == job_id)).scalar_one_or_none()
        if not job:
            return None
        return {
            "job_id": job.job_id,
            "status": job.status,
            "filename": job.filename,
            "created_at": job.created_at,
            "completed_at": job.completed_at,
            "error": job.error,
            "result_file": job.result_file,
            "groups": job.groups,
            "total_rows": job.total_rows,
        }

    def update(self, db: Session, job_id: str, **fields: Any) -> None:
        job = db.execute(select(ParseJob).where(ParseJob.job_id == job_id)).scalar_one_or_none()
        if not job:
            return
        for key, value in fields.items():
            setattr(job, key, value)
        db.add(job)
        db.commit()

    def list_all(self, db: Session, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        rows = db.execute(
            select(ParseJob).order_by(ParseJob.id.desc()).limit(limit).offset(offset)
        ).scalars().all()
        return [self.get(db, r.job_id) for r in rows]


job_store = SqlServerJobStore()
