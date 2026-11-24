import importlib
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


class FakeQuery:
    def __init__(self, client):
        self.client = client
        self.rows = list(client.rows)

    def select(self, columns):
        self.columns = columns.split(",")
        return self

    def eq(self, key, value):
        self.rows = [r for r in self.rows if r[key] == value]
        return self

    def gte(self, key, value):
        self.rows = [r for r in self.rows if r[key] >= value]
        return self

    def lte(self, key, value):
        self.rows = [r for r in self.rows if r[key] <= value]
        return self

    def order(self, key, desc=False):
        self.rows.sort(key=lambda r: r[key], reverse=desc)
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def execute(self):
        if self.client.database_error:
            raise RuntimeError("private database error")
        return SimpleNamespace(data=[{k: r[k] for k in self.columns} for r in self.rows])


class FakeSupabase:
    def __init__(self):
        self.rows = []
        self.database_error = False
        self.storage_error = False
        self.signed = {"signedURL": "https://example.test/recap.mp4?token=fake"}
        self.sign_calls = []
        self.table_calls = []
        self.storage = self
        self.auth = self

    def get_user(self, token):
        if token != "valid":
            raise ValueError("bad token")
        return SimpleNamespace(user=SimpleNamespace(id="alice"))

    def table(self, name):
        self.table_calls.append(name)
        assert name == "recaps"
        return FakeQuery(self)

    def from_(self, bucket):
        assert bucket == "recaps"
        return self

    def create_signed_url(self, path, seconds):
        self.sign_calls.append((path, seconds))
        if self.storage_error:
            raise RuntimeError("private storage error")
        return self.signed


def recap(day="2026-11-23", user="alice", created="2026-11-23T12:00:00Z"):
    return {"user_id": user, "date": day, "storage_path": f"{user}/{day}/recap.mp4",
            "created_at": created}


@pytest.fixture
def api(monkeypatch):
    import dotenv
    import supabase

    fake = FakeSupabase()
    # Prevent import-time initialization from reading credentials or using a real client.
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)
    monkeypatch.setenv("SUPABASE_URL", "https://example.test")
    monkeypatch.setenv("SUPABASE_KEY", "fake-test-key")
    monkeypatch.setattr(supabase, "create_client", lambda *args: fake)
    monkeypatch.delitem(sys.modules, "main", raising=False)
    main = importlib.import_module("main")
    with TestClient(main.app) as client:
        client.headers["Authorization"] = "Bearer valid"
        yield client, fake
    sys.modules.pop("main", None)


@pytest.mark.parametrize("signed_key", ["signedURL", "signedUrl"])
def test_recap_is_scoped_and_signed_for_one_hour(api, signed_key):
    client, fake = api
    fake.rows = [recap(user="bob"), recap(), recap(day="2026-11-22")]
    fake.signed = {signed_key: "https://example.test/play"}
    response = client.get("/recaps?date=2026-11-23&user_id=bob")
    assert response.status_code == 200
    assert response.json() == {"date": "2026-11-23", "url": "https://example.test/play",
                               "created_at": "2026-11-23T12:00:00Z"}
    assert fake.sign_calls == [("alice/2026-11-23/recap.mp4", 3600)]


def test_newest_recap_when_duplicate_rows_exist(api):
    client, fake = api
    old = recap(created="2026-11-23T01:00:00Z")
    old["storage_path"] = "alice/old.mp4"
    fake.rows = [old, recap()]
    assert client.get("/recaps?date=2026-11-23").status_code == 200
    assert fake.sign_calls[0][0] == "alice/2026-11-23/recap.mp4"


def test_missing_recap_is_404_and_does_not_sign_another_users_file(api):
    client, fake = api
    fake.rows = [recap(user="bob")]
    response = client.get("/recaps?date=2026-11-23")
    assert response.status_code == 404
    assert response.json() == {"detail": "No recap available for 2026-11-23 yet"}
    assert fake.sign_calls == []


@pytest.mark.parametrize("month,days", [
    ("2026-11", ["2026-11-01", "2026-11-30"]),
    ("2026-12", ["2026-12-01", "2026-12-31"]),
    ("2028-02", ["2028-02-01", "2028-02-29"]),
])
def test_days_are_sorted_unique_and_scoped_to_user_and_month(api, month, days):
    client, fake = api
    fake.rows = [recap(days[1]), recap(days[0]), recap(days[0]),
                 recap(days[0], user="bob"), recap("2026-10-31"), recap("2027-01-01")]
    response = client.get(f"/recaps/days?month={month}&user_id=bob")
    assert response.status_code == 200
    assert response.json() == {"dates": days}
    assert fake.sign_calls == []


def test_empty_month(api):
    client, _ = api
    assert client.get("/recaps/days?month=2026-11").json() == {"dates": []}


@pytest.mark.parametrize("path", ["/recaps?date=2026-11-23", "/recaps/days?month=2026-11"])
@pytest.mark.parametrize("token", [None, "Bearer invalid"])
def test_authentication_required(api, path, token):
    client, fake = api
    client.headers.pop("Authorization")
    response = client.get(path, headers={"Authorization": token} if token else {})
    assert response.status_code == 401
    assert fake.table_calls == []
    assert fake.sign_calls == []


@pytest.mark.parametrize("path", [
    "/recaps", "/recaps?date=2026-02-30", "/recaps?date=garbage",
    "/recaps/days", "/recaps/days?month=2026-13", "/recaps/days?month=2026-00",
    "/recaps/days?month=2026-1", "/recaps/days?month=0000-01",
    "/recaps/days?month=2026-11-01",
])
def test_invalid_dates_rejected_before_database_access(api, path):
    client, fake = api
    assert client.get(path).status_code == 422
    assert fake.table_calls == []


@pytest.mark.parametrize("path", ["/recaps?date=2026-11-23", "/recaps/days?month=2026-11"])
def test_database_failure_is_502(api, path):
    client, fake = api
    fake.database_error = True
    response = client.get(path)
    assert response.status_code == 502
    assert "private" not in response.text


@pytest.mark.parametrize("failure", ["exception", "missing_url"])
def test_signing_failure_is_502(api, failure):
    client, fake = api
    fake.rows = [recap()]
    fake.storage_error = failure == "exception"
    fake.signed = {}
    response = client.get("/recaps?date=2026-11-23")
    assert response.status_code == 502
    assert response.json() == {"detail": "Failed to create recap playback URL"}


def test_docs_describe_token_auth_without_user_id_query(api):
    client, _ = api
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for path, parameter in [("/recaps", "date"), ("/recaps/days", "month")]:
        operation = paths[path]["get"]
        assert [p["name"] for p in operation["parameters"]] == [parameter]
        assert operation["security"] == [{"HTTPBearer": []}]
