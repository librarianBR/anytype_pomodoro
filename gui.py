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

import json
from typing import Optional

import flet as ft

from anytype_client import AnytypeClient, AnytypeError
from config import AppConfig, load_config, save_config
from notifier import notify, play_sound, sound_path_for_phase
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


def main(page: ft.Page) -> None:
    page.title = "Pomodoro + Anytype"
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

    def snack(message: str, error: bool = False):
        page.show_dialog(
            ft.SnackBar(
                content=ft.Text(message),
                bgcolor=ft.Colors.RED_400 if error else ft.Colors.GREEN_700,
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
    progress = ft.ProgressBar(value=0, width=420)
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
            label = next((o.text for o in task_dropdown.options if o.key == new_task_id), "")
            linked_task_text.value = f"Vinculada a: {label}"
            try:
                task_manager.set_status(new_task_id, config.anytype.in_progress_status_name)
                task_manager.add_note(new_task_id, "Sessão vinculada a esta tarefa.")
            except (AnytypeError, SetupError) as ex:
                snack(str(ex), error=True)
        else:
            linked_task_text.value = ""
        page.update()

    def on_task_dropdown_change(e):
        link_task(task_dropdown.value)

    def unlink_task(e):
        link_task(None)

    task_dropdown.on_select = on_task_dropdown_change
    unlink_btn = ft.Button("Desvincular", icon=ft.Icons.LINK_OFF, on_click=unlink_task)

    def on_phase_start(phase: Phase, total_seconds: int, cycle: int):
        notify(f"{PHASE_LABELS[phase]} iniciado", f"Ciclo {cycle}")

        def apply():
            phase_icon.icon = PHASE_ICONS[phase]
            phase_text.value = PHASE_LABELS[phase]
            mini_phase_icon.icon = PHASE_ICONS[phase]
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
                try:
                    task_manager.add_note(state["linked_task_id"], log_text)
                    if mark_done:
                        task_manager.set_status(state["linked_task_id"], config.anytype.done_status_name)
                        snack(f"Tarefa marcada como '{config.anytype.done_status_name}' e observação registrada.")
                    else:
                        snack("Observação registrada na tarefa.")
                except AnytypeError as ex:
                    snack(str(ex), error=True)
                close_dialog(dlg)

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
            schedule_on_ui(ask_mark_done)

    def on_tick(status):
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
                ft.Text("Sessão Pomodoro", size=22, weight=ft.FontWeight.BOLD),
                ft.Container(height=10),
                phase_row,
                time_text,
                cycle_text,
                progress,
                ft.Container(height=10),
                ft.Row([task_dropdown, unlink_btn], alignment=ft.MainAxisAlignment.CENTER),
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
                ft.Button("Excluir", on_click=confirm, bgcolor=ft.Colors.RED_400),
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
            width=150,
            value=task.status if task.status in config.anytype.status_options else None,
            options=[ft.DropdownOption(key=s, text=s) for s in config.anytype.status_options],
        )
        status_dd.on_select = make_status_change_handler(task, status_dd)
        return ft.Container(
            content=ft.Row(
                [
                    ft.Text(task.name, expand=True, overflow=ft.TextOverflow.ELLIPSIS),
                    status_dd,
                    ft.IconButton(ft.Icons.EDIT, tooltip="Renomear", on_click=lambda e, t=task: rename_task_dialog(t)),
                    ft.IconButton(ft.Icons.EDIT_NOTE, tooltip="Observações", on_click=lambda e, t=task: show_notes_dialog(t)),
                    ft.IconButton(ft.Icons.DELETE, tooltip="Excluir", on_click=lambda e, t=task: delete_task_dialog(t)),
                    ft.IconButton(ft.Icons.INFO_OUTLINE, tooltip="Ver JSON bruto", on_click=lambda e, t=task: show_raw_json(t)),
                ],
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=8,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
        )

    def refresh_tasks_list(e=None):
        tasks_list.controls.clear()
        if not config.anytype.space_id:
            tasks_list.controls.append(ft.Text("Escolha um espaço do Anytype nas Configurações primeiro."))
            page.update()
            return
        try:
            task_manager.setup()
        except SetupError as ex:
            tasks_list.controls.append(ft.Text(f"Configuração incompleta: {ex}", color=ft.Colors.RED_400))
            page.update()
            return
        except AnytypeError as ex:
            tasks_list.controls.append(ft.Text(f"Erro: {ex}", color=ft.Colors.RED_400))
            page.update()
            return

        try:
            tasks = task_manager.list_tasks()
        except AnytypeError as ex:
            tasks_list.controls.append(ft.Text(f"Erro ao listar tarefas: {ex}", color=ft.Colors.RED_400))
            page.update()
            return

        if not tasks:
            tasks_list.controls.append(ft.Text("(nenhuma tarefa)"))
        for t in tasks:
            tasks_list.controls.append(build_task_row(t))
        page.update()

    def create_task(e):
        name = (new_task_name.value or "").strip()
        if not name:
            snack("Digite um nome para a tarefa.", error=True)
            return
        try:
            task_manager.setup()
            task_manager.create_task(name, status=new_task_status.value)
            new_task_name.value = ""
            snack("Tarefa criada.")
            refresh_tasks_list()
        except (AnytypeError, SetupError) as ex:
            snack(str(ex), error=True)

    def build_tasks_view() -> ft.Control:
        new_task_status.options = [ft.DropdownOption(key=s, text=s) for s in config.anytype.status_options]
        if not new_task_status.value and config.anytype.status_options:
            new_task_status.value = config.anytype.status_options[0]
        refresh_tasks_list()
        return ft.Column(
            [
                ft.Text("Tarefas (Anytype)", size=22, weight=ft.FontWeight.BOLD),
                ft.Row([new_task_name, new_task_status, ft.Button("Criar", icon=ft.Icons.ADD, on_click=create_task)]),
                ft.Row([ft.Button("Atualizar lista", icon=ft.Icons.REFRESH, on_click=refresh_tasks_list)]),
                tasks_list,
            ],
            spacing=12,
        )

    # ========================================================= CONFIGURAÇÕES
    work_field = ft.TextField(label="Foco (min)", value=str(config.pomodoro.work_minutes), width=140)
    short_field = ft.TextField(label="Pausa curta (min)", value=str(config.pomodoro.short_break_minutes), width=160)
    long_field = ft.TextField(label="Pausa longa (min)", value=str(config.pomodoro.long_break_minutes), width=160)
    cycles_field = ft.TextField(
        label="Ciclos até pausa longa", value=str(config.pomodoro.cycles_before_long_break), width=200
    )
    sound_checkbox = ft.Checkbox(label="Tocar som no início de cada fase", value=config.pomodoro.sound_enabled)

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
        "Pareado" if config.anytype.api_key else "Não pareado", color=ft.Colors.GREEN_700 if config.anytype.api_key else ft.Colors.RED_400
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
                pairing_status_text.color = ft.Colors.GREEN_700
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

    def build_settings_view() -> ft.Control:
        return ft.Column(
            [
                ft.Text("Configurações do Pomodoro", size=20, weight=ft.FontWeight.BOLD),
                ft.Row([work_field, short_field, long_field, cycles_field]),
                sound_checkbox,
                ft.Row(
                    [
                        ft.Text("Testar sons:"),
                        ft.Button("Foco", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: play_phase_sound(Phase.WORK, force=True)),
                        ft.Button("Pausa curta", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: play_phase_sound(Phase.SHORT_BREAK, force=True)),
                        ft.Button("Pausa longa", icon=ft.Icons.PLAY_ARROW, on_click=lambda e: play_phase_sound(Phase.LONG_BREAK, force=True)),
                    ],
                    wrap=True,
                ),
                ft.Button("Salvar tempos", icon=ft.Icons.SAVE, on_click=save_pomodoro_config),
                ft.Divider(),
                ft.Text("Conexão com o Anytype", size=20, weight=ft.FontWeight.BOLD),
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
    title_control = ft.Text("Pomodoro + Anytype", size=28, weight=ft.FontWeight.BOLD)
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
