"""Write inspectable CSV snapshots of the canonical SQLite job store."""

import csv
from dataclasses import asdict
import os
from pathlib import Path
import tempfile

from .database import JobDatabase
from .models import JobRecord

CSV_FIELDS = (
    "id", "title", "company", "location", "url", "source", "source_job_id",
    "description", "created_at",
)


def record_to_dict(record: JobRecord) -> dict[str, str | int]:
    return {"id": record.id, **asdict(record.job), "created_at": record.created_at}


def export_jobs(database: JobDatabase, output_path: str | Path) -> int:
    output = Path(output_path)
    if output.resolve() == database.path.resolve():
        raise ValueError("CSV output must not overwrite the SQLite database")
    records = database.list_jobs()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=output.parent,
            prefix=f".{output.name}.", suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(record_to_dict(record) for record in records)
        os.replace(temporary_path, output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return len(records)
