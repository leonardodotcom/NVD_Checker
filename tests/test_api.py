import httpx
import respx

from app.sources.nvd import API_URL

from .fixtures import cve, page


def test_project_crud(client):
    assert client.get("/api/projects").json() == []
    p = client.post("/api/projects", json={"name": "Web stack"}).json()
    assert p["name"] == "Web stack" and p["keywords"] == []
    assert client.post("/api/projects", json={"name": "Web stack"}).status_code == 409

    k = client.post(f"/api/projects/{p['id']}/keywords", json={"term": "nginx", "exact_match": True}).json()
    assert client.post(f"/api/projects/{p['id']}/keywords", json={"term": "nginx"}).status_code == 409
    assert client.post(f"/api/projects/{p['id']}/keywords", json={"term": "   "}).status_code == 422

    got = client.get(f"/api/projects/{p['id']}").json()
    assert got["keywords"] == [{"id": k["id"], "term": "nginx", "exact_match": True}]

    assert client.put(f"/api/projects/{p['id']}", json={"name": "Infra"}).json()["name"] == "Infra"
    assert client.delete(f"/api/projects/{p['id']}/keywords/{k['id']}").status_code == 204
    assert client.delete(f"/api/projects/{p['id']}").status_code == 204
    assert client.get(f"/api/projects/{p['id']}").status_code == 404


def test_sources_listing(client):
    sources = {s["id"]: s for s in client.get("/api/sources").json()}
    assert sources["nvd"]["enabled"] is True
    assert sources["cnnvd"]["enabled"] is False and sources["cnnvd"]["requires_auth"] is True
    assert sources["cnvd"]["enabled"] is False


@respx.mock
def test_search_with_project_and_csv(client):
    respx.get(API_URL).mock(side_effect=lambda req: httpx.Response(
        200, json=page([cve("CVE-2026-1", desc=f"about {req.url.params['keywordSearch']}")])))
    p = client.post("/api/projects", json={"name": "P"}).json()
    for term in ("openssl", "curl"):
        client.post(f"/api/projects/{p['id']}/keywords", json={"term": term})
    assert client.post(f"/api/projects/{p['id']}/keywords", json={"term": "OpenSSL"}).status_code == 409

    # extra ad-hoc keywords are merged with the project's, case-insensitively
    body = {"project_id": p["id"], "keywords": [{"term": "CURL"}], "sources": ["nvd", "cnnvd"], "window": "7d"}
    data = client.post("/api/search", json=body).json()
    assert data["total"] == 1
    assert sorted(data["results"][0]["matched_keywords"]) == ["curl", "openssl"]
    assert data["errors"] == []

    csv_resp = client.post("/api/search/export.csv", json=body)
    assert csv_resp.headers["content-type"].startswith("text/csv")
    lines = csv_resp.text.strip().splitlines()
    assert lines[0].startswith("id,source,severity") and "CVE-2026-1" in lines[1]


def test_search_validation(client):
    assert client.post("/api/search", json={"keywords": []}).status_code == 422
    assert client.post("/api/search", json={"keywords": [{"term": "x"}], "sources": ["nope"]}).status_code == 422
    assert client.post("/api/search", json={"keywords": [{"term": "x"}], "sources": ["cnvd"]}).status_code == 422
    assert client.post("/api/search", json={"project_id": 999}).status_code == 404
