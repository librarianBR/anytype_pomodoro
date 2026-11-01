"""Sons da aplicação: sino no início de cada fase e contagem regressiva nos
últimos segundos. Os arquivos ficam em assets/ (gerados por
generate_sounds.py) e são tocados pelo tocador de áudio do próprio sistema
operacional — som é um extra: se nada puder tocar, nada quebra."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import threading
from typing import Optional

from .paths import resource_path

SOUNDS_DIR = resource_path("assets")

# Quantos segundos antes do fim de cada fase a contagem regressiva começa
COUNTDOWN_SECONDS = 5

# Chaves iguais ao .value de pomodoro_timer.Phase (work/short_break/long_break)
_PHASE_SOUND_FILES = {
    "work": "work_start.wav",
    "short_break": "short_break_start.wav",
    "long_break": "long_break_start.wav",
}
_COUNTDOWN_TICK = "countdown_tick.wav"
_COUNTDOWN_LAST = "countdown_last.wav"


def _existing(filename: Optional[str]) -> Optional[str]:
    """Caminho absoluto do arquivo em assets/, ou None se não existir
    (ex.: os sons ainda não foram gerados com generate_sounds.py)."""
    if not filename:
        return None
    path = os.path.join(SOUNDS_DIR, filename)
    return path if os.path.exists(path) else None


def sound_path_for_phase(phase_value: str) -> Optional[str]:
    """Som de início da fase (pelo .value de Phase)."""
    return _existing(_PHASE_SOUND_FILES.get(phase_value))


def countdown_sound_path(remaining_seconds: int) -> Optional[str]:
    """Som da contagem para o segundo restante informado: um tique de
    COUNTDOWN_SECONDS até 2, um tique mais agudo no 1, e None fora da
    contagem."""
    if not 1 <= remaining_seconds <= COUNTDOWN_SECONDS:
        return None
    return _existing(_COUNTDOWN_LAST if remaining_seconds == 1 else _COUNTDOWN_TICK)


def play_sound(path: Optional[str]) -> None:
    """Toca um .wav em segundo plano, sem bloquear. Melhor esforço: tenta um
    tocador comum do sistema e não faz nada se nenhum estiver disponível."""
    if not path or not os.path.exists(path):
        return
    try:
        system = platform.system()
        if system == "Darwin":
            _spawn(["afplay", path])
        elif system == "Windows":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            for player in ("paplay", "aplay", "ffplay"):
                if shutil.which(player):
                    extra = ["-nodisp", "-autoexit", "-loglevel", "quiet"] if player == "ffplay" else []
                    _spawn([player, *extra, path])
                    break
    except Exception:
        pass


def play_countdown_demo() -> None:
    """Toca a contagem regressiva completa (5…1), um tique por segundo — para
    testar nas Configurações sem esperar uma fase acabar."""
    for delay, remaining in enumerate(range(COUNTDOWN_SECONDS, 0, -1)):
        threading.Timer(delay, play_sound, args=(countdown_sound_path(remaining),)).start()


def _spawn(cmd: list) -> None:
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
