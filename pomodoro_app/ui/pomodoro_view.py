"""Tela "Pomodoro": timer, controles da sessão e tarefa vinculada. Também
fornece os indicadores compactos usados pelo modo mini."""
from __future__ import annotations

from typing import Optional

import flet as ft

from ..formatting import format_mmss
from ..pomodoro_timer import PHASE_LABELS, Phase, PomodoroStatus
from .context import ANYTYPE_ERRORS, AppContext, field_text, note_field
from .theme import PHASE_COLORS, PHASE_ICONS, heading, muted


class PomodoroView:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.session = ctx.session
        self.session.on_phase_start = self._on_phase_start
        self.session.on_tick = self._on_tick
        self.session.on_focus_end = self._on_focus_end

        # indicadores da fase (versões normal e compacta, do modo mini)
        self.phase_icon = ft.Icon(ft.Icons.TIMER, size=30)
        self.phase_text = ft.Text(size=26, weight=ft.FontWeight.BOLD)
        self.time_text = ft.Text(size=72, weight=ft.FontWeight.BOLD)
        self.mini_phase_icon = ft.Icon(ft.Icons.TIMER, size=18)
        self.mini_time_text = ft.Text(size=26, weight=ft.FontWeight.BOLD)
        self.cycle_text = muted(size=15)
        self.progress = ft.ProgressBar(
            value=0, width=420, bar_height=8, border_radius=8, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST
        )

        # tarefa vinculada
        self.linked_task_text = ft.Text("", italic=True, size=13)
        self.task_dropdown = ft.Dropdown(
            label="Vincular a uma tarefa (opcional)", options=[], width=420,
            on_select=lambda e: self.link(self.task_dropdown.value),
        )
        self.unlink_btn = ft.Button("Desvincular", icon=ft.Icons.LINK_OFF, on_click=lambda e: self.link(None))
        self.complete_btn = ft.Button("Concluir tarefa", icon=ft.Icons.TASK_ALT, on_click=self._ask_complete)

        # controles do timer
        self.start_btn = ft.Button("Iniciar", icon=ft.Icons.PLAY_ARROW, on_click=self._start)
        self.pause_btn = ft.Button("Pausar", icon=ft.Icons.PAUSE, on_click=self._pause)
        self.resume_btn = ft.Button("Retomar", icon=ft.Icons.PLAY_ARROW, on_click=self._resume)
        self.restart_btn = ft.Button("Reiniciar fase", icon=ft.Icons.RESTART_ALT, on_click=self._restart)
        self.skip_btn = ft.Button("Pular fase", icon=ft.Icons.SKIP_NEXT, on_click=lambda e: self.session.skip())
        self.stop_btn = ft.Button("Parar", icon=ft.Icons.STOP, on_click=self._stop)

        self._show_phase(Phase.IDLE, 0)
        self._set_running(False)
        self._update_link_buttons()

    # ------------------------------------------------------------ desenho
    def build(self) -> ft.Control:
        self.refresh_task_dropdown()
        return ft.Column(
            [
                heading("Sessão Pomodoro", 22),
                ft.Container(height=10),
                ft.Row([self.phase_icon, self.phase_text], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                self.time_text,
                self.cycle_text,
                self.progress,
                ft.Container(height=10),
                ft.Row(
                    [self.task_dropdown, self.unlink_btn, self.complete_btn],
                    alignment=ft.MainAxisAlignment.CENTER, wrap=True,
                ),
                self.linked_task_text,
                ft.Container(height=10),
                ft.Row(
                    [self.start_btn, self.pause_btn, self.resume_btn, self.restart_btn, self.skip_btn, self.stop_btn],
                    alignment=ft.MainAxisAlignment.CENTER, wrap=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

    def mini_indicators(self) -> ft.Row:
        return ft.Row([self.mini_phase_icon, self.mini_time_text], alignment=ft.MainAxisAlignment.CENTER, spacing=8)

    def _show_phase(self, phase: Phase, total_seconds: int, cycle: Optional[int] = None) -> None:
        """Ícone, nome, tempo e cor da fase (normal e modo mini)."""
        color = PHASE_COLORS[phase]
        for icon in (self.phase_icon, self.mini_phase_icon):
            icon.icon = PHASE_ICONS[phase]
        self.phase_text.value = PHASE_LABELS[phase]
        for control in (self.phase_icon, self.phase_text, self.mini_phase_icon, self.time_text, self.mini_time_text):
            control.color = color
        self.progress.color = color
        self.progress.value = 0
        self._show_time(total_seconds)
        self.cycle_text.value = (
            f"Ciclo {cycle} — pausa longa a cada {self.ctx.config.pomodoro.cycles_before_long_break} ciclos"
            if cycle else ""
        )

    def _show_time(self, seconds: int) -> None:
        self.time_text.value = self.mini_time_text.value = format_mmss(seconds)

    def _set_running(self, running: bool) -> None:
        self.start_btn.disabled = running
        for btn in (self.pause_btn, self.resume_btn, self.restart_btn, self.skip_btn, self.stop_btn):
            btn.disabled = not running

    # ------------------------------------ eventos da sessão (thread do timer)
    # Os eventos chegam à tela pela fila do loop da interface; um evento que
    # já estava na fila quando o usuário clicou em "Parar" é descartado, senão
    # sobrescreveria a tela zerada com o tempo antigo.
    def _on_phase_start(self, phase: Phase, total_seconds: int, cycle: int) -> None:
        def apply():
            if self.session.is_running:
                self._show_phase(phase, total_seconds, cycle)
                self.ctx.update()
        self.ctx.run_on_ui(apply)

    def _on_tick(self, status: PomodoroStatus) -> None:
        def apply():
            if self.session.is_running:
                self._show_time(status.remaining_seconds)
                self.progress.value = status.progress
                self.ctx.update()
        self.ctx.run_on_ui(apply)

    def _on_focus_end(self, cycle: int) -> None:
        self.ctx.run_on_ui(self._ask_focus_done)

    # ------------------------------------------------------------- timer
    def _start(self, e):
        self.session.start()
        self._set_running(True)
        self.ctx.update()

    def _pause(self, e):
        self.session.pause()
        self.ctx.snack("Pausado.")

    def _resume(self, e):
        self.session.resume()
        self.ctx.snack("Retomado.")

    def _restart(self, e):
        self.session.restart_phase()
        self.ctx.snack("Fase reiniciada.")

    def _stop(self, e):
        # parar não desfaz o vínculo com a tarefa (ver PomodoroSession.stop)
        self.session.stop()
        self._show_phase(Phase.IDLE, 0)
        self._set_running(False)
        self.ctx.update()

    # ---------------------------------------------------------- tarefas
    def refresh_task_dropdown(self) -> None:
        """Lista as tarefas não concluídas, mantendo a vinculada selecionada."""
        self.task_dropdown.options = []
        self.task_dropdown.value = None
        if not self.ctx.config.anytype.space_id:
            return
        try:
            self.ctx.task_manager.setup()
            tasks = self.ctx.task_manager.list_pending_tasks()
        except ANYTYPE_ERRORS:
            return  # ainda não configurado: o dropdown só fica vazio
        self.task_dropdown.options = [ft.DropdownOption(key=t.id, text=f"[{t.status}] {t.name}") for t in tasks]
        linked = self.session.linked_task_id
        if any(o.key == linked for o in self.task_dropdown.options):
            self.task_dropdown.value = linked

    def _linked_task_name(self) -> str:
        """Nome da tarefa vinculada, sem o "[status]" do dropdown — esse status
        foi lido ao carregar a lista e fica desatualizado após o vínculo."""
        task_id = self.session.linked_task_id
        text = next((o.text for o in self.task_dropdown.options if o.key == task_id), "")
        if text.startswith("[") and "] " in text:
            text = text.split("] ", 1)[1]
        return f"'{text}'" if text else "a tarefa vinculada"

    def _update_link_buttons(self) -> None:
        has_task = bool(self.session.linked_task_id)
        self.unlink_btn.disabled = self.complete_btn.disabled = not has_task
        self.task_dropdown.value = self.session.linked_task_id
        self.linked_task_text.value = f"Vinculada a: {self._linked_task_name()}" if has_task else ""

    def link(self, task_id: Optional[str]) -> None:
        self.ctx.show_warnings(self.session.link(task_id))
        self._update_link_buttons()
        self.ctx.update()

    def _after_completed(self, message: str) -> None:
        """A tarefa saiu da sessão: o dropdown volta vazio, sem ela na lista."""
        self.refresh_task_dropdown()
        self._update_link_buttons()
        self.ctx.snack(message)

    def _ask_complete(self, e=None):
        """Botão "Concluir tarefa": concluir a qualquer momento."""
        if not self.session.linked_task_id:
            return
        done = self.ctx.config.anytype.done_status_name
        note = note_field()

        def complete():
            if self.ctx.attempt(lambda: self.session.complete(self.session.completion_note(field_text(note)))):
                self._after_completed(f"Tarefa marcada como '{done}'. Escolha a próxima quando quiser.")

        self.ctx.confirm(
            "Concluir tarefa",
            ft.Column(
                [
                    ft.Text(f"Marcar {self._linked_task_name()} como '{done}'?"),
                    muted("Ela sai da sessão e o timer continua rodando normalmente.", size=12),
                    note,
                ],
                tight=True, spacing=10,
            ),
            complete, confirm_label="Concluir", icon=ft.Icons.TASK_ALT,
        )

    def _ask_focus_done(self):
        """Fim de um ciclo de foco com tarefa vinculada (o timer está pausado
        pela sessão até finish_focus)."""
        self.pause_btn.disabled = self.resume_btn.disabled = True
        done = self.ctx.config.anytype.done_status_name
        note = note_field()

        def answer(mark_done: bool):
            self.ctx.close(dlg)
            ok = self.ctx.attempt(lambda: self.session.finish_focus(field_text(note), mark_done=mark_done))
            self.pause_btn.disabled = self.resume_btn.disabled = False
            if ok and mark_done:
                self._after_completed(f"Tarefa marcada como '{done}' e observação registrada.")
            elif ok:
                self.ctx.snack("Observação registrada na tarefa.")
            self.ctx.update()

        dlg = self.ctx.dialog(
            "Ciclo de foco terminado",
            ft.Column([ft.Text(f"Marcar a tarefa vinculada como '{done}'?"), note], tight=True, spacing=10),
            [
                ft.TextButton("Agora não", on_click=lambda e: answer(False)),
                ft.Button("Sim", on_click=lambda e: answer(True)),
            ],
        )
