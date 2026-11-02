import pytest

from pomodoro_app import APP_NAME
from pomodoro_app.anytype_client import (
    AnytypeAuthError, AnytypeClient, AnytypeError, AnytypeForbiddenError,
    _find_by_name, _unwrap_list, _unwrap_object,
)


def test_unwrap_object_accepts_both_formats():
    assert _unwrap_object({"object": {"id": "a"}}) == {"id": "a"}  # versão 2025-11-08
    assert _unwrap_object({"data": {"id": "b"}}) == {"id": "b"}    # versões anteriores
    assert _unwrap_object({"id": "c"}) == {"id": "c"}


def test_unwrap_list():
    assert _unwrap_list({"data": [1, 2], "pagination": {}}) == [1, 2]
    assert _unwrap_list({"data": None}) == []
    assert _unwrap_list(None) == []


def test_find_by_name_ignores_case_and_spaces():
    items = [{"name": "Task"}, {"name": " Status "}]
    assert _find_by_name(items, "status") == {"name": " Status "}
    assert _find_by_name(items, "Notes") is None


def test_list_objects_follows_pagination(monkeypatch):
    """Antes parava na primeira página (100 objetos)."""
    client = AnytypeClient("http://localhost:31009/", "2025-11-08", "chave")
    pages = {0: ["a", "b"], 2: ["c", "d"], 4: ["e"]}
    calls = []

    def fake_request(method, path, **kwargs):
        offset = kwargs["params"]["offset"]
        calls.append(kwargs["params"])
        return {"data": pages[offset], "pagination": {"has_more": offset < 4}}

    monkeypatch.setattr(client, "_request", fake_request)
    assert client.list_objects("space", type_key="task", limit=2) == ["a", "b", "c", "d", "e"]
    assert [c["offset"] for c in calls] == [0, 2, 4]
    assert all(c["type"] == "task" for c in calls)


def test_configure_strips_trailing_slash():
    client = AnytypeClient("http://localhost:31009/", "v1")
    client.configure("http://127.0.0.1:9999///", "v2")
    assert (client.base_url, client.api_version) == ("http://127.0.0.1:9999", "v2")


def test_requests_without_pairing_explain_what_to_do():
    with pytest.raises(AnytypeError, match="pareada"):
        AnytypeClient("http://localhost:31009", "v1")._headers()


class _FakeResponse:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self._body = body or {}
        self.content = b"x"
        self.text = str(self._body)

    def json(self):
        return self._body


def _client_returning(monkeypatch, status_code, body=None):
    client = AnytypeClient("http://localhost:31009", "v1", "chave")
    monkeypatch.setattr(client.session, "request", lambda *a, **k: _FakeResponse(status_code, body))
    return client


def test_401_asks_to_pair_again(monkeypatch):
    client = _client_returning(monkeypatch, 401)
    with pytest.raises(AnytypeAuthError, match="Pareie de novo"):
        client.list_spaces()


def test_403_explains_space_not_granted(monkeypatch):
    client = _client_returning(monkeypatch, 403)
    with pytest.raises(AnytypeForbiddenError, match="não liberou este espaço"):
        client.list_types("space")


def test_pairing_errors_keep_raw_message(monkeypatch):
    """No pareamento, 401 é código errado, não chave revogada."""
    client = _client_returning(monkeypatch, 401, {"message": "invalid code"})
    with pytest.raises(AnytypeError, match="401") as info:
        client.solve_challenge("ch", "0000")
    assert not isinstance(info.value, AnytypeAuthError)


def test_challenge_sends_app_name(monkeypatch):
    client = AnytypeClient("http://localhost:31009", "v1")
    sent = {}

    def fake_request(method, path, **kwargs):
        sent.update(kwargs["json"])
        return {"challenge_id": "ch"}

    monkeypatch.setattr(client, "_request", fake_request)
    assert client.create_challenge() == "ch"
    assert sent == {"app_name": APP_NAME}
