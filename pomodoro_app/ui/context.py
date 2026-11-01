"""O que todas as telas compartilham: a página, a configuração, o acesso ao
Anytype e a sessão Pomodoro — mais avisos e diálogos padronizados."""
from __future__ import annotations

from typing import Callable, List, Optional

import flet as ft

from ..anytype_client import AnytypeClient, AnytypeError
from ..config import AppConfig, save_config
from ..session import PomodoroSession
from ..task_manager import SetupError, TaskManager

# Erros esperados ao falar com o Anytype: viram um aviso, não um travamento.
ANYTYPE_ERRORS = (AnytypeError, SetupError)


class AppContext:
    def __init__(self, page: ft.Page, config: AppConfig):
        self.page = page
        self.config = config
        self.client = AnytypeClient(
            config.anytype.base_url, config.anytype.api_version, config.anytype.api_key
        )
        self.task_manager = TaskManager(self.client, config)
        # os callbacks da sessão são ligados pela tela Pomodoro
        self.session = PomodoroSession(config, self.task_manager)

    def persist(self) -> None:
        save_config(self.config)

    def update(self) -> None:
        self.page.update()

    def run_on_ui(self, fn: Callable, *args) -> None:
        """Agenda fn(*args) no loop da página. Necessário para eventos que
        vêm da thread do timer: mudar controles e chamar page.update() fora
        do loop da página não é aplicado de forma confiável."""
        self.page.loop.call_soon_threadsafe(fn, *args)

    # ------------------------------------------------------------- avisos
    def snack(self, message: str, error: bool = False) -> None:
        self.page.show_dialog(
            ft.SnackBar(
                content=ft.Text(message, color=ft.Colors.ON_ERROR if error else ft.Colors.ON_PRIMARY_CONTAINER),
                bgcolor=ft.Colors.ERROR if error else ft.Colors.PRIMARY_CONTAINER,
                open=True,
            )
        )
        self.page.update()

    def show_warnings(self, warnings: List[str]) -> None:
        for warning in warnings:
            self.snack(warning, error=True)

    def attempt(self, action: Callable[[], object], success: Optional[str] = None) -> bool:
        """Executa uma operação no Anytype: mostra `success` se der certo, ou
        a mensagem de erro. Devolve se deu certo."""
        try:
            action()
        except ANYTYPE_ERRORS as ex:
            self.snack(str(ex), error=True)
            return False
        if success:
            self.snack(success)
        return True

    # ------------------------------------------------------------ diálogos
    def dialog(
        self,
        title: str,
        content: ft.Control,
        actions: List[ft.Control],
        width: Optional[int] = None,
        height: Optional[int] = None,
        scrollable: bool = False,
    ) -> ft.AlertDialog:
        """Abre um diálogo modal e o devolve (para fechar com close())."""
        if width or height:
            content = ft.Container(content=content, width=width, height=height)
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(title), content=content, actions=actions,
            scrollable=scrollable, open=True,
        )
        self.page.show_dialog(dlg)
        self.page.update()
        return dlg

    def close(self, dlg: ft.AlertDialog) -> None:
        dlg.open = False
        self.page.update()

    def confirm(
        self,
        title: str,
        content: ft.Control,
        on_confirm: Callable[[], object],
        confirm_label: str = "Confirmar",
        cancel_label: str = "Cancelar",
        icon: Optional[str] = None,
        danger: bool = False,
    ) -> ft.AlertDialog:
        """Diálogo com Cancelar / Confirmar. O diálogo fecha antes de
        `on_confirm` rodar."""
        dlg: ft.AlertDialog

        def confirmed(e):
            self.close(dlg)
            on_confirm()

        style = {"bgcolor": ft.Colors.ERROR, "color": ft.Colors.ON_ERROR} if danger else {}
        dlg = self.dialog(title, content, [
            ft.TextButton(cancel_label, on_click=lambda e: self.close(dlg)),
            ft.Button(confirm_label, icon=icon, on_click=confirmed, **style),
        ])
        return dlg


def note_field(label: str = "Observação (opcional)") -> ft.TextField:
    """Campo de observação multilinha usado em vários diálogos."""
    return ft.TextField(label=label, multiline=True, min_lines=2, max_lines=4)


def field_text(control) -> str:
    """Valor de um TextField já sem espaços nas pontas."""
    return (control.value or "").strip()
