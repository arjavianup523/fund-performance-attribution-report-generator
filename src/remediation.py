from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "outputs" / "remediation_workflow.db"

VALID_STATUSES = {
    "OPEN",
    "IN_PROGRESS",
    "BLOCKED",
    "RESOLVED",
    "CLOSED",
}
VALID_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(db_path: str | Path = DEFAULT_DB) -> None:
    """Create persistent remediation and append-only event tables."""
    with _connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS remediation_issues (
                issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_key TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                severity TEXT NOT NULL
                    CHECK (severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
                status TEXT NOT NULL DEFAULT 'OPEN'
                    CHECK (status IN (
                        'OPEN','IN_PROGRESS','BLOCKED','RESOLVED','CLOSED'
                    )),
                owner TEXT,
                resolution TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS remediation_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                issue_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                actor TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                event_time TEXT NOT NULL,
                FOREIGN KEY (issue_id)
                    REFERENCES remediation_issues(issue_id)
            );

            CREATE INDEX IF NOT EXISTS idx_issues_status
                ON remediation_issues(status);

            CREATE INDEX IF NOT EXISTS idx_events_issue
                ON remediation_events(issue_id, event_id);
            """
        )


def create_issue(
    issue_key: str,
    title: str,
    description: str = "",
    severity: str = "MEDIUM",
    owner: str | None = None,
    actor: str = "system",
    db_path: str | Path = DEFAULT_DB,
) -> int:
    """Create an issue once; reject duplicate issue keys."""
    initialize_database(db_path)

    issue_key = issue_key.strip()
    title = title.strip()
    severity = severity.upper()

    if not issue_key or not title:
        raise ValueError("issue_key and title are required.")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {severity}")

    timestamp = _now()

    with _connect(db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO remediation_issues
                (issue_key, title, description, severity, owner,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue_key, title, description, severity, owner,
                timestamp, timestamp,
            ),
        )
        issue_id = int(cursor.lastrowid)

        connection.execute(
            """
            INSERT INTO remediation_events
                (issue_id, event_type, old_status, new_status,
                 actor, details, event_time)
            VALUES (?, 'CREATED', NULL, 'OPEN', ?, ?, ?)
            """,
            (issue_id, actor, f"Issue created: {issue_key}", timestamp),
        )

    return issue_id


def update_issue(
    issue_key: str,
    *,
    status: str | None = None,
    owner: str | None = None,
    resolution: str | None = None,
    details: str = "",
    actor: str,
    db_path: str | Path = DEFAULT_DB,
) -> None:
    """Update an issue and append an audit event in one transaction."""
    initialize_database(db_path)

    if not actor.strip():
        raise ValueError("actor is required.")

    if status is not None:
        status = status.upper()
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")

    if status in {"RESOLVED", "CLOSED"} and not (
        resolution and resolution.strip()
    ):
        raise ValueError("A resolution is required to resolve or close an issue.")

    timestamp = _now()

    with _connect(db_path) as connection:
        issue = connection.execute(
            "SELECT * FROM remediation_issues WHERE issue_key = ?",
            (issue_key,),
        ).fetchone()

        if issue is None:
            raise KeyError(f"Issue not found: {issue_key}")

        old_status = issue["status"]
        new_status = status if status is not None else old_status
        new_owner = owner if owner is not None else issue["owner"]
        new_resolution = (
            resolution if resolution is not None else issue["resolution"]
        )

        if new_status in {"RESOLVED", "CLOSED"} and not (
            new_resolution and new_resolution.strip()
        ):
            raise ValueError("A resolution is required to resolve or close an issue.")

        connection.execute(
            """
            UPDATE remediation_issues
            SET status = ?, owner = ?, resolution = ?, updated_at = ?
            WHERE issue_key = ?
            """,
            (new_status, new_owner, new_resolution, timestamp, issue_key),
        )

        changed_fields = []
        if new_status != old_status:
            changed_fields.append(f"status: {old_status} -> {new_status}")
        if new_owner != issue["owner"]:
            changed_fields.append(f"owner: {issue['owner']} -> {new_owner}")
        if new_resolution != issue["resolution"]:
            changed_fields.append("resolution updated")
        if details.strip():
            changed_fields.append(details.strip())

        event_type = "STATUS_CHANGED" if new_status != old_status else "UPDATED"

        connection.execute(
            """
            INSERT INTO remediation_events
                (issue_id, event_type, old_status, new_status,
                 actor, details, event_time)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                issue["issue_id"], event_type, old_status, new_status,
                actor, "; ".join(changed_fields) or "Issue reviewed",
                timestamp,
            ),
        )


def list_issues(
    status: str | None = None,
    db_path: str | Path = DEFAULT_DB,
) -> list[dict[str, Any]]:
    """Return issues in most-recently-updated order."""
    initialize_database(db_path)

    with _connect(db_path) as connection:
        if status is None:
            rows = connection.execute(
                """
                SELECT * FROM remediation_issues
                ORDER BY updated_at DESC, issue_id DESC
                """
            ).fetchall()
        else:
            normalized = status.upper()
            if normalized not in VALID_STATUSES:
                raise ValueError(f"Invalid status: {status}")
            rows = connection.execute(
                """
                SELECT * FROM remediation_issues
                WHERE status = ?
                ORDER BY updated_at DESC, issue_id DESC
                """,
                (normalized,),
            ).fetchall()

    return [dict(row) for row in rows]


def get_audit_events(
    issue_key: str | None = None,
    db_path: str | Path = DEFAULT_DB,
) -> list[dict[str, Any]]:
    """Read audit events; no update/delete API is provided."""
    initialize_database(db_path)

    query = """
        SELECT e.event_id, i.issue_key, e.event_type, e.old_status,
               e.new_status, e.actor, e.details, e.event_time
        FROM remediation_events e
        JOIN remediation_issues i ON i.issue_id = e.issue_id
    """
    params: tuple[Any, ...] = ()

    if issue_key is not None:
        query += " WHERE i.issue_key = ?"
        params = (issue_key,)

    query += " ORDER BY e.event_id"

    with _connect(db_path) as connection:
        rows = connection.execute(query, params).fetchall()

    return [dict(row) for row in rows]
