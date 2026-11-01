"""
Camada de mais alto nível sobre o AnytypeClient, especializada em tarefas.

Responsabilidades:
- Garantir (uma vez, e depois guardar no config) que existem no espaço:
  - um tipo de objeto para tarefas (ex.: "Task");
  - uma propriedade "select" para status (ex.: "Status") e as tags de cada
    status configurado;
  - (opcional) o checkbox nativo "Done" do Anytype, mantido em sincronia;
  - (opcional) uma propriedade de texto "Notes", para o histórico.
- Criar, listar, renomear, excluir tarefas e trocar o status.
- Registrar observações no histórico de uma tarefa.

O tipo de objeto e a propriedade "Status" precisam existir no espaço (o
usuário os cria uma vez no Anytype), pois criar tipos e propriedades pela
API ainda não é confiável. Se faltarem, setup() explica o que falta.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .anytype_client import TAG_COLORS, AnytypeClient, AnytypeError
from .config import AnytypeConfig, AppConfig, save_config
from .formatting import DATETIME_FORMAT


class SetupError(RuntimeError):
    """O espaço do Anytype ainda não tem o que a aplicação precisa."""


@dataclass
class Task:
    id: str
    name: str
    status: str
    raw: Dict[str, Any]
    # Data de criação (propriedade nativa "created_date"), no fuso local.
    created: Optional[_dt.datetime] = None
    # Data de entrega (propriedade nativa "due_date"); None se não definida.
    due: Optional[_dt.date] = None
    # Descrição do Anytype — onde fica a história de usuário (Scrum).
    description: str = ""


# ------------------------------------------------- leitura de propriedades
def find_property(obj: Dict[str, Any], key: str = "", prop_id: str = "", name: str = "") -> Optional[Dict[str, Any]]:
    """Primeira propriedade do objeto que casa com o key, o id ou o nome
    (sem diferenciar maiúsculas) informados — o que estiver disponível."""
    wanted_name = name.strip().lower()
    for prop in obj.get("properties", []):
        if (
            (key and prop.get("key") == key)
            or (prop_id and prop.get("id") == prop_id)
            or (wanted_name and prop.get("name", "").strip().lower() == wanted_name)
        ):
            return prop
    return None


def extract_tag_ref(value: Any) -> Optional[str]:
    """Normaliza o valor de uma propriedade select/multi_select, que pode vir
    como string (id/key da tag), dict ({"id":..,"key":..}) ou lista (para
    multi_select) — retorna um único id/key de tag."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("id") or value.get("key")
    if isinstance(value, list) and value:
        return extract_tag_ref(value[0])
    return None


def parse_created_date(prop: Optional[Dict[str, Any]]) -> Optional[_dt.datetime]:
    """"2026-06-12T18:35:57Z" -> datetime no fuso local. None se faltar ou
    vier num formato inesperado."""
    value = (prop or {}).get("date")
    if not value:
        return None
    try:
        return _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def parse_due_date(prop: Optional[Dict[str, Any]]) -> Optional[_dt.date]:
    """A data de entrega é um DIA, guardado pelo Anytype como meia-noite UTC
    ("2026-11-15T00:00:00Z"). Pega só a parte da data, SEM converter para o
    fuso local — senão, no Brasil (UTC-3), viraria o dia anterior."""
    value = (prop or {}).get("date")
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def due_date_value(due: _dt.date) -> str:
    """Formato que a API aceita para gravar a data de entrega."""
    return f"{due.isoformat()}T00:00:00Z"


class TaskManager:
    def __init__(self, client: AnytypeClient, app_config: AppConfig):
        self.client = client
        self.app_config = app_config

    @property
    def cfg(self) -> AnytypeConfig:
        return self.app_config.anytype

    # --------------------------------------------------------------- setup
    def select_space(self, space_id: str) -> None:
        """Troca o espaço de trabalho e esquece o que foi descoberto no
        anterior (ids de tipo, propriedades e tags valem só por espaço)."""
        self.cfg.space_id = space_id
        self.cfg.reset_space_cache()
        save_config(self.app_config)

    def setup(self) -> None:
        """Descobre (e guarda no config) o tipo de tarefa, a propriedade de
        status e suas tags, e as propriedades opcionais Done e Notes."""
        cfg = self.cfg
        if not cfg.space_id:
            raise SetupError("Nenhum espaço do Anytype escolhido. Escolha um nas Configurações.")

        if not cfg.task_type_key:
            task_type = self.client.find_type_by_name(cfg.space_id, cfg.task_type_name)
            if not task_type:
                raise SetupError(
                    f"Não encontrei um tipo chamado '{cfg.task_type_name}' no seu "
                    "espaço do Anytype. Crie esse tipo de objeto no Anytype (ou "
                    "informe o nome de um tipo existente nas Configurações) e tente de novo."
                )
            cfg.task_type_key = task_type.get("key") or task_type.get("id")

        if not cfg.status_property_id:
            prop = self.client.find_property_by_name(cfg.space_id, cfg.status_property_name)
            if not prop:
                raise SetupError(
                    f"Não encontrei uma propriedade chamada '{cfg.status_property_name}' "
                    "no seu espaço. Crie uma propriedade do tipo 'Select' com esse nome "
                    "no Anytype (no tipo de tarefa) e tente de novo."
                )
            cfg.status_property_id = prop["id"]
            cfg.status_property_key = prop.get("key", "")

        for i, status_name in enumerate(cfg.status_options):
            if status_name not in cfg.status_tag_ids:
                cfg.status_tag_ids[status_name] = self.client.ensure_tag(
                    cfg.space_id, cfg.status_property_id, status_name,
                    color=TAG_COLORS[i % len(TAG_COLORS)],
                )

        # Opcionais: se não existirem, a aplicação só não sincroniza o
        # checkbox / não registra observações (add_note explica o que falta).
        if not cfg.done_checkbox_property_id:
            prop = self.client.find_property_by_name(cfg.space_id, cfg.done_checkbox_property_name)
            if prop:
                cfg.done_checkbox_property_id = prop["id"]
                cfg.done_checkbox_property_key = prop.get("key") or cfg.done_checkbox_property_key
        if not cfg.notes_property_id:
            prop = self.client.find_property_by_name(cfg.space_id, cfg.notes_property_name)
            if prop:
                cfg.notes_property_id = prop["id"]
                cfg.notes_property_key = prop.get("key", "")

        save_config(self.app_config)

    # ----------------------------------------------------- conversão/leitura
    def _status_property(self, status_name: str) -> Dict[str, Any]:
        if status_name not in self.cfg.status_tag_ids:
            raise SetupError(
                f"O status '{status_name}' ainda não tem uma tag no Anytype. Rode "
                "\"Testar / preparar\" nas Configurações. Status configurados: "
                f"{', '.join(self.cfg.status_options)}"
            )
        # Algumas versões da API identificam a propriedade pelo "key", outras
        # pelo "id": mandamos o que houver, preferindo o key.
        return {
            "key": self.cfg.status_property_key or self.cfg.status_property_id,
            "select": self.cfg.status_tag_ids[status_name],
        }

    def _status_name(self, obj: Dict[str, Any]) -> str:
        """Nome do status da tarefa, ou "?" se não for reconhecido."""
        prop = find_property(
            obj, key=self.cfg.status_property_key, prop_id=self.cfg.status_property_id,
            name=self.cfg.status_property_name,
        )
        if not prop:
            return "?"
        raw_value = prop.get("select", prop.get("value"))
        tag_ref = extract_tag_ref(raw_value)
        for name, tag_id in self.cfg.status_tag_ids.items():
            if tag_ref and tag_id == tag_ref:
                return name
        # não achamos pelo id guardado: o valor pode já trazer o nome da tag
        if isinstance(raw_value, dict) and raw_value.get("name"):
            return raw_value["name"]
        return "?"

    def to_task(self, obj: Dict[str, Any]) -> Task:
        description = find_property(obj, key=self.cfg.description_property_key)
        return Task(
            id=obj.get("id"),
            name=obj.get("name", ""),
            status=self._status_name(obj),
            raw=obj,
            created=parse_created_date(find_property(obj, key="created_date")),
            due=parse_due_date(find_property(obj, key=self.cfg.due_date_property_key)),
            description=(description or {}).get("text") or "",
        )

    # ---------------------------------------------------------------- CRUD
    def create_task(
        self,
        name: str,
        description: str = "",
        status: Optional[str] = None,
        due: Optional[_dt.date] = None,
    ) -> Task:
        """Cria a tarefa. `description` (ex.: uma história de usuário) e
        `due` (data de entrega) são opcionais."""
        status = status or self.cfg.status_options[0]
        properties = [self._status_property(status)]
        if due:
            properties.append({"key": self.cfg.due_date_property_key, "date": due_date_value(due)})
        description = (description or "").strip()
        if description:
            properties.append({"key": self.cfg.description_property_key, "text": description})
        obj = self.client.create_object(
            self.cfg.space_id, name=name, type_key=self.cfg.task_type_key, properties=properties
        )
        task = self.to_task(obj)
        if task.id:
            self._sync_done_checkbox(task.id, status == self.cfg.done_status_name)
        return task

    def list_tasks(self) -> List[Task]:
        objs = self.client.list_objects(self.cfg.space_id, type_key=self.cfg.task_type_key)
        return [self.to_task(o) for o in objs]

    def list_pending_tasks(self) -> List[Task]:
        """Tarefas que ainda não estão com o status de concluído."""
        return [t for t in self.list_tasks() if t.status != self.cfg.done_status_name]

    def rename_task(self, task_id: str, new_name: str) -> Task:
        return self.to_task(self.client.update_object(self.cfg.space_id, task_id, name=new_name))

    def set_status(self, task_id: str, status_name: str) -> Task:
        obj = self.client.update_object(
            self.cfg.space_id, task_id, properties=[self._status_property(status_name)]
        )
        self._sync_done_checkbox(task_id, status_name == self.cfg.done_status_name)
        return self.to_task(obj)

    def _sync_done_checkbox(self, task_id: str, is_done: bool) -> None:
        """Melhor esforço: mantém o checkbox nativo "Done" do Anytype (layout
        Action, como o Task embutido) alinhado com o status. Se a
        propriedade não existir, falha em silêncio — não pode atrapalhar a
        troca de status, que é a operação principal."""
        prop_ref = self.cfg.done_checkbox_property_key or self.cfg.done_checkbox_property_id
        if not prop_ref:
            return
        try:
            self.client.update_object(
                self.cfg.space_id, task_id, properties=[{"key": prop_ref, "checkbox": is_done}]
            )
        except AnytypeError:
            pass

    def delete_task(self, task_id: str) -> None:
        self.client.delete_object(self.cfg.space_id, task_id)

    # ------------------------------------------------------------ notas
    # Guardadas numa propriedade de TEXTO (não no corpo da página): atualizar
    # o "body" de um objeto pela API não é confiável nesta versão do Anytype.
    def _notes_property_ref(self) -> str:
        prop_ref = self.cfg.notes_property_key or self.cfg.notes_property_id
        if not prop_ref:
            raise SetupError(
                f"Não encontrei uma propriedade de texto chamada "
                f"'{self.cfg.notes_property_name}' no seu espaço. Crie uma "
                "propriedade do tipo 'Text' com esse nome no Anytype (no tipo de "
                "tarefa) e rode \"Testar / preparar\" nas Configurações."
            )
        return prop_ref

    def get_task_notes(self, task_id: str) -> str:
        """Texto atual do histórico de observações da tarefa."""
        self._notes_property_ref()
        obj = self.client.get_object(self.cfg.space_id, task_id)
        prop = find_property(obj, key=self.cfg.notes_property_key, prop_id=self.cfg.notes_property_id)
        return (prop or {}).get("text") or ""

    def add_note(self, task_id: str, text: str) -> Task:
        """Acrescenta uma observação com data e hora ao final do histórico
        (o que já existia é mantido)."""
        prop_ref = self._notes_property_ref()
        entry = f"[{_dt.datetime.now().strftime(DATETIME_FORMAT)}] {text}"
        current = self.get_task_notes(task_id)
        new_value = f"{current}\n{entry}" if current else entry
        obj = self.client.update_object(
            self.cfg.space_id, task_id, properties=[{"key": prop_ref, "text": new_value}]
        )
        return self.to_task(obj)
