"""
Gera os sons de notificação da aplicação (assets/sounds/*.wav).

São carrilhões curtos sintetizados matematicamente (seno + um leve harmônico,
com envelope de ataque/decaimento suave) — não usa nenhum banco de sons
externo, então não há questão de licenciamento nem dependência de internet.

Rode de novo se quiser trocar as notas/timbre:
    python generate_sounds.py
"""
from __future__ import annotations

import math
import os
import struct
import wave

SAMPLE_RATE = 44100
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _note(freq: float, duration: float, volume: float = 0.35, decay: float = 4.5) -> list:
    """Uma nota tipo 'sino': fundamental + harmônico fraco, com ataque rápido
    (5ms) e decaimento exponencial suave — soa como um carrilhão, não um bipe."""
    n = int(SAMPLE_RATE * duration)
    attack = max(1, int(SAMPLE_RATE * 0.005))
    samples = []
    for i in range(n):
        t = i / SAMPLE_RATE
        envelope = math.exp(-decay * t)
        if i < attack:
            envelope *= i / attack
        value = math.sin(2 * math.pi * freq * t)
        value += 0.25 * math.sin(2 * math.pi * freq * 2 * t)  # harmônico
        samples.append(volume * envelope * value)
    return samples


def _write_wav(path: str, samples: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        frames = b"".join(
            struct.pack("<h", max(-32768, min(32767, int(s * 32767)))) for s in samples
        )
        wf.writeframes(frames)


def _sequence(notes: list, gap: float = 0.02) -> list:
    """Concatena notas com um pequeno intervalo de silêncio entre elas."""
    silence = [0.0] * int(SAMPLE_RATE * gap)
    out: list = []
    for freq, dur, vol, decay in notes:
        out.extend(_note(freq, dur, vol, decay))
        out.extend(silence)
    return out


# Notas (Hz) de referência: C5=523.25, E5=659.25, G4=392.00

SOUNDS = {
    # Foco: dois tons curtos e brilhantes, subindo — energizante, "vamos lá"
    "work_start.wav": _sequence([
        (523.25, 0.22, 0.32, 6.0),
        (659.25, 0.30, 0.34, 5.0),
    ]),
    # Pausa curta: um único tom calmo e morno
    "short_break_start.wav": _note(392.00, 0.9, volume=0.30, decay=3.0),
    # Pausa longa: três tons descendo devagar — relaxante, "pode soltar"
    "long_break_start.wav": _sequence([
        (659.25, 0.35, 0.28, 3.2),
        (523.25, 0.40, 0.28, 3.0),
        (392.00, 0.55, 0.30, 2.4),
    ], gap=0.04),
}


def main():
    for filename, samples in SOUNDS.items():
        _write_wav(os.path.join(OUT_DIR, filename), samples)
        print(f"gerado: assets/{filename}")


if __name__ == "__main__":
    main()
