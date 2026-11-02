"""
Interface de linha de comando: técnica Pomodoro + tarefas no Anytype, por
menus no terminal. Rode com:  python main.py

Na primeira vez: abra o Anytype Desktop, escolha "Parear com o Anytype" e
digite o código de 4 dígitos que aparece nele; depois escolha o espaço das
tarefas (veja o README para o que precisa existir nesse espaço).
"""
from __future__ import annotations

import json
import sys
from typing import Callable, Dict, List, Optional, Sequence, Tuple, TypeVar

from .anytype_client import NO_SPACES_MESSAGE, PAIRING_HINT, AnytypeClient, AnytypeError
from .config import AppConfig, load_config, save_config
from .formatting import format_date, parse_date
from .session import PomodoroSession
from .task_manager import SetupError, Task, TaskManager
from .user_story import build_story

T = TypeVar("T")

SESSION_COMMANDS = "status | pausar | retomar | reiniciar | pular | vincular | desvincular | concluir | parar"


# ------------------------------------------------------- entrada do usuário
def input_nonempty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("  (não pode ficar vazio)")


def ask_yes_no(prompt: str) -> bool:
    return input(f"{prompt} (s/N): ").strip().lower() == "s"


def choose_from_list(items: Sequence[T], label_fn: Callable[[T], str], prompt: str = "Escolha: ") -> T:
    for i, item in enumerate(items, 1):
        print(f"  {i}. {label_fn(item)}")
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("  Opção inválida.")


def run_menu(title: str, options: List[Tuple[str, Callable[[], object]]], exit_label: str = "Voltar") -> None:
    """Menu numerado que se repete até a opção 0. Erros do Anytype são
    mostrados sem derrubar o menu."""
    while True:
        print(f"\n== {title} ==")
        for i, (label, _) in enumerate(options, 1):
            print(f"{i}. {label}")
        print(f"0. {exit_label}")
        choice = input("Escolha: ").strip()
        if choice == "0":
            return
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            try:
                options[int(choice) - 1][1]()
            except (AnytypeError, SetupError) as e:
                print(f"Erro: {e}")
        else:
            print("Opção inválida.")


class App:
    def __init__(self):
        self.config: AppConfig = load_config()
        self.client = AnytypeClient(
            self.config.anytype.base_url, self.config.anytype.api_version, self.config.anytype.api_key
        )
        self.task_manager = TaskManager(self.client, self.config)
        self.session = PomodoroSession(self.config, self.task_manager, on_focus_end=self._on_focus_end)

    @property
    def done_status(self) -> str:
        return self.config.anytype.done_status_name

    # ------------------------------------------------------------- Anytype
    def pair_with_anytype(self):
        print("\n== Pareamento com o Anytype ==\nAbra o Anytype Desktop antes de continuar.")
        try:
            challenge_id = self.client.create_challenge()
            print(PAIRING_HINT)
            api_key = self.client.solve_challenge(challenge_id, input_nonempty("Digite o código de 4 dígitos: "))
        except AnytypeError as e:
            print(f"Erro: {e}")
            return
        self.config.anytype.api_key = api_key
        save_config(self.config)
        print("Pareado com sucesso! A chave foi salva em config.json.")

    def choose_space(self):
        try:
            spaces = self.client.list_spaces()
        except AnytypeError as e:
            print(f"Erro: {e}")
            return
        if not spaces:
            print(NO_SPACES_MESSAGE)
            return
        space = choose_from_list(spaces, lambda s: s.get("name", s.get("id")))
        self.task_manager.select_space(space["id"])
        print(f"Espaço selecionado: {space.get('name')}")

    def ensure_setup(self) -> bool:
        try:
            self.task_manager.setup()
            return True
        except SetupError as e:
            print(f"\nConfiguração incompleta: {e}")
        except AnytypeError as e:
            print(f"\nErro de comunicação com o Anytype: {e}")
        return False

    # -------------------------------------------------------------- tarefas
    def menu_tasks(self):
        if self.ensure_setup():
            run_menu("Tarefas", [
                ("Listar tarefas", self._list_tasks),
                ("Criar tarefa", self._create_task),
                ("Renomear tarefa", self._rename_task),
                ("Mudar status de uma tarefa", self._change_status),
                ("Excluir tarefa", self._delete_task),
                ("Ver/adicionar observações", self._manage_notes),
                ("[depurar] ver JSON bruto de uma tarefa", self._debug_raw),
            ])

    def _list_tasks(self):
        tasks = self.task_manager.list_tasks()
        if not tasks:
            print("(nenhuma tarefa)")
        for t in tasks:
            due = f"  — entrega {format_date(t.due)}" if t.due else ""
            print(f"  [{t.status}] {t.name}{due}")

    def _pick_task(self, pending_only: bool = False) -> Optional[Task]:
        tasks = self.task_manager.list_pending_tasks() if pending_only else self.task_manager.list_tasks()
        if not tasks:
            print("(nenhuma tarefa)")
            return None
        return choose_from_list(tasks, lambda t: f"[{t.status}] {t.name}")

    def _choose_status(self) -> str:
        return choose_from_list(self.config.anytype.status_options, lambda s: s)

    def _create_task(self):
        name = input_nonempty("Nome da tarefa: ")
        status = self._choose_status()
        due = self._ask_due_date()
        story = self._ask_user_story()
        task = self.task_manager.create_task(name, description=story, status=status, due=due)
        extra = f", entrega em {format_date(task.due)}" if task.due else ""
        print(f"Tarefa criada: {task.name} [{task.status}]{extra}")

    @staticmethod
    def _ask_due_date():
        while True:
            try:
                return parse_date(input("Data de entrega (dd/mm/aaaa, Enter para nenhuma): "))
            except ValueError:
                print("  (data inválida — use dd/mm/aaaa, ex.: 15/11/2026)")

    @staticmethod
    def _ask_user_story() -> str:
        """História de usuário opcional, montada pelas perguntas do Scrum."""
        if not ask_yes_no("Escrever uma história de usuário (Scrum)?"):
            return ""
        who = input_nonempty("  Como (tipo de usuário): ")
        what = input_nonempty("  quero (objetivo): ")
        why = input("  para (benefício, opcional): ")
        print("  Critérios de aceitação (um por linha, Enter vazio para terminar):")
        criteria = []
        while line := input("   - ").strip():
            criteria.append(line)
        return build_story(who, what, why, criteria)

    def _rename_task(self):
        task = self._pick_task()
        if task:
            task = self.task_manager.rename_task(task.id, input_nonempty("Novo nome: "))
            print(f"Renomeada para: {task.name}")

    def _change_status(self):
        task = self._pick_task()
        if task:
            task = self.task_manager.set_status(task.id, self._choose_status())
            print(f"Novo status de '{task.name}': {task.status}")

    def _delete_task(self):
        task = self._pick_task()
        if task and ask_yes_no(f"Excluir '{task.name}'?"):
            self.task_manager.delete_task(task.id)
            print("Excluída.")

    def _manage_notes(self):
        task = self._pick_task()
        if not task:
            return
        print("\n--- Observações registradas ---")
        print(self.task_manager.get_task_notes(task.id) or "(nenhuma observação registrada ainda)")
        note = input("\nNova observação (Enter para não adicionar nada): ").strip()
        if note:
            self.task_manager.add_note(task.id, note)
            print("Observação adicionada.")

    def _debug_raw(self):
        task = self._pick_task()
        if not task:
            return
        cfg = self.config.anytype
        print("\n--- JSON bruto da tarefa (properties) ---")
        print(json.dumps(task.raw.get("properties", task.raw), indent=2, ensure_ascii=False))
        print("\n--- Propriedade de status configurada ---")
        print("status_property_id no config.json:", cfg.status_property_id)
        try:
            props = self.client.list_properties(cfg.space_id)
            status_prop = next(
                (p for p in props if p.get("id") == cfg.status_property_id
                 or p.get("name", "").lower() == cfg.status_property_name.lower()),
                None,
            )
            print(json.dumps(status_prop, indent=2, ensure_ascii=False))
            if status_prop:
                print("\n--- Tags dessa propriedade ---")
                print(json.dumps(self.client.list_tags(cfg.space_id, status_prop["id"]), indent=2, ensure_ascii=False))
        except AnytypeError as e:
            print(f"(não consegui buscar detalhes da propriedade: {e})")

    # --------------------------------------------------------- configuração
    def menu_configure_pomodoro(self):
        p = self.config.pomodoro
        print("\n== Configurar tempos (em minutos, Enter para manter) ==")

        def ask(label: str, current, convert):
            while True:
                raw = input(f"{label} [{current:g}]: ").strip()
                if not raw:
                    return current
                try:
                    value = convert(raw.replace(",", "."))
                    if value > 0:
                        return value
                except ValueError:
                    pass
                print("  (use um número maior que zero)")

        p.work_minutes = ask("Tempo de foco", p.work_minutes, float)
        p.short_break_minutes = ask("Pausa curta", p.short_break_minutes, float)
        p.long_break_minutes = ask("Pausa longa", p.long_break_minutes, float)
        p.cycles_before_long_break = ask("Ciclos até pausa longa", p.cycles_before_long_break, int)
        raw = input(f"Tocar sons (início de fase e contagem regressiva)? (s/n) [{'s' if p.sound_enabled else 'n'}]: ")
        if raw.strip().lower() in ("s", "n"):
            p.sound_enabled = raw.strip().lower() == "s"
        save_config(self.config)
        print("Configuração salva.")

    # -------------------------------------------------------------- sessão
    def _on_focus_end(self, cycle: int):
        """Fim de um ciclo de foco com tarefa vinculada (o timer já está
        pausado pela sessão até finish_focus)."""
        note = input(
            "\nCiclo de foco terminado. Observação para registrar na tarefa (opcional, Enter para pular): "
        )
        mark_done = ask_yes_no(f"Marcar a tarefa como '{self.done_status}'?")
        try:
            self.session.finish_focus(note, mark_done=mark_done)
            if mark_done:
                print(f"Tarefa marcada como {self.done_status}. Use 'vincular' para escolher a próxima.")
        except (AnytypeError, SetupError) as e:
            print(f"Não consegui atualizar a tarefa: {e}")

    def _link(self, task_id: Optional[str]):
        for warning in self.session.link(task_id):
            print(f"Aviso: {warning}")

    def _ask_link(self):
        if self.config.anytype.space_id and self.ensure_setup():
            task = self._pick_task(pending_only=True)
            if task:
                self._link(task.id)
                print(f"Vinculado. Status atualizado para '{self.config.anytype.in_progress_status_name}'.")

    def _complete(self):
        if not self.session.linked_task_id:
            print("Nenhuma tarefa vinculada. Use 'vincular' primeiro.")
            return
        if not ask_yes_no(f"Marcar a tarefa vinculada como '{self.done_status}'?"):
            return
        note = input("Observação (opcional, Enter para pular): ")
        try:
            self.session.complete(self.session.completion_note(note))
            print(f"Tarefa marcada como {self.done_status} e desvinculada. Use 'vincular' para escolher a próxima.")
        except (AnytypeError, SetupError) as e:
            print(f"Não consegui atualizar a tarefa: {e}")

    def run_pomodoro(self):
        if self.config.anytype.space_id and ask_yes_no("Vincular esta sessão a uma tarefa do Anytype?"):
            self._ask_link()
        self.session.start()
        print(f"\nSessão iniciada. Comandos: {SESSION_COMMANDS}\n")

        def unlink():
            self._link(None)
            print("Desvinculado.")

        commands: Dict[str, Callable[[], object]] = {
            "status": lambda: print(self.session.status()),
            "pausar": lambda: (self.session.pause(), print("Pausado.")),
            "retomar": lambda: (self.session.resume(), print("Retomado.")),
            "reiniciar": lambda: (self.session.restart_phase(), print("Fase reiniciada.")),
            "pular": self.session.skip,
            "vincular": self._ask_link,
            "desvincular": unlink,
            "concluir": self._complete,
        }
        aliases = {"s": "status", "p": "pausar", "r": "retomar", "restart": "reiniciar", "skip": "pular",
                   "trocar": "vincular", "link": "vincular", "unlink": "desvincular", "done": "concluir",
                   "feito": "concluir"}
        while True:
            cmd = input("> ").strip().lower()
            cmd = aliases.get(cmd, cmd)
            if cmd in ("parar", "sair", "stop", "q"):
                self.session.stop()
                print("Sessão encerrada.")
                return
            if cmd in commands:
                commands[cmd]()
            else:
                print(f"Comandos: {SESSION_COMMANDS}")

    # --------------------------------------------------------------- menu
    def main_menu(self):
        print("\n===== Anytype + Pomodoro =====")
        run_menu("Menu principal", [
            ("Iniciar sessão Pomodoro", self.run_pomodoro),
            ("Configurar tempos do Pomodoro", self.menu_configure_pomodoro),
            ("Parear com o Anytype", self.pair_with_anytype),
            ("Escolher espaço do Anytype", self.choose_space),
            ("Gerenciar tarefas", self.menu_tasks),
        ], exit_label="Sair")
        print("Até mais!")


def main():
    try:
        App().main_menu()
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        sys.exit(0)
