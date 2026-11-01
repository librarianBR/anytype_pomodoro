"""
Cliente para a API Local do Anytype (roda embutida no Anytype Desktop,
totalmente offline, em http://localhost:31009 por padrão).

Referência oficial: https://developers.anytype.io/docs/reference
A API é relativamente nova e evolui rápido — se algo aqui não bater com a
versão instalada no seu computador, confira o endpoint correspondente na
documentação (o cabeçalho Anytype-Version define a versão usada) e ajuste.
Este cliente usa a versão "2025-11-08".

Fluxo de autenticação (uma única vez, pelo pareamento na interface):
  1. POST /v1/auth/challenges {"app_name": "..."} -> {"challenge_id": ...}
     O Anytype Desktop mostra um código de 4 dígitos na tela.
  2. Você digita esse código quando o script pedir.
  3. POST /v1/auth/api_keys {"challenge_id":..., "code":...} -> {"api_key": ...}
  A api_key vira um Bearer token para todas as chamadas seguintes e é salva
  no config.json para não precisar repetir o pareamento toda vez.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import requests


class AnytypeError(RuntimeError):
    """Erro de comunicação com a API do Anytype."""


# Cores aceitas pela API do Anytype para tags (campo obrigatório em
# CreateTagRequest). Ver https://developers.anytype.io/docs/reference
TAG_COLORS = [
    "grey", "yellow", "orange", "red", "pink",
    "purple", "blue", "ice", "teal", "lime",
]


def _unwrap_list(data: Any) -> List[Dict[str, Any]]:
    """Listagens vêm como {"data": [...], "pagination": {...}}."""
    if isinstance(data, dict) and "data" in data:
        return data["data"] or []
    return data or []


def _find_by_name(items: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    """Primeiro item cujo "name" é igual a `name`, sem diferenciar maiúsculas."""
    wanted = name.strip().lower()
    return next((i for i in items if i.get("name", "").strip().lower() == wanted), None)


def _unwrap_object(data: Any) -> Any:
    """As respostas de criar/consultar/editar um objeto vêm como
    {"object": {...}} nesta versão da API (outras versões usavam "data").
    Devolve o objeto em si, aceitando os dois formatos."""
    if isinstance(data, dict):
        if isinstance(data.get("object"), dict):
            return data["object"]
        if isinstance(data.get("data"), dict):
            return data["data"]
    return data


class AnytypeClient:
    def __init__(self, base_url: str, api_version: str, api_key: str = ""):
        self.session = requests.Session()
        self.api_key = api_key
        self.configure(base_url, api_version)

    def configure(self, base_url: str, api_version: str) -> None:
        """Atualiza endereço e versão da API (ex.: após salvar nas Configurações)."""
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version

    # --------------------------------------------------------- utilidades
    def _headers(self, auth: bool = True) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Anytype-Version": self.api_version,
        }
        if auth:
            if not self.api_key:
                raise AnytypeError(
                    "A aplicação ainda não está pareada com o Anytype. Faça o "
                    "pareamento (\"Parear com o Anytype\") antes de usar as tarefas."
                )
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _request(self, method: str, path: str, auth: bool = True, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, headers=self._headers(auth), timeout=10, **kwargs)
        except requests.exceptions.ConnectionError as exc:
            raise AnytypeError(
                "Não foi possível conectar ao Anytype Desktop. Verifique se o "
                f"app está aberto e se a API local está ativa em {self.base_url}."
            ) from exc
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json()
            except ValueError:
                detail = resp.text
            raise AnytypeError(f"Anytype API retornou {resp.status_code}: {detail}")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # -------------------------------------------------------- autenticação
    def create_challenge(self, app_name: str = "python-pomodoro") -> str:
        data = self._request(
            "POST", "/v1/auth/challenges", auth=False, json={"app_name": app_name}
        )
        return data["challenge_id"]

    def solve_challenge(self, challenge_id: str, code: str) -> str:
        data = self._request(
            "POST",
            "/v1/auth/api_keys",
            auth=False,
            json={"challenge_id": challenge_id, "code": code},
        )
        self.api_key = data["api_key"]
        return self.api_key

    # ------------------------------------------------------------ espaços
    def list_spaces(self) -> List[Dict[str, Any]]:
        return _unwrap_list(self._request("GET", "/v1/spaces"))

    # ----------------------------------------------- tipos e propriedades
    def list_types(self, space_id: str) -> List[Dict[str, Any]]:
        return _unwrap_list(self._request("GET", f"/v1/spaces/{space_id}/types"))

    def find_type_by_name(self, space_id: str, name: str) -> Optional[Dict[str, Any]]:
        return _find_by_name(self.list_types(space_id), name)

    def list_properties(self, space_id: str) -> List[Dict[str, Any]]:
        return _unwrap_list(self._request("GET", f"/v1/spaces/{space_id}/properties"))

    def find_property_by_name(self, space_id: str, name: str) -> Optional[Dict[str, Any]]:
        return _find_by_name(self.list_properties(space_id), name)

    # --------------------------------------------------------------- tags
    def list_tags(self, space_id: str, property_id: str) -> List[Dict[str, Any]]:
        return _unwrap_list(
            self._request("GET", f"/v1/spaces/{space_id}/properties/{property_id}/tags")
        )

    def create_tag(
        self, space_id: str, property_id: str, name: str, color: str = "grey"
    ) -> Dict[str, Any]:
        if color not in TAG_COLORS:
            color = "grey"
        data = self._request(
            "POST",
            f"/v1/spaces/{space_id}/properties/{property_id}/tags",
            json={"name": name, "color": color},
        )
        return _unwrap_object(data)

    def ensure_tag(
        self, space_id: str, property_id: str, name: str, color: str = "grey"
    ) -> str:
        """Id da tag com esse nome, criando-a (com a cor dada) se não existir."""
        existing = _find_by_name(self.list_tags(space_id, property_id), name)
        if existing:
            return existing["id"]
        return self.create_tag(space_id, property_id, name, color=color).get("id")

    # ------------------------------------------------------------ objetos
    def create_object(
        self,
        space_id: str,
        name: str,
        type_key: str,
        properties: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Cria um objeto. Atenção: na versão 2025-11-08 da API, o campo
        "description" de topo é ignorado na criação — a descrição precisa ir
        em `properties` como {"key": "description", "text": ...}."""
        payload: Dict[str, Any] = {"name": name, "type_key": type_key}
        if properties:
            payload["properties"] = properties
        data = self._request("POST", f"/v1/spaces/{space_id}/objects", json=payload)
        return _unwrap_object(data)

    def update_object(
        self,
        space_id: str,
        object_id: str,
        name: Optional[str] = None,
        properties: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if properties is not None:
            payload["properties"] = properties
        data = self._request(
            "PATCH", f"/v1/spaces/{space_id}/objects/{object_id}", json=payload
        )
        return _unwrap_object(data)

    def delete_object(self, space_id: str, object_id: str) -> None:
        self._request("DELETE", f"/v1/spaces/{space_id}/objects/{object_id}")

    def get_object(self, space_id: str, object_id: str) -> Dict[str, Any]:
        data = self._request("GET", f"/v1/spaces/{space_id}/objects/{object_id}")
        return _unwrap_object(data)

    def list_objects(
        self, space_id: str, type_key: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Lista TODOS os objetos (do tipo informado, se houver), seguindo a
        paginação da API — `limit` é só o tamanho de cada página. Sem isso,
        espaços com mais objetos que uma página teriam tarefas "sumindo"."""
        objects: List[Dict[str, Any]] = []
        offset = 0
        while True:
            params: Dict[str, Any] = {"limit": limit, "offset": offset}
            if type_key:
                params["type"] = type_key
            data = self._request("GET", f"/v1/spaces/{space_id}/objects", params=params)
            page = _unwrap_list(data)
            objects.extend(page)
            pagination = (data.get("pagination") if isinstance(data, dict) else None) or {}
            if not pagination.get("has_more") or not page:
                return objects
            offset += len(page)
