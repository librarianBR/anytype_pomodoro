"""
Núcleo do timer Pomodoro.

Roda em uma thread própria (não bloqueia a interface). Expõe:
- start()/pause()/resume()/stop()/skip()
- status() -> dict com fase atual, tempo restante, ciclo atual etc.
- callbacks on_phase_start / on_phase_end / on_tick, chamados a cada evento,
  para você saber exatamente quando algo começa/termina e o que está
  acontecendo a qualquer momento.

Não depende do Anytype nem de nada de I/O: pode ser usado isoladamente,
com uma interface de texto, gráfica, ou apenas em scripts.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

from config import PomodoroConfig


class Phase(str, Enum):
    WORK = "work"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"
    IDLE = "idle"


PHASE_LABELS_PT = {
    Phase.WORK: "Foco (execução)",
    Phase.SHORT_BREAK: "Pausa curta",
    Phase.LONG_BREAK: "Pausa longa",
    Phase.IDLE: "Parado",
}


@dataclass
class PomodoroStatus:
    phase: Phase
    cycle: int                 # número do ciclo de trabalho atual (1, 2, 3...)
    cycles_before_long_break: int
    total_seconds: int         # duração total da fase atual
    remaining_seconds: int     # quanto falta para a fase atual acabar
    is_paused: bool
    is_running: bool

    @property
    def elapsed_seconds(self) -> int:
        return self.total_seconds - self.remaining_seconds

    def __str__(self) -> str:
        m, s = divmod(max(self.remaining_seconds, 0), 60)
        estado = "pausado" if self.is_paused else ("rodando" if self.is_running else "parado")
        return (
            f"[{PHASE_LABELS_PT[self.phase]}] ciclo {self.cycle} "
            f"(próxima pausa longa após o ciclo {self.cycles_before_long_break}) "
            f"— {m:02d}:{s:02d} restantes — {estado}"
        )


OnPhaseStart = Callable[[Phase, int, int], None]   # phase, total_seconds, cycle
OnPhaseEnd = Callable[[Phase, int], None]          # phase, cycle
OnTick = Callable[[PomodoroStatus], None]          # a cada segundo


class PomodoroTimer:
    def __init__(
        self,
        config: PomodoroConfig,
        on_phase_start: Optional[OnPhaseStart] = None,
        on_phase_end: Optional[OnPhaseEnd] = None,
        on_tick: Optional[OnTick] = None,
    ):
        self.config = config
        self.on_phase_start = on_phase_start
        self.on_phase_end = on_phase_end
        self.on_tick = on_tick

        self._lock = threading.Lock()
        self._phase = Phase.IDLE
        self._cycle = 1
        self._total_seconds = 0
        self._remaining_seconds = 0
        self._running = False

        self._pause_event = threading.Event()   # setado = pausado
        self._stop_event = threading.Event()     # setado = deve parar tudo
        self._skip_event = threading.Event()     # setado = pular fase atual
        self._restart_event = threading.Event()  # setado = reiniciar fase atual
        self._thread: Optional[threading.Thread] = None

    # ---------------------------------------------------------- controles
    def start(self) -> None:
        """Inicia o ciclo de pomodoros em uma thread de fundo."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self._pause_event.set()

    def resume(self) -> None:
        self._pause_event.clear()

    def skip(self) -> None:
        """Encerra a fase atual imediatamente e passa para a próxima."""
        self._skip_event.set()

    def restart_phase(self) -> None:
        """Reinicia a contagem da fase atual do zero (volta para a duração
        total), sem avançar de fase nem de ciclo."""
        self._restart_event.set()

    def stop(self) -> None:
        """Para completamente o timer (encerra a thread)."""
        self._stop_event.set()
        self._pause_event.clear()
        if self._thread:
            self._thread.join(timeout=2)
        with self._lock:
            self._phase = Phase.IDLE
            self._running = False

    # ------------------------------------------------------------- status
    def status(self) -> PomodoroStatus:
        with self._lock:
            return PomodoroStatus(
                phase=self._phase,
                cycle=self._cycle,
                cycles_before_long_break=self.config.cycles_before_long_break,
                total_seconds=self._total_seconds,
                remaining_seconds=self._remaining_seconds,
                is_paused=self._pause_event.is_set(),
                is_running=self._running,
            )

    # ------------------------------------------------------------ interno
    def _run_loop(self) -> None:
        with self._lock:
            self._running = True
            self._cycle = 1
        while not self._stop_event.is_set():
            completed = self._run_phase(Phase.WORK, self.config.work_minutes * 60)
            if not completed:
                break
            self._wait_while_paused()
            if self._stop_event.is_set():
                break

            with self._lock:
                is_long = self._cycle % self.config.cycles_before_long_break == 0
            break_phase = Phase.LONG_BREAK if is_long else Phase.SHORT_BREAK
            break_minutes = (
                self.config.long_break_minutes if is_long else self.config.short_break_minutes
            )
            completed = self._run_phase(break_phase, break_minutes * 60)
            if not completed:
                break
            self._wait_while_paused()
            if self._stop_event.is_set():
                break

            with self._lock:
                self._cycle += 1

        with self._lock:
            self._running = False
            self._phase = Phase.IDLE

    def _wait_while_paused(self) -> None:
        """Bloqueia entre uma fase e a próxima enquanto o timer estiver
        pausado. Existe para o caso de a interface pausar o timer no exato
        momento em que uma fase termina (ex.: enquanto espera o usuário
        responder a uma caixa de diálogo) — sem isso, a fase seguinte
        começaria a contar em segundo plano antes de a pergunta ser
        respondida, "roubando" tempo dela."""
        while self._pause_event.is_set() and not self._stop_event.is_set():
            time.sleep(0.2)

    def _run_phase(self, phase: Phase, duration_seconds: float) -> bool:
        """Executa uma fase até o fim, pausa ou parada. Retorna False se foi
        interrompida por stop()."""
        total = int(round(duration_seconds))
        with self._lock:
            self._phase = phase
            self._total_seconds = total
            self._remaining_seconds = total
            cycle = self._cycle

        if self.on_phase_start:
            self.on_phase_start(phase, total, cycle)

        self._skip_event.clear()
        self._restart_event.clear()
        remaining = total
        while remaining > 0:
            if self._stop_event.is_set():
                return False
            if self._skip_event.is_set():
                remaining = 0
                with self._lock:
                    self._remaining_seconds = 0
                break
            if self._restart_event.is_set():
                self._restart_event.clear()
                remaining = total
                with self._lock:
                    self._remaining_seconds = remaining
                if self.on_phase_start:
                    self.on_phase_start(phase, total, cycle)
                continue
            if self._pause_event.is_set():
                time.sleep(0.2)
                continue

            time.sleep(1)
            remaining -= 1
            with self._lock:
                self._remaining_seconds = remaining
            if self.on_tick:
                self.on_tick(self.status())

        if self.on_phase_end:
            self.on_phase_end(phase, cycle)
        return True
