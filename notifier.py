"""Notificações de início/fim de fase: sempre imprime no terminal e, se a
biblioteca 'plyer' estiver instalada, também dispara uma notificação nativa
do sistema operacional. Também toca um som curto no início de cada fase."""
from __future__ import annotations

import datetime as _dt
import os
import platform
import shutil
import subprocess

try:
    from plyer import notification as _plyer_notification
except Exception:  # biblioteca opcional
    _plyer_notification = None

_SOUNDS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

# Chaves iguais ao .value de pomodoro_timer.Phase (work/short_break/long_break)
_PHASE_SOUND_FILES = {
    "work": "work_start.wav",
    "short_break": "short_break_start.wav",
    "long_break": "long_break_start.wav",
}


def sound_path_for_phase(phase_value: str) -> str | None:
    """Caminho absoluto do .wav de início da fase, ou None se não existir
    (ex.: os arquivos ainda não foram gerados com generate_sounds.py)."""
    filename = _PHASE_SOUND_FILES.get(phase_value)
    if not filename:
        return None
    path = os.path.join(_SOUNDS_DIR, filename)
    return path if os.path.exists(path) else None


def play_sound(path: str | None) -> None:
    """Toca um .wav em segundo plano (não bloqueia a aplicação). Melhor
    esforço: tenta um tocador comum do sistema operacional e simplesmente
    não faz nada se nenhum estiver disponível — som é um extra, nunca deve
    travar ou quebrar a aplicação."""
    if not path or not os.path.exists(path):
        return
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Windows":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        else:
            for player in ("paplay", "aplay", "ffplay"):
                if shutil.which(player):
                    cmd = (
                        [player, path]
                        if player != "ffplay"
                        else [player, "-nodisp", "-autoexit", "-loglevel", "quiet", path]
                    )
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
    except Exception:
        pass


def notify(title: str, message: str) -> None:
    now = _dt.datetime.now().strftime("%H:%M:%S")
    print(f"\a[{now}] {title} — {message}")
    if _plyer_notification:
        try:
            _plyer_notification.notify(title=title, message=message, timeout=5)
        except Exception:
            pass  # notificação de SO é apenas um extra, nunca deve quebrar o app
