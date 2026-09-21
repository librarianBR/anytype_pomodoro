"""
Camada de mais alto nível sobre o AnytypeClient, especializada em tarefas.

Responsabilidades:
- Garantir (uma vez, e depois cachear no config) que existem:
  - um tipo de objeto para tarefas (ex.: "Task");
  - uma propriedade "select" para status (ex.: "Status");
  - as tags de cada status configurado;
  - (opcional) o checkbox nativo "Done" do Anytype, para ficar sincronizado;
  - (opcional) uma propriedade de texto "Notes", para o histórico de
    observações de cada tarefa.
- Criar, editar, excluir e listar tarefas.
- Trocar o status de uma tarefa.
- Registrar observações no histórico de uma tarefa.

Importante: o tipo de objeto e a propriedade "Status" precisam já existir
no seu espaço do Anytype (ou serem criados manualmente por você lá), pois a
criação de Tipos e Propriedades por API ainda é limitada/instável em várias
versões do Anytype. Se não existirem, o setup() abaixo avisa exatamente o
que falta. O checkbox "Done" e a propriedade "Notes" são descobertos da
mesma forma, mas de forma opcional (a aplicação funciona sem eles, só sem
sincronizar o checkbox / sem conseguir registrar observações).
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from anytype_client import AnytypeClient, AnytypeError, TAG_COLORS
from config import AnytypeConfig, AppConfig, save_config


class SetupError(RuntimeError):
    pass


@dataclass
class Task:
    id: str
    name: str
    status: str
    raw: Dict[str, Any]


class TaskManager:
    def __init__(self, client: AnytypeClient, app_config: AppConfig):
        self.client = client
        self.app_config = app_config
        self.cfg: AnytypeConfig = app_config.anytype

    # --------------------------------------------------------------- setup
    def setup(self) -> None:
        """Descobre (e cacheia) o type_key da tarefa, o id da propriedade de
        status e os ids das tags de cada status configurado."""
        cfg = self.cfg
        if not cfg.space_id:
            raise SetupError("Nenhum space_id configurado. Escolha um espaço primeiro.")

        if not cfg.task_type_key:
            t = self.client.find_type_by_name(cfg.space_id, cfg.task_type_name)
            if not t:
                raise SetupError(
                    f"Não encontrei um tipo chamado '{cfg.task_type_name}' no seu "
                    "espaço do Anytype. Crie esse tipo de objeto no Anytype "
                    "(ou ajuste task_type_name no config.json para um tipo existente, "
                    "ex.: 'Page' ou 'Note') e tente de novo."
                )
            cfg.task_type_key = t.get("key") or t.get("id")

        if not cfg.status_property_id:
            p = self.client.find_property_by_name(cfg.space_id, cfg.status_property_name)
            if not p:
                raise SetupError(
                    f"Não encontrei uma propriedade chamada '{cfg.status_property_name}' "
                    "no seu espaço. Crie uma propriedade do tipo 'Select' com esse nome "
                    "no Anytype (em qualquer objeto do tipo de tarefa) e tente de novo."
                )
            cfg.status_property_id = p["id"]
            cfg.status_property_key = p.get("key", "")

        for i, status_name in enumerate(cfg.status_options):
            if status_name not in cfg.status_tag_ids:
                color = TAG_COLORS[i % len(TAG_COLORS)]
                tag_id = self.client.ensure_tag(
                    cfg.space_id, cfg.status_property_id, status_name, color=color
                )
                cfg.status_tag_ids[status_name] = tag_id

        # Checkbox "Done" nativo do Anytype (layout Action) — opcional: se
        # não existir no seu espaço, simplesmente não sincronizamos com ele
        # (a chave "done" já vem como palpite de reserva no config).
        if not cfg.done_checkbox_property_id:
            p = self.client.find_property_by_name(cfg.space_id, cfg.done_checkbox_property_name)
            if p:
                cfg.done_checkbox_property_id = p["id"]
                cfg.done_checkbox_property_key = p.get("key") or cfg.done_checkbox_property_key

        # Propriedade de texto para observações — opcional na descoberta;
        # get_task_notes()/add_note() é que exigem que ela exista quando
        # forem realmente usadas.
        if not cfg.notes_property_id:
            p = self.client.find_property_by_name(cfg.space_id, cfg.notes_property_name)
            if p:
                cfg.notes_property_id = p["id"]
                cfg.notes_property_key = p.get("key", "")

        save_config(self.app_config)

    def _status_property(self, status_name: str) -> Dict[str, Any]:
        if status_name not in self.cfg.status_tag_ids:
            raise SetupError(
                f"Status '{status_name}' ainda não tem uma tag associada no "
                "Anytype. Rode a configuração/preparação (setup) antes de "
                f"criar ou editar tarefas. Status configurados: {self.cfg.status_options}"
            )
        # Algumas versões da API identificam a propriedade pelo seu "key"
        # (slug), outras pelo "id". Mandamos o que tivermos disponível,
        # preferindo o key (mais próximo do padrão usado em type_key).
        prop_ref = self.cfg.status_property_key or self.cfg.status_property_id
        return {
            "key": prop_ref,
            "select": self.cfg.status_tag_ids[status_name],
        }

    @staticmethod
    def _extract_tag_ref(value: Any) -> Optional[str]:
        """Normaliza o valor de uma propriedade select/multi_select, que
        pode vir como string (id/key da tag), dict ({"id":..,"key":..}) ou
        lista (para multi_select) — retorna um único id/key de tag."""
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("id") or value.get("key")
        if isinstance(value, list) and value:
            return TaskManager._extract_tag_ref(value[0])
        return None

    def _to_task(self, obj: Dict[str, Any]) -> Task:
        status_name = "?"
        prop_id = self.cfg.status_property_id
        prop_key = self.cfg.status_property_key
        for prop in obj.get("properties", []):
            matches = (
                (prop_id and prop.get("id") == prop_id)
                or (prop_key and prop.get("key") == prop_key)
                or prop.get("name", "").lower() == self.cfg.status_property_name.lower()
            )
            if not matches:
                continue
            raw_value = prop.get("select", prop.get("value"))
            tag_ref = self._extract_tag_ref(raw_value)
            if tag_ref:
                for name, tid in self.cfg.status_tag_ids.items():
                    if tid == tag_ref:
                        status_name = name
                        break
                else:
                    # não achamos pelo id cacheado: pode ser que o valor
                    # devolvido já seja o próprio nome/label da tag
                    if isinstance(raw_value, dict) and raw_value.get("name"):
                        status_name = raw_value["name"]
            break
        return Task(id=obj.get("id"), name=obj.get("name", ""), status=status_name, raw=obj)

    # ---------------------------------------------------------------- CRUD
    def create_task(self, name: str, description: str = "", status: Optional[str] = None) -> Task:
        status = status or self.cfg.status_options[0]
        obj = self.client.create_object(
            self.cfg.space_id,
            name=name,
            type_key=self.cfg.task_type_key,
            description=description,
            properties=[self._status_property(status)],
        )
        task = self._to_task(obj)
        self._sync_done_checkbox(task.id, status == self.cfg.done_status_name)
        return task

    def list_tasks(self) -> List[Task]:
        objs = self.client.list_objects(self.cfg.space_id, type_key=self.cfg.task_type_key)
        return [self._to_task(o) for o in objs]

    def rename_task(self, task_id: str, new_name: str) -> Task:
        obj = self.client.update_object(self.cfg.space_id, task_id, name=new_name)
        return self._to_task(obj)

    def set_status(self, task_id: str, status_name: str) -> Task:
        obj = self.client.update_object(
            self.cfg.space_id, task_id, properties=[self._status_property(status_name)]
        )
        self._sync_done_checkbox(task_id, status_name == self.cfg.done_status_name)
        return self._to_task(obj)

    def _sync_done_checkbox(self, task_id: str, is_done: bool) -> None:
        """Melhor esforço: mantém o checkbox nativo 'Done' do Anytype
        (usado em objetos de layout Action, como o Task embutido) alinhado
        com o status. Se essa propriedade não existir na sua instalação,
        a chamada falha silenciosamente — não deve travar a troca de status,
        que é a operação principal."""
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
    # Guardadas numa propriedade de TEXTO customizada (não no corpo/conteúdo
    # da página): atualizar o "body" de um objeto via API não é confiável
    # nesta versão do Anytype (a própria comunidade recomenda recriar o
    # objeto do zero para isso, o que mudaria o id da tarefa a cada nota —
    # inaceitável aqui, já que dependemos do id permanecer estável).
    def _require_notes_property(self) -> str:
        prop_ref = self.cfg.notes_property_key or self.cfg.notes_property_id
        if not prop_ref:
            raise SetupError(
                f"Não encontrei uma propriedade de texto chamada "
                f"'{self.cfg.notes_property_name}' no seu espaço. Crie uma "
                "propriedade do tipo 'Text' com esse nome no Anytype (em "
                "qualquer objeto do tipo de tarefa) e rode a preparação de "
                "novo (abra a aba Tarefas)."
            )
        return prop_ref

    def get_task_notes(self, task_id: str) -> str:
        """Texto atual do histórico de observações da tarefa."""
        prop_ref = self._require_notes_property()
        obj = self.client.get_object(self.cfg.space_id, task_id)
        for prop in obj.get("properties", []):
            matches = (
                (self.cfg.notes_property_id and prop.get("id") == self.cfg.notes_property_id)
                or (self.cfg.notes_property_key and prop.get("key") == self.cfg.notes_property_key)
            )
            if matches:
                return prop.get("text") or ""
        return ""

    def add_note(self, task_id: str, text: str) -> Task:
        """Acrescenta uma observação com data/hora ao final do histórico
        (não apaga o que já existia)."""
        prop_ref = self._require_notes_property()
        timestamp = _dt.datetime.now().strftime("%d/%m/%Y %H:%M")
        current = self.get_task_notes(task_id)
        entry = f"[{timestamp}] {text}"
        new_value = f"{current}\n{entry}" if current else entry
        obj = self.client.update_object(
            self.cfg.space_id, task_id, properties=[{"key": prop_ref, "text": new_value}]
        )
        return self._to_task(obj)
