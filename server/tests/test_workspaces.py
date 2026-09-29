"""Workspace membership and the role boundaries that depend on it.

The cases that matter here are the negative ones. A collaboration feature that
works when everyone is an owner is not a collaboration feature - the tests that
earn their place are the ones asserting that a viewer cannot write and that a
non-member cannot tell whether a workspace exists at all.
"""

from tests.conftest import register


def make_workspace(client, headers, name="Team"):
    response = client.post("/workspaces", json={"name": name}, headers=headers)
    assert response.status_code == 201, response.text

    return response.json()


def test_creator_becomes_owner(client, auth_headers):
    workspace = make_workspace(client, auth_headers)

    assert workspace["role"] == "owner"
    assert workspace["member_count"] == 1


def test_invite_and_list_members(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    register(client, email="teammate@example.com")

    response = client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"email": "teammate@example.com", "role": "editor"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert response.json()["role"] == "editor"

    members = client.get(
        f"/workspaces/{workspace['id']}/members", headers=auth_headers
    ).json()

    assert {m["email"] for m in members} == {
        "dev@example.com",
        "teammate@example.com",
    }


def test_inviting_an_unknown_email_is_404(client, auth_headers):
    workspace = make_workspace(client, auth_headers)

    response = client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"email": "nobody@example.com"},
        headers=auth_headers,
    )

    assert response.status_code == 404


def test_duplicate_invite_is_409(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    register(client, email="teammate@example.com")

    body = {"email": "teammate@example.com", "role": "editor"}
    client.post(
        f"/workspaces/{workspace['id']}/members", json=body, headers=auth_headers
    )
    second = client.post(
        f"/workspaces/{workspace['id']}/members", json=body, headers=auth_headers
    )

    assert second.status_code == 409


def test_non_member_sees_404_not_403(client, auth_headers):
    """A stranger must not be able to distinguish "exists" from "does not"."""
    workspace = make_workspace(client, auth_headers)
    outsider = register(client, email="outsider@example.com")

    assert client.get(
        f"/workspaces/{workspace['id']}", headers=outsider
    ).status_code == 404

    # The same code for an id that genuinely does not exist - which is the
    # entire point of choosing 404 over 403 here.
    assert client.get("/workspaces/999999", headers=outsider).status_code == 404


def test_last_owner_cannot_be_demoted(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    me = client.get("/auth/me", headers=auth_headers).json()

    response = client.patch(
        f"/workspaces/{workspace['id']}/members/{me['id']}",
        json={"role": "viewer"},
        headers=auth_headers,
    )

    assert response.status_code == 409


def test_last_owner_cannot_leave(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    me = client.get("/auth/me", headers=auth_headers).json()

    response = client.delete(
        f"/workspaces/{workspace['id']}/members/{me['id']}", headers=auth_headers
    )

    assert response.status_code == 409


def test_member_can_leave_without_being_owner(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    teammate = register(client, email="teammate@example.com")
    client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"email": "teammate@example.com", "role": "editor"},
        headers=auth_headers,
    )
    teammate_id = client.get("/auth/me", headers=teammate).json()["id"]

    response = client.delete(
        f"/workspaces/{workspace['id']}/members/{teammate_id}", headers=teammate
    )

    assert response.status_code == 200
    assert client.get(
        f"/workspaces/{workspace['id']}", headers=teammate
    ).status_code == 404


def test_shared_project_is_visible_to_members(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    teammate = register(client, email="teammate@example.com")
    client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"email": "teammate@example.com", "role": "editor"},
        headers=auth_headers,
    )

    project = client.post(
        "/projects",
        json={"name": "Shared", "workspace_id": workspace["id"]},
        headers=auth_headers,
    ).json()

    listed = client.get("/projects", headers=teammate).json()

    assert [p["id"] for p in listed] == [project["id"]]


def test_viewer_can_read_but_not_write(client, auth_headers):
    """The role boundary that makes 'viewer' mean anything."""
    workspace = make_workspace(client, auth_headers)
    viewer = register(client, email="viewer@example.com")
    client.post(
        f"/workspaces/{workspace['id']}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
        headers=auth_headers,
    )

    project = client.post(
        "/projects",
        json={"name": "Shared", "workspace_id": workspace["id"]},
        headers=auth_headers,
    ).json()
    file_out = client.post(
        f"/projects/{project['id']}/files",
        json={"name": "main.py", "content": "print('hi')"},
        headers=auth_headers,
    ).json()

    # Reading is allowed.
    assert client.get(
        f"/projects/{project['id']}/files", headers=viewer
    ).status_code == 200
    assert client.get(
        f"/projects/file/{file_out['id']}", headers=viewer
    ).status_code == 200

    # Writing is not - and says so, rather than pretending the file is gone.
    assert client.put(
        f"/projects/file/{file_out['id']}",
        json={"content": "malicious()"},
        headers=viewer,
    ).status_code == 403
    assert client.delete(
        f"/projects/file/{file_out['id']}", headers=viewer
    ).status_code == 403
    assert client.post(
        f"/projects/{project['id']}/files",
        json={"name": "new.py", "content": ""},
        headers=viewer,
    ).status_code == 403


def test_outsider_cannot_reach_a_workspace_project(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    outsider = register(client, email="outsider@example.com")

    project = client.post(
        "/projects",
        json={"name": "Shared", "workspace_id": workspace["id"]},
        headers=auth_headers,
    ).json()

    assert client.get(
        f"/projects/{project['id']}", headers=outsider
    ).status_code == 404


def test_creating_a_project_in_someone_elses_workspace_is_404(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    outsider = register(client, email="outsider@example.com")

    response = client.post(
        "/projects",
        json={"name": "Sneaky", "workspace_id": workspace["id"]},
        headers=outsider,
    )

    assert response.status_code == 404


def test_deleting_a_workspace_keeps_its_projects(client, auth_headers):
    workspace = make_workspace(client, auth_headers)
    project = client.post(
        "/projects",
        json={"name": "Shared", "workspace_id": workspace["id"]},
        headers=auth_headers,
    ).json()

    assert client.delete(
        f"/workspaces/{workspace['id']}", headers=auth_headers
    ).status_code == 200

    # The project survives and returns to its owner, rather than being
    # destroyed along with the workspace it was shared in.
    still_there = client.get(f"/projects/{project['id']}", headers=auth_headers)

    assert still_there.status_code == 200
    assert still_there.json()["workspace_id"] is None
