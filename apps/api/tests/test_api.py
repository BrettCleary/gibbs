async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200


async def test_campaign_crud_and_validation(client):
    r = await client.post(
        "/campaigns",
        json={"name": "demo", "strategy": "grid", "simulation_budget": 6, "lattice_size": 8},
    )
    assert r.status_code == 201, r.text
    campaign = r.json()
    assert campaign["status"] == "CREATED"
    assert campaign["simulations_used"] == 0

    r = await client.get("/campaigns")
    assert [c["id"] for c in r.json()] == [campaign["id"]]

    r = await client.get(f"/campaigns/{campaign['id']}")
    assert r.json()["name"] == "demo"

    # invalid temperature range rejected
    r = await client.post(
        "/campaigns",
        json={"name": "bad", "temperature_min": 3.0, "temperature_max": 2.0},
    )
    assert r.status_code == 422

    r = await client.get("/campaigns/doesnotexist")
    assert r.status_code == 404


async def test_pause_requires_running(client):
    r = await client.post("/campaigns", json={"name": "x"})
    cid = r.json()["id"]
    r = await client.post(f"/campaigns/{cid}/pause")
    assert r.status_code == 409


async def test_agent_strategy_requires_key(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = await client.post("/campaigns", json={"name": "llm", "strategy": "agent"})
    cid = r.json()["id"]
    r = await client.post(f"/campaigns/{cid}/start")
    assert r.status_code == 400
    assert "OPENAI_API_KEY" in r.json()["detail"]
