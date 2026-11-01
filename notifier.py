"""Notificações de início/fim de fase: sempre imprime no terminal e também
dispara uma notificação nativa do sistema operacional — no Linux via
`notify-send`; nos demais (ou se ele não existir) via a biblioteca opcional
'plyer'. Também toca um som curto no início de cada fase e uma contagem
regressiva nos últimos segundos de cada fase."""
from __future__ import annotations

import datetime as _dt
import os
import platform
import shutil
import subprocess

from paths import resource_path

try:
    from plyer import notification as _plyer_notification
except Exception:  # biblioteca opcional
    _plyer_notification = None

_SOUNDS_DIR = resource_path("assets")

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


# Quantos segundos antes do fim de cada fase a contagem regressiva começa
COUNTDOWN_SECONDS = 5


def countdown_sound_path(remaining_seconds: int) -> str | None:
    """Som da contagem regressiva para o segundo restante informado: um
    tique de COUNTDOWN_SECONDS até 2, um tique mais agudo no 1, e None fora
    da contagem (ou se os arquivos não existirem)."""
    if not 1 <= remaining_seconds <= COUNTDOWN_SECONDS:
        return None
    filename = "countdown_last.wav" if remaining_seconds == 1 else "countdown_tick.wav"
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


APP_NAME = "Anytype Pomodoro"
NOTIFICATION_TIMEOUT_SECONDS = 5


def _notify_send(title: str, message: str) -> bool:
    """Notificação nativa no Linux via `notify-send` (pacote libnotify-bin,
    presente por padrão no GNOME, KDE, XFCE etc.). Preferido ao plyer no
    Linux porque o plyer, sem o pacote `dbus-python` (que precisa ser
    compilado), imprime um aviso a cada execução, ignora o tempo de
    exibição pedido e espera o comando terminar. Retorna False se o
    notify-send não existir, para cair no plyer."""
    if not shutil.which("notify-send"):
        return False
    subprocess.Popen(
        [
            "notify-send",
            "--app-name", APP_NAME,
            "--expire-time", str(NOTIFICATION_TIMEOUT_SECONDS * 1000),
            title,
            message,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True


def notify(title: str, message: str) -> None:
    now = _dt.datetime.now().strftime("%H:%M:%S")
    print(f"\a[{now}] {title} — {message}")
    # notificação de SO é apenas um extra, nunca deve quebrar o app
    try:
        if platform.system() == "Linux" and _notify_send(title, message):
            return
        if _plyer_notification:
            _plyer_notification.notify(
                title=title, message=message, app_name=APP_NAME, timeout=NOTIFICATION_TIMEOUT_SECONDS
            )
    except Exception:
        pass
