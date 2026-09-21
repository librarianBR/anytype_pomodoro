"""
Aplicação de linha de comando: técnica Pomodoro + tarefas no Anytype.

Rode com:  python main.py

Tudo é feito por um menu interativo. Na primeira vez, você vai precisar:
  1) abrir o Anytype Desktop no seu computador;
  2) no menu principal, escolher "Parear com o Anytype" e digitar o código
     de 4 dígitos que vai aparecer na tela do Anytype;
  3) escolher o espaço (space) onde as tarefas serão criadas;
  4) garantir que existe um tipo de objeto (ex.: "Task") e uma propriedade
     do tipo Select chamada "Status" nesse espaço — veja o README.
"""
from __future__ import annotations

import sys

from anytype_client import AnytypeClient, AnytypeError
from config import AppConfig, load_config, save_config
from notifier import notify, play_sound, sound_path_for_phase
from pomodoro_timer import Phase, PomodoroTimer
from task_manager import SetupError, TaskManager

PHASE_LABELS = {
    Phase.WORK: "🍅 Foco",
    Phase.SHORT_BREAK: "☕ Pausa curta",
    Phase.LONG_BREAK: "🛋️  Pausa longa",
    Phase.IDLE: "Parado",
}


def input_nonempty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("  (não pode ficar vazio)")


def choose_from_list(items, label_fn, prompt="Escolha: "):
    for i, item in enumerate(items, 1):
        print(f"  {i}. {label_fn(item)}")
    while True:
        raw = input(prompt).strip()
        if raw.isdigit() and 1 <= int(raw) <= len(items):
            return items[int(raw) - 1]
        print("  Opção inválida.")


class App:
    def __init__(self):
        self.config: AppConfig = load_config()
        self.client = AnytypeClient(
            self.config.anytype.base_url,
            self.config.anytype.api_version,
            self.config.anytype.api_key,
        )
        self.task_manager = TaskManager(self.client, self.config)
        self.timer: PomodoroTimer | None = None
        self.current_task_id: str | None = None

    def save(self):
        save_config(self.config)

    # ------------------------------------------------------------- Anytype
    def pair_with_anytype(self):
        print("\n== Pareamento com o Anytype ==")
        print("Abra o Anytype Desktop antes de continuar.")
        try:
            challenge_id = self.client.create_challenge()
        except AnytypeError as e:
            print(f"Erro: {e}")
            return
        print("Um código de 4 dígitos deve aparecer no Anytype Desktop agora.")
        code = input_nonempty("Digite o código de 4 dígitos: ")
        try:
            api_key = self.client.solve_challenge(challenge_id, code)
        except AnytypeError as e:
            print(f"Erro ao validar o código: {e}")
            return
        self.config.anytype.api_key = api_key
        self.save()
        print("Pareado com sucesso! A chave foi salva em config.json.")

    def choose_space(self):
        try:
            spaces = self.client.list_spaces()
        except AnytypeError as e:
            print(f"Erro: {e}")
            return
        if not spaces:
            print("Nenhum espaço encontrado.")
            return
        space = choose_from_list(spaces, lambda s: s.get("name", s.get("id")))
        self.config.anytype.space_id = space["id"]
        # muda de espaço invalida caches específicos do espaço anterior
        self.config.anytype.task_type_key = ""
        self.config.anytype.status_property_id = ""
        self.config.anytype.status_tag_ids = {}
        self.save()
        print(f"Espaço selecionado: {space.get('name')}")

    def ensure_setup(self) -> bool:
        try:
            self.task_manager.setup()
            return True
        except SetupError as e:
            print(f"\nConfiguração incompleta: {e}")
            return False
        except AnytypeError as e:
            print(f"\nErro de comunicação com o Anytype: {e}")
            return False

    # -------------------------------------------------------------- tarefas
    def menu_tasks(self):
        if not self.ensure_setup():
            return
        while True:
            print("\n== Tarefas ==")
            print("1. Listar tarefas")
            print("2. Criar tarefa")
            print("3. Editar (renomear) tarefa")
            print("4. Mudar status de uma tarefa")
            print("5. Excluir tarefa")
            print("6. Ver/adicionar observações")
            print("7. [depurar] ver JSON bruto de uma tarefa")
            print("0. Voltar")
            choice = input("Escolha: ").strip()
            try:
                if choice == "1":
                    self._list_tasks()
                elif choice == "2":
                    self._create_task()
                elif choice == "3":
                    self._rename_task()
                elif choice == "4":
                    self._change_status()
                elif choice == "5":
                    self._delete_task()
                elif choice == "6":
                    self._manage_notes()
                elif choice == "7":
                    self._debug_raw()
                elif choice == "0":
                    return
                else:
                    print("Opção inválida.")
            except (AnytypeError, SetupError) as e:
                print(f"Erro: {e}")

    def _list_tasks(self):
        tasks = self.task_manager.list_tasks()
        if not tasks:
            print("(nenhuma tarefa)")
            return
        for t in tasks:
            print(f"  [{t.status}] {t.name}  (id={t.id})")

    def _pick_task(self, exclude_done: bool = False):
        tasks = self.task_manager.list_tasks()
        if exclude_done:
            tasks = [t for t in tasks if t.status != self.config.anytype.done_status_name]
        if not tasks:
            print("(nenhuma tarefa)")
            return None
        return choose_from_list(tasks, lambda t: f"[{t.status}] {t.name}")

    def _create_task(self):
        name = input_nonempty("Nome da tarefa: ")
        desc = input("Descrição (opcional): ").strip()
        status = choose_from_list(self.config.anytype.status_options, lambda s: s)
        task = self.task_manager.create_task(name, description=desc, status=status)
        print(f"Tarefa criada: {task.name} [{task.status}]")

    def _rename_task(self):
        task = self._pick_task()
        if not task:
            return
        new_name = input_nonempty("Novo nome: ")
        task = self.task_manager.rename_task(task.id, new_name)
        print(f"Renomeada para: {task.name}")

    def _change_status(self):
        task = self._pick_task()
        if not task:
            return
        status = choose_from_list(self.config.anytype.status_options, lambda s: s)
        task = self.task_manager.set_status(task.id, status)
        print(f"Novo status de '{task.name}': {task.status}")

    def _delete_task(self):
        task = self._pick_task()
        if not task:
            return
        confirm = input(f"Excluir '{task.name}'? (s/N): ").strip().lower()
        if confirm == "s":
            self.task_manager.delete_task(task.id)
            print("Excluída.")

    def _manage_notes(self):
        task = self._pick_task()
        if not task:
            return
        body = self.task_manager.get_task_notes(task.id)
        print("\n--- Observações registradas ---")
        print(body if body else "(nenhuma observação registrada ainda)")
        note = input("\nNova observação (Enter para não adicionar nada): ").strip()
        if note:
            self.task_manager.add_note(task.id, note)
            print("Observação adicionada.")

    def _debug_raw(self):
        import json
        task = self._pick_task()
        if not task:
            return
        print("\n--- JSON bruto da tarefa (properties) ---")
        print(json.dumps(task.raw.get("properties", task.raw), indent=2, ensure_ascii=False))
        print("\n--- Propriedade de status configurada ---")
        print("status_property_id no config.json:", self.config.anytype.status_property_id)
        try:
            props = self.client.list_properties(self.config.anytype.space_id)
            status_prop = next(
                (p for p in props if p.get("id") == self.config.anytype.status_property_id
                 or p.get("name", "").lower() == self.config.anytype.status_property_name.lower()),
                None,
            )
            print(json.dumps(status_prop, indent=2, ensure_ascii=False))
            if status_prop:
                tags = self.client.list_tags(self.config.anytype.space_id, status_prop["id"])
                print("\n--- Tags dessa propriedade ---")
                print(json.dumps(tags, indent=2, ensure_ascii=False))
        except AnytypeError as e:
            print(f"(não consegui buscar detalhes da propriedade: {e})")

    # --------------------------------------------------------- configuração
    def menu_configure_pomodoro(self):
        p = self.config.pomodoro
        print("\n== Configurar tempos (em minutos, Enter para manter) ==")

        def ask(label, current):
            raw = input(f"{label} [{current}]: ").strip()
            return float(raw) if raw else current

        p.work_minutes = ask("Tempo de foco", p.work_minutes)
        p.short_break_minutes = ask("Pausa curta", p.short_break_minutes)
        p.long_break_minutes = ask("Pausa longa", p.long_break_minutes)
        raw = input(f"Ciclos até pausa longa [{p.cycles_before_long_break}]: ").strip()
        if raw:
            p.cycles_before_long_break = int(raw)
        raw = input(f"Tocar som no início de cada fase? (s/n) [{'s' if p.sound_enabled else 'n'}]: ").strip().lower()
        if raw in ("s", "n"):
            p.sound_enabled = raw == "s"
        self.save()
        print("Configuração salva.")

    # -------------------------------------------------------------- timer
    def _on_phase_start(self, phase: Phase, total_seconds: int, cycle: int):
        m = total_seconds // 60
        if self.config.pomodoro.sound_enabled:
            play_sound(sound_path_for_phase(phase.value))
        notify(
            f"{PHASE_LABELS[phase]} iniciado",
            f"Ciclo {cycle} — duração de {m} min. Digite 'status' a qualquer momento.",
        )

    def _on_phase_end(self, phase: Phase, cycle: int):
        notify(f"{PHASE_LABELS[phase]} terminou", f"Fim do ciclo {cycle}.")
        if phase == Phase.WORK and self.current_task_id:
            note = input(
                "\nCiclo de foco terminado. Observação para registrar na tarefa "
                "(opcional, Enter para pular): "
            ).strip()
            log_text = f"Sessão de foco concluída ({self.config.pomodoro.work_minutes:g} min)"
            if note:
                log_text += f" — {note}"
            try:
                self.task_manager.add_note(self.current_task_id, log_text)
            except (AnytypeError, SetupError) as e:
                print(f"Não consegui registrar a observação: {e}")

            resp = input(
                f"Marcar a tarefa como '{self.config.anytype.done_status_name}'? (s/N): "
            ).strip().lower()
            if resp == "s":
                try:
                    self.task_manager.set_status(
                        self.current_task_id, self.config.anytype.done_status_name
                    )
                    print(f"Tarefa marcada como {self.config.anytype.done_status_name}.")
                except AnytypeError as e:
                    print(f"Não consegui atualizar a tarefa: {e}")

    def _link_task(self, new_task_id: str | None):
        """Vincula, troca ou desvincula a tarefa da sessão a qualquer
        momento, registrando o histórico em ambas as tarefas envolvidas."""
        old_task_id = self.current_task_id
        if old_task_id == new_task_id:
            return
        if old_task_id:
            try:
                self.task_manager.add_note(old_task_id, "Sessão desvinculada desta tarefa.")
            except (AnytypeError, SetupError) as e:
                print(f"Aviso: não consegui registrar a observação ({e}).")

        self.current_task_id = new_task_id
        if new_task_id:
            try:
                self.task_manager.set_status(new_task_id, self.config.anytype.in_progress_status_name)
                self.task_manager.add_note(new_task_id, "Sessão vinculada a esta tarefa.")
                print(f"Vinculado. Status atualizado para '{self.config.anytype.in_progress_status_name}'.")
            except (AnytypeError, SetupError) as e:
                print(f"Aviso: não consegui atualizar a tarefa ({e}).")

    def run_pomodoro(self):
        if self.config.anytype.space_id and self.ensure_setup():
            resp = input("Vincular esta sessão a uma tarefa do Anytype? (s/N): ").strip().lower()
            if resp == "s":
                link_task = self._pick_task(exclude_done=True)
                if link_task:
                    self._link_task(link_task.id)

        self.timer = PomodoroTimer(
            self.config.pomodoro,
            on_phase_start=self._on_phase_start,
            on_phase_end=self._on_phase_end,
        )
        self.timer.start()
        print(
            "\nSessão iniciada. Comandos: status | pausar | retomar | "
            "reiniciar | pular | vincular | desvincular | parar\n"
        )
        while True:
            cmd = input("> ").strip().lower()
            if cmd in ("status", "s"):
                print(self.timer.status())
            elif cmd in ("pausar", "p"):
                self.timer.pause()
                print("Pausado.")
            elif cmd in ("retomar", "r"):
                self.timer.resume()
                print("Retomado.")
            elif cmd in ("reiniciar", "restart"):
                self.timer.restart_phase()
                print("Fase reiniciada (mesmo ciclo, contagem do zero).")
            elif cmd in ("pular", "skip"):
                self.timer.skip()
            elif cmd in ("vincular", "trocar", "link"):
                if self.config.anytype.space_id and self.ensure_setup():
                    task = self._pick_task(exclude_done=True)
                    if task:
                        self._link_task(task.id)
            elif cmd in ("desvincular", "unlink"):
                self._link_task(None)
                print("Desvinculado.")
            elif cmd in ("parar", "sair", "stop", "q"):
                self.timer.stop()
                print("Sessão encerrada.")
                return
            else:
                print(
                    "Comandos: status | pausar | retomar | reiniciar | pular | "
                    "vincular | desvincular | parar"
                )

    # --------------------------------------------------------------- menu
    def main_menu(self):
        while True:
            print("\n===== Pomodoro + Anytype =====")
            print("1. Iniciar sessão Pomodoro")
            print("2. Configurar tempos do Pomodoro")
            print("3. Parear com o Anytype")
            print("4. Escolher espaço do Anytype")
            print("5. Gerenciar tarefas")
            print("0. Sair")
            choice = input("Escolha: ").strip()
            if choice == "1":
                self.run_pomodoro()
            elif choice == "2":
                self.menu_configure_pomodoro()
            elif choice == "3":
                self.pair_with_anytype()
            elif choice == "4":
                self.choose_space()
            elif choice == "5":
                self.menu_tasks()
            elif choice == "0":
                print("Até mais!")
                return
            else:
                print("Opção inválida.")


def main():
    app = App()
    try:
        app.main_menu()
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
        sys.exit(0)


if __name__ == "__main__":
    main()
