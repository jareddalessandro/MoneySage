"""Sharing a household or a company by invite: inviting, accepting, roles, removing and leaving."""

import pytest

from app.config import settings


@pytest.fixture
def accounts_on(monkeypatch):
    """Sharing is only offered with sign-in. Who's asking still comes from the `people` fixture."""
    monkeypatch.setattr(settings, "auth_mode", "google")


def invite(client, email, role="editor", company_id=None):
    path = f"/api/companies/{company_id}/access/invites" if company_id else "/api/household/access/invites"
    return client.post(path, json={"email": email, "role": role})


def accept_only_invite(client) -> dict:
    invites = client.get("/api/invites").json()
    assert len(invites) == 1
    response = client.post(f"/api/invites/{invites[0]['id']}/accept")
    assert response.status_code == 200, response.text
    return response.json()


def test_share_the_household_with_a_spouse(client, people, accounts_on):
    owner = people.local
    with_owner = {"X-Household-Id": str(owner["household_id"])}
    client.post("/api/credit-cards", json={"name": "Family card"})
    cid = client.post("/api/companies", json={"name": "Side business"}).json()["id"]
    spouse = people.add("spouse@example.com")

    created = invite(client, "Spouse@Example.com ")
    assert created.status_code == 201 and created.json()["email"] == "spouse@example.com"
    listed = client.get("/api/household/access").json()
    assert [p["role"] for p in listed["people"]] == ["owner"] and len(listed["invites"]) == 1

    people.act_as(spouse)
    invites = client.get("/api/invites").json()
    assert invites[0]["kind"] == "household" and invites[0]["role"] == "editor"
    assert invites[0]["name"] == "You's household"  # the offline user is called "You"
    assert accept_only_invite(client) == {"kind": "household", "id": owner["household_id"]}

    me = client.get("/api/me").json()
    assert [h["role"] for h in me["households"]] == ["owner", "editor"]
    assert me["households"][1]["owner_name"] == "You"
    # Their own household is still the default; the header opens the shared one, where they can edit.
    assert client.get("/api/credit-cards").json() == []
    assert [c["name"] for c in client.get("/api/credit-cards", headers=with_owner).json()] == ["Family card"]
    assert client.post("/api/credit-cards", json={"name": "Spouse's card"}, headers=with_owner).status_code == 201
    # Editors can't share, and the household never brings its companies along.
    assert invite(client, "friend@example.com").status_code == 201  # their own household: fine
    assert client.post(
        "/api/household/access/invites", json={"email": "friend@example.com", "role": "viewer"}, headers=with_owner
    ).status_code == 403
    assert client.get("/api/companies").json() == []
    assert client.get(f"/api/companies/{cid}").status_code == 404

    # The owner sees them as a member, and the invite is gone.
    people.act_as(None)
    listed = client.get("/api/household/access").json()
    assert [(p["email"], p["role"]) for p in listed["people"]] == [("local@moneysage.invalid", "owner"), ("spouse@example.com", "editor")]
    assert listed["invites"] == []


def test_share_one_company_with_a_partner(client, people, accounts_on):
    client.post("/api/credit-cards", json={"name": "Family card"})
    shared = client.post("/api/companies", json={"name": "Apps LLC"}).json()["id"]
    client.post("/api/companies", json={"name": "Consulting"})
    partner = people.add("partner@example.com")
    assert invite(client, "partner@example.com", company_id=shared).status_code == 201

    people.act_as(partner)
    assert accept_only_invite(client) == {"kind": "company", "id": shared}
    assert [(c["name"], c["role"]) for c in client.get("/api/companies").json()] == [("Apps LLC", "editor")]
    entry = {"kind": "income", "date": "2026-03-01", "description": "Sale", "amount": 100}
    assert client.post(f"/api/companies/{shared}/entries", json=entry).status_code == 201
    # Nothing of the household, no resharing, no deleting.
    assert client.get("/api/credit-cards").json() == []
    assert invite(client, "someone@example.com", company_id=shared).status_code == 403
    assert client.delete(f"/api/companies/{shared}").status_code == 403
    people_listed = client.get(f"/api/companies/{shared}/access").json()
    assert people_listed["can_manage"] is False and people_listed["invites"] == []
    assert len(people_listed["people"]) == 2


def test_viewers_and_role_changes(client, people, accounts_on):
    cid = client.post("/api/companies", json={"name": "Acme"}).json()["id"]
    viewer = people.add("viewer@example.com")
    invite(client, "viewer@example.com", role="viewer", company_id=cid)
    people.act_as(viewer)
    accept_only_invite(client)
    entry = {"kind": "income", "date": "2026-03-01", "description": "Sale", "amount": 100}
    assert client.get(f"/api/companies/{cid}").status_code == 200
    assert client.post(f"/api/companies/{cid}/entries", json=entry).status_code == 403

    people.act_as(None)
    response = client.patch(f"/api/companies/{cid}/access/{viewer['id']}", json={"role": "editor"})
    assert response.status_code == 200
    people.act_as(viewer)
    assert client.post(f"/api/companies/{cid}/entries", json=entry).status_code == 201

    # The owner's own access can't be changed or removed.
    people.act_as(None)
    me = people.local["id"]
    assert client.patch(f"/api/companies/{cid}/access/{me}", json={"role": "viewer"}).status_code == 400
    assert client.delete(f"/api/companies/{cid}/access/{me}").status_code == 400

    assert client.delete(f"/api/companies/{cid}/access/{viewer['id']}").status_code == 204
    people.act_as(viewer)
    assert client.get(f"/api/companies/{cid}").status_code == 404


def test_leaving(client, people, accounts_on):
    owner = people.local
    member = people.add("member@example.com")
    invite(client, "member@example.com", role="viewer")
    people.act_as(member)
    accept_only_invite(client)
    # A viewer can leave even though they can't change anything else.
    assert client.delete(f"/api/me/households/{owner['household_id']}").status_code == 204
    assert len(client.get("/api/me").json()["households"]) == 1
    # Nobody can leave a household they own.
    assert client.delete(f"/api/me/households/{member['household_id']}").status_code == 400
    assert client.delete(f"/api/me/households/{owner['household_id']}").status_code == 404


def test_invites_are_only_for_their_address(client, people, accounts_on):
    invite(client, "spouse@example.com")
    stranger = people.add("stranger@example.com")
    invite_id = client.get("/api/household/access").json()["invites"][0]["id"]
    people.act_as(stranger)
    assert client.get("/api/invites").json() == []
    assert client.post(f"/api/invites/{invite_id}/accept").status_code == 404
    assert client.post(f"/api/invites/{invite_id}/decline").status_code == 404


def test_declining_and_revoking(client, people, accounts_on):
    spouse = people.add("spouse@example.com")
    invite(client, "spouse@example.com")
    people.act_as(spouse)
    invite_id = client.get("/api/invites").json()[0]["id"]
    assert client.post(f"/api/invites/{invite_id}/decline").status_code == 204
    assert client.get("/api/invites").json() == []
    assert len(client.get("/api/me").json()["households"]) == 1

    people.act_as(None)
    invite_id = invite(client, "spouse@example.com").json()["id"]
    assert client.delete(f"/api/household/access/invites/{invite_id}").status_code == 204
    people.act_as(spouse)
    assert client.get("/api/invites").json() == []


def test_invite_checks(client, people, accounts_on):
    assert invite(client, "not an email").status_code == 422
    assert client.post("/api/household/access/invites", json={"email": "a@b.co", "role": "owner"}).status_code == 422
    assert invite(client, "local@moneysage.invalid").status_code == 400  # yourself
    assert invite(client, "spouse@example.com").status_code == 201
    assert invite(client, "spouse@example.com", role="viewer").status_code == 409
    spouse = people.add("spouse@example.com")
    people.act_as(spouse)
    accept_only_invite(client)
    people.act_as(None)
    assert invite(client, "spouse@example.com").status_code == 409  # already has access


def test_deleting_a_company_drops_its_invites(client, people, accounts_on):
    cid = client.post("/api/companies", json={"name": "Acme"}).json()["id"]
    invite(client, "partner@example.com", company_id=cid)
    assert client.delete(f"/api/companies/{cid}").status_code == 204
    people.act_as(people.add("partner@example.com"))
    assert client.get("/api/invites").json() == []


def test_sharing_needs_sign_in(client, people):
    assert invite(client, "spouse@example.com").status_code == 400
