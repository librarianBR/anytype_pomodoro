"""Tela "Configurações": aparência, tempos e sons do Pomodoro, e a conexão
com o Anytype (pareamento, espaço, nomes de tipo/propriedade/status)."""
from __future__ import annotations

from typing import Callable

import flet as ft

from ..anytype_client import NO_SPACES_MESSAGE, PAIRING_HINT, AnytypeError
from ..pomodoro_timer import Phase
from ..sounds import COUNTDOWN_SECONDS, play_countdown_demo, play_sound, sound_path_for_phase
from .context import AppContext, field_text
from .theme import DEFAULT_THEME, DEFAULT_THEME_MODE, THEME_MODES, THEMES, apply_theme, heading


def _text_field(label: str, value, width: int) -> ft.TextField:
    return ft.TextField(label=label, value=str(value), width=width)


class SettingsView:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx
        p, a, gui = ctx.config.pomodoro, ctx.config.anytype, ctx.config.gui

        # ---- aparência (vale na hora)
        self.theme_dropdown = ft.Dropdown(
            label="Paleta de cores", width=220, leading_icon=ft.Icons.PALETTE,
            options=[self._theme_option(k) for k in THEMES],
            value=gui.theme if gui.theme in THEMES else DEFAULT_THEME,
            on_select=self._on_theme_change,
        )
        self.theme_mode = ft.SegmentedButton(
            segments=[ft.Segment(value=k, label=label, icon=icon) for k, (label, _, icon) in THEME_MODES.items()],
            selected=[gui.theme_mode if gui.theme_mode in THEME_MODES else DEFAULT_THEME_MODE],
            allow_empty_selection=False, allow_multiple_selection=False,
            on_change=self._on_theme_change,
        )

        # ---- pomodoro
        self.work_field = _text_field("Foco (min)", p.work_minutes, 140)
        self.short_field = _text_field("Pausa curta (min)", p.short_break_minutes, 160)
        self.long_field = _text_field("Pausa longa (min)", p.long_break_minutes, 160)
        self.cycles_field = _text_field("Ciclos até pausa longa", p.cycles_before_long_break, 200)
        self.sound_checkbox = ft.Checkbox(
            label=f"Tocar sons (início de cada fase e contagem regressiva nos últimos {COUNTDOWN_SECONDS} s)",
            value=p.sound_enabled,
        )

        # ---- anytype
        self.pairing_text = ft.Text()
        self._show_pairing()
        self.space_dropdown = ft.Dropdown(label="Espaço do Anytype", width=320, options=[], on_select=self._select_space)
        self.base_url_field = _text_field("URL base da API", a.base_url, 320)
        self.api_version_field = _text_field("Versão da API", a.api_version, 200)
        self.task_type_field = _text_field("Nome do tipo de tarefa", a.task_type_name, 250)
        self.status_prop_field = _text_field("Nome da propriedade de status", a.status_property_name, 280)
        self.status_options_field = _text_field("Opções de status (separadas por vírgula)", ", ".join(a.status_options), 500)
        self.in_progress_field = _text_field("Status usado como 'em andamento'", a.in_progress_status_name, 240)
        self.done_field = _text_field("Status usado como 'concluído'", a.done_status_name, 240)

    def build(self) -> ft.Control:
        def sound_button(label: str, play: Callable[[], None]) -> ft.Button:
            return ft.Button(label, icon=ft.Icons.PLAY_ARROW, on_click=lambda e: play())

        def phase_sound(phase: Phase) -> Callable[[], None]:
            return lambda: play_sound(sound_path_for_phase(phase.value))

        return ft.Column(
            [
                heading("Aparência"),
                ft.Row([self.theme_dropdown, self.theme_mode], spacing=16, wrap=True,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Divider(),
                heading("Configurações do Pomodoro"),
                ft.Row([self.work_field, self.short_field, self.long_field, self.cycles_field]),
                self.sound_checkbox,
                ft.Row(
                    [
                        ft.Text("Testar sons:"),
                        sound_button("Foco", phase_sound(Phase.WORK)),
                        sound_button("Pausa curta", phase_sound(Phase.SHORT_BREAK)),
                        sound_button("Pausa longa", phase_sound(Phase.LONG_BREAK)),
                        sound_button("Contagem regressiva", play_countdown_demo),
                    ],
                    wrap=True,
                ),
                ft.Button("Salvar tempos", icon=ft.Icons.SAVE, on_click=self._save_pomodoro),
                ft.Divider(),
                heading("Conexão com o Anytype"),
                ft.Row([self.pairing_text, ft.Button("Parear com o Anytype", icon=ft.Icons.LINK, on_click=self._pair)]),
                ft.Row([self.space_dropdown, ft.Button("Carregar espaços", icon=ft.Icons.REFRESH, on_click=self._load_spaces)]),
                ft.Row([self.base_url_field, self.api_version_field]),
                ft.Row([self.task_type_field, self.status_prop_field]),
                self.status_options_field,
                ft.Row([self.in_progress_field, self.done_field]),
                ft.Row(
                    [
                        ft.Button("Salvar configurações", icon=ft.Icons.SAVE, on_click=self._save_anytype),
                        ft.Button("Testar / preparar (tipo, propriedade, tags)", icon=ft.Icons.CHECK, on_click=self._test_setup),
                    ],
                    wrap=True,
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

    # ---------------------------------------------------------- aparência
    @staticmethod
    def _theme_option(key: str) -> ft.DropdownOption:
        label, seed = THEMES[key]
        swatch = ft.Container(width=16, height=16, border_radius=8, bgcolor=seed)
        return ft.DropdownOption(key=key, text=label, content=ft.Row([swatch, ft.Text(label)], spacing=10))

    def _on_theme_change(self, e=None) -> None:
        gui = self.ctx.config.gui
        gui.theme = self.theme_dropdown.value or DEFAULT_THEME
        gui.theme_mode = (self.theme_mode.selected or [DEFAULT_THEME_MODE])[0]
        apply_theme(self.ctx.page, gui)
        self.ctx.persist()
        self.ctx.update()

    # ----------------------------------------------------------- pomodoro
    def _save_pomodoro(self, e) -> None:
        try:
            values = (
                float(field_text(self.work_field).replace(",", ".")),
                float(field_text(self.short_field).replace(",", ".")),
                float(field_text(self.long_field).replace(",", ".")),
                int(field_text(self.cycles_field)),
            )
        except ValueError:
            self.ctx.snack("Use números válidos nos campos de tempo.", error=True)
            return
        if any(v <= 0 for v in values):
            self.ctx.snack("Os tempos e o número de ciclos precisam ser maiores que zero.", error=True)
            return
        p = self.ctx.config.pomodoro
        p.work_minutes, p.short_break_minutes, p.long_break_minutes, p.cycles_before_long_break = values
        p.sound_enabled = bool(self.sound_checkbox.value)
        self.ctx.persist()
        self.ctx.snack("Tempos do Pomodoro salvos.")

    # ------------------------------------------------------------ anytype
    def _show_pairing(self) -> None:
        paired = bool(self.ctx.config.anytype.api_key)
        self.pairing_text.value = "Pareado" if paired else "Não pareado"
        self.pairing_text.color = ft.Colors.GREEN_600 if paired else ft.Colors.ERROR

    def _pair(self, e) -> None:
        client = self.ctx.client
        try:
            challenge_id = client.create_challenge()
        except AnytypeError as ex:
            self.ctx.snack(str(ex), error=True)
            return
        code_field = ft.TextField(label="Código de 4 dígitos exibido no Anytype", autofocus=True)

        def confirm():
            def solve():
                self.ctx.config.anytype.api_key = client.solve_challenge(challenge_id, field_text(code_field))
                self.ctx.persist()
            if self.ctx.attempt(solve, "Pareado com sucesso!"):
                self._show_pairing()
                self.ctx.update()

        self.ctx.confirm(
            "Parear com o Anytype",
            ft.Column([ft.Text(PAIRING_HINT), code_field], tight=True),
            confirm,
        )

    def _load_spaces(self, e) -> None:
        try:
            spaces = self.ctx.client.list_spaces()
        except AnytypeError as ex:
            self.ctx.snack(str(ex), error=True)
            return
        self.space_dropdown.options = [ft.DropdownOption(key=s["id"], text=s.get("name", s["id"])) for s in spaces]
        self.space_dropdown.value = self.ctx.config.anytype.space_id or None
        if not spaces:
            self.ctx.snack(NO_SPACES_MESSAGE, error=True)
        self.ctx.update()

    def _select_space(self, e) -> None:
        if self.space_dropdown.value:
            self.ctx.task_manager.select_space(self.space_dropdown.value)
            self.ctx.snack("Espaço selecionado.")

    def _save_anytype(self, e) -> None:
        a = self.ctx.config.anytype
        a.base_url = field_text(self.base_url_field) or a.base_url
        a.api_version = field_text(self.api_version_field) or a.api_version
        # nome trocado = procurar de novo no próximo setup (senão o id antigo,
        # guardado no config, continuaria valendo)
        task_type = field_text(self.task_type_field) or a.task_type_name
        if task_type != a.task_type_name:
            a.task_type_name, a.task_type_key = task_type, ""
        status_prop = field_text(self.status_prop_field) or a.status_property_name
        if status_prop != a.status_property_name:
            a.status_property_name = status_prop
            a.status_property_id = a.status_property_key = ""
            a.status_tag_ids = {}
        a.set_status_options(field_text(self.status_options_field).split(","))
        a.in_progress_status_name = field_text(self.in_progress_field) or a.in_progress_status_name
        a.done_status_name = field_text(self.done_field) or a.done_status_name
        self.ctx.client.configure(a.base_url, a.api_version)
        self.ctx.persist()
        self.ctx.snack("Configurações do Anytype salvas.")

    def _test_setup(self, e) -> None:
        self.ctx.attempt(
            self.ctx.task_manager.setup,
            "Configuração validada com sucesso! Tipo, propriedade e tags encontrados/criados.",
        )
