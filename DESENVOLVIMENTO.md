# Desenvolvimento

Notas técnicas para quem vai mexer no código. Para instalar e usar a
aplicação, veja o [README](README.md).

## Ambiente

```bash
uv sync            # cria o .venv com as dependências (inclui o pytest)
uv run gui.py      # interface gráfica (Flet)
uv run main.py     # linha de comando
uv run pytest      # testes automatizados
```

O `config.json` é criado na primeira execução a partir de
`config.example.json`. Ele guarda a chave da API do Anytype e por isso está
no `.gitignore`: nunca faça commit dele. Para mudar os valores padrão de
quem usa o projeto pela primeira vez, edite `config.example.json`.

## Estrutura do código

```
gui.py, main.py          pontos de entrada (só chamam o pacote)
generate_sounds.py       gera os sons em assets/*.wav
pomodoro_app/
  config.py              configuração (config.json) e seus ajustes
  paths.py               onde ficam config.json e assets (script ou executável)
  anytype_client.py      cliente HTTP da API local do Anytype
  task_manager.py        tarefas: preparar o espaço, CRUD, status, observações
  pomodoro_timer.py      o timer (thread própria, sem I/O) e os nomes das fases
  session.py             regras da sessão, comuns às duas interfaces
  task_filters.py        busca, filtro e ordenação da lista (funções puras)
  user_story.py          modelo de história de usuário (Scrum)
  formatting.py          tempo (mm:ss) e datas (dd/mm/aaaa)
  sounds.py              sons de fase e contagem regressiva
  notifier.py            notificações do sistema
  cli.py                 interface de linha de comando
  ui/
    app.py               janela, navegação e modo mini
    context.py           o que as telas compartilham (config, Anytype,
                         sessão, avisos e diálogos padronizados)
    theme.py             paletas, cores e ícones das fases, estilos
    pomodoro_view.py     tela Pomodoro
    tasks_view.py        tela Tarefas
    settings_view.py     tela Configurações
tests/                   testes automatizados (pytest)
```

As camadas dependem só "para baixo": as interfaces (`cli.py` e `ui/`)
usam `session.py`, que usa `task_manager.py` e `pomodoro_timer.py`, que
usam `anytype_client.py` e `config.py`. Nada abaixo das interfaces
importa o Flet.

**Onde mexer:**

- Comportamento da sessão (vincular, concluir, o que vai para o histórico,
  sons, notificações): `session.py`. Vale para a GUI e para a CLI de uma vez.
- O que a interface mostra: o módulo da tela em `ui/` (ou `cli.py`).
- Conversa com o Anytype: `task_manager.py` (regras) e `anytype_client.py`
  (HTTP).
- Cores e estilos: `ui/theme.py`.

**`PomodoroSession`** (`session.py`) avisa a interface por três callbacks,
chamados na thread do timer: `on_phase_start`, `on_tick` e `on_focus_end`.
No fim de um ciclo de foco com tarefa vinculada, a sessão pausa o timer e
chama `on_focus_end`; a interface pergunta ao usuário e responde com
`finish_focus(...)`, que registra no histórico e retoma o timer.

## Testes

```bash
uv run pytest            # todos (cerca de 5 s)
uv run pytest -k session # só os que têm "session" no nome
```

Os testes não precisam do Anytype nem de internet: `tests/conftest.py` tem
um `FakeClient`, um Anytype em memória que responde nos mesmos formatos da
API real (inclusive as particularidades listadas abaixo). Eles também
garantem que nada é gravado no `config.json` de verdade e que nenhum som ou
notificação é disparado.

| Arquivo | O que cobre |
|---|---|
| `test_task_manager.py` | preparação do espaço, criar/listar/renomear/excluir, status e checkbox Done, observações, data de entrega (sem erro de fuso), troca de espaço |
| `test_session.py` | vincular/trocar/desvincular, concluir, fim do ciclo de foco (pausa, pergunta, retomada mesmo com erro), sons |
| `test_task_filters.py` | busca sem acentos, filtros de status, ordenações e limite |
| `test_config.py` | salvar/carregar, chaves desconhecidas, migração de nomes antigos, troca de espaço e de status |
| `test_anytype_client.py` | formatos de resposta, paginação, configuração |
| `test_formatting.py`, `test_user_story.py` | tempo, datas e história de usuário |
| `test_timer_and_sounds.py` | sequência real de fases (com fases de 1–2 s) e sons |

A interface gráfica em si não tem testes automatizados: as regras que ela
usa estão em `session.py`, `task_filters.py` e `task_manager.py`, que são
testados; o desenho das telas é conferido abrindo a aplicação.

## Integração com a API do Anytype

A API local roda dentro do Anytype Desktop (`http://localhost:31009`).
O projeto usa a versão `2025-11-08` (cabeçalho `Anytype-Version`,
configurável em `anytype.api_version`), conforme
<https://developers.anytype.io/docs/reference>. A API é nova e muda com
frequência; quando uma chamada falha, o erro já traz o corpo da resposta,
o que normalmente mostra o campo que mudou.

Particularidades já encontradas nessa versão:

- **Respostas de objeto vêm em `{"object": {...}}`** (criar, consultar,
  editar). `anytype_client._unwrap_object` aceita esse formato e o antigo
  `{"data": {...}}`.
- **O campo `description` de topo na criação é ignorado.** A descrição
  precisa ir como propriedade: `{"key": "description", "text": ...}`.
- **Data de entrega**: propriedade nativa `due_date`, formato
  `"2026-11-15T00:00:00Z"` (meia-noite UTC). Ao ler, use só a parte da
  data, sem converter fuso, senão no Brasil (UTC-3) vira o dia anterior.
- **Data de criação**: propriedade nativa `created_date` (essa, sim, é um
  instante, e é exibida no fuso local).
- **Listagem paginada**: `GET /objects` devolve `pagination.has_more`;
  `list_objects` segue as páginas até o fim.
- **Exclusão** manda o objeto para a lixeira; a listagem pode levar um
  instante para refletir.
- **Corpo da página (`body`)** não é atualizável de forma confiável via
  API, por isso o histórico de observações fica numa propriedade de texto
  (`Notes`).
- **Tipos e propriedades** não são criados de forma confiável via API; o
  usuário cria o "esqueleto" (tipo, `Status`, `Notes`) uma vez, no app.
- **Checkbox `done`** dos objetos de layout "Action" não acompanha o
  `Status` sozinho; `TaskManager._sync_done_checkbox` sincroniza os dois em
  modo melhor esforço.

O reconhecimento do status (`TaskManager.to_task`) tolera variações: a
propriedade pode vir por `id` ou `key`, e o valor de um "select" como
string ou objeto `{"id", "name"}`. Se o status aparecer como `?`, o botão
"Ver JSON bruto" da aba Tarefas mostra o que a instalação devolve.

## Interface (Flet)

- O timer roda em outra thread: mudanças de interface vindas dele passam
  por `AppContext.run_on_ui` (`page.loop.call_soon_threadsafe`). Eventos
  que chegam depois de "Parar" são descartados (`session.is_running`).
- Para falar com o Anytype a partir de uma tela, use `ctx.attempt(ação,
  "mensagem de sucesso")`: mostra o aviso de sucesso ou o erro, sem travar.
- **Cuidado com layout**: um filho com `expand=True` dentro de uma `Row`
  com `wrap=True`, ou dentro de uma `Column` com `scroll`, é erro no
  Flutter, e a área inteira vira um quadro cinza (sem erro no terminal).
- Sons usam o tocador do sistema (`sounds.play_sound`) em vez do
  controle `Audio` do Flet, que se mostrou inconsistente entre plataformas.
- Redimensionar a janela em tempo de execução não funciona em Wayland
  nativo ([flet-dev/flet#5988](https://github.com/flet-dev/flet/issues/5988));
  o modo mini lembra o tamanho que o usuário arrastar.

## Gerar um executável (PyInstaller)

```bash
pip install pyinstaller
pyinstaller pomodoro.spec
```

O executável fica em `dist/` (`PomodoroAnytype.exe` no Windows). O
`config.json` é criado ao lado dele e persiste entre execuções (veja
`pomodoro_app/paths.py`). A receita inclui a pasta `assets/` e o
`config.example.json`, que o PyInstaller não inclui sozinho.

Sem o `.spec`, o equivalente no Windows é:

```bash
pyinstaller --onefile --windowed --add-data "assets;assets" --name PomodoroAnytype gui.py
```

No Linux e no macOS, troque o `;` por `:` em `--add-data`. Se o executável
reclamar de módulo faltando (comum com o Flet), acrescente
`--collect-all flet`.

> A geração do executável **ainda não foi testada** num Windows real.
