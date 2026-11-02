@echo off
rem Executa o Anytype + Pomodoro no Windows.
rem   executar.bat        -> interface grafica (gui.py)
rem   executar.bat cli    -> linha de comando (main.py)
setlocal
cd /d "%~dp0"

set "SCRIPT=gui.py"
if /i "%~1"=="cli" set "SCRIPT=main.py"

where uv >nul 2>nul
if %errorlevel%==0 (
    uv run "%SCRIPT%"
) else if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "%SCRIPT%"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Erro: nem o uv nem o Python foram encontrados. Veja o README.md.
        pause
        exit /b 1
    )
    python "%SCRIPT%"
)

if errorlevel 1 pause
endlocal
