# Especificação do PyInstaller para empacotar a interface gráfica (gui.py)
# num único executável, incluindo a pasta de sons (assets/).
#
# Uso, dentro da pasta do projeto (com as dependências já instaladas):
#     pyinstaller pomodoro.spec
#
# O executável final fica em dist/PomodoroAnytype.exe (Windows) ou
# dist/PomodoroAnytype (Linux/Mac). O config.json é criado ao lado desse
# executável na primeira execução e persiste normalmente entre uma
# execução e outra (veja paths.py) — não precisa mais parear/configurar
# tudo de novo toda vez que abrir.
#
# Se o PyInstaller reclamar de algum módulo faltando ao rodar o .exe
# (comum em bibliotecas como o Flet, que carregam alguns submódulos de
# forma dinâmica), tente adicionar --collect-all flet ao comando abaixo,
# ou rode `pyinstaller --onefile --windowed --add-data "assets;assets"
# --collect-all flet --name PomodoroAnytype gui.py` diretamente, sem usar
# este arquivo .spec.

a = Analysis(
    ["gui.py"],
    pathex=[],
    binaries=[],
    datas=[("assets", "assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="PomodoroAnytype",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # sem janela de terminal atrás da interface gráfica
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
