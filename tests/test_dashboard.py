from .conftest import api_headers


def test_summary_reflects_completed_tasks(client):
    task = client.post("/api/tasks", json={"title": "Read book"}, headers=api_headers()).get_json()
    client.post(f"/api/tasks/{task['id']}/complete", headers=api_headers())

    resp = client.get("/api/dashboard/summary")
    data = resp.get_json()
    assert data["completed_count"] == 1
    assert data["completed_today"] == 1


def test_calendar_filters_tasks_by_date(client):
    client.post(
        "/api/tasks",
        json={"title": "Scheduled", "date": "2026-09-15"},
        headers=api_headers(),
    )
    client.post("/api/tasks", json={"title": "Unscheduled"}, headers=api_headers())

    resp = client.get("/api/dashboard/calendar?date=2026-09-15")
    data = resp.get_json()
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["title"] == "Scheduled"

    resp = client.get("/api/dashboard/calendar?date=2026-09-16")
    assert resp.get_json()["tasks"] == []


def test_log_timer_session_and_calendar(client):
    resp = client.post(
        "/api/timer/session",
        json={"kind": "pomodoro_work", "duration_seconds": 1500},
        headers=api_headers(),
    )
    assert resp.status_code == 201

    resp = client.get("/api/dashboard/summary")
    assert resp.get_json()["last_14_days"][-1]["total_seconds"] >= 1500


def test_log_timer_session_rejects_bad_kind(client):
    resp = client.post(
        "/api/timer/session",
        json={"kind": "not_a_real_kind", "duration_seconds": 60},
        headers=api_headers(),
    )
    assert resp.status_code == 400


def test_log_timer_session_rejects_huge_duration(client):
    resp = client.post(
        "/api/timer/session",
        json={"kind": "pomodoro_work", "duration_seconds": 999999},
        headers=api_headers(),
    )
    assert resp.status_code == 400
