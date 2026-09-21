"""
Configuração da aplicação: tempos do Pomodoro e credenciais/parâmetros do Anytype.

O arquivo config.json é criado automaticamente na primeira execução (a partir
de config.example.json) e é onde ficam salvos os tempos configurados e, após
o pareamento, a api_key do Anytype — então não é preciso autenticar de novo
a cada execução.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Optional

from paths import app_data_dir, resource_path

CONFIG_PATH = os.path.join(app_data_dir(), "config.json")
EXAMPLE_CONFIG_PATH = resource_path("config.example.json")


@dataclass
class PomodoroConfig:
    work_minutes: float = 25
    short_break_minutes: float = 5
    long_break_minutes: float = 15
    # a cada quantos ciclos de trabalho ocorre uma pausa longa
    cycles_before_long_break: int = 4
    # toca um som (sino) no início de cada fase, nas duas interfaces
    sound_enabled: bool = True


@dataclass
class AnytypeConfig:
    # Endereço da API local do Anytype Desktop (roda no seu PC, offline)
    base_url: str = "http://localhost:31009"
    # Versão da API (cabeçalho Anytype-Version), ver developers.anytype.io
    api_version: str = "2025-11-08"
    # Preenchido automaticamente após o pareamento (fluxo de challenge/código)
    api_key: str = ""
    # Id do espaço (space) do Anytype onde as tarefas serão criadas
    space_id: str = ""
    # Nome do tipo de objeto usado para as tarefas (ex.: "Task", "Tarefa")
    task_type_name: str = "Task"
    task_type_key: str = ""
    # Nome da propriedade usada como status (tipo "select" no Anytype)
    status_property_name: str = "Status"
    status_property_id: str = ""
    status_property_key: str = ""
    # Nomes das opções (tags) de status, em ordem lógica do fluxo
    status_options: List[str] = field(default_factory=lambda: [
        "To Do", "In Progress", "Done",
    ])
    # Quais dessas opções a aplicação usa automaticamente ao iniciar uma
    # sessão vinculada a uma tarefa (in_progress) e ao perguntar se a
    # tarefa terminou (done). Precisam ser um dos nomes em status_options.
    in_progress_status_name: str = "In Progress"
    done_status_name: str = "Done"
    # cache: nome da tag -> id da tag, preenchido automaticamente
    status_tag_ids: dict = field(default_factory=dict)

    # Propriedade "checkbox" nativa que o Anytype usa em objetos de layout
    # "Action" (o Task embutido tem isso) — fica desmarcada por padrão e
    # NÃO é sincronizada automaticamente com o Status. Se existir, mantemos
    # ela marcada/desmarcada de acordo com o status ser "concluído" ou não.
    # "done" é o nome/chave interno usado pelo próprio Anytype para essa
    # propriedade em várias instalações — mantido como palpite de reserva
    # mesmo que não seja encontrada pelo nome ao configurar.
    done_checkbox_property_name: str = "Done"
    done_checkbox_property_id: str = ""
    done_checkbox_property_key: str = "done"

    # Propriedade de TEXTO usada para guardar o histórico de observações de
    # cada tarefa (precisa ser criada manualmente no Anytype, tipo "Text").
    # Não usamos o corpo/conteúdo da página para isso porque atualizar o
    # "body" de um objeto via API não é confiável nesta versão do Anytype.
    notes_property_name: str = "Notes"
    notes_property_id: str = ""
    notes_property_key: str = ""


@dataclass
class GuiConfig:
    # Tamanho da janela lembrado da última vez que o "modo mini" foi usado
    # (você redimensiona manualmente arrastando a borda; da próxima vez que
    # abrir o modo mini, tentamos aplicar esse mesmo tamanho automaticamente
    # — pode não funcionar em todo ambiente Linux/Wayland, é melhor esforço).
    mini_width: Optional[float] = None
    mini_height: Optional[float] = None


@dataclass
class AppConfig:
    pomodoro: PomodoroConfig = field(default_factory=PomodoroConfig)
    anytype: AnytypeConfig = field(default_factory=AnytypeConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)

    @staticmethod
    def from_dict(data: dict) -> "AppConfig":
        return AppConfig(
            pomodoro=PomodoroConfig(**data.get("pomodoro", {})),
            anytype=AnytypeConfig(**data.get("anytype", {})),
            gui=GuiConfig(**data.get("gui", {})),
        )

    def to_dict(self) -> dict:
        return {
            "pomodoro": asdict(self.pomodoro),
            "anytype": asdict(self.anytype),
            "gui": asdict(self.gui),
        }


def load_config(path: str = CONFIG_PATH) -> AppConfig:
    if not os.path.exists(path):
        # primeira execução: parte do exemplo (ou de um config padrão)
        if os.path.exists(EXAMPLE_CONFIG_PATH):
            with open(EXAMPLE_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = AppConfig().to_dict()
        save_config(AppConfig.from_dict(data), path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    config = AppConfig.from_dict(data)
    if _migrate_legacy_status_names(config):
        save_config(config, path)
    return config


# Nomes de status usados em versões anteriores desta aplicação (em
# português). Se o config.json do usuário ainda tiver exatamente esse
# conjunto (ou seja, ele nunca customizou), migramos automaticamente para
# os nomes em inglês no padrão do Anytype, sem exigir edição manual.
_LEGACY_STATUS_MAP = {
    "A Fazer": "To Do",
    "Fazendo": "In Progress",
    "Feito": "Done",
    "Arquivado": "Done",  # não há mais um 4º status por padrão
}


def _migrate_legacy_status_names(config: AppConfig) -> bool:
    old_options = config.anytype.status_options
    if not old_options or old_options == ["To Do", "In Progress", "Done"]:
        return False
    if not all(name in _LEGACY_STATUS_MAP for name in old_options):
        return False  # o usuário customizou para algo que não reconhecemos: não mexe
    config.anytype.status_options = ["To Do", "In Progress", "Done"]
    config.anytype.in_progress_status_name = "In Progress"
    config.anytype.done_status_name = "Done"
    config.anytype.status_tag_ids = {}  # força re-descoberta/criação das tags novas
    return True


def save_config(config: AppConfig, path: str = CONFIG_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
