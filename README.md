# Sala do Futuro - Alerta de Atividades

Automatiza a verificacao de atividades pendentes no Sala do Futuro, le o enunciado de cada atividade, gera uma resposta educacional e envia tudo pelo Telegram.

Roda via GitHub Actions, sem precisar de computador ligado.

## Como funciona

1. GitHub Actions executa o script diariamente as 10h (horario de Brasilia).
2. O script faz login, acessa /tarefas e verifica atividades pendentes.
3. Para cada atividade nova ou alterada, abre a pagina, extrai o conteudo e gera uma resposta educacional.
4. Envia um resumo completo pelo Telegram.
5. Salva o estado no proprio repositorio para evitar alertas duplicados.

## Configuracao

### 1. Fork ou clone este repositorio

### 2. Configure os GitHub Secrets

Acesse Settings -> Secrets and variables -> Actions -> New repository secret e adicione:

| Secret | Descricao | Obrigatorio |
|---|---|---|
| RA | Numero do RA do aluno | Sim |
| DIGITO | Digito do RA | Sim |
| SENHA | Senha de acesso | Sim |
| TELEGRAM_TOKEN | Token do bot do Telegram | Sim |
| TELEGRAM_CHAT_ID | ID do chat/grupo do Telegram | Sim |
| ANTHROPIC_API_KEY | Chave da API Anthropic (Claude) | Opcional |

Nunca coloque credenciais diretamente no codigo.

### 3. Ative o workflow

Acesse Actions -> Alerta Sala do Futuro -> Enable workflow.

Para testar manualmente: Actions -> Alerta Sala do Futuro -> Run workflow.

### 4. Crie o bot do Telegram

1. Fale com @BotFather no Telegram.
2. Use /newbot e siga as instrucoes.
3. Copie o token gerado para o secret TELEGRAM_TOKEN.
4. Para obter o TELEGRAM_CHAT_ID, envie uma mensagem para o bot e acesse:
   https://api.telegram.org/bot<TOKEN>/getUpdates

## Resposta educacional com IA (opcional)

Se o secret ANTHROPIC_API_KEY estiver configurado, o script usara o Claude Haiku para gerar uma explicacao passo a passo de cada atividade.

Sem a chave, o script ainda envia o enunciado e o conteudo extraido, mas sem a resposta automatica.

Obtenha sua chave em console.anthropic.com.

## Seletores do site

O Sala do Futuro pode atualizar o HTML sem aviso. Se o script parar de extrair o conteudo corretamente, ajuste os seletores CSS em sala_futuro_alerta.py.

Funcoes marcadas com "AJUSTE O SELETOR":
- fazer_login() -- campos de RA, digito, senha e botao
- listar_atividades_pendentes() -- links e cards de atividades
- extrair_conteudo_atividade() -- titulo, disciplina, prazo, enunciado, alternativas

Para inspecionar: abra o site no Chrome, pressione F12 e use o inspetor de elementos.

## Variaveis de ambiente opcionais

| Variavel | Padrao | Descricao |
|---|---|---|
| ENVIAR_OK | false | Se true, envia mensagem mesmo sem atividades novas |
| TELEGRAM_MAX_LENGTH | 4000 | Limite de caracteres por mensagem |

## Persistencia de estado

O arquivo atividades_salvas.json armazena o historico de atividades processadas. Ele e commitado automaticamente no repositorio apos cada execucao.

Isso substitui o uso de actions/cache com chave fixa, que nao garantia atualizacao confiavel.

## Seguranca

- Nenhuma credencial esta hardcoded no codigo.
- Logs nao exibem RA, senha ou tokens.
- O script falha imediatamente se qualquer variavel obrigatoria estiver ausente.
- O token GITHUB_TOKEN usado para commit tem escopo minimo (contents: write).
