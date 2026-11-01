"""Busca, filtro e ordenação da lista de tarefas (aba Tarefas). Funções
puras, sem interface: recebem a lista já carregada do Anytype."""
from __future__ import annotations

import unicodedata
from typing import List, Sequence, Tuple

from .task_manager import Task

# Filtro de status: "" = todos; STATUS_PENDING = tudo que não está concluído;
# qualquer outro valor = exatamente aquele status.
STATUS_ALL = ""
STATUS_PENDING = "__pending__"

SORT_OPTIONS: List[Tuple[str, str]] = [
    ("created_desc", "Criação: mais recentes primeiro"),
    ("created_asc", "Criação: mais antigas primeiro"),
    ("name_asc", "Título: A → Z"),
    ("name_desc", "Título: Z → A"),
    ("due_asc", "Entrega: mais próxima primeiro"),
]
SORT_KEYS = {key for key, _ in SORT_OPTIONS}
DEFAULT_SORT = "created_desc"

LIMIT_OPTIONS = [10, 25, 50, 100, 0]  # 0 = todas
DEFAULT_LIMIT = 25


def normalize(text: str) -> str:
    """Minúsculas e sem acentos: "Linguística" e "linguistica" ficam iguais."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def matches_status(task: Task, status_filter: str, done_status_name: str) -> bool:
    if status_filter == STATUS_ALL:
        return True
    if status_filter == STATUS_PENDING:
        return task.status != done_status_name
    return task.status == status_filter


def sort_tasks(tasks: Sequence[Task], sort: str) -> List[Task]:
    """Ordena sem alterar a lista original. Tarefas sem a data usada na
    ordenação (criação ou entrega) vão sempre para o fim."""
    if sort in ("created_desc", "created_asc"):
        dated = sorted((t for t in tasks if t.created), key=lambda t: t.created, reverse=sort == "created_desc")
        return dated + [t for t in tasks if not t.created]
    if sort == "due_asc":
        with_due = sorted((t for t in tasks if t.due), key=lambda t: t.due)
        return with_due + [t for t in tasks if not t.due]
    return sorted(tasks, key=lambda t: normalize(t.name), reverse=sort == "name_desc")


def filter_tasks(
    tasks: Sequence[Task],
    query: str = "",
    status_filter: str = STATUS_ALL,
    done_status_name: str = "Done",
    sort: str = DEFAULT_SORT,
) -> List[Task]:
    """Tarefas cujo título contém `query` (sem diferenciar maiúsculas nem
    acentos) e que passam no filtro de status, já ordenadas."""
    needle = normalize(query).strip()
    selected = [
        t for t in tasks
        if (not needle or needle in normalize(t.name))
        and matches_status(t, status_filter, done_status_name)
    ]
    return sort_tasks(selected, sort)


def limit_tasks(tasks: Sequence[Task], limit: int) -> List[Task]:
    """As primeiras `limit` tarefas (0 = todas)."""
    return list(tasks[:limit]) if limit else list(tasks)
