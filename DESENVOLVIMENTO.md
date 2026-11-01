# Desenvolvimento

Notas técnicas para quem vai mexer no código. Para instalar e usar a
aplicação, veja o [README](README.md).

## Ambiente

```bash
uv sync            # cria o .venv com as dependências do uv.lock
uv run gui.py      # interface gráfica (Flet)
uv run main.py     # linha de comando
```

O `config.json` é criado na primeira execução a partir de
`config.example.json`. Ele guarda a chave da API do Anytype e por isso está
no `.gitignore`: nunca faça commit dele. Para mudar os valores padrão de
quem usa o projeto pela primeira vez, edite `config.example.json`.

## Estrutura dos arquivos

- `pomodoro_timer.py`: núcleo do timer. Roda em thread própria e não
  depende do Anytype, então pode ser reaproveitado em outra interface.
  Expõe callbacks `on_phase_start`, `on_phase_end` e `on_tick`.
- `anytype_client.py`: cliente HTTP puro para a API local do Anytype
  (autenticação, tipos, propriedades, tags, objetos).
- `task_manager.py`: regras de negócio de "tarefa com status" sobre o
  cliente (setup, CRUD, status, notas, data de entrega, descrição).
- `config.py`: modelo de configuração e leitura/escrita do `config.json`.
- `paths.py`: resolve onde ficam o `config.json` e os sons, tanto rodando
  com `python` quanto empacotado pelo PyInstaller.
- `notifier.py`: notificações (terminal, `notify-send` no Linux, `plyer`
  nos demais) e sons (tocador do sistema).
- `main.py`: menu interativo (CLI).
- `gui.py`: interface gráfica (Flet), incluindo modo mini.
- `generate_sounds.py`: sintetiza os sons em `assets/*.wav` (sinos de
  início de fase e tiques da contagem regressiva). Rode de novo depois de
  mudar notas ou timbre.
- `pomodoro.spec`: receita do PyInstaller para gerar um executável.

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

O reconhecimento do status (`TaskManager._to_task`) tolera variações: a
propriedade pode vir por `id` ou `key`, e o valor de um "select" como
string ou objeto `{"id", "name"}`. Se o status aparecer como `?`, o botão
"Ver JSON bruto" da aba Tarefas mostra o que a instalação devolve.

## Interface (Flet)

- O timer roda em outra thread: mudanças de interface vindas dele passam
  por `schedule_on_ui` (`page.loop.call_soon_threadsafe`).
- **Cuidado com layout**: um filho com `expand=True` dentro de uma `Row`
  com `wrap=True`, ou dentro de uma `Column` com `scroll`, é erro no
  Flutter, e a área inteira vira um quadro cinza (sem erro no terminal).
- Sons usam o tocador do sistema (`notifier.play_sound`) em vez do
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
`paths.py`). A receita inclui a pasta `assets/`, que o PyInstaller não
inclui sozinho.

Sem o `.spec`, o equivalente no Windows é:

```bash
pyinstaller --onefile --windowed --add-data "assets;assets" --name PomodoroAnytype gui.py
```

No Linux e no macOS, troque o `;` por `:` em `--add-data`. Se o executável
reclamar de módulo faltando (comum com o Flet), acrescente
`--collect-all flet`.

> A geração do executável **ainda não foi testada** num Windows real.
