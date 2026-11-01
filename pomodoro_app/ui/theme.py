"""Aparência da interface: paletas de cores, modo claro/escuro, cores e
ícones de cada fase, e pequenos estilos reaproveitados pelas telas."""
from __future__ import annotations

import flet as ft

from ..config import GuiConfig
from ..pomodoro_timer import Phase

# Ícones do Material Design (embutidos no Flet, aparecem em qualquer sistema)
# em vez de emojis, que dependem de uma fonte nem sempre presente.
PHASE_ICONS = {
    Phase.WORK: ft.Icons.LOCAL_FIRE_DEPARTMENT,
    Phase.SHORT_BREAK: ft.Icons.COFFEE,
    Phase.LONG_BREAK: ft.Icons.WEEKEND,
    Phase.IDLE: ft.Icons.TIMER,
}

# Cor de cada fase em papéis do tema (não cores fixas): acompanham a paleta
# escolhida e funcionam no modo claro e no escuro.
PHASE_COLORS = {
    Phase.WORK: ft.Colors.PRIMARY,
    Phase.SHORT_BREAK: ft.Colors.TERTIARY,
    Phase.LONG_BREAK: ft.Colors.SECONDARY,
    Phase.IDLE: ft.Colors.ON_SURFACE_VARIANT,
}

# Paletas (Configurações → Aparência). Cada uma é só uma cor base: o
# Material 3 gera a partir dela um esquema completo e harmonioso, em versão
# clara e escura.
THEMES = {
    "tomate": ("Tomate", "#E8594A"),
    "pessego": ("Pêssego", "#F28C5B"),
    "girassol": ("Girassol", "#E3A008"),
    "menta": ("Menta", "#2BAE8C"),
    "oceano": ("Oceano", "#3A7BD5"),
    "lavanda": ("Lavanda", "#8E7CC3"),
    "grafite": ("Grafite", "#5F6B7A"),
}
DEFAULT_THEME = "tomate"

THEME_MODES = {
    "system": ("Automático", ft.ThemeMode.SYSTEM, ft.Icons.BRIGHTNESS_AUTO),
    "light": ("Claro", ft.ThemeMode.LIGHT, ft.Icons.LIGHT_MODE),
    "dark": ("Escuro", ft.ThemeMode.DARK, ft.Icons.DARK_MODE),
}
DEFAULT_THEME_MODE = "system"


def apply_theme(page: ft.Page, gui: GuiConfig) -> None:
    """Aplica a paleta e o modo salvos (corrigindo valores inválidos)."""
    if gui.theme not in THEMES:
        gui.theme = DEFAULT_THEME
    if gui.theme_mode not in THEME_MODES:
        gui.theme_mode = DEFAULT_THEME_MODE
    seed = THEMES[gui.theme][1]
    page.theme = ft.Theme(color_scheme_seed=seed, visual_density=ft.VisualDensity.COMFORTABLE)
    page.dark_theme = ft.Theme(color_scheme_seed=seed, visual_density=ft.VisualDensity.COMFORTABLE)
    page.theme_mode = THEME_MODES[gui.theme_mode][1]


def heading(text: str, size: int = 20) -> ft.Text:
    """Título de seção, na cor principal da paleta."""
    return ft.Text(text, size=size, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY)


def muted(text: str = "", size: int = 13, **kwargs) -> ft.Text:
    """Texto secundário (legendas, contadores, dicas)."""
    return ft.Text(text, size=size, color=ft.Colors.ON_SURFACE_VARIANT, **kwargs)


def card(content: ft.Control) -> ft.Container:
    """Cartão arredondado com fundo suave (cada tarefa da lista)."""
    return ft.Container(
        content=content,
        padding=ft.Padding.symmetric(horizontal=12, vertical=8),
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=12,
    )
