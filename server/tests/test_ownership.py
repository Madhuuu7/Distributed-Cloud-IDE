"""Verifies one user cannot see or touch another user's projects and files."""

from tests.conftest import register


def make_project_with_file(client, headers, project_name="Demo", file_name="main.py"):
    project = client.post("/projects", json={"name": project_name}, headers=headers)
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]

    created = client.post(
        f"/projects/{project_id}/files",
        json={"name": file_name, "content": "print('hi')"},
        headers=headers,
    )
    assert created.status_code == 201, created.text

    return project_id, created.json()["id"]


def test_project_owner_is_the_caller_not_a_hardcoded_id(client, auth_headers):
    me = client.get("/auth/me", headers=auth_headers).json()
    project = client.post("/projects", json={"name": "Mine"}, headers=auth_headers)

    assert project.json()["owner_id"] == me["id"]


def test_list_projects_only_returns_own_projects(client):
    alice = register(client, email="alice@example.com")
    bob = register(client, email="bob@example.com")

    client.post("/projects", json={"name": "Alice Project"}, headers=alice)
    client.post("/projects", json={"name": "Bob Project"}, headers=bob)

    alice_projects = client.get("/projects", headers=alice).json()
    bob_projects = client.get("/projects", headers=bob).json()

    assert [p["name"] for p in alice_projects] == ["Alice Project"]
    assert [p["name"] for p in bob_projects] == ["Bob Project"]


def test_cannot_read_another_users_project(client):
    alice = register(client, email="alice@example.com")
    bob = register(client, email="bob@example.com")

    project_id, _ = make_project_with_file(client, alice)

    assert client.get(f"/projects/{project_id}", headers=bob).status_code == 404
    assert client.get(f"/projects/{project_id}/files", headers=bob).status_code == 404
    assert client.delete(f"/projects/{project_id}", headers=bob).status_code == 404


def test_cannot_read_or_overwrite_another_users_file(client):
    alice = register(client, email="alice@example.com")
    bob = register(client, email="bob@example.com")

    _, file_id = make_project_with_file(client, alice)

    assert client.get(f"/projects/file/{file_id}", headers=bob).status_code == 404

    overwrite = client.put(
        f"/projects/file/{file_id}",
        json={"content": "pwned"},
        headers=bob,
    )
    assert overwrite.status_code == 404

    assert client.delete(f"/projects/file/{file_id}", headers=bob).status_code == 404

    # Alice's content is untouched.
    still_mine = client.get(f"/projects/file/{file_id}", headers=alice).json()
    assert still_mine["content"] == "print('hi')"


def test_cannot_create_a_file_in_another_users_project(client):
    alice = register(client, email="alice@example.com")
    bob = register(client, email="bob@example.com")

    project_id, _ = make_project_with_file(client, alice)

    response = client.post(
        f"/projects/{project_id}/files",
        json={"name": "sneaky.py", "content": ""},
        headers=bob,
    )
    assert response.status_code == 404


def test_file_language_is_detected_from_extension(client, auth_headers):
    project_id, _ = make_project_with_file(client, auth_headers, file_name="script.py")
    files = client.get(f"/projects/{project_id}/files", headers=auth_headers).json()

    assert files[0]["language"] == "python"


def test_duplicate_file_name_in_project_is_rejected(client, auth_headers):
    project_id, _ = make_project_with_file(client, auth_headers, file_name="main.py")

    response = client.post(
        f"/projects/{project_id}/files",
        json={"name": "main.py"},
        headers=auth_headers,
    )
    assert response.status_code == 409


def test_deleting_a_project_removes_its_files(client, auth_headers):
    project_id, file_id = make_project_with_file(client, auth_headers)

    assert client.delete(f"/projects/{project_id}", headers=auth_headers).status_code == 200
    assert client.get(f"/projects/file/{file_id}", headers=auth_headers).status_code == 404
