def test_credit_card_crud(client):
    card = client.post("/api/credit-cards", json={
        "name": " Sapphire Preferred ",
        "issuer": "Chase",
        "payment_url": "chase.com/pay",
        "annual_fee": 95,
        "annual_fee_month": 3,
        "benefits": ["3x on dining", "  ", " 2x on travel "],
    })
    assert card.status_code == 201, card.text
    card = card.json()
    assert card["name"] == "Sapphire Preferred"
    assert card["payment_url"] == "https://chase.com/pay"  # scheme added so the link opens
    assert card["annual_fee"] == 95
    assert card["benefits"] == ["3x on dining", "2x on travel"]  # trimmed, blanks dropped

    updated = client.put(f"/api/credit-cards/{card['id']}", json={
        "name": "Sapphire Preferred", "annual_fee": 0, "benefits": [],
    }).json()
    assert updated["annual_fee"] == 0 and updated["issuer"] is None and updated["payment_url"] is None

    client.post("/api/credit-cards", json={"name": "Amex Gold", "annual_fee": 325})
    assert [c["name"] for c in client.get("/api/credit-cards").json()] == ["Amex Gold", "Sapphire Preferred"]

    assert client.delete(f"/api/credit-cards/{card['id']}").status_code == 204
    assert [c["name"] for c in client.get("/api/credit-cards").json()] == ["Amex Gold"]


def test_credit_card_validation(client):
    assert client.post("/api/credit-cards", json={"name": "A"}).status_code == 201
    assert client.post("/api/credit-cards", json={"name": "A"}).status_code == 409
    bad = [
        {"name": "B", "payment_url": "javascript:alert(1)"},  # only web links
        {"name": "B", "annual_fee": -1},
        {"name": "B", "annual_fee_month": 13},
        {"name": "  "},
    ]
    for body in bad:
        assert client.post("/api/credit-cards", json=body).status_code == 422, body
