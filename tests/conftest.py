"""Peças compartilhadas pelos testes: configuração de exemplo e um cliente
do Anytype em memória (sem rede), que imita o formato das respostas reais."""
from __future__ import annotations

import copy
import itertools
from typing import Any, Dict, List, Optional

import pytest

from pomodoro_app.config import AppConfig
from pomodoro_app.task_manager import TaskManager


@pytest.fixture(autouse=True)
def no_config_writes(monkeypatch):
    """Nenhum teste pode gravar no config.json de verdade do usuário."""
    monkeypatch.setattr("pomodoro_app.task_manager.save_config", lambda *a, **k: None)


@pytest.fixture(autouse=True)
def silent(monkeypatch):
    """Sem sons nem notificações do sistema durante os testes."""
    monkeypatch.setattr("pomodoro_app.session.play_sound", lambda *a, **k: None)
    monkeypatch.setattr("pomodoro_app.session.notify", lambda *a, **k: None)


class FakeClient:
    """Anytype em memória com o necessário para TaskManager: um tipo Task,
    as propriedades Status / Done / Notes e objetos com propriedades."""

    def __init__(self, with_notes: bool = True, with_task_type: bool = True):
        self._ids = (f"obj{i}" for i in itertools.count(1))
        self.types = [{"id": "type-task", "key": "task", "name": "Task"}] if with_task_type else []
        self.properties = [
            {"id": "prop-status", "key": "status", "name": "Status", "format": "select"},
            {"id": "prop-done", "key": "done", "name": "Done", "format": "checkbox"},
        ]
        if with_notes:
            self.properties.append({"id": "prop-notes", "key": "notes", "name": "Notes", "format": "text"})
        self.tags: Dict[str, List[Dict[str, Any]]] = {"prop-status": []}
        self.objects: Dict[str, Dict[str, Any]] = {}
        self.updates: List[Dict[str, Any]] = []  # registro de update_object

    # ----- tipos, propriedades e tags
    def find_type_by_name(self, space_id, name):
        return next((t for t in self.types if t["name"].lower() == name.lower()), None)

    def find_property_by_name(self, space_id, name):
        return next((p for p in self.properties if p["name"].lower() == name.lower()), None)

    def ensure_tag(self, space_id, property_id, name, color="grey"):
        tags = self.tags.setdefault(property_id, [])
        for tag in tags:
            if tag["name"].lower() == name.lower():
                return tag["id"]
        tag = {"id": f"tag-{name}", "name": name, "color": color}
        tags.append(tag)
        return tag["id"]

    # ----- objetos
    def create_object(self, space_id, name, type_key, properties=None):
        obj_id = next(self._ids)
        obj = {
            "id": obj_id, "name": name, "type": type_key,
            "properties": [{"key": "created_date", "format": "date", "date": "2026-06-12T18:35:57Z"}],
        }
        self.objects[obj_id] = obj
        self._apply(obj, properties or [])
        return copy.deepcopy(obj)

    def update_object(self, space_id, object_id, name=None, properties=None):
        obj = self.objects[object_id]
        self.updates.append({"id": object_id, "name": name, "properties": properties})
        if name is not None:
            obj["name"] = name
        self._apply(obj, properties or [])
        return copy.deepcopy(obj)

    def get_object(self, space_id, object_id):
        return copy.deepcopy(self.objects[object_id])

    def list_objects(self, space_id, type_key=None, limit=100):
        return [copy.deepcopy(o) for o in self.objects.values() if not type_key or o["type"] == type_key]

    def delete_object(self, space_id, object_id):
        del self.objects[object_id]

    def _apply(self, obj: Dict[str, Any], properties: List[Dict[str, Any]]) -> None:
        """Grava as propriedades como a API devolve: select vira o objeto tag."""
        for prop in properties:
            stored = dict(prop)
            if "select" in prop:
                tag = next(t for t in self.tags["prop-status"] if t["id"] == prop["select"])
                stored["select"] = {"object": "tag", **tag}
            obj["properties"] = [p for p in obj["properties"] if p.get("key") != prop["key"]] + [stored]


def make_config(**anytype) -> AppConfig:
    config = AppConfig()
    config.anytype.space_id = "space-1"
    config.anytype.api_key = "chave-de-teste"
    for key, value in anytype.items():
        setattr(config.anytype, key, value)
    config.pomodoro.sound_enabled = False
    return config


@pytest.fixture
def config() -> AppConfig:
    return make_config()


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def manager(config, client) -> TaskManager:
    tm = TaskManager(client, config)
    tm.setup()
    return tm


def prop(obj: Dict[str, Any], key: str) -> Optional[Dict[str, Any]]:
    return next((p for p in obj["properties"] if p.get("key") == key), None)
