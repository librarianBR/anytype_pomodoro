"""Tela "Tarefas": criar tarefas (com data de entrega e história de usuário),
buscar/filtrar/ordenar a lista e editar cada tarefa."""
from __future__ import annotations

import datetime as _dt
import json
from typing import List, Optional

import flet as ft

from .. import task_filters as tf
from .. import user_story
from ..formatting import format_date, format_datetime
from ..task_manager import Task
from .context import ANYTYPE_ERRORS, AppContext, field_text, note_field
from .theme import card, heading, muted


class TasksView:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.tasks: List[Task] = []  # cache: filtros não consultam o Anytype de novo
        self.new_task_due: Optional[_dt.date] = None
        gui = ctx.config.gui

        # ---- formulário de nova tarefa
        self.name_field = ft.TextField(label="Nova tarefa", expand=True)
        self.status_field = ft.Dropdown(label="Status inicial", width=160)
        self.due_button = ft.OutlinedButton("Data de entrega", icon=ft.Icons.CALENDAR_MONTH, on_click=self._open_due_picker)
        self.due_clear_btn = ft.IconButton(
            ft.Icons.CLOSE, tooltip="Remover data de entrega", visible=False,
            on_click=lambda e: self._set_due(None),
        )
        self.story_field = ft.TextField(
            label="História de usuário (opcional)", hint_text=user_story.HINT,
            multiline=True, min_lines=2, max_lines=6, expand=True,
        )
        self.story_template_btn = ft.TextButton(
            "Usar modelo de história", icon=ft.Icons.AUTO_STORIES, on_click=self._use_story_template,
            tooltip="Preenche com o formato de história de usuário do Scrum: substitua os campos entre < >",
        )

        # ---- filtros (ordenação, status e quantidade ficam salvos no config)
        self.filter_title = ft.TextField(
            label="Buscar no título", prefix_icon=ft.Icons.SEARCH, width=260, dense=True,
            on_change=lambda e: self.render(),
        )
        self.filter_status = ft.Dropdown(label="Status", width=190, dense=True, on_select=self._on_filter_change)
        self.filter_sort = ft.Dropdown(
            label="Ordenar por", width=330, dense=True, on_select=self._on_filter_change,
            options=[ft.DropdownOption(key=k, text=t) for k, t in tf.SORT_OPTIONS],
            value=gui.tasks_sort if gui.tasks_sort in tf.SORT_KEYS else tf.DEFAULT_SORT,
        )
        self.filter_limit = ft.Dropdown(
            label="Mostrar", width=120, dense=True, on_select=self._on_filter_change,
            options=[ft.DropdownOption(key=str(n), text=str(n) if n else "Todas") for n in tf.LIMIT_OPTIONS],
            value=str(gui.tasks_limit if gui.tasks_limit in tf.LIMIT_OPTIONS else tf.DEFAULT_LIMIT),
        )
        self.count_text = muted()
        self.list_view = ft.ListView(expand=True, spacing=8, height=420)

    # ------------------------------------------------------------ desenho
    def build(self) -> ft.Control:
        self._refresh_status_options()  # a lista de status pode ter mudado nas Configurações
        self.refresh()
        return ft.Column(
            [
                heading("Tarefas (Anytype)", 22),
                # Sem wrap=True: o campo de nome usa expand=True, e o Flutter não
                # aceita filho "expandido" numa linha que quebra (a tela vira um
                # quadro cinza).
                ft.Row([
                    self.name_field, self.status_field, self.due_button, self.due_clear_btn,
                    ft.Button("Criar", icon=ft.Icons.ADD, on_click=self._create),
                ]),
                ft.Row([self.story_field, self.story_template_btn], vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Divider(height=1),
                ft.Row([self.filter_title, self.filter_status, self.filter_sort, self.filter_limit], wrap=True, spacing=10),
                ft.Row(
                    [
                        ft.Button("Atualizar lista", icon=ft.Icons.REFRESH, on_click=lambda e: self.refresh()),
                        ft.TextButton("Limpar filtros", icon=ft.Icons.FILTER_ALT_OFF, on_click=self._clear_filters),
                        self.count_text,
                    ],
                    wrap=True,
                ),
                self.list_view,
            ],
            spacing=12,
            # Sem scroll: a lista (ListView com expand=True) já rola sozinha, e
            # "expandir" dentro de uma coluna rolável é erro de layout no Flutter.
            expand=True,
        )

    def _refresh_status_options(self) -> None:
        cfg, gui = self.ctx.config.anytype, self.ctx.config.gui
        statuses = [ft.DropdownOption(key=s, text=s) for s in cfg.status_options]
        self.status_field.options = list(statuses)
        if self.status_field.value not in cfg.status_options:
            self.status_field.value = cfg.status_options[0] if cfg.status_options else None
        self.filter_status.options = [
            ft.DropdownOption(key=tf.STATUS_ALL, text="Todos"),
            ft.DropdownOption(key=tf.STATUS_PENDING, text="Não concluídas"),
            *statuses,
        ]
        valid = {o.key for o in self.filter_status.options}
        self.filter_status.value = gui.tasks_status_filter if gui.tasks_status_filter in valid else tf.STATUS_ALL

    # ---------------------------------------------------------- carregar
    def _show_message(self, text: str, error: bool = False) -> None:
        self.list_view.controls = [ft.Text(text, color=ft.Colors.ERROR if error else None)]
        self.count_text.value = ""
        self.ctx.update()

    def refresh(self) -> None:
        """Recarrega as tarefas do Anytype e redesenha com os filtros atuais."""
        self.tasks = []
        if not self.ctx.config.anytype.space_id:
            self._show_message("Escolha um espaço do Anytype nas Configurações primeiro.")
            return
        try:
            self.ctx.task_manager.setup()
            self.tasks = self.ctx.task_manager.list_tasks()
        except ANYTYPE_ERRORS as ex:
            self._show_message(f"Não foi possível carregar as tarefas: {ex}", error=True)
            return
        self.render()

    def render(self) -> None:
        """Redesenha a lista a partir do cache, aplicando os filtros."""
        visible = tf.filter_tasks(
            self.tasks,
            query=self.filter_title.value or "",
            status_filter=self.filter_status.value or tf.STATUS_ALL,
            done_status_name=self.ctx.config.anytype.done_status_name,
            sort=self.filter_sort.value or tf.DEFAULT_SORT,
        )
        shown = tf.limit_tasks(visible, int(self.filter_limit.value or 0))
        if not self.tasks:
            self.list_view.controls = [ft.Text("(nenhuma tarefa)")]
        elif not visible:
            self.list_view.controls = [ft.Text("(nenhuma tarefa corresponde aos filtros)")]
        else:
            self.list_view.controls = [self._task_row(t) for t in shown]
        total = f" — {len(self.tasks)} no total" if len(visible) != len(self.tasks) else ""
        self.count_text.value = f"Mostrando {len(shown)} de {len(visible)} tarefa(s){total}" if self.tasks else ""
        self.ctx.update()

    def _on_filter_change(self, e=None) -> None:
        gui = self.ctx.config.gui
        gui.tasks_sort = self.filter_sort.value or tf.DEFAULT_SORT
        gui.tasks_status_filter = self.filter_status.value or tf.STATUS_ALL
        gui.tasks_limit = int(self.filter_limit.value or 0)
        self.ctx.persist()
        self.render()

    def _clear_filters(self, e=None) -> None:
        self.filter_title.value = ""
        self.filter_status.value = tf.STATUS_ALL
        self.filter_sort.value = tf.DEFAULT_SORT
        self.filter_limit.value = str(tf.DEFAULT_LIMIT)
        self._on_filter_change()

    # -------------------------------------------------------- uma tarefa
    def _task_row(self, task: Task) -> ft.Control:
        cfg = self.ctx.config.anytype
        status_dd = ft.Dropdown(
            width=175,
            value=task.status if task.status in cfg.status_options else None,
            options=[ft.DropdownOption(key=s, text=s) for s in cfg.status_options],
        )
        status_dd.on_select = lambda e: self._change_status(task, status_dd.value)

        info = [ft.TextSpan(f"Criada em {format_datetime(task.created)}" if task.created else "Data de criação desconhecida")]
        if task.due:
            info.append(ft.TextSpan(f"  ·  Entrega: {format_date(task.due)}"))
            if task.due < _dt.date.today() and task.status != cfg.done_status_name:
                info.append(ft.TextSpan("  (atrasada)", style=ft.TextStyle(color=ft.Colors.ERROR, weight=ft.FontWeight.BOLD)))
        texts = [
            ft.Text(task.name, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(spans=info, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
        ]
        story = task.description.strip()
        if story:  # só a primeira linha da história; o resto no tooltip
            texts.append(ft.Text(story.splitlines()[0], size=12, italic=True, max_lines=1,
                                 overflow=ft.TextOverflow.ELLIPSIS, tooltip=story))

        def action(icon, tooltip, handler):
            return ft.IconButton(icon, tooltip=tooltip, on_click=lambda e: handler(task))

        return card(ft.Row([
            ft.Column(texts, spacing=2, expand=True),
            status_dd,
            action(ft.Icons.EDIT, "Renomear", self._rename_dialog),
            action(ft.Icons.EDIT_NOTE, "Observações", self._notes_dialog),
            action(ft.Icons.DELETE, "Excluir", self._delete_dialog),
            action(ft.Icons.INFO_OUTLINE, "Ver JSON bruto", self._raw_json_dialog),
        ]))

    def _change_status(self, task: Task, status: str) -> None:
        self.ctx.attempt(
            lambda: self.ctx.task_manager.set_status(task.id, status),
            f"Status de '{task.name}' agora é '{status}'.",
        )
        self.refresh()

    def _rename_dialog(self, task: Task) -> None:
        field = ft.TextField(label="Novo nome", value=task.name)

        def rename():
            new_name = field_text(field)
            if new_name and self.ctx.attempt(lambda: self.ctx.task_manager.rename_task(task.id, new_name), "Tarefa renomeada."):
                self.refresh()

        self.ctx.confirm("Renomear tarefa", field, rename, confirm_label="Salvar")

    def _delete_dialog(self, task: Task) -> None:
        def delete():
            if self.ctx.attempt(lambda: self.ctx.task_manager.delete_task(task.id), "Tarefa excluída."):
                self.refresh()

        self.ctx.confirm(
            "Excluir tarefa", ft.Text(f"Tem certeza que deseja excluir '{task.name}'?"),
            delete, confirm_label="Excluir", danger=True,
        )

    def _notes_dialog(self, task: Task) -> None:
        tm = self.ctx.task_manager
        try:
            notes = tm.get_task_notes(task.id)
        except ANYTYPE_ERRORS as ex:
            self.ctx.snack(str(ex), error=True)
            return
        history = ft.Text(notes or "(nenhuma observação registrada ainda)")
        new_note = note_field("Nova observação")

        def add(e):
            text = field_text(new_note)
            if text and self.ctx.attempt(lambda: tm.add_note(task.id, text), "Observação adicionada."):
                history.value = tm.get_task_notes(task.id)
                new_note.value = ""
                self.ctx.update()

        dlg = self.ctx.dialog(
            f"Observações — {task.name}",
            ft.Column([history, ft.Divider(), new_note], spacing=10, tight=True),
            [
                ft.TextButton("Fechar", on_click=lambda e: self.ctx.close(dlg)),
                ft.Button("Adicionar", icon=ft.Icons.ADD, on_click=add),
            ],
            width=600, height=400, scrollable=True,
        )

    def _raw_json_dialog(self, task: Task) -> None:
        dlg = self.ctx.dialog(
            f"JSON bruto — {task.name}",
            ft.Text(json.dumps(task.raw, indent=2, ensure_ascii=False), selectable=True),
            [ft.TextButton("Fechar", on_click=lambda e: self.ctx.close(dlg))],
            width=600, height=400, scrollable=True,
        )

    # ------------------------------------------------------- nova tarefa
    def _set_due(self, value: Optional[_dt.date]) -> None:
        self.new_task_due = value
        self.due_button.content = f"Entrega: {format_date(value)}" if value else "Data de entrega"
        self.due_clear_btn.visible = bool(value)
        self.ctx.update()

    def _open_due_picker(self, e) -> None:
        def picked(ev):
            value = ev.control.value  # o DatePicker devolve um datetime; só o dia interessa
            self._set_due(value.date() if isinstance(value, _dt.datetime) else value)

        today = _dt.date.today()
        self.ctx.page.show_dialog(ft.DatePicker(
            value=self.new_task_due or today,
            first_date=today - _dt.timedelta(days=365),
            last_date=today + _dt.timedelta(days=365 * 5),
            help_text="Data de entrega", cancel_text="Cancelar", confirm_text="OK",
            locale=ft.Locale("pt", "BR"),
            on_change=picked,
        ))

    def _use_story_template(self, e) -> None:
        if field_text(self.story_field):
            self.ctx.snack("O campo de história já tem texto — apague-o para usar o modelo.", error=True)
            return
        self.story_field.value = user_story.TEMPLATE
        self.ctx.update()
        self.story_field.focus()

    def _create(self, e) -> None:
        name, story = field_text(self.name_field), field_text(self.story_field)
        if not name:
            self.ctx.snack("Digite um nome para a tarefa.", error=True)
            return
        if user_story.has_placeholders(story):
            self.ctx.snack("Substitua os campos entre < > do modelo de história (ou apague a parte que não usar).", error=True)
            return
        tm = self.ctx.task_manager

        def create():
            tm.setup()
            tm.create_task(name, description=story, status=self.status_field.value, due=self.new_task_due)

        if self.ctx.attempt(create, "Tarefa criada."):
            self.name_field.value = self.story_field.value = ""
            self._set_due(None)
            self.refresh()
