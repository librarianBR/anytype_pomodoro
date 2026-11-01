"""Janela principal da interface gráfica (Flet): monta as telas, a
navegação entre elas e o modo mini."""
from __future__ import annotations

import flet as ft

from ..config import load_config
from .context import AppContext
from .pomodoro_view import PomodoroView
from .settings_view import SettingsView
from .tasks_view import TasksView
from .theme import apply_theme, muted

APP_TITLE = "Pomodoro + Anytype"
PAGE_PADDING = 24


def main(page: ft.Page) -> None:
    page.title = APP_TITLE
    # textos embutidos do Flutter (calendário, menus etc.) em português
    page.locale_configuration = ft.LocaleConfiguration(
        supported_locales=[ft.Locale("pt", "BR"), ft.Locale("en", "US")],
        current_locale=ft.Locale("pt", "BR"),
    )
    page.padding = PAGE_PADDING
    page.scroll = ft.ScrollMode.AUTO
    try:
        page.window.width, page.window.height = 920, 720
    except Exception:
        pass  # em modo web não existe "window"

    ctx = AppContext(page, load_config())
    apply_theme(page, ctx.config.gui)
    MainWindow(ctx).show()


class MainWindow:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        self.page = ctx.page
        self.pomodoro = PomodoroView(ctx)
        self.tasks = TasksView(ctx)
        self.settings = SettingsView(ctx)
        self.in_mini_mode = False

        self.content = ft.Container(expand=True)
        self.title = ft.Text(APP_TITLE, size=28, weight=ft.FontWeight.W_800, color=ft.Colors.PRIMARY)
        self.nav = ft.Row(
            [
                ft.Button("Pomodoro", icon=ft.Icons.TIMER, on_click=lambda e: self.go(self.pomodoro)),
                ft.Button("Tarefas", icon=ft.Icons.CHECKLIST, on_click=lambda e: self.go(self.tasks)),
                ft.Button("Configurações", icon=ft.Icons.SETTINGS, on_click=lambda e: self.go(self.settings)),
                ft.Button("Modo mini", icon=ft.Icons.PICTURE_IN_PICTURE_ALT, on_click=self.enter_mini_mode),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            wrap=True,
        )
        self.page.on_resize = self._on_resize

    def show(self) -> None:
        self.page.controls.clear()
        self.page.add(self.title, self.nav, ft.Divider(), self.content)
        self.go(self.pomodoro)

    def go(self, view) -> None:
        self.content.content = view.build()
        self.page.update()

    # ------------------------------------------------------------ modo mini
    # Mesma janela, só com a fase e o tempo, sempre por cima das outras.
    # Redimensionar a janela por código é "melhor esforço": em Wayland nativo
    # o pedido é ignorado (bug do Flet: github.com/flet-dev/flet/issues/5988),
    # então o usuário arrasta a borda e o tamanho é lembrado.
    def enter_mini_mode(self, e=None) -> None:
        gui = self.ctx.config.gui
        self.in_mini_mode = True
        if gui.mini_width and gui.mini_height:
            self.page.window.width, self.page.window.height = gui.mini_width, gui.mini_height
        self.page.window.always_on_top = True
        self.page.padding = 0
        self.page.controls.clear()
        self.page.add(ft.Container(
            content=ft.Column(
                [
                    self.pomodoro.mini_indicators(),
                    muted("Arraste a borda da janela para deixá-la pequena.", size=11, italic=True,
                          text_align=ft.TextAlign.CENTER),
                    ft.Button("Restaurar", icon=ft.Icons.OPEN_IN_FULL, on_click=self.exit_mini_mode),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            alignment=ft.Alignment.CENTER, expand=True, padding=16,
        ))
        self.page.update()

    def exit_mini_mode(self, e=None) -> None:
        self.in_mini_mode = False
        self.page.window.always_on_top = False
        self.page.padding = PAGE_PADDING
        self.show()

    def _on_resize(self, e) -> None:
        # no modo mini, guarda o tamanho que o usuário deixou (arrastando a
        # borda) para reaplicar da próxima vez
        window = self.page.window
        if self.in_mini_mode and window.width and window.height:
            self.ctx.config.gui.mini_width, self.ctx.config.gui.mini_height = window.width, window.height
            self.ctx.persist()


def run() -> None:
    ft.run(main)
