"""API-level tests for projects and repository bindings (ENG-012)."""

import uuid as uuidlib

from sqlalchemy import text


def create_project(client, name="demo", **extra):
    payload = {"name": name, "description": "demo project", **extra}
    response = client.post("/projects", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_project_returns_persisted_fields(client):
    body = create_project(client)
    assert body["name"] == "demo"
    assert body["status"] == "active"
    assert uuidlib.UUID(body["id"])
    assert body["created_at"] and body["updated_at"]


def test_create_project_name_is_trimmed(client):
    body = create_project(client, name="  spaced  ")
    assert body["name"] == "spaced"


def test_create_project_blank_name_rejected(client):
    response = client.post("/projects", json={"name": "   "})
    assert response.status_code == 422


def test_duplicate_project_name_conflicts(client):
    create_project(client, name="taken")
    response = client.post("/projects", json={"name": "taken"})
    assert response.status_code == 409


def test_list_and_get_project(client):
    created = create_project(client, name="first")
    create_project(client, name="second")

    listing = client.get("/projects")
    assert listing.status_code == 200
    names = [p["name"] for p in listing.json()]
    assert names == ["first", "second"]

    fetched = client.get(f"/projects/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]


def test_get_missing_project_is_404(client):
    response = client.get(f"/projects/{uuidlib.uuid4()}")
    assert response.status_code == 404


def bind(client, project_id, owner="acme", name="demo-target", **extra):
    payload = {"owner": owner, "name": name, **extra}
    return client.post(f"/projects/{project_id}/repository-binding", json=payload)


def test_bind_repository_sets_full_name_and_defaults(client):
    project = create_project(client, name="bound")
    response = bind(client, project["id"], base_sha="abc1234")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["full_name"] == "acme/demo-target"
    assert body["provider"] == "github"
    assert body["default_branch"] == "main"
    assert body["status"] == "active"
    assert body["base_sha"] == "abc1234"


def test_bind_on_missing_project_is_404(client):
    response = bind(client, str(uuidlib.uuid4()))
    assert response.status_code == 404


def test_get_active_binding_when_none_is_404(client):
    project = create_project(client, name="unbound")
    response = client.get(f"/projects/{project['id']}/repository-binding")
    assert response.status_code == 404


def test_rebinding_keeps_history_and_swaps_active(client):
    project = create_project(client, name="rebind")
    first = bind(client, project["id"], owner="acme", name="old-repo").json()
    second = bind(client, project["id"], owner="acme", name="new-repo").json()

    active = client.get(f"/projects/{project['id']}/repository-binding")
    assert active.status_code == 200
    assert active.json()["id"] == second["id"]
    assert active.json()["full_name"] == "acme/new-repo"

    history = client.get(f"/projects/{project['id']}/repository-bindings")
    assert history.status_code == 200
    statuses = {row["full_name"]: row["status"] for row in history.json()}
    assert statuses == {"acme/new-repo": "active", "acme/old-repo": "disconnected"}
    assert second["id"] != first["id"]


def test_rebinding_same_repository_is_idempotent(client):
    project = create_project(client, name="stable")
    first = bind(client, project["id"]).json()
    second_response = bind(client, project["id"])
    assert second_response.status_code == 201
    assert second_response.json()["id"] == first["id"]


def test_status_is_stored_as_lowercase_value(session, client):
    """Storage contract: the DB holds enum VALUES ('active'), not names ('ACTIVE')."""
    bind_project = create_project(client, name="stored-values")
    bind(client, bind_project["id"])

    project_row = session.execute(
        text("SELECT status FROM projects WHERE name = 'stored-values'")
    ).one()
    binding_row = session.execute(
        text("SELECT status FROM repository_bindings")
    ).one()
    assert project_row[0] == "active"
    assert binding_row[0] == "active"
