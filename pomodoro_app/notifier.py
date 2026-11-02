"""Notificações de início/fim de fase: sempre imprimem no terminal e também
disparam uma notificação nativa do sistema operacional — no Linux via
`notify-send`; nos demais (ou se ele não existir) via a biblioteca opcional
'plyer'. Notificação é um extra: nunca deve quebrar a aplicação."""
from __future__ import annotations

import datetime as _dt
import platform
import shutil
import subprocess

from . import APP_NAME

try:
    from plyer import notification as _plyer_notification
except Exception:  # biblioteca opcional
    _plyer_notification = None

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
    try:
        if platform.system() == "Linux" and _notify_send(title, message):
            return
        if _plyer_notification:
            _plyer_notification.notify(
                title=title, message=message, app_name=APP_NAME, timeout=NOTIFICATION_TIMEOUT_SECONDS
            )
    except Exception:
        pass
