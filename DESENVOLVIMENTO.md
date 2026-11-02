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

Para quem só quer abrir a aplicação há atalhos na raiz: `./executar.sh`
(Linux/macOS) e `executar.bat` (Windows), com o argumento `cli` para a
linha de comando. Eles tentam, nesta ordem, o `uv`, o `.venv` do projeto e
o Python do sistema. O `.gitattributes` fixa as quebras de linha (CRLF no
`.bat`, LF no `.sh`); sem isso o Git pode convertê-las e quebrar o script.

O `config.json` é criado na primeira execução a partir de
`config.example.json`. Ele guarda a chave da API do Anytype e por isso está
no `.gitignore`: nunca faça commit dele. Para mudar os valores padrão de
quem usa o projeto pela primeira vez, edite `config.example.json`.

## Estrutura do código

```
gui.py, main.py          pontos de entrada (só chamam o pacote)
executar.sh, executar.bat  atalhos para abrir a aplicação (Linux / Windows)
generate_sounds.py       gera os sons em assets/*.wav
pomodoro_app/
  __init__.py            APP_NAME (nome no pareamento e nas notificações)
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
| `test_anytype_client.py` | formatos de resposta, paginação, configuração, nome no pareamento, erros 401/403 e o estado "pareamento inválido" |
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

### Pareamento (Anytype 0.57+)

O fluxo está descrito no topo de `anytype_client.py`. A partir do Anytype
Desktop 0.57, antes de mostrar o código de 4 dígitos o Anytype abre uma
janela de aprovação com o `app_name` enviado em `create_challenge` (por
isso ele é `APP_NAME`, "Anytype + Pomodoro"), e a autorização passa a
valer só para os espaços que o usuário liberar. Consequências no código:

- `GET /v1/spaces` lista só os espaços liberados. Lista vazia vira o aviso
  `NO_SPACES_MESSAGE` (GUI e CLI). O texto do diálogo de pareamento é
  `PAIRING_HINT`, também compartilhado pelas duas interfaces.
- Em chamadas autenticadas, **401** vira `AnytypeAuthError` (chave
  revogada: pareie de novo) e **403** vira `AnytypeForbiddenError` (espaço
  não liberado), ambas subclasses de `AnytypeError` com mensagens prontas.
  Nas chamadas do próprio pareamento (`auth=False`) um 401 é código
  errado, então a mensagem crua é mantida.
- **Num 401 a chave não é apagada.** O cliente marca `key_rejected = True`
  e avisa por `on_key_status_change` (pode vir da thread do timer; a tela
  Configurações repassa por `run_on_ui`). A tela mostra "Pareamento
  inválido" e destaca o botão de parear. A próxima chamada autenticada que
  der certo, ou um novo pareamento, volta `key_rejected` para `False`.
  Motivo: a chave recusada já não dá acesso a nada (apagá-la não traz
  segurança), e um 401 passageiro, por exemplo com o Anytype ainda
  iniciando, desfaria o pareamento à toa.

Esses comportamentos seguem as notas da versão 0.57.0 do `anytype-ts` e
ainda não foram conferidos contra um Anytype 0.57 real.

### Particularidades da versão `2025-11-08`

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
- A tela Pomodoro mostra a história de usuário (a `description` da tarefa)
  da tarefa vinculada num cartão, durante todas as fases. Ela vem das
  tarefas carregadas no dropdown (`_tasks_by_id`), relidas a cada vez que a
  aba é aberta, por isso uma edição feita no Anytype aparece ao voltar à aba.
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
