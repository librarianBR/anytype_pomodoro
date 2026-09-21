# Pomodoro + Anytype

Aplicação de linha de comando em Python que implementa a técnica Pomodoro
com tempos configuráveis e integra a lista de tarefas com o **Anytype**
(usando a API local dele como "banco de dados").

**Está aplicação foi gerada por meio de Vibe Coding usando o Claude Pro**

## O que a aplicação faz

- **Timer Pomodoro configurável**: tempo de foco, pausa curta, pausa longa e
  quantos ciclos de foco acontecem antes de uma pausa longa.
- **Você sempre sabe o que está acontecendo**: a qualquer momento (comando
  `status`) mostra a fase atual (foco / pausa curta / pausa longa), o ciclo
  em andamento e quantos minutos/segundos faltam. Início e fim de cada fase
  disparam uma notificação (terminal + notificação do SO, se tiver a lib
  `plyer` instalada).
- **Tarefas no Anytype**: criar, renomear, excluir e mudar o status
  (padrão: To Do / In Progress / Done) de tarefas, usando a API
  local do Anytype Desktop — sem precisar de nenhum servidor externo, tudo
  roda no seu computador.
- **Integração das duas coisas**: ao iniciar uma sessão Pomodoro você pode
  vincular a uma tarefa; ela é automaticamente marcada como "In Progress", e ao
  final de um ciclo de foco a aplicação pergunta se quer marcá-la como
  "Done".

## Instalação

```bash
cd anytype_pomodoro
pip install -r requirements.txt
```

(`plyer` é opcional — sem ele, as notificações aparecem só no terminal.)

## Pré-requisitos no Anytype

1. Tenha o **Anytype Desktop** instalado e aberto (a API roda embutida nele,
   em `http://localhost:31009` por padrão, totalmente offline).
2. No espaço (space) onde você quer guardar as tarefas, garanta que existem:
   - um **tipo de objeto** para tarefas (por padrão a aplicação procura um
     chamado `Task`; se você usa outro nome, ex. `Tarefa`, ajuste
     `task_type_name` no `config.json` depois da primeira execução);
   - uma **propriedade do tipo "Select"** chamada `Status` (também
     configurável via `status_property_name`), com as opções que quiser —
     a aplicação cria automaticamente as tags que faltarem, com os nomes
     definidos em `status_options` (padrão: `To Do`, `In Progress`,
     `Done`). Quais desses nomes contam como "em andamento" e "concluído"
     são configuráveis separadamente (`in_progress_status_name` e
     `done_status_name`);
   - **(opcional, recomendado)** uma **propriedade do tipo "Text"** chamada
     `Notes` (configurável via `notes_property_name`) — é onde o histórico
     de observações de cada tarefa é guardado. Sem ela, tudo funciona
     normalmente, só a função de observações fica indisponível (com uma
     mensagem de erro clara explicando o que falta).

   Isso é necessário porque criar Tipos e Propriedades novos por API ainda
   é uma funcionalidade instável/limitada em várias versões do Anytype — é
   mais confiável criar esse "esqueleto" manualmente uma vez, direto no app.

3. Se o seu tipo `Task` usa o layout nativo "Action" do Anytype (o que dá
   aquele checkbox ao lado do título), ele tem uma propriedade `Done`
   (checkbox) própria do Anytype que **não é sincronizada automaticamente**
   com o "Status" — são duas coisas independentes por padrão no próprio
   Anytype. Esta aplicação tenta manter as duas alinhadas sozinha (marca/
   desmarca esse checkbox junto com o Status), em modo "melhor esforço": se
   a propriedade não existir na sua instalação, simplesmente não sincroniza
   nada, sem dar erro.

## Uso

Há duas interfaces disponíveis, usando exatamente a mesma lógica por baixo:

### Interface gráfica (recomendada) — Flet

```bash
uv add flet   # se ainda não tiver instalado
uv run gui.py
```

Abre uma janela com três seções (botões no topo): **Pomodoro** (timer com
início/pausa/retomar/reiniciar/pular/parar e vínculo opcional a uma tarefa),
**Tarefas** (criar/renomear/excluir/mudar status, com um botão "Ver JSON
bruto" em cada tarefa para depuração) e **Configurações** (tempos do
Pomodoro, sons, pareamento com o Anytype, escolha de espaço, nomes de
tipo/propriedade e lista de status).

### Sons de início de fase

Cada fase (foco, pausa curta, pausa longa) tem um som diferente — três
sinos curtos e suaves, sintetizados localmente (sem depender de nenhum
arquivo de áudio baixado da internet), em `assets/*.wav`. Dá pra ligar ou
desligar em Configurações → "Tocar som no início de cada fase", e testar
cada um sem esperar um ciclo inteiro com os botões "Testar sons". Se quiser
trocar o timbre, edite e rode `python generate_sounds.py` de novo.

Tanto a CLI quanto a GUI tocam o som chamando o tocador de áudio que já
existir no seu sistema operacional (`paplay`/`aplay`/`ffplay` no Linux,
`afplay` no macOS, nativo no Windows) via `notifier.play_sound()` —
propositalmente não usamos o controle `Audio` do Flet, pois ele se mostrou
inconsistente entre versões/plataformas do cliente desktop (em algumas
instalações no Linux aparece como "Unknown control: Audio" mesmo com todas
as bibliotecas corretas instaladas). Se nenhum tocador for encontrado no
seu sistema, a aplicação simplesmente não emite som — sem travar nem gerar
erro.

### Modo mini

O botão **"Modo mini"** deixa a janela sempre por cima das outras (mesmo
trocando de app) e mostra só o ícone da fase e a contagem regressiva. Como
redimensionar a janela programaticamente é um
[bug conhecido e ainda aberto do próprio Flet](https://github.com/flet-dev/flet/issues/5988)
em sessões Wayland nativas do Linux (a maioria das instalações recentes de
Ubuntu/GNOME) — o pedido de novo tamanho é ignorado pelo motor gráfico
enquanto o app já está rodando —, a janela continua com tamanho livre: é só
arrastar a borda para deixá-la pequena manualmente (isso funciona porque é
o próprio gerenciador de janelas do sistema cuidando do redimensionamento,
não o Flet). O botão "Restaurar" volta ao normal.

O tamanho que você deixar é lembrado (salvo em `config.json`) e a
aplicação tenta reaplicá-lo automaticamente da próxima vez que você clicar
em "Modo mini" — isso é "melhor esforço": como reaplicar tamanho de janela
em tempo de execução é justamente a operação afetada pelo bug acima, pode
não colar dependendo do seu ambiente. Nesse caso, é só arrastar a borda de
novo (o tamanho novo será lembrado igual).

Se preferir tentar o redimensionamento automático mesmo assim, rodar sob
X11/XWayland em vez de Wayland nativo pode ajudar (o problema não ocorre
lá, segundo o relato do bug):
```bash
GDK_BACKEND=x11 uv run gui.py
```

### Vincular tarefa a qualquer momento

O dropdown "Vincular a uma tarefa" na sessão Pomodoro fica disponível o
tempo todo — rodando ou não — e trocar a seleção tem efeito imediato: a
tarefa escolhida é marcada como "em andamento" (`in_progress_status_name`)
e ganha uma observação "Sessão vinculada a esta tarefa." no histórico. Um
botão **"Desvincular"** remove o vínculo a qualquer momento. Isso permite
trocar de tarefa no meio de uma sessão (por exemplo, se você terminar uma
tarefa antes do tempo do ciclo acabar): tanto a tarefa que está sendo
deixada quanto a nova recebem uma observação registrando a troca, com data
e hora — nada fica perdido. O dropdown só lista tarefas que ainda não
estão com o status de "concluído" (`done_status_name`).

Parar a sessão (botão "Parar") não desfaz o vínculo — isso é intencional,
para você poder apertar "Iniciar" de novo sem precisar reselecionar a
mesma tarefa.

### Observações nas tarefas

Cada tarefa pode acumular um histórico de observações, guardado numa
propriedade de texto customizada chamada `Notes` (veja
"Pré-requisitos no Anytype" acima) — nada se perde, cada nota nova é
acrescentada embaixo das anteriores, com data e hora. Isso acontece de
várias formas:
- **Automaticamente**: ao terminar um ciclo de foco vinculado a uma tarefa,
  a aplicação registra "Sessão de foco concluída (X min)" e oferece um
  campo opcional para você escrever algo a mais antes de confirmar;
- **Automaticamente**: ao vincular, trocar ou desvincular uma tarefa da
  sessão (veja a seção acima);
- **A qualquer momento**: pelo ícone de observações (📝) em cada tarefa na
  aba Tarefas, que mostra o histórico e permite adicionar uma nova nota.

Por que uma propriedade de texto, e não o corpo/conteúdo da página (a
seção "Details" que aparece dentro de cada tarefa no Anytype)? Porque
atualizar o `body` de um objeto via API não é confiável nesta versão do
Anytype — é uma limitação conhecida da própria API (a comunidade recomenda
até recriar o objeto do zero para contornar isso, o que mudaria o id da
tarefa a cada nota; inviável aqui, já que dependemos do id permanecer
estável). Guardar num campo/propriedade dedicado é o caminho confiável.

### Linha de comando

```bash
python main.py
```


No primeiro uso (em qualquer uma das duas interfaces), você vai precisar:

1. **Parear com o Anytype**: a aplicação pede pro Anytype um código de 4
   dígitos (que aparece na tela do Anytype Desktop) — digite o código
   quando solicitado. A chave de acesso gerada fica salva em `config.json`,
   então isso só precisa ser feito uma vez.
2. **Escolher espaço do Anytype**: seleciona em qual space as tarefas vão
   ser criadas/lidas.
3. Gerenciar tarefas: criar/editar/excluir e mudar status livremente, sem
   precisar rodar um pomodoro.
4. Configurar tempos do Pomodoro: ajustar foco/pausas/ciclos.
5. Iniciar uma sessão Pomodoro. Na CLI, comandos disponíveis durante a
   sessão: `status`, `pausar`, `retomar`, `reiniciar`, `pular`, `vincular`,
   `desvincular`, `parar`. Na interface gráfica, os mesmos controles
   aparecem como botões (`Reiniciar fase` volta a contagem da fase atual
   para o início, sem avançar de ciclo; vincular/desvincular tarefa
   funciona a qualquer momento, veja a seção correspondente abaixo).

Tudo fica salvo em `config.json` (tempos, espaço escolhido, chave de API,
ids de tipo/propriedade/tags já descobertos) — não é preciso reconfigurar
nada nas próximas execuções.

## Sobre a integração com o Anytype

A API Local do Anytype é relativamente nova e muda com alguma frequência.
Este projeto usa a versão de API `2025-11-08` (configurável em
`config.json`, campo `anytype.api_version`) e segue o formato documentado
em https://developers.anytype.io/docs/reference. Se uma chamada falhar por
causa de alguma mudança de schema entre versões, o erro impresso já traz o
corpo de resposta da API — normalmente dá pra ver ali o campo que mudou de
nome e ajustar em `anytype_client.py`.

O reconhecimento do status de cada tarefa (`task_manager.py`, método
`_to_task`) foi escrito de forma tolerante a algumas variações conhecidas
de formato (a propriedade pode ser referenciada por `id` ou por `key`, e o
valor de uma propriedade "select" pode vir como string simples ou como um
objeto `{"id":..., "name":...}`). Se, mesmo assim, o status aparecer como
`?` na lista de tarefas, use o botão **"Ver JSON bruto"** de qualquer
tarefa (na aba Tarefas da interface gráfica) para ver exatamente o que a
sua instalação do Anytype está devolvendo, e ajustar `_to_task` de acordo.


## Estrutura dos arquivos

- `pomodoro_timer.py` — núcleo do timer (roda em thread própria, sem
  nenhuma dependência do Anytype; pode ser reaproveitado em outra interface).
- `anytype_client.py` — cliente HTTP puro para a API local do Anytype
  (autenticação, tipos, propriedades, tags, objetos).
- `task_manager.py` — regras de negócio de "tarefa com status" em cima do
  cliente do Anytype.
- `config.py` — modelo de configuração e leitura/escrita do `config.json`.
- `notifier.py` — notificação em terminal + notificação nativa opcional.
- `main.py` — menu interativo (CLI) que une tudo.
- `gui.py` — interface gráfica (Flet) que une tudo, incluindo sons e modo mini.
- `generate_sounds.py` — sintetiza os sons de início de fase (`assets/*.wav`).
