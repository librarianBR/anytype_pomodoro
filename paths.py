"""
Resolução de caminhos que funciona tanto rodando com `python arquivo.py`
quanto empacotado como um único .exe pelo PyInstaller.

Por que isso é necessário: quando o PyInstaller empacota tudo num único
executável (--onefile), ele extrai os arquivos para uma pasta TEMPORÁRIA
diferente a cada execução (acessível via `sys._MEIPASS`), que é apagada ao
fechar o programa. Se o código calcula caminhos a partir de `__file__`
(como um script normal faria), ele acaba lendo/gravando dentro dessa pasta
temporária sem perceber — e por isso o config.json "some" a cada vez que o
.exe é fechado, e os arquivos de som "não aparecem" na pasta do dist (eles
nem são copiados pra lá automaticamente; precisam ser declarados na hora de
empacotar, veja o README).

Este módulo separa dois tipos de caminho, que precisam de tratamento
diferente:
- `resource_path()`: arquivos empacotados e SOMENTE LEITURA (ex.: os sons em
  assets/). Dentro de um .exe, ficam na pasta temporária do PyInstaller
  (`sys._MEIPASS`) — e é só ali que eles existem de verdade a cada execução.
- `app_data_dir()`: pasta para dados do USUÁRIO, que precisam ser GRAVADOS e
  PERSISTIR entre execuções (o config.json). Dentro de um .exe, isso fica ao
  lado do próprio arquivo .exe (não na pasta temporária), para não se perder
  quando o programa fecha.

Rodando como script normal (`python gui.py`), os dois caminhos coincidem:
a pasta onde os arquivos .py estão.
"""
from __future__ import annotations

import os
import sys


def _is_frozen() -> bool:
    """True quando rodando dentro de um executável gerado por PyInstaller
    (ou ferramenta semelhante que define sys.frozen)."""
    return bool(getattr(sys, "frozen", False))


def resource_path(*parts: str) -> str:
    """Caminho para um recurso empacotado e somente-leitura (ex.: um som em
    assets/). Use para LER arquivos que vieram junto com a aplicação."""
    if _is_frozen():
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, *parts)


def app_data_dir() -> str:
    """Pasta persistente e gravável para dados do usuário (config.json).
    Ao lado do .exe quando empacotado; ao lado dos arquivos .py em modo
    script normal. Use para LER e GRAVAR configuração/estado do usuário."""
    if _is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
