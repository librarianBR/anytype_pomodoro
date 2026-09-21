"""
Cliente para a API Local do Anytype (roda embutida no Anytype Desktop,
totalmente offline, em http://localhost:31009 por padrão).

Referência oficial: https://developers.anytype.io/docs/reference
A API é relativamente nova e evolui rápido — se algo aqui não bater com a
versão instalada no seu computador, confira o endpoint correspondente na
documentação (o cabeçalho Anytype-Version define a versão usada) e ajuste.
Este cliente usa a versão "2025-11-08".

Fluxo de autenticação (uma única vez, feito por pair()):
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


class AnytypeClient:
    def __init__(self, base_url: str, api_version: str, api_key: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.api_key = api_key
        self.session = requests.Session()

    # --------------------------------------------------------- utilidades
    def _headers(self, auth: bool = True) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Anytype-Version": self.api_version,
        }
        if auth:
            if not self.api_key:
                raise AnytypeError(
                    "Sem api_key configurada. Rode o pareamento (opção "
                    "'parear com o Anytype' no menu) antes de usar as tarefas."
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
        data = self._request("GET", "/v1/spaces")
        return data.get("data", data)

    # ------------------------------------------------------------- tipos
    def list_types(self, space_id: str) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/v1/spaces/{space_id}/types")
        return data.get("data", data)

    def find_type_by_name(self, space_id: str, name: str) -> Optional[Dict[str, Any]]:
        for t in self.list_types(space_id):
            if t.get("name", "").lower() == name.lower():
                return t
        return None

    # -------------------------------------------------------- propriedades
    def list_properties(self, space_id: str) -> List[Dict[str, Any]]:
        data = self._request("GET", f"/v1/spaces/{space_id}/properties")
        return data.get("data", data)

    def find_property_by_name(self, space_id: str, name: str) -> Optional[Dict[str, Any]]:
        for p in self.list_properties(space_id):
            if p.get("name", "").lower() == name.lower():
                return p
        return None

    # --------------------------------------------------------------- tags
    def list_tags(self, space_id: str, property_id: str) -> List[Dict[str, Any]]:
        data = self._request(
            "GET", f"/v1/spaces/{space_id}/properties/{property_id}/tags"
        )
        return data.get("data", data)

    def create_tag(
        self, space_id: str, property_id: str, name: str, color: str = "grey"
    ) -> Dict[str, Any]:
        if color not in TAG_COLORS:
            color = "grey"
        return self._request(
            "POST",
            f"/v1/spaces/{space_id}/properties/{property_id}/tags",
            json={"name": name, "color": color},
        )

    def ensure_tag(
        self, space_id: str, property_id: str, name: str, color: str = "grey"
    ) -> str:
        """Retorna o id da tag com esse nome, criando-a (com a cor dada) se
        não existir."""
        for tag in self.list_tags(space_id, property_id):
            if tag.get("name", "").lower() == name.lower():
                return tag["id"]
        created = self.create_tag(space_id, property_id, name, color=color)
        return created.get("id") or created.get("data", {}).get("id")

    # ------------------------------------------------------------ objetos
    def create_object(
        self,
        space_id: str,
        name: str,
        type_key: str,
        description: str = "",
        body: str = "",
        properties: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"name": name, "type_key": type_key}
        if description:
            payload["description"] = description
        if body:
            payload["body"] = body
        if properties:
            payload["properties"] = properties
        data = self._request("POST", f"/v1/spaces/{space_id}/objects", json=payload)
        return data.get("data", data)

    def update_object(
        self,
        space_id: str,
        object_id: str,
        name: Optional[str] = None,
        properties: Optional[List[Dict[str, Any]]] = None,
        body: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if properties is not None:
            payload["properties"] = properties
        if body is not None:
            payload["body"] = body
        data = self._request(
            "PATCH", f"/v1/spaces/{space_id}/objects/{object_id}", json=payload
        )
        return data.get("data", data)

    def delete_object(self, space_id: str, object_id: str) -> None:
        self._request("DELETE", f"/v1/spaces/{space_id}/objects/{object_id}")

    def get_object(self, space_id: str, object_id: str) -> Dict[str, Any]:
        data = self._request("GET", f"/v1/spaces/{space_id}/objects/{object_id}")
        return data.get("data", data)

    def list_objects(
        self, space_id: str, type_key: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        params = {"limit": limit}
        if type_key:
            params["type"] = type_key
        data = self._request("GET", f"/v1/spaces/{space_id}/objects", params=params)
        return data.get("data", data)
