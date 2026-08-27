"""Element-pair generality: campaigns take [A, B]; engines validate support."""

import asyncio

from gibbs.agent.loop import runner_registry


async def test_elements_validation(client, monkeypatch):
    r = await client.post("/campaigns", json={"name": "x", "problem_type": "dft_v3", "elements": ["Cu"]})
    assert r.status_code == 422
    r = await client.post("/campaigns", json={"name": "x", "problem_type": "dft_v3", "elements": ["Cu", "Xx"]})
    assert r.status_code == 422
    # EMT cannot do Fe.
    r = await client.post("/campaigns", json={"name": "x", "problem_type": "dft_v3", "dft_engine": "emt", "elements": ["Fe", "Al"]})
    assert r.status_code == 400 and "EMT" in r.json()["detail"]
    # Espresso: missing pseudopotential -> actionable error naming the fetch command.
    monkeypatch.setenv("ALLOYLAB_PSEUDO_DIR", "/nonexistent")
    from gibbs.config import get_settings
    get_settings.cache_clear()
    r = await client.post("/campaigns", json={"name": "x", "problem_type": "dft_v3", "dft_engine": "espresso", "elements": ["Cu", "Au"]})
    get_settings.cache_clear()
    assert r.status_code == 400 and "gibbs.pseudos" in r.json()["detail"]


async def test_cu_au_emt_campaign(client):
    r = await client.post(
        "/campaigns",
        json={"name": "Cu-Au via EMT", "problem_type": "dft_v3", "dft_engine": "emt",
              "elements": ["cu", "au"], "strategy": "uncertainty", "simulation_budget": 8},
    )
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["elements"] == ["Cu", "Au"] and "Cu-Au" in c["objective"]
    cid = c["id"]
    await client.post(f"/campaigns/{cid}/start")
    await asyncio.wait_for(runner_registry.wait(cid), timeout=180)
    assert (await client.get(f"/campaigns/{cid}")).json()["status"] == "COMPLETED"

    structures = (await client.get(f"/campaigns/{cid}/structures")).json()
    assert all(set(s["atomic_numbers"]) <= {29, 79} for s in structures)
    assert any(s["chemical_formula"] == "Au" for s in structures)
    calcs = (await client.get(f"/campaigns/{cid}/calculations")).json()
    pure = {c["input_parameters"]["structure_label"]: c["output"] for c in calcs
            if c["input_parameters"]["composition"] in (0.0, 1.0)}
    a_opt = sorted(o["optimal_lattice_constant"] for o in pure.values())
    # EMT relaxes pure Cu and Au to their own lattice constants from the Cu parent lattice.
    assert abs(a_opt[0] - 3.61) < 0.12 and abs(a_opt[1] - 4.08) < 0.12
    events = (await client.get(f"/campaigns/{cid}/agent-events")).json()
    assert any("Cu-Au" in (e["action"] or "") for e in events)


async def test_hidden_problems_accept_elements(client):
    r = await client.post("/campaigns", json={"name": "x", "problem_type": "fcc_v2", "elements": ["Pd", "Pt"], "strategy": "grid"})
    assert r.status_code == 201 and r.json()["elements"] == ["Pd", "Pt"]
    r = await client.post("/campaigns", json={"name": "x", "problem_type": "phase_v2", "elements": ["Ag", "Au"], "strategy": "grid"})
    assert r.status_code == 201 and "Ag-Au" in r.json()["objective"]


async def test_element_catalog_endpoint(client):
    r = await client.get("/campaigns/elements")
    assert r.status_code == 200
    catalog = {e["symbol"]: e for e in r.json()}
    assert {"Cu", "Au", "Ni", "Al", "Fe", "Pt"} <= set(catalog)
    assert catalog["Cu"]["fcc_native"] and catalog["Cu"]["engines"]["emt"]
    assert not catalog["Fe"]["fcc_native"] and "hypothetical FCC" in catalog["Fe"]["note"]
    assert not catalog["Fe"]["engines"]["emt"]
    assert catalog["Au"]["a_fcc"] == 4.08
    # Espresso support reflects the pseudopotentials actually on disk.
    assert catalog["Ni"]["engines"]["espresso"] is True
    assert "Xe" not in catalog


async def test_off_catalog_element_rejected(client):
    r = await client.post("/campaigns", json={"name": "x", "problem_type": "fcc_v2", "elements": ["Xe", "Kr"]})
    assert r.status_code == 422 and "catalog" in r.text


async def test_report_flags_non_fcc_element(client):
    r = await client.post(
        "/campaigns",
        json={"name": "FeNi", "problem_type": "fcc_v2", "elements": ["Fe", "Ni"], "strategy": "grid", "simulation_budget": 4},
    )
    cid = r.json()["id"]
    report = (await client.get(f"/campaigns/{cid}/report")).json()
    assert any("hypothetical FCC" in l and "BCC" in l for l in report["limitations"])
