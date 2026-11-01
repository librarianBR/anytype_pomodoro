"""
Sessão Pomodoro: o timer + a tarefa vinculada, com as regras que valem para
qualquer interface (gráfica ou linha de comando):

- sons de início de fase e contagem regressiva, e notificações do sistema;
- vincular / trocar / desvincular a tarefa, com registro no histórico;
- concluir a tarefa a qualquer momento;
- no fim de cada ciclo de foco com tarefa vinculada, pausar o timer e pedir
  à interface que pergunte se a tarefa foi concluída (finish_focus retoma).

A interface só desenha e pergunta: recebe os eventos pelos callbacks
on_phase_start / on_tick / on_focus_end, que são chamados na thread do timer
(a interface é responsável por levar a atualização para a sua própria thread).
"""
from __future__ import annotations

from typing import Callable, List, Optional

from .anytype_client import AnytypeError
from .config import AppConfig
from .formatting import format_mmss
from .notifier import notify
from .pomodoro_timer import PHASE_LABELS, Phase, PomodoroStatus, PomodoroTimer
from .sounds import countdown_sound_path, play_sound, sound_path_for_phase
from .task_manager import SetupError, TaskManager

NOTE_LINKED = "Sessão vinculada a esta tarefa."
NOTE_UNLINKED = "Sessão desvinculada desta tarefa."

OnPhaseStart = Callable[[Phase, int, int], None]   # fase, duração (s), ciclo
OnTick = Callable[[PomodoroStatus], None]
OnFocusEnd = Callable[[int], None]                 # ciclo que terminou


class PomodoroSession:
    def __init__(
        self,
        config: AppConfig,
        task_manager: TaskManager,
        on_phase_start: Optional[OnPhaseStart] = None,
        on_tick: Optional[OnTick] = None,
        on_focus_end: Optional[OnFocusEnd] = None,
    ):
        self.config = config
        self.task_manager = task_manager
        self.on_phase_start = on_phase_start
        self.on_tick = on_tick
        self.on_focus_end = on_focus_end
        self.timer: Optional[PomodoroTimer] = None
        self.linked_task_id: Optional[str] = None

    # ------------------------------------------------------------ timer
    @property
    def is_running(self) -> bool:
        return self.timer is not None

    def start(self) -> None:
        if self.timer:
            return
        self.timer = PomodoroTimer(
            self.config.pomodoro,
            on_phase_start=self._handle_phase_start,
            on_phase_end=self._handle_phase_end,
            on_tick=self._handle_tick,
        )
        self.timer.start()

    def stop(self) -> None:
        """Para o timer. O vínculo com a tarefa é mantido (de propósito: dá
        para iniciar de novo sem escolher a tarefa outra vez)."""
        if self.timer:
            self.timer.stop()
            self.timer = None

    def pause(self) -> None:
        if self.timer:
            self.timer.pause()

    def resume(self) -> None:
        if self.timer:
            self.timer.resume()

    def skip(self) -> None:
        if self.timer:
            self.timer.skip()

    def restart_phase(self) -> None:
        if self.timer:
            self.timer.restart_phase()

    def status(self) -> Optional[PomodoroStatus]:
        return self.timer.status() if self.timer else None

    # ------------------------------------------- eventos (thread do timer)
    def _sounds_on(self) -> bool:
        return self.config.pomodoro.sound_enabled

    def _handle_phase_start(self, phase: Phase, total_seconds: int, cycle: int) -> None:
        if self._sounds_on():
            play_sound(sound_path_for_phase(phase.value))
        notify(f"{PHASE_LABELS[phase]} iniciado", f"Ciclo {cycle} — {format_mmss(total_seconds)}")
        if self.on_phase_start:
            self.on_phase_start(phase, total_seconds, cycle)

    def _handle_tick(self, status: PomodoroStatus) -> None:
        # Tocado aqui, na thread do timer, para o tique sair no segundo certo
        # (play_sound não bloqueia).
        if self._sounds_on():
            play_sound(countdown_sound_path(status.remaining_seconds))
        if self.on_tick:
            self.on_tick(status)

    def _handle_phase_end(self, phase: Phase, cycle: int) -> None:
        notify(f"{PHASE_LABELS[phase]} terminou", f"Fim do ciclo {cycle}")
        if phase == Phase.WORK and self.linked_task_id and self.on_focus_end:
            # Pausa AQUI, ainda na thread do timer e antes de a fase seguinte
            # começar — senão a pausa já contaria tempo enquanto a pergunta
            # está na tela. finish_focus() retoma.
            self.pause()
            self.on_focus_end(cycle)

    # ------------------------------------------------------------ tarefas
    def link(self, task_id: Optional[str]) -> List[str]:
        """Vincula, troca ou (com None) desvincula a tarefa, a qualquer
        momento. A nova tarefa passa a "em andamento". O histórico das duas
        tarefas registra a troca. Devolve avisos de erro do Anytype (o
        vínculo muda mesmo assim)."""
        old_id = self.linked_task_id
        if old_id == task_id:
            return []
        warnings: List[str] = []
        if old_id:
            warnings += self._try(lambda: self.task_manager.add_note(old_id, NOTE_UNLINKED))
        self.linked_task_id = task_id
        if task_id:
            warnings += self._try(
                lambda: self.task_manager.set_status(task_id, self.config.anytype.in_progress_status_name),
                lambda: self.task_manager.add_note(task_id, NOTE_LINKED),
            )
        return warnings

    def unlink(self) -> List[str]:
        return self.link(None)

    def completion_note(self, extra: str = "") -> str:
        """Texto do histórico ao concluir pelo botão/comando "Concluir"."""
        text = "Tarefa concluída"
        status = self.status()
        if status and status.is_running and status.phase == Phase.WORK:
            text += f" durante o ciclo de foco {status.cycle} ({status.elapsed_seconds // 60} min de foco nele)"
        return _with_extra(text, extra)

    def focus_note(self, extra: str = "") -> str:
        """Texto do histórico ao fim de um ciclo de foco."""
        return _with_extra(f"Sessão de foco concluída ({self.config.pomodoro.work_minutes:g} min)", extra)

    def complete(self, note: Optional[str] = None) -> None:
        """Marca a tarefa vinculada como concluída, registra `note` no
        histórico (se houver) e a tira da sessão. Não usa unlink(), para não
        registrar "desvinculada" logo após a conclusão. O timer não muda.
        Propaga AnytypeError/SetupError (aí a tarefa continua vinculada)."""
        task_id = self.linked_task_id
        if not task_id:
            return
        if note:
            self.task_manager.add_note(task_id, note)
        self.task_manager.set_status(task_id, self.config.anytype.done_status_name)
        self.linked_task_id = None

    def finish_focus(self, extra_note: str = "", mark_done: bool = False) -> None:
        """Resposta à pergunta do fim do ciclo de foco: registra a sessão (e
        conclui a tarefa, se pedido) e retoma o timer — mesmo se o Anytype
        der erro, que é propagado depois de retomar."""
        try:
            if self.linked_task_id:
                note = self.focus_note(extra_note)
                if mark_done:
                    self.complete(note)
                else:
                    self.task_manager.add_note(self.linked_task_id, note)
        finally:
            self.resume()

    @staticmethod
    def _try(*actions: Callable[[], object]) -> List[str]:
        """Executa as ações em ordem; para na primeira que falhar e devolve
        a mensagem de erro."""
        try:
            for action in actions:
                action()
        except (AnytypeError, SetupError) as ex:
            return [str(ex)]
        return []


def _with_extra(text: str, extra: str) -> str:
    extra = (extra or "").strip()
    return f"{text} — {extra}" if extra else text
