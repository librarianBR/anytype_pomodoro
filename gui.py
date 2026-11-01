"""
Interface gráfica (Flet) para o Pomodoro + Anytype.

Rodar com:
    uv run gui.py
ou
    python gui.py

Usa a mesma lógica de negócio de main.py (config.py, pomodoro_timer.py,
anytype_client.py, task_manager.py) — só muda a camada de interface.
"""
from __future__ import annotations

import datetime
import json
import threading
import unicodedata
from typing import Optional

import flet as ft

from anytype_client import AnytypeClient, AnytypeError
from config import AppConfig, load_config, save_config
from notifier import COUNTDOWN_SECONDS, countdown_sound_path, notify, play_sound, sound_path_for_phase
from pomodoro_timer import Phase, PomodoroTimer
from task_manager import SetupError, Task, TaskManager

PHASE_LABELS = {
    Phase.WORK: "Foco",
    Phase.SHORT_BREAK: "Pausa curta",
    Phase.LONG_BREAK: "Pausa longa",
    Phase.IDLE: "Parado",
}

# Ícones do Material Design (embutidos no Flet, renderizam em qualquer SO)
# em vez de emojis, que dependem de uma fonte de emoji nem sempre presente
# no motor gráfico (Flutter) do sistema, aparecendo como uma caixinha "tofu"
# quando ausente.
PHASE_ICONS = {
    Phase.WORK: ft.Icons.LOCAL_FIRE_DEPARTMENT,
    Phase.SHORT_BREAK: ft.Icons.COFFEE,
    Phase.LONG_BREAK: ft.Icons.WEEKEND,
    Phase.IDLE: ft.Icons.TIMER,
}

# Cor de cada fase, em papéis do tema (não cores fixas): assim acompanham
# a paleta escolhida e funcionam no modo claro e no escuro.
PHASE_COLORS = {
    Phase.WORK: ft.Colors.PRIMARY,
    Phase.SHORT_BREAK: ft.Colors.TERTIARY,
    Phase.LONG_BREAK: ft.Colors.SECONDARY,
    Phase.IDLE: ft.Colors.ON_SURFACE_VARIANT,
}

# Paletas de cores (Configurações → Aparência). Cada uma é só uma cor base:
# o Material 3 gera a partir dela um esquema completo e harmonioso (fundos,
# botões, destaques), em versão clara e escura.
THEMES = {
    "tomate": ("Tomate", "#E8594A"),
    "pessego": ("Pêssego", "#F28C5B"),
    "girassol": ("Girassol", "#E3A008"),
    "menta": ("Menta", "#2BAE8C"),
    "oceano": ("Oceano", "#3A7BD5"),
    "lavanda": ("Lavanda", "#8E7CC3"),
    "grafite": ("Grafite", "#5F6B7A"),
}
THEME_MODES = {
    "system": ("Automático", ft.ThemeMode.SYSTEM, ft.Icons.BRIGHTNESS_AUTO),
    "light": ("Claro", ft.ThemeMode.LIGHT, ft.Icons.LIGHT_MODE),
    "dark": ("Escuro", ft.ThemeMode.DARK, ft.Icons.DARK_MODE),
}


def main(page: ft.Page) -> None:
    page.title = "Pomodoro + Anytype"
    # Textos embutidos do Flutter (calendário, menus etc.) em português
    page.locale_configuration = ft.LocaleConfiguration(
        supported_locales=[ft.Locale("pt", "BR"), ft.Locale("en", "US")],
        current_locale=ft.Locale("pt", "BR"),
    )
    page.padding = 24
    page.scroll = ft.ScrollMode.AUTO
    try:
        page.window.width = 920
        page.window.height = 720
    except Exception:
        pass  # em modo web, não existe "window"

    # --------------------------------------------------------- estado global
    config: AppConfig = load_config()
    client = AnytypeClient(
        config.anytype.base_url, config.anytype.api_version, config.anytype.api_key
    )
    task_manager = TaskManager(client, config)

    def apply_theme():
        """Aplica a paleta e o modo claro/escuro salvos em config.gui."""
        if config.gui.theme not in THEMES:
            config.gui.theme = "tomate"
        if config.gui.theme_mode not in THEME_MODES:
            config.gui.theme_mode = "system"
        seed = THEMES[config.gui.theme][1]
        page.theme = ft.Theme(color_scheme_seed=seed, visual_density=ft.VisualDensity.COMFORTABLE)
        page.dark_theme = ft.Theme(color_scheme_seed=seed, visual_density=ft.VisualDensity.COMFORTABLE)
        page.theme_mode = THEME_MODES[config.gui.theme_mode][1]

    apply_theme()

    state = {
        "timer": None,          # type: Optional[PomodoroTimer]
        "linked_task_id": None,  # type: Optional[str]
        "challenge_id": None,    # type: Optional[str]
        "space_options": [],     # cache de espaços carregados
        "in_mini_mode": False,
    }

    def persist():
        save_config(config)

    # Toca os sons via tocador de áudio do sistema (mesma abordagem da CLI,
    # em notifier.py). Evita depender do controle Audio do Flet, que se
    # mostrou inconsistente entre plataformas/versões do cliente desktop.
    def play_phase_sound(phase: Phase, force: bool = False):
        if not force and not config.pomodoro.sound_enabled:
            return
        play_sound(sound_path_for_phase(phase.value))

    def play_countdown_demo():
        """Toca a contagem regressiva completa (5…1), um tique por segundo,
        para testar nas Configurações sem esperar uma fase acabar."""
        for i, remaining in enumerate(range(COUNTDOWN_SECONDS, 0, -1)):
            threading.Timer(i, play_sound, args=(countdown_sound_path(remaining),)).start()

    def snack(message: str, error: bool = False):
        page.show_dialog(
            ft.SnackBar(
                content=ft.Text(
                    message, color=ft.Colors.ON_ERROR if error else ft.Colors.ON_PRIMARY_CONTAINER
                ),
                bgcolor=ft.Colors.ERROR if error else ft.Colors.PRIMARY_CONTAINER,
                open=True,
            )
        )
        page.update()

    def schedule_on_ui(fn, *args) -> None:
        """Agenda fn(*args) para rodar na thread/loop da página. Necessário
        porque o PomodoroTimer roda em sua própria thread de fundo, e mudar
        controles + chamar page.update() de fora da thread da página não é
        aplicado de forma confiável (só "aparece" quando outro evento força
        um refresh, como um clique de botão)."""
        page.loop.call_soon_threadsafe(fn, *args)

    def close_dialog(dlg: ft.AlertDialog):
        dlg.open = False
        page.update()

    # ============================================================ POMODORO
    phase_icon = ft.Icon(ft.Icons.TIMER, size=30)
    phase_text = ft.Text("Parado", size=26, weight=ft.FontWeight.BOLD)
    phase_row = ft.Row([phase_icon, phase_text], alignment=ft.MainAxisAlignment.CENTER, spacing=8)

    # Versões compactas dos mesmos indicadores, usadas só no "modo mini"
    # (janela pequena, sempre visível). Atualizadas em paralelo às normais.
    mini_phase_icon = ft.Icon(ft.Icons.TIMER, size=18)
    mini_time_text = ft.Text("00:00", size=26, weight=ft.FontWeight.BOLD)
    time_text = ft.Text("00:00", size=72, weight=ft.FontWeight.BOLD)
    cycle_text = ft.Text("", size=15, color=ft.Colors.ON_SURFACE_VARIANT)
    progress = ft.ProgressBar(
        value=0, width=420, bar_height=8, border_radius=8, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST
    )
    linked_task_text = ft.Text("", italic=True, size=13)
    task_dropdown = ft.Dropdown(label="Vincular a uma tarefa (opcional)", options=[], width=420)

    start_btn = ft.Button("Iniciar", icon=ft.Icons.PLAY_ARROW)
    pause_btn = ft.Button("Pausar", icon=ft.Icons.PAUSE, disabled=True)
    resume_btn = ft.Button("Retomar", icon=ft.Icons.PLAY_ARROW, disabled=True)
    restart_btn = ft.Button("Reiniciar fase", icon=ft.Icons.RESTART_ALT, disabled=True)
    skip_btn = ft.Button("Pular fase", icon=ft.Icons.SKIP_NEXT, disabled=True)
    stop_btn = ft.Button("Parar", icon=ft.Icons.STOP, disabled=True)

    def set_running_controls(running: bool):
        start_btn.disabled = running
        pause_btn.disabled = not running
        resume_btn.disabled = not running
        restart_btn.disabled = not running
        skip_btn.disabled = not running
        stop_btn.disabled = not running
        # task_dropdown continua habilitado mesmo rodando: vincular/trocar/
        # desvincular a tarefa é permitido a qualquer momento.

    def refresh_task_dropdown():
        current = state.get("linked_task_id")
        task_dropdown.options = []
        if not config.anytype.space_id:
            task_dropdown.value = None
            return
        try:
            task_manager.setup()
            tasks = task_manager.list_tasks()
            pending = [t for t in tasks if t.status != config.anytype.done_status_name]
            task_dropdown.options = [
                ft.DropdownOption(key=t.id, text=f"[{t.status}] {t.name}") for t in pending
            ]
            # preserva a tarefa vinculada atual na seleção, se ela ainda
            # estiver na lista (evita "desvincular" sozinho ao trocar de aba)
            task_dropdown.value = current if any(o.key == current for o in task_dropdown.options) else None
        except (AnytypeError, SetupError):
            pass  # se não estiver configurado ainda, só deixa o dropdown vazio

    def link_task(new_task_id: Optional[str]):
        """Vincula (ou troca/desvincula) a tarefa da sessão a qualquer
        momento, rodando ou não. Registra uma observação tanto na tarefa
        que está sendo deixada quanto na nova, para manter o histórico."""
        old_task_id = state.get("linked_task_id")
        if old_task_id == new_task_id:
            return
        if old_task_id:
            try:
                task_manager.add_note(old_task_id, "Sessão desvinculada desta tarefa.")
            except (AnytypeError, SetupError) as ex:
                snack(str(ex), error=True)

        state["linked_task_id"] = new_task_id
        task_dropdown.value = new_task_id
        if new_task_id:
            linked_task_text.value = f"Vinculada a: {linked_task_label()}"
            try:
                task_manager.set_status(new_task_id, config.anytype.in_progress_status_name)
                task_manager.add_note(new_task_id, "Sessão vinculada a esta tarefa.")
            except (AnytypeError, SetupError) as ex:
                snack(str(ex), error=True)
        else:
            linked_task_text.value = ""
        update_link_buttons()
        page.update()

    def on_task_dropdown_change(e):
        link_task(task_dropdown.value)

    def unlink_task(e):
        link_task(None)

    def complete_linked_task(note: Optional[str] = None) -> bool:
        """Marca a tarefa vinculada como concluída (done_status_name),
        registra `note` no histórico (se houver) e a tira da sessão: o
        dropdown volta vazio, sem ela na lista, esperando a próxima. O timer
        não é afetado. Não usa link_task(None) para não registrar uma
        observação "desvinculada" redundante logo após a de conclusão.
        Retorna False (e mostra o erro) se o Anytype recusar."""
        task_id = state.get("linked_task_id")
        if not task_id:
            return False
        try:
            if note:
                task_manager.add_note(task_id, note)
            task_manager.set_status(task_id, config.anytype.done_status_name)
        except (AnytypeError, SetupError) as ex:
            snack(str(ex), error=True)
            return False
        state["linked_task_id"] = None
        linked_task_text.value = ""
        refresh_task_dropdown()
        update_link_buttons()
        page.update()
        return True

    def linked_task_label() -> str:
        """Nome da tarefa vinculada, sem o "[status]" do texto do dropdown —
        esse status foi lido ao carregar a lista e fica desatualizado assim
        que o vínculo marca a tarefa como "em andamento"."""
        task_id = state.get("linked_task_id")
        text = next((o.text for o in task_dropdown.options if o.key == task_id), "")
        if text.startswith("[") and "] " in text:
            text = text.split("] ", 1)[1]
        return f"'{text}'" if text else "a tarefa vinculada"

    def ask_complete_task(e=None):
        """Botão "Concluir tarefa": concluir a qualquer momento, sem esperar
        o ciclo de foco acabar (ex.: terminou a tarefa no meio do ciclo)."""
        if not state.get("linked_task_id"):
            return
        note_field = ft.TextField(
            label="Observação (opcional)", multiline=True, min_lines=2, max_lines=4
        )

        def confirm(e):
            status = state["timer"].status() if state["timer"] else None
            log_text = "Tarefa concluída"
            if status and status.is_running and status.phase == Phase.WORK:
                log_text += f" durante o ciclo de foco {status.cycle} ({status.elapsed_seconds // 60} min de foco nele)"
            note_text = (note_field.value or "").strip()
            if note_text:
                log_text += f" — {note_text}"
            close_dialog(dlg)
            if complete_linked_task(log_text):
                snack(f"Tarefa marcada como '{config.anytype.done_status_name}'. Escolha a próxima quando quiser.")

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Concluir tarefa"),
            content=ft.Column(
                [
                    ft.Text(f"Marcar {linked_task_label()} como '{config.anytype.done_status_name}'?"),
                    ft.Text(
                        "Ela sai da sessão e o timer continua rodando normalmente.",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    note_field,
                ],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: close_dialog(dlg)),
                ft.Button("Concluir", icon=ft.Icons.TASK_ALT, on_click=confirm),
            ],
            open=True,
        )
        page.show_dialog(dlg)
        page.update()

    task_dropdown.on_select = on_task_dropdown_change
    unlink_btn = ft.Button("Desvincular", icon=ft.Icons.LINK_OFF, on_click=unlink_task)
    complete_btn = ft.Button("Concluir tarefa", icon=ft.Icons.TASK_ALT, on_click=ask_complete_task)

    def update_link_buttons():
        """Desvincular/Concluir só fazem sentido com uma tarefa vinculada."""
        has_task = bool(state.get("linked_task_id"))
        unlink_btn.disabled = not has_task
        complete_btn.disabled = not has_task

    update_link_buttons()

    def on_phase_start(phase: Phase, total_seconds: int, cycle: int):
        notify(f"{PHASE_LABELS[phase]} iniciado", f"Ciclo {cycle}")

        def apply():
            phase_icon.icon = PHASE_ICONS[phase]
            phase_text.value = PHASE_LABELS[phase]
            mini_phase_icon.icon = PHASE_ICONS[phase]
            apply_phase_colors(phase)
            cycle_text.value = (
                f"Ciclo {cycle} — pausa longa a cada "
                f"{config.pomodoro.cycles_before_long_break} ciclos"
            )
            m, s = divmod(total_seconds, 60)
            time_text.value = f"{m:02d}:{s:02d}"
            mini_time_text.value = f"{m:02d}:{s:02d}"
            progress.value = 0
            play_phase_sound(phase)
            page.update()

        schedule_on_ui(apply)

    def ask_mark_done():
        pause_btn.disabled = True
        resume_btn.disabled = True
        page.update()

        note_field = ft.TextField(
            label="Observação (opcional)", multiline=True, min_lines=2, max_lines=4
        )

        def finish(mark_done: bool):
            def handler(e):
                minutes = config.pomodoro.work_minutes
                note_text = (note_field.value or "").strip()
                log_text = f"Sessão de foco concluída ({minutes:g} min)"
                if note_text:
                    log_text += f" — {note_text}"
                if mark_done:
                    if complete_linked_task(log_text):
                        snack(f"Tarefa marcada como '{config.anytype.done_status_name}' e observação registrada.")
                else:
                    try:
                        task_manager.add_note(state["linked_task_id"], log_text)
                        snack("Observação registrada na tarefa.")
                    except (AnytypeError, SetupError) as ex:
                        snack(str(ex), error=True)
                close_dialog(dlg)
                if state["timer"]:
                    state["timer"].resume()
                pause_btn.disabled = False
                resume_btn.disabled = False
                page.update()

            return handler

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Ciclo de foco terminado"),
            content=ft.Column(
                [
                    ft.Text(f"Marcar a tarefa vinculada como '{config.anytype.done_status_name}'?"),
                    note_field,
                ],
                tight=True,
                spacing=10,
            ),
            actions=[
                ft.TextButton("Agora não", on_click=finish(False)),
                ft.Button("Sim", on_click=finish(True)),
            ],
            open=True,
        )
        page.show_dialog(dlg)
        page.update()

    def on_phase_end(phase: Phase, cycle: int):
        notify(f"{PHASE_LABELS[phase]} terminou", f"Fim do ciclo {cycle}")
        if phase == Phase.WORK and state["linked_task_id"]:
            # Pausa AQUI, de forma síncrona, ainda na thread do timer —
            # antes mesmo do diálogo aparecer. É essencial que isso
            # aconteça antes de _run_phase retornar, senão a fase seguinte
            # já teria começado a contar em segundo plano por uma pequena
            # janela de tempo (o timer não tem como "esperar" um diálogo
            # assíncrono da interface sozinho).
            if state["timer"]:
                state["timer"].pause()
            schedule_on_ui(ask_mark_done)

    def apply_phase_colors(phase: Phase):
        """Ícone, tempo e barra de progresso na cor da fase."""
        color = PHASE_COLORS[phase]
        for control in (phase_icon, phase_text, mini_phase_icon, time_text, mini_time_text):
            control.color = color
        progress.color = color

    apply_phase_colors(Phase.IDLE)

    def on_tick(status):
        # Contagem regressiva sonora nos últimos segundos da fase. Tocada
        # direto aqui (thread do timer), sem esperar o loop da interface,
        # para o tique sair no segundo certo; play_sound não bloqueia.
        if config.pomodoro.sound_enabled:
            play_sound(countdown_sound_path(status.remaining_seconds))

        def apply():
            m, s = divmod(max(status.remaining_seconds, 0), 60)
            time_text.value = f"{m:02d}:{s:02d}"
            mini_time_text.value = f"{m:02d}:{s:02d}"
            progress.value = (
                (status.elapsed_seconds / status.total_seconds) if status.total_seconds else 0
            )
            page.update()

        schedule_on_ui(apply)

    def start_session(e):
        # o vínculo com a tarefa já é tratado por link_task() a qualquer
        # momento (via seleção no dropdown) — aqui só iniciamos o timer.
        timer = PomodoroTimer(
            config.pomodoro, on_phase_start=on_phase_start, on_phase_end=on_phase_end, on_tick=on_tick
        )
        state["timer"] = timer
        timer.start()
        set_running_controls(True)
        page.update()

    def pause_session(e):
        if state["timer"]:
            state["timer"].pause()
            snack("Pausado.")

    def resume_session(e):
        if state["timer"]:
            state["timer"].resume()
            snack("Retomado.")

    def skip_session(e):
        if state["timer"]:
            state["timer"].skip()

    def restart_session(e):
        if state["timer"]:
            state["timer"].restart_phase()
            snack("Fase reiniciada.")

    def stop_session(e):
        if state["timer"]:
            state["timer"].stop()
        phase_icon.icon = ft.Icons.TIMER
        phase_text.value = "Parado"
        time_text.value = "00:00"
        mini_phase_icon.icon = ft.Icons.TIMER
        mini_time_text.value = "00:00"
        cycle_text.value = ""
        progress.value = 0
        apply_phase_colors(Phase.IDLE)
        # o vínculo com a tarefa NÃO é desfeito ao parar — parar é só o
        # timer; vincular/desvincular é uma ação independente e explícita
        # (dropdown ou botão "Desvincular"), disponível a qualquer momento.
        set_running_controls(False)
        page.update()

    start_btn.on_click = start_session
    pause_btn.on_click = pause_session
    resume_btn.on_click = resume_session
    restart_btn.on_click = restart_session
    skip_btn.on_click = skip_session
    stop_btn.on_click = stop_session

    def build_pomodoro_view() -> ft.Control:
        refresh_task_dropdown()
        return ft.Column(
            [
                ft.Text("Sessão Pomodoro", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                ft.Container(height=10),
                phase_row,
                time_text,
                cycle_text,
                progress,
                ft.Container(height=10),
                ft.Row([task_dropdown, unlink_btn, complete_btn], alignment=ft.MainAxisAlignment.CENTER, wrap=True),
                linked_task_text,
                ft.Container(height=10),
                ft.Row(
                    [start_btn, pause_btn, resume_btn, restart_btn, skip_btn, stop_btn],
                    alignment=ft.MainAxisAlignment.CENTER,
                    wrap=True,
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=8,
        )

    # =============================================================== TAREFAS
    tasks_list = ft.ListView(expand=True, spacing=8, height=420)
    new_task_name = ft.TextField(label="Nova tarefa", expand=True)
    new_task_status = ft.Dropdown(
        label="Status inicial",
        width=160,
        options=[ft.DropdownOption(key=s, text=s) for s in config.anytype.status_options],
        value=config.anytype.status_options[0] if config.anytype.status_options else None,
    )

    # ---- data de entrega (opcional) da nova tarefa
    state["new_task_due"] = None  # type: Optional[datetime.date]
    due_button = ft.OutlinedButton("Data de entrega", icon=ft.Icons.CALENDAR_MONTH)
    due_clear_btn = ft.IconButton(ft.Icons.CLOSE, tooltip="Remover data de entrega", visible=False)

    def set_new_task_due(value):
        state["new_task_due"] = value
        due_button.content = f"Entrega: {value.strftime('%d/%m/%Y')}" if value else "Data de entrega"
        due_clear_btn.visible = bool(value)
        page.update()

    def on_due_picked(e):
        value = e.control.value
        # o DatePicker devolve um datetime; só o dia interessa
        set_new_task_due(value.date() if isinstance(value, datetime.datetime) else value)

    def open_due_picker(e):
        today = datetime.date.today()
        page.show_dialog(
            ft.DatePicker(
                value=state["new_task_due"] or today,
                first_date=today - datetime.timedelta(days=365),
                last_date=today + datetime.timedelta(days=365 * 5),
                help_text="Data de entrega",
                locale=ft.Locale("pt", "BR"),
                cancel_text="Cancelar",
                confirm_text="OK",
                on_change=on_due_picked,
            )
        )

    due_button.on_click = open_due_picker
    due_clear_btn.on_click = lambda e: set_new_task_due(None)

    # ---- história de usuário (Scrum), gravada na descrição da tarefa
    STORY_PLACEHOLDERS = ("<tipo de usuário>", "<objetivo>", "<benefício>", "<contexto>", "<ação>", "<resultado esperado>")
    STORY_TEMPLATE = (
        "Como <tipo de usuário>, quero <objetivo> para <benefício>.\n"
        "\n"
        "Critérios de aceitação:\n"
        "- Dado <contexto>, quando <ação>, então <resultado esperado>."
    )
    new_task_story = ft.TextField(
        label="História de usuário (opcional)",
        hint_text="Como <tipo de usuário>, quero <objetivo> para <benefício>.",
        multiline=True,
        min_lines=2,
        max_lines=6,
        expand=True,
    )

    def use_story_template(e):
        if (new_task_story.value or "").strip():
            snack("O campo de história já tem texto — apague-o para usar o modelo.", error=True)
            return
        new_task_story.value = STORY_TEMPLATE
        page.update()
        new_task_story.focus()

    story_template_btn = ft.TextButton(
        "Usar modelo de história", icon=ft.Icons.AUTO_STORIES, on_click=use_story_template,
        tooltip="Preenche com o formato de história de usuário do Scrum: substitua os campos entre < >",
    )

    # ---- filtros da lista de tarefas (aplicados sobre a lista já carregada
    # do Anytype, guardada em state["tasks_cache"] — mudar um filtro não faz
    # nova chamada à API; só "Atualizar lista" e as edições recarregam).
    state["tasks_cache"] = []
    SORT_OPTIONS = [
        ("created_desc", "Criação: mais recentes primeiro"),
        ("created_asc", "Criação: mais antigas primeiro"),
        ("name_asc", "Título: A → Z"),
        ("name_desc", "Título: Z → A"),
        ("due_asc", "Entrega: mais próxima primeiro"),
    ]
    STATUS_ALL, STATUS_PENDING = "", "__pending__"
    LIMIT_OPTIONS = [10, 25, 50, 100, 0]  # 0 = todas

    filter_title = ft.TextField(
        label="Buscar no título", prefix_icon=ft.Icons.SEARCH, width=260, dense=True
    )
    filter_status = ft.Dropdown(label="Status", width=190, dense=True)
    filter_sort = ft.Dropdown(
        label="Ordenar por",
        width=330,
        dense=True,
        options=[ft.DropdownOption(key=k, text=t) for k, t in SORT_OPTIONS],
        value=config.gui.tasks_sort if any(k == config.gui.tasks_sort for k, _ in SORT_OPTIONS) else "created_desc",
    )
    filter_limit = ft.Dropdown(
        label="Mostrar",
        width=120,
        dense=True,
        options=[ft.DropdownOption(key=str(n), text=str(n) if n else "Todas") for n in LIMIT_OPTIONS],
        value=str(config.gui.tasks_limit) if config.gui.tasks_limit in LIMIT_OPTIONS else "25",
    )
    tasks_count_text = ft.Text("", size=13, color=ft.Colors.ON_SURFACE_VARIANT)

    def refresh_status_filter_options():
        filter_status.options = [
            ft.DropdownOption(key=STATUS_ALL, text="Todos"),
            ft.DropdownOption(key=STATUS_PENDING, text="Não concluídas"),
        ] + [ft.DropdownOption(key=s, text=s) for s in config.anytype.status_options]
        valid = {o.key for o in filter_status.options}
        wanted = config.gui.tasks_status_filter
        filter_status.value = wanted if wanted in valid else STATUS_ALL

    refresh_status_filter_options()

    def _normalize(text: str) -> str:
        """Minúsculas e sem acentos, para a busca achar "tarefa" em "Tárefa"."""
        decomposed = unicodedata.normalize("NFKD", text or "")
        return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()

    def filtered_tasks(tasks: list) -> list:
        query = _normalize(filter_title.value or "").strip()
        status = filter_status.value or STATUS_ALL
        result = [
            t for t in tasks
            if (not query or query in _normalize(t.name))
            and (
                status == STATUS_ALL
                or (status == STATUS_PENDING and t.status != config.anytype.done_status_name)
                or t.status == status
            )
        ]
        sort = filter_sort.value or "created_desc"
        if sort.startswith("created"):
            # tarefas sem data de criação vão sempre para o fim da lista
            dated = [t for t in result if t.created]
            undated = [t for t in result if not t.created]
            dated.sort(key=lambda t: t.created, reverse=(sort == "created_desc"))
            result = dated + undated
        elif sort == "due_asc":
            # sem data de entrega vão para o fim
            with_due = sorted((t for t in result if t.due), key=lambda t: t.due)
            result = with_due + [t for t in result if not t.due]
        else:
            result.sort(key=lambda t: _normalize(t.name), reverse=(sort == "name_desc"))
        return result

    def render_tasks():
        """Redesenha a lista a partir do cache, aplicando os filtros."""
        tasks = state["tasks_cache"]
        visible = filtered_tasks(tasks)
        limit = int(filter_limit.value or 0)
        shown = visible[:limit] if limit else visible
        tasks_list.controls.clear()
        if not tasks:
            tasks_list.controls.append(ft.Text("(nenhuma tarefa)"))
        elif not visible:
            tasks_list.controls.append(ft.Text("(nenhuma tarefa corresponde aos filtros)"))
        for t in shown:
            tasks_list.controls.append(build_task_row(t))
        tasks_count_text.value = (
            f"Mostrando {len(shown)} de {len(visible)} tarefa(s)"
            + (f" — {len(tasks)} no total" if len(visible) != len(tasks) else "")
            if tasks else ""
        )
        page.update()

    def on_filter_change(e=None):
        # guarda as escolhas (exceto a busca por título, que é momentânea)
        config.gui.tasks_sort = filter_sort.value or "created_desc"
        config.gui.tasks_status_filter = filter_status.value or STATUS_ALL
        config.gui.tasks_limit = int(filter_limit.value or 0)
        persist()
        render_tasks()

    filter_title.on_change = lambda e: render_tasks()
    filter_status.on_select = on_filter_change
    filter_sort.on_select = on_filter_change
    filter_limit.on_select = on_filter_change

    def clear_filters(e=None):
        filter_title.value = ""
        filter_status.value = STATUS_ALL
        filter_sort.value = "created_desc"
        filter_limit.value = "25"
        on_filter_change()

    def show_notes_dialog(task: Task):
        try:
            current_notes = task_manager.get_task_notes(task.id)
        except (AnytypeError, SetupError) as ex:
            snack(str(ex), error=True)
            return

        history = ft.Text(current_notes or "(nenhuma observação registrada ainda)")
        new_note_field = ft.TextField(label="Nova observação", multiline=True, min_lines=2, max_lines=4)

        def add(e):
            text = (new_note_field.value or "").strip()
            if not text:
                return
            try:
                task_manager.add_note(task.id, text)
                history.value = task_manager.get_task_notes(task.id)
                new_note_field.value = ""
                page.update()
                snack("Observação adicionada.")
            except (AnytypeError, SetupError) as ex:
                snack(str(ex), error=True)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Observações — {task.name}"),
            content=ft.Container(
                content=ft.Column([history, ft.Divider(), new_note_field], spacing=10, tight=True),
                width=600,
                height=400,
            ),
            actions=[
                ft.TextButton("Fechar", on_click=lambda e: close_dialog(dlg)),
                ft.Button("Adicionar", icon=ft.Icons.ADD, on_click=add),
            ],
            scrollable=True,
            open=True,
        )
        page.show_dialog(dlg)
        page.update()

    def show_raw_json(task: Task):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"JSON bruto — {task.name}"),
            content=ft.Container(
                content=ft.Text(json.dumps(task.raw, indent=2, ensure_ascii=False)),
                width=600,
                height=400,
            ),
            actions=[ft.TextButton("Fechar", on_click=lambda e: close_dialog(dlg))],
            scrollable=True,
            open=True,
        )
        page.show_dialog(dlg)
        page.update()

    def rename_task_dialog(task: Task):
        field = ft.TextField(label="Novo nome", value=task.name)

        def confirm(e):
            try:
                task_manager.rename_task(task.id, field.value)
                snack("Tarefa renomeada.")
                refresh_tasks_list()
            except AnytypeError as ex:
                snack(str(ex), error=True)
            close_dialog(dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Renomear tarefa"),
            content=field,
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: close_dialog(dlg)),
                ft.Button("Salvar", on_click=confirm),
            ],
            open=True,
        )
        page.show_dialog(dlg)
        page.update()

    def delete_task_dialog(task: Task):
        def confirm(e):
            try:
                task_manager.delete_task(task.id)
                snack("Tarefa excluída.")
                refresh_tasks_list()
            except AnytypeError as ex:
                snack(str(ex), error=True)
            close_dialog(dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Excluir tarefa"),
            content=ft.Text(f"Tem certeza que deseja excluir '{task.name}'?"),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e: close_dialog(dlg)),
                ft.Button("Excluir", on_click=confirm, bgcolor=ft.Colors.ERROR, color=ft.Colors.ON_ERROR),
            ],
            open=True,
        )
        page.show_dialog(dlg)
        page.update()

    def make_status_change_handler(task: Task, dropdown: ft.Dropdown):
        def handler(e):
            try:
                task_manager.set_status(task.id, dropdown.value)
                snack(f"Status de '{task.name}' agora é '{dropdown.value}'.")
            except AnytypeError as ex:
                snack(str(ex), error=True)
            refresh_tasks_list()

        return handler

    def build_task_row(task: Task) -> ft.Control:
        status_dd = ft.Dropdown(
            width=175,
            value=task.status if task.status in config.anytype.status_options else None,
            options=[ft.DropdownOption(key=s, text=s) for s in config.anytype.status_options],
        )
        status_dd.on_select = make_status_change_handler(task, status_dd)
        created_label = task.created.strftime("Criada em %d/%m/%Y %H:%M") if task.created else "Data de criação desconhecida"
        info_spans = [ft.TextSpan(created_label)]
        if task.due:
            overdue = task.due < datetime.date.today() and task.status != config.anytype.done_status_name
            info_spans.append(ft.TextSpan(f"  ·  Entrega: {task.due.strftime('%d/%m/%Y')}"))
            if overdue:
                info_spans.append(
                    ft.TextSpan("  (atrasada)", style=ft.TextStyle(color=ft.Colors.ERROR, weight=ft.FontWeight.BOLD))
                )
        texts = [
            ft.Text(task.name, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Text(spans=info_spans, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
        ]
        if task.description.strip():
            # só a primeira linha da história, para a lista não ficar enorme
            first_line = task.description.strip().splitlines()[0]
            texts.append(
                ft.Text(first_line, size=12, italic=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
                        tooltip=task.description.strip())
            )
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(texts, spacing=2, expand=True),
                    status_dd,
                    ft.IconButton(ft.Icons.EDIT, tooltip="Renomear", on_click=lambda e, t=task: rename_task_dialog(t)),
                    ft.IconButton(ft.Icons.EDIT_NOTE, tooltip="Observações", on_click=lambda e, t=task: show_notes_dialog(t)),
                    ft.IconButton(ft.Icons.DELETE, tooltip="Excluir", on_click=lambda e, t=task: delete_task_dialog(t)),
                    ft.IconButton(ft.Icons.INFO_OUTLINE, tooltip="Ver JSON bruto", on_click=lambda e, t=task: show_raw_json(t)),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=12,
        )

    def refresh_tasks_list(e=None):
        """Recarrega as tarefas do Anytype e redesenha com os filtros atuais."""
        tasks_list.controls.clear()
        tasks_count_text.value = ""
        state["tasks_cache"] = []
        if not config.anytype.space_id:
            tasks_list.controls.append(ft.Text("Escolha um espaço do Anytype nas Configurações primeiro."))
            page.update()
            return
        try:
            task_manager.setup()
        except SetupError as ex:
            tasks_list.controls.append(ft.Text(f"Configuração incompleta: {ex}", color=ft.Colors.ERROR))
            page.update()
            return
        except AnytypeError as ex:
            tasks_list.controls.append(ft.Text(f"Erro: {ex}", color=ft.Colors.ERROR))
            page.update()
            return

        try:
            tasks = task_manager.list_tasks()
        except AnytypeError as ex:
            tasks_list.controls.append(ft.Text(f"Erro ao listar tarefas: {ex}", color=ft.Colors.ERROR))
            page.update()
            return

        state["tasks_cache"] = tasks
        render_tasks()

    def create_task(e):
        name = (new_task_name.value or "").strip()
        if not name:
            snack("Digite um nome para a tarefa.", error=True)
            return
        story = (new_task_story.value or "").strip()
        if any(ph in story for ph in STORY_PLACEHOLDERS):
            snack("Substitua os campos entre < > do modelo de história (ou apague a parte que não usar).", error=True)
            return
        try:
            task_manager.setup()
            task_manager.create_task(
                name, description=story, status=new_task_status.value, due=state["new_task_due"]
            )
            new_task_name.value = ""
            new_task_story.value = ""
            set_new_task_due(None)
            snack("Tarefa criada.")
            refresh_tasks_list()
        except (AnytypeError, SetupError) as ex:
            snack(str(ex), error=True)

    def build_tasks_view() -> ft.Control:
        new_task_status.options = [ft.DropdownOption(key=s, text=s) for s in config.anytype.status_options]
        if not new_task_status.value and config.anytype.status_options:
            new_task_status.value = config.anytype.status_options[0]
        refresh_status_filter_options()  # a lista de status pode ter mudado nas Configurações
        refresh_tasks_list()
        return ft.Column(
            [
                ft.Text("Tarefas (Anytype)", size=22, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                # Sem wrap=True aqui: o campo de nome usa expand=True, e o
                # Flutter não aceita filho "expandido" numa linha que quebra
                # (a aba inteira vira um quadro cinza de erro).
                ft.Row(
                    [new_task_name, new_task_status, due_button, due_clear_btn,
                     ft.Button("Criar", icon=ft.Icons.ADD, on_click=create_task)],
                ),
                ft.Row([new_task_story, story_template_btn], vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Divider(height=1),
                ft.Row(
                    [filter_title, filter_status, filter_sort, filter_limit],
                    wrap=True,
                    spacing=10,
                ),
                ft.Row(
                    [
                        ft.Button("Atualizar lista", icon=ft.Icons.REFRESH, on_click=refresh_tasks_list),
                        ft.TextButton("Limpar filtros", icon=ft.Icons.FILTER_ALT_OFF, on_click=clear_filters),
                        tasks_count_text,
                    ],
                    wrap=True,
                ),
                tasks_list,
            ],
            spacing=12,
            # Sem scroll aqui: tasks_list (ListView com expand=True) já rola
            # sozinha, e "expandir" dentro de uma coluna rolável é erro de
            # layout no Flutter.
            expand=True,
        )

    # ========================================================= CONFIGURAÇÕES
    work_field = ft.TextField(label="Foco (min)", value=str(config.pomodoro.work_minutes), width=140)
    short_field = ft.TextField(label="Pausa curta (min)", value=str(config.pomodoro.short_break_minutes), width=160)
    long_field = ft.TextField(label="Pausa longa (min)", value=str(config.pomodoro.long_break_minutes), width=160)
    cycles_field = ft.TextField(
        label="Ciclos até pausa longa", value=str(config.pomodoro.cycles_before_long_break), width=200
    )
    sound_checkbox = ft.Checkbox(
        label=f"Tocar sons (início de cada fase e contagem regressiva nos últimos {COUNTDOWN_SECONDS} s)",
        value=config.pomodoro.sound_enabled,
    )

    def save_pomodoro_config(e):
        try:
            config.pomodoro.work_minutes = float(work_field.value)
            config.pomodoro.short_break_minutes = float(short_field.value)
            config.pomodoro.long_break_minutes = float(long_field.value)
            config.pomodoro.cycles_before_long_break = int(cycles_field.value)
            config.pomodoro.sound_enabled = sound_checkbox.value
            persist()
            snack("Tempos do Pomodoro salvos.")
        except ValueError:
            snack("Use números válidos nos campos de tempo.", error=True)

    base_url_field = ft.TextField(label="URL base da API", value=config.anytype.base_url, width=320)
    api_version_field = ft.TextField(label="Versão da API", value=config.anytype.api_version, width=200)
    task_type_field = ft.TextField(label="Nome do tipo de tarefa", value=config.anytype.task_type_name, width=250)
    status_prop_field = ft.TextField(label="Nome da propriedade de status", value=config.anytype.status_property_name, width=280)
    status_options_field = ft.TextField(
        label="Opções de status (separadas por vírgula)",
        value=", ".join(config.anytype.status_options),
        width=500,
    )
    in_progress_field = ft.TextField(
        label="Status usado como 'em andamento'", value=config.anytype.in_progress_status_name, width=240
    )
    done_field = ft.TextField(
        label="Status usado como 'concluído'", value=config.anytype.done_status_name, width=240
    )
    space_dropdown = ft.Dropdown(label="Espaço do Anytype", width=320, options=[])
    pairing_status_text = ft.Text(
        "Pareado" if config.anytype.api_key else "Não pareado", color=ft.Colors.GREEN_600 if config.anytype.api_key else ft.Colors.ERROR
    )

    def load_spaces(e):
        try:
            spaces = client.list_spaces()
        except AnytypeError as ex:
            snack(str(ex), error=True)
            return
        state["space_options"] = spaces
        space_dropdown.options = [ft.DropdownOption(key=s["id"], text=s.get("name", s["id"])) for s in spaces]
        if config.anytype.space_id:
            space_dropdown.value = config.anytype.space_id
        page.update()

    def select_space(e):
        if not space_dropdown.value:
            return
        config.anytype.space_id = space_dropdown.value
        # muda de espaço invalida os caches específicos do espaço anterior
        config.anytype.task_type_key = ""
        config.anytype.status_property_id = ""
        config.anytype.status_property_key = ""
        config.anytype.status_tag_ids = {}
        persist()
        snack("Espaço selecionado.")

    space_dropdown.on_select = select_space

    def do_pairing(e):
        try:
            state["challenge_id"] = client.create_challenge()
        except AnytypeError as ex:
            snack(str(ex), error=True)
            return

        code_field = ft.TextField(label="Código de 4 dígitos exibido no Anytype", autofocus=True)

        def confirm_code(e2):
            try:
                api_key = client.solve_challenge(state["challenge_id"], code_field.value)
                config.anytype.api_key = api_key
                persist()
                pairing_status_text.value = "Pareado"
                pairing_status_text.color = ft.Colors.GREEN_600
                snack("Pareado com sucesso!")
            except AnytypeError as ex:
                snack(str(ex), error=True)
            close_dialog(dlg)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("Parear com o Anytype"),
            content=ft.Column(
                [ft.Text("Abra o Anytype Desktop: um código de 4 dígitos deve aparecer na tela."), code_field],
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda e2: close_dialog(dlg)),
                ft.Button("Confirmar", on_click=confirm_code),
            ],
            open=True,
        )
        page.show_dialog(dlg)
        page.update()

    def save_anytype_config(e):
        config.anytype.base_url = base_url_field.value
        config.anytype.api_version = api_version_field.value
        config.anytype.task_type_name = task_type_field.value
        config.anytype.status_property_name = status_prop_field.value
        new_options = [s.strip() for s in status_options_field.value.split(",") if s.strip()]
        if new_options and new_options != config.anytype.status_options:
            config.anytype.status_options = new_options
            # nomes de status mudaram: força re-descoberta das tags
            config.anytype.status_tag_ids = {}
        config.anytype.in_progress_status_name = in_progress_field.value.strip() or config.anytype.in_progress_status_name
        config.anytype.done_status_name = done_field.value.strip() or config.anytype.done_status_name
        client.base_url = config.anytype.base_url.rstrip("/")
        client.api_version = config.anytype.api_version
        persist()
        snack("Configurações do Anytype salvas.")

    def test_setup(e):
        try:
            task_manager.setup()
            snack("Configuração validada com sucesso! Tipo, propriedade e tags encontrados/criados.")
        except SetupError as ex:
            snack(str(ex), error=True)
        except AnytypeError as ex:
            snack(str(ex), error=True)

    # ---- Aparência: paleta e modo claro/escuro, aplicados na hora
    def theme_option(key: str) -> ft.DropdownOption:
        label, seed = THEMES[key]
        return ft.DropdownOption(
            key=key,
            text=label,
            content=ft.Row(
                [ft.Container(width=16, height=16, border_radius=8, bgcolor=seed), ft.Text(label)],
                spacing=10,
            ),
        )

    theme_dropdown = ft.Dropdown(
        label="Paleta de cores",
        width=220,
        leading_icon=ft.Icons.PALETTE,
        options=[theme_option(k) for k in THEMES],
        value=config.gui.theme if config.gui.theme in THEMES else "tomate",
    )
    theme_mode_selector = ft.SegmentedButton(
        segments=[
            ft.Segment(value=k, label=label, icon=icon) for k, (label, _, icon) in THEME_MODES.items()
        ],
        selected=[config.gui.theme_mode if config.gui.theme_mode in THEME_MODES else "system"],
        allow_empty_selection=False,
        allow_multiple_selection=False,
    )

    def on_theme_change(e=None):
        config.gui.theme = theme_dropdown.value or "tomate"
        selected = theme_mode_selector.selected or ["system"]
        config.gui.theme_mode = selected[0]
        apply_theme()
        persist()
        page.update()

    theme_dropdown.on_select = on_theme_change
    theme_mode_selector.on_change = on_theme_change

    def build_settings_view() -> ft.Control:
        return ft.Column(
            [
                ft.Text("Aparência", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                ft.Row(
                    [theme_dropdown, theme_mode_selector],
                    spacing=16,
                    wrap=True,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Divider(),
                ft.Text("Configurações do Pomodoro", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                ft.Row([work_field, short_field, long_field, cycles_field]),
                sound_checkbox,
                ft.Row(
                    [
                        ft.Text("Testar sons:"),
                        ft.Button("Foco", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: play_phase_sound(Phase.WORK, force=True)),
                        ft.Button("Pausa curta", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: play_phase_sound(Phase.SHORT_BREAK, force=True)),
                        ft.Button("Pausa longa", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: play_phase_sound(Phase.LONG_BREAK, force=True)),
                        ft.Button("Contagem regressiva", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: play_countdown_demo()),
                    ],
                    wrap=True,
                ),
                ft.Button("Salvar tempos", icon=ft.Icons.SAVE, on_click=save_pomodoro_config),
                ft.Divider(),
                ft.Text("Conexão com o Anytype", size=20, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY),
                ft.Row([pairing_status_text, ft.Button("Parear com o Anytype", icon=ft.Icons.LINK, on_click=do_pairing)]),
                ft.Row([space_dropdown, ft.Button("Carregar espaços", icon=ft.Icons.REFRESH, on_click=load_spaces)]),
                ft.Row([base_url_field, api_version_field]),
                ft.Row([task_type_field, status_prop_field]),
                status_options_field,
                ft.Row([in_progress_field, done_field]),
                ft.Row(
                    [
                        ft.Button("Salvar configurações", icon=ft.Icons.SAVE, on_click=save_anytype_config),
                        ft.Button("Testar / preparar (tipo, propriedade, tags)", icon=ft.Icons.CHECK, on_click=test_setup),
                    ],
                    wrap=True,
                ),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

    # =============================================================== NAVEGAÇÃO
    content_area = ft.Container(expand=True)

    def go_pomodoro(e=None):
        content_area.content = build_pomodoro_view()
        page.update()

    def go_tasks(e=None):
        content_area.content = build_tasks_view()
        page.update()

    def go_settings(e=None):
        content_area.content = build_settings_view()
        page.update()

    # ------------------------------------------------------------- modo mini
    # Encolhe a MESMA janela para um "carimbo" pequeno, sem borda, sempre
    # visível por cima das outras janelas, que pode ser arrastado para
    # qualquer lugar da tela (clique e arraste em qualquer ponto, exceto no
    # botão de restaurar).
    title_control = ft.Text("Pomodoro + Anytype", size=28, weight=ft.FontWeight.W_800, color=ft.Colors.PRIMARY)
    divider = ft.Divider()

    def build_mini_view() -> ft.Control:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Row([mini_phase_icon, mini_time_text], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                    ft.Text(
                        "Arraste a borda da janela para deixá-la pequena.",
                        size=11,
                        italic=True,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Button("Restaurar", icon=ft.Icons.OPEN_IN_FULL, on_click=lambda e: exit_mini_mode()),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
            padding=16,
        )

    def enter_mini_mode(e=None):
        # OBS: tentar forçar page.window.width/height é um "melhor esforço"
        # — em algumas instalações Linux/Wayland esse pedido é ignorado
        # pelo motor gráfico em tempo de execução (bug conhecido do Flet:
        # https://github.com/flet-dev/flet/issues/5988). Por isso a janela
        # continua livre/redimensionável: se o tamanho lembrado não for
        # aplicado, é só arrastar a borda manualmente de novo.
        state["in_mini_mode"] = True
        if config.gui.mini_width and config.gui.mini_height:
            page.window.width = config.gui.mini_width
            page.window.height = config.gui.mini_height
        page.window.always_on_top = True
        page.padding = 0
        page.controls.clear()
        page.add(build_mini_view())
        page.update()

    def exit_mini_mode(e=None):
        state["in_mini_mode"] = False
        page.window.always_on_top = False
        page.padding = 24
        page.controls.clear()
        page.add(title_control, nav, divider, content_area)
        go_pomodoro()
        page.update()

    def on_page_resize(e):
        # enquanto estiver no modo mini, guarda o tamanho atual da janela
        # (o que o usuário ajustou arrastando a borda) para reaplicar da
        # próxima vez que "Modo mini" for clicado.
        if state.get("in_mini_mode") and page.window.width and page.window.height:
            config.gui.mini_width = page.window.width
            config.gui.mini_height = page.window.height
            persist()

    page.on_resize = on_page_resize

    nav = ft.Row(
        [
            ft.Button("Pomodoro", icon=ft.Icons.TIMER, on_click=go_pomodoro),
            ft.Button("Tarefas", icon=ft.Icons.CHECKLIST, on_click=go_tasks),
            ft.Button("Configurações", icon=ft.Icons.SETTINGS, on_click=go_settings),
            ft.Button("Modo mini", icon=ft.Icons.PICTURE_IN_PICTURE_ALT, on_click=enter_mini_mode),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        wrap=True,
    )

    page.add(title_control, nav, divider, content_area)
    go_pomodoro()


if __name__ == "__main__":
    ft.run(main)
