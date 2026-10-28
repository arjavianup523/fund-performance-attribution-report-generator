import pytest

from src.remediation import (
    create_issue,
    get_audit_events,
    list_issues,
    update_issue,
)


def test_create_issue_persists_required_fields(tmp_path):
    db = tmp_path / "test.db"

    issue_id = create_issue(
        "DQ-001",
        "Missing benchmark values",
        description="Benchmark values are missing for a reporting period.",
        severity="HIGH",
        owner="Reporting Team",
        db_path=db,
    )

    issue = list_issues(db_path=db)[0]
    assert issue["issue_id"] == issue_id
    assert issue["issue_key"] == "DQ-001"
    assert issue["status"] == "OPEN"
    assert issue["severity"] == "HIGH"
    assert issue["owner"] == "Reporting Team"


def test_duplicate_issue_key_is_rejected(tmp_path):
    db = tmp_path / "test.db"
    create_issue("DQ-002", "First issue", db_path=db)

    with pytest.raises(Exception):
        create_issue("DQ-002", "Duplicate issue", db_path=db)


def test_status_update_and_assignment_are_audited(tmp_path):
    db = tmp_path / "test.db"
    create_issue("DQ-003", "Price mismatch", db_path=db)

    update_issue(
        "DQ-003",
        status="IN_PROGRESS",
        owner="Data Operations",
        actor="analyst",
        details="Investigation started",
        db_path=db,
    )

    issue = list_issues(db_path=db)[0]
    events = get_audit_events("DQ-003", db_path=db)

    assert issue["status"] == "IN_PROGRESS"
    assert issue["owner"] == "Data Operations"
    assert len(events) == 2
    assert events[-1]["actor"] == "analyst"
    assert events[-1]["old_status"] == "OPEN"
    assert events[-1]["new_status"] == "IN_PROGRESS"


def test_resolution_requires_explanation(tmp_path):
    db = tmp_path / "test.db"
    create_issue("DQ-004", "Unexplained return gap", db_path=db)

    with pytest.raises(ValueError, match="resolution is required"):
        update_issue(
            "DQ-004",
            status="RESOLVED",
            actor="analyst",
            db_path=db,
        )


def test_resolved_issue_keeps_resolution_and_history(tmp_path):
    db = tmp_path / "test.db"
    create_issue("DQ-005", "Duplicate price record", db_path=db)

    update_issue(
        "DQ-005",
        status="RESOLVED",
        resolution="Duplicate record investigated and corrected in the source.",
        actor="reviewer",
        db_path=db,
    )

    issue = list_issues(status="RESOLVED", db_path=db)[0]
    events = get_audit_events("DQ-005", db_path=db)

    assert issue["resolution"].startswith("Duplicate record investigated")
    assert events[-1]["new_status"] == "RESOLVED"
    assert events[-1]["actor"] == "reviewer"


def test_invalid_status_is_rejected(tmp_path):
    db = tmp_path / "test.db"
    create_issue("DQ-006", "Test issue", db_path=db)

    with pytest.raises(ValueError, match="Invalid status"):
        update_issue(
            "DQ-006",
            status="DONE",
            actor="analyst",
            db_path=db,
        )


def test_status_filter_returns_only_matching_issues(tmp_path):
    db = tmp_path / "test.db"
    create_issue("DQ-007", "Open issue", db_path=db)
    create_issue("DQ-008", "Another issue", db_path=db)

    update_issue(
        "DQ-008",
        status="BLOCKED",
        actor="analyst",
        db_path=db,
    )

    assert len(list_issues(status="OPEN", db_path=db)) == 1
    assert list_issues(status="BLOCKED", db_path=db)[0]["issue_key"] == "DQ-008"
