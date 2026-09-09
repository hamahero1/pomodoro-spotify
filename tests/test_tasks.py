from .conftest import api_headers


def test_create_and_list_task(client):
    resp = client.post("/api/tasks", json={"title": "Write report"}, headers=api_headers())
    assert resp.status_code == 201
    task = resp.get_json()
    assert task["title"] == "Write report"
    assert task["status"] == "not_started"

    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    tasks = resp.get_json()
    assert len(tasks) == 1
    assert tasks[0]["id"] == task["id"]


def test_create_task_requires_title(client):
    resp = client.post("/api/tasks", json={"title": "  "}, headers=api_headers())
    assert resp.status_code == 400


def test_start_stop_tracks_time(client):
    task = client.post("/api/tasks", json={"title": "Focus block"}, headers=api_headers()).get_json()

    resp = client.post(f"/api/tasks/{task['id']}/start", headers=api_headers())
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "in_progress"

    resp = client.post(f"/api/tasks/{task['id']}/stop", headers=api_headers())
    assert resp.status_code == 200
    stopped = resp.get_json()
    assert stopped["status"] == "not_started"
    assert stopped["logged_seconds"] >= 0


def test_subtask_time_rolls_up_to_parent(client):
    parent = client.post("/api/tasks", json={"title": "Project"}, headers=api_headers()).get_json()
    sub = client.post(
        "/api/tasks",
        json={"title": "Subtask", "parent_task_id": parent["id"]},
        headers=api_headers(),
    ).get_json()
    assert sub["parent_task_id"] == parent["id"]

    client.post(f"/api/tasks/{sub['id']}/start", headers=api_headers())
    client.post(f"/api/tasks/{sub['id']}/stop", headers=api_headers())

    resp = client.get(f"/api/tasks/{parent['id']}")
    data = resp.get_json()
    assert len(data["subtasks"]) == 1
    assert data["total_logged_seconds"] == data["subtasks"][0]["logged_seconds"]


def test_complete_task(client):
    task = client.post("/api/tasks", json={"title": "Ship it"}, headers=api_headers()).get_json()
    resp = client.post(f"/api/tasks/{task['id']}/complete", headers=api_headers())
    data = resp.get_json()
    assert data["status"] == "done"
    assert data["completed_at"] is not None


def test_delete_task(client):
    task = client.post("/api/tasks", json={"title": "Temp"}, headers=api_headers()).get_json()
    resp = client.delete(f"/api/tasks/{task['id']}", headers=api_headers())
    assert resp.status_code == 200
    assert client.get(f"/api/tasks/{task['id']}").status_code == 404


def test_mutation_without_fetch_header_is_blocked(client):
    # No X-Requested-With header => same-origin check in app.py should reject it.
    resp = client.post("/api/tasks", json={"title": "Should fail"})
    assert resp.status_code == 403
