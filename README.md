# Anytype + Pomodoro

Um timer **Pomodoro** com a sua lista de tarefas guardada no **Anytype**.
Você escolhe a tarefa, foca nos ciclos de trabalho e pausa, e o andamento
fica registrado na própria tarefa: status, histórico de sessões e
observações, tudo dentro do Anytype.

Tudo roda no seu computador: a aplicação conversa com o Anytype Desktop
pela API local dele, sem servidores externos nem conta em outro serviço.

## Benefícios

- **Foco com ritmo**: ciclos de foco, pausas curtas e pausas longas com os
  tempos que você escolher.
- **Você sempre sabe em que fase está**: contagem na tela, notificação do
  sistema no início e no fim de cada fase, um som diferente para cada fase
  e uma contagem regressiva sonora nos últimos 5 segundos.
- **Tarefas organizadas no Anytype**: crie, renomeie, exclua e mude o status
  das tarefas sem sair da aplicação. Tudo continua disponível no Anytype,
  em qualquer dispositivo sincronizado.
- **Histórico automático**: cada sessão de foco, cada vínculo e cada
  conclusão fica registrada na tarefa, com data e hora.
- **Backlog no estilo Scrum**: data de entrega e história de usuário ("Como…,
  quero…, para…") já na criação da tarefa, com um modelo pronto.
- **Encontre o que precisa**: busca por título, filtro por status,
  ordenação por criação, título ou entrega, e aviso de tarefas atrasadas.
- **Modo mini**: uma janela pequena, sempre por cima das outras, só com o
  tempo restante.
- **Do seu jeito**: sete paletas de cores e modo claro, escuro ou
  automático.
- **Privacidade**: seus dados não saem do seu computador (além da
  sincronização normal do próprio Anytype).

## Requisitos

- **Anytype Desktop** instalado e **aberto** enquanto você usa a aplicação.
- **Python 3.14** ou mais recente.
- Linux, Windows ou macOS.
- Recomendado: o gerenciador [uv](https://docs.astral.sh/uv/), que instala
  tudo com um comando.

## Instalação

### Com uv (recomendado)

```bash
git clone https://github.com/librarianBR/anytype_pomodoro.git
cd anytype_pomodoro
uv sync
```

### Com pip

```bash
git clone https://github.com/librarianBR/anytype_pomodoro.git
cd anytype_pomodoro
python -m venv .venv
source .venv/bin/activate        # no Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Preparar o Anytype (uma vez só)

No espaço do Anytype onde vão ficar as tarefas, confira se existem:

1. **Um tipo de objeto para tarefas.** O tipo `Task`, que já vem com o
   Anytype, serve. Se você usa outro nome (por exemplo `Tarefa`), informe-o
   depois em Configurações.
2. **Uma propriedade do tipo "Select" chamada `Status`**, adicionada a esse
   tipo. As opções (`To Do`, `In Progress`, `Done`) são criadas pela
   aplicação automaticamente, se faltarem.
3. **(Recomendado) Uma propriedade do tipo "Text" chamada `Notes`**,
   adicionada ao tipo. É onde fica o histórico de cada tarefa. Sem ela tudo
   funciona, menos as observações.

A data de entrega (`Due date`) e a descrição já existem no tipo `Task` do
Anytype: não é preciso criar nada para elas.

## Primeiro uso

1. Abra o Anytype Desktop.
2. Inicie a aplicação:
   ```bash
   uv run gui.py      # ou, com pip: python gui.py
   ```
   Ou use os atalhos prontos: `./executar.sh` no Linux/macOS e
   `executar.bat` no Windows (dá para clicar duas vezes). Eles usam o uv se
   estiver instalado, senão o `.venv` do projeto, senão o Python do sistema.
   Acrescente `cli` (`./executar.sh cli`) para abrir a versão de terminal.
3. Vá em **Configurações** e clique em **"Parear com o Anytype"**. O
   Anytype mostra um código de 4 dígitos; digite-o na aplicação. Isso só é
   feito uma vez: a chave fica salva no seu computador.
4. Clique em **"Carregar espaços"** e escolha o espaço das tarefas.
5. Clique em **"Testar / preparar"**. A aplicação confere o tipo e as
   propriedades e avisa exatamente o que estiver faltando.
6. Ajuste os tempos do Pomodoro, se quiser, e clique em **"Salvar tempos"**.

Pronto. Nas próximas vezes, é só abrir e usar.

## Como usar

A janela tem três seções, escolhidas pelos botões no topo, mais o modo mini.

### Pomodoro

- **Iniciar / Pausar / Retomar / Parar**: controlam a sessão.
- **Reiniciar fase**: volta a contagem da fase atual para o início, sem
  mudar de ciclo.
- **Pular fase**: encerra a fase atual e passa para a próxima.
- **Vincular a uma tarefa**: escolha a tarefa em que vai trabalhar. Ela
  passa para "In Progress", e a lista mostra só tarefas ainda não
  concluídas. Dá para vincular ou trocar a qualquer momento, com o timer
  rodando ou não; a troca fica registrada no histórico das duas tarefas.
- **Concluir tarefa**: marca a tarefa vinculada como "Done" na hora, com uma
  observação opcional, e a tira da sessão para você escolher a próxima. O
  timer continua normalmente.
- **Desvincular**: só tira o vínculo. A tarefa continua com o status que
  tinha.
- **Fim do ciclo de foco**: se houver tarefa vinculada, o timer espera e
  pergunta se a tarefa foi concluída, com um campo para observação. A sessão
  de foco fica registrada no histórico de qualquer forma.
- **Parar** não desfaz o vínculo: aperte "Iniciar" de novo e continue na
  mesma tarefa.

### Tarefas

**Criar uma tarefa:**

- **Nome** e **Status inicial**.
- **Data de entrega** (opcional): clique no botão e escolha no calendário.
  O ✕ ao lado remove a data.
- **História de usuário** (opcional): texto livre. O botão **"Usar modelo
  de história"** preenche o formato usado em backlogs Scrum:

  ```
  Como <tipo de usuário>, quero <objetivo> para <benefício>.

  Critérios de aceitação:
  - Dado <contexto>, quando <ação>, então <resultado esperado>.
  ```

  Troque os campos entre `< >` pelo seu texto; a aplicação avisa se algum
  ficar sem preencher. A história aparece na descrição da tarefa no Anytype.

**Encontrar tarefas:**

- **Buscar no título**: filtra enquanto você digita, sem diferenciar
  maiúsculas nem acentos ("linguistica" encontra "Linguística").
- **Status**: Todos, Não concluídas ou um status específico.
- **Ordenar por**: criação (mais recentes ou mais antigas primeiro), título
  (A → Z ou Z → A) ou entrega (mais próxima primeiro).
- **Mostrar**: 10, 25, 50, 100 ou todas.
- **Limpar filtros** volta ao padrão. A aplicação lembra suas escolhas na
  próxima vez.

**Em cada tarefa** você vê a data de criação, a entrega (com
**(atrasada)** em vermelho se o prazo passou e ela não foi concluída) e a
primeira linha da história; passe o mouse sobre ela para ler tudo. Os
botões ao lado servem para mudar o status, renomear, ver e adicionar
**observações** (📝), excluir e ver os dados brutos da tarefa.

Mudou algo direto no Anytype? Clique em **"Atualizar lista"**.

### Configurações

- **Aparência**: escolha a paleta de cores (Tomate, Pêssego, Girassol,
  Menta, Oceano, Lavanda ou Grafite) e o modo **Claro**, **Escuro** ou
  **Automático** (segue o sistema). A mudança vale na hora e fica salva.
  Cada fase do Pomodoro ganha uma cor própria da paleta, para você
  reconhecer de relance se está em foco ou em pausa.
- **Tempos**: foco, pausa curta, pausa longa e quantos ciclos até a pausa
  longa (números maiores que zero; aceita fração, como `0.5`). Clique em
  **"Salvar tempos"**; os novos tempos valem a partir da próxima sessão.
- **Sons**: liga ou desliga todos os sons. Os botões **"Testar sons"** tocam
  cada som, inclusive a contagem regressiva, sem esperar uma fase acabar.
- **Conexão com o Anytype**: pareamento, escolha do espaço e os nomes do
  tipo de tarefa, da propriedade de status e das opções de status. Se você
  usa nomes próprios (por exemplo "A fazer / Fazendo / Feito"), informe-os
  aqui e indique qual conta como "em andamento" e qual como "concluído".
  Depois de mudar algo, clique em **"Salvar configurações"** e em
  **"Testar / preparar"**, que procura os novos nomes no Anytype.

### Modo mini

O botão **"Modo mini"** deixa a janela sempre por cima das outras, mostrando
só a fase e o tempo restante. Arraste a borda para deixá-la do tamanho que
quiser: a aplicação lembra esse tamanho. **"Restaurar"** volta ao normal.

### Linha de comando (alternativa)

Prefere o terminal? `uv run main.py` (ou `python main.py`) oferece as mesmas
funções por menus. Durante a sessão, digite: `status`, `pausar`, `retomar`,
`reiniciar`, `pular`, `vincular`, `desvincular`, `concluir` ou `parar`.

## Limitações

- **O Anytype Desktop precisa estar aberto.** A aplicação usa a API local
  dele; não funciona só com o Anytype do celular ou da web.
- **Um espaço por vez.** As tarefas vêm do espaço escolhido em
  Configurações.
- **O tipo de tarefa e as propriedades `Status` e `Notes` são criados à
  mão**, uma vez, no Anytype. A API do Anytype ainda não cria tipos e
  propriedades de forma confiável.
- **Data de entrega e história só na criação.** Para alterá-las depois,
  edite a tarefa direto no Anytype.
- **O histórico fica na propriedade `Notes`**, não no corpo da página da
  tarefa: a API do Anytype ainda não edita o corpo de forma confiável.
- **A lista não se atualiza sozinha.** Mudanças feitas no Anytype aparecem
  ao clicar em "Atualizar lista".
- **A API do Anytype é nova e muda com frequência.** Uma atualização do
  Anytype pode exigir uma atualização desta aplicação.
- **Modo mini no Linux com Wayland**: o redimensionamento automático da
  janela pode não funcionar (limitação do Flet, a biblioteca de interface).
  Arraste a borda manualmente, ou inicie com
  `GDK_BACKEND=x11 uv run gui.py`.
- **Sons** dependem de um tocador de áudio do sistema (`paplay`, `aplay`
  ou `ffplay` no Linux; já incluído no Windows e no macOS). Sem ele, a
  aplicação funciona normalmente, só que sem som.
- **Interface em português.** Os nomes de status padrão estão em inglês
  (como no Anytype), mas podem ser trocados em Configurações.

## Solução de problemas

| Problema | O que fazer |
|---|---|
| Erro de conexão com o Anytype | Confira se o Anytype Desktop está aberto. Se acabou de atualizá-lo, faça o pareamento de novo em Configurações. |
| "Configuração incompleta" na aba Tarefas | Clique em "Testar / preparar" em Configurações: a mensagem diz o que falta no Anytype (tipo, propriedade `Status` etc.). |
| Status aparece como `?` | Confira o nome da propriedade e das opções de status em Configurações. Se persistir, use "Ver JSON bruto" na tarefa e abra uma *issue* com o conteúdo. |
| Observações não funcionam | Crie a propriedade de texto `Notes` e adicione-a ao tipo de tarefa no Anytype. |
| Sem notificações no Linux | Instale o pacote `libnotify-bin` (que fornece o `notify-send`) e confira se o modo "não perturbe" está desligado. |
| Sem som | Confira a opção de sons em Configurações e se existe `paplay`, `aplay` ou `ffplay` no sistema. |

Encontrou um problema ou tem uma sugestão? Abra uma *issue* em
<https://github.com/librarianBR/anytype_pomodoro/issues>.

## Privacidade

A chave de acesso ao Anytype e suas preferências ficam no arquivo
`config.json`, só no seu computador (ele não é enviado ao repositório).
Não compartilhe esse arquivo.

## Para desenvolvedores

Estrutura do código, como rodar os testes automatizados (`uv run pytest`),
detalhes da integração com a API do Anytype e como gerar um executável:
veja [DESENVOLVIMENTO.md](DESENVOLVIMENTO.md).

## Licença

[MIT](LICENSE).
