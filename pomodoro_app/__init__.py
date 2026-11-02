"""Anytype + Pomodoro: timer Pomodoro com tarefas guardadas no Anytype.

Organização:
- config, paths ............ configuração (config.json) e caminhos
- anytype_client ........... cliente HTTP da API local do Anytype
- task_manager ............. tarefas: setup do espaço, CRUD, status, notas
- pomodoro_timer ........... o timer (thread própria, sem I/O)
- session .................. regras da sessão, comuns às duas interfaces
- task_filters, user_story,
  formatting ............... lógica pura (busca/ordenação, história, datas)
- sounds, notifier ......... sons e notificações do sistema
- cli ...................... interface de linha de comando
- ui/ ...................... interface gráfica (Flet), uma tela por módulo
"""

# Nome mostrado pelo Anytype na janela de aprovação do pareamento.
APP_NAME = "Anytype + Pomodoro"
