# Sala do Futuro - Tutor Avancado

Este pacote adiciona uma automacao em modo tutor para o Sala do Futuro.

Ele foi feito para ajudar no estudo, nao para preencher ou entregar atividades automaticamente.

## O que ele faz

- Faz login no Sala do Futuro usando GitHub Secrets.
- Encontra atividades abertas.
- Abre cada atividade.
- Detecta questoes por estrutura da pagina.
- Identifica tipos como:
  - alternativa unica;
  - multipla escolha;
  - certo/errado;
  - dropdown/lacunas;
  - dissertativa;
  - texto extraido quando nao conseguir separar por questao.
- Coleta alternativas, controles e opcoes de dropdown.
- Envia ao Telegram:
  - um resumo do que foi extraido;
  - um guia de raciocinio e estudo gerado pela IA.

## O que ele nao faz

- Nao marca alternativas.
- Nao preenche dropdowns.
- Nao escreve resposta final pronta em campos dissertativos.
- Nao salva rascunho.
- Nao entrega atividade.

## Arquivos

Copie estes arquivos para o seu repositorio:

```text
sala_futuro_tutor.py
.github/workflows/alerta-tutor.yml
requirements.txt
README_TUTOR_AVANCADO.md
```

## Secrets obrigatorios

Em Settings -> Secrets and variables -> Actions -> Repository secrets:

```text
RA
DIGITO
SENHA
TELEGRAM_TOKEN
TELEGRAM_CHAT_ID
```

## Secret opcional

```text
GROQ_API_KEY
```

Sem `GROQ_API_KEY`, o script ainda tenta extrair as questoes, mas nao gera orientacao com IA.

## Variaveis opcionais

Em Settings -> Secrets and variables -> Actions -> Variables:

```text
DEBUG_DOM=true
MOSTRAR_ALTERNATIVAS=true
EXPLICAR_RACIOCINIO=true
TELEGRAM_MAX_LENGTH=3800
```

## Como rodar

Depois de subir os arquivos:

```bash
git add .
git commit -m "feat: adiciona tutor avancado do Sala do Futuro"
git push
```

No GitHub:

```text
Actions -> Sala do Futuro - Tutor Avancado -> Run workflow
```

## Observacao

Se o site mudar o HTML, os seletores podem precisar de ajuste. Ative `DEBUG_DOM=true` para receber no Telegram o que foi extraido da pagina.
