import os
import time

from pomodoro_app.config import PomodoroConfig
from pomodoro_app.pomodoro_timer import Phase, PomodoroStatus, PomodoroTimer
from pomodoro_app.sounds import COUNTDOWN_SECONDS, countdown_sound_path, sound_path_for_phase


def test_status_progress_and_text():
    status = PomodoroStatus(Phase.WORK, 2, 4, total_seconds=1500, remaining_seconds=375,
                            is_paused=False, is_running=True)
    assert status.elapsed_seconds == 1125
    assert status.progress == 0.75
    assert str(status) == "[Foco] ciclo 2 (pausa longa a cada 4 ciclos) — 06:15 restantes — rodando"
    assert PomodoroStatus(Phase.IDLE, 1, 4, 0, 0, False, False).progress == 0.0


def test_countdown_sounds():
    assert os.path.basename(countdown_sound_path(COUNTDOWN_SECONDS)) == "countdown_tick.wav"
    assert os.path.basename(countdown_sound_path(2)) == "countdown_tick.wav"
    assert os.path.basename(countdown_sound_path(1)) == "countdown_last.wav"  # último: mais agudo
    assert countdown_sound_path(COUNTDOWN_SECONDS + 1) is None
    assert countdown_sound_path(0) is None


def test_every_phase_has_a_start_sound():
    for phase in (Phase.WORK, Phase.SHORT_BREAK, Phase.LONG_BREAK):
        assert sound_path_for_phase(phase.value), phase
    assert sound_path_for_phase(Phase.IDLE.value) is None


def test_timer_runs_phases_in_order():
    """Integração real com fases curtíssimas (2 s de foco, 1 s de pausa)."""
    events = []
    timer = PomodoroTimer(
        PomodoroConfig(work_minutes=2 / 60, short_break_minutes=1 / 60, long_break_minutes=1, cycles_before_long_break=4),
        on_phase_start=lambda phase, total, cycle: events.append(("início", phase, total, cycle)),
        on_phase_end=lambda phase, cycle: events.append(("fim", phase, cycle)),
    )
    timer.start()
    time.sleep(3.6)
    timer.stop()
    assert events[:4] == [
        ("início", Phase.WORK, 2, 1),
        ("fim", Phase.WORK, 1),
        ("início", Phase.SHORT_BREAK, 1, 1),
        ("fim", Phase.SHORT_BREAK, 1),
    ]
    assert timer.status().phase == Phase.IDLE and not timer.status().is_running
