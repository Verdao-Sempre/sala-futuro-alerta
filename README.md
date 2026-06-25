# Sala do Futuro - Alerta de Atividades

Automatiza a verificação de atividades pendentes no Sala do Futuro, lê o enunciado de cada atividade, gera uma resposta educacional e envia tudo pelo Telegram.

**Agora com INTERFACE WEB!** 🎉

## 🚀 Como Usar

### Opção 1: Interface Web (Recomendado)
Acesse a interface web, coloque suas credenciais (não armazenadas!) e veja as atividades em tempo real.

```bash
python app.py
# Abra http://localhost:5000
```

**✅ Seguro** - Credenciais NÃO são guardadas
**✅ Rápido** - Resultado instantâneo
**✅ Bonito** - Interface moderna e responsiva

### Opção 2: GitHub Actions (Automático)
O script roda diariamente às 10h (horário de Brasília) sem precisar de computador ligado.

```
GitHub Actions → Roda script → Processa atividades → Envia no Telegram
```

---

## 📋 Configuração

### Para a Interface Web (localhost)

1. **Clonar o repositório**
```bash
git clone https://github.com/Verdao-Sempre/sala-futuro-alerta.git
cd sala-futuro-alerta
```

2. **Instalar dependências**
```bash
pip install -r requirements.txt
python -m playwright install
```

3. **Executar**
```bash
python app.py
```

### Para GitHub Actions (Automático)

Acesse Settings → Secrets and variables → Actions → New repository secret e adicione:

| Secret | Descrição | Obrigatório |
|---|---|---|
| RA | Numero do RA do aluno | Sim |
| DIGITO | Digito do RA | Sim |
| SENHA | Senha de acesso | Sim |
| TELEGRAM_TOKEN | Token do bot do Telegram | Opcional |
| TELEGRAM_CHAT_ID | ID do chat/grupo do Telegram | Opcional |
| GROQ_API_KEY | Chave da API Anthropic (Claude) | Opcional |

Nunca coloque credenciais diretamente no código.

---

## 🔒 Segurança

✅ **Credenciais NÃO são armazenadas** (interface web)
✅ **Usadas apenas na sessão atual**
✅ **HTTPS obrigatório em produção**
✅ **Nenhum cookie de autenticação persistente**

---

## 🎯 Funcionalidades

✅ Login automático
✅ Detecção de atividades pendentes
✅ Extração de conteúdo
✅ Respostas automáticas com IA (Groq)
✅ Cliques automáticos em selects, checkboxes e radio buttons
✅ Salvamento de rascunho
✅ Notificações via Telegram
✅ Interface web moderna
✅ Histórico de atividades

---

## 📚 Seletores do site

O Sala do Futuro pode atualizar o HTML sem aviso. Se o script parar de extrair o conteúdo corretamente, ajuste os seletores CSS em `sala_futuro_alerta.py`.

Funções marcadas com "AJUSTE O SELETOR":
- `fazer_login()` -- campos de RA, digito, senha e botao
- `buscar_atividades()` -- links e cards de atividades
- `abrir_atividade()` -- botao de prosseguir
- `clicar_dropdown()` -- selects e comboboxes

Para inspecionar: abra o site no Chrome, pressione F12 e use o inspetor de elementos.

---

## 🔧 Resposta educacional com IA (opcional)

Se o secret GROQ_API_KEY estiver configurado, o script usará o Groq (Llama 3.1) para gerar explicações de cada atividade.

Sem a chave, o script ainda envia o enunciado e o conteúdo extraído, mas sem a resposta automática.

Obtenha sua chave em [console.groq.com](https://console.groq.com)

---

## 📖 Variáveis de ambiente opcionais

| Variável | Padrão | Descrição |
|---|---|---|
| ENVIAR_OK | false | Se true, envia mensagem mesmo sem atividades novas |
| TELEGRAM_MAX_LENGTH | 4000 | Limite de caracteres por mensagem |
| GROQ_API_KEY | vazio | Chave da API Groq para respostas com IA |
| FLASK_ENV | production | development ou production |

---

## 📁 Estrutura do Projeto

```
.
├── app.py                      # Backend Flask (interface web)
├── sala_futuro_alerta.py       # Script original (GitHub Actions)
├── requirements.txt            # Dependências Python
├── atividades_salvas.json      # Histórico de atividades
├── static/
│   ├── style.css              # Estilos CSS
│   └── script.js              # JavaScript frontend
├── templates/
│   └── index.html             # Página HTML
├── .github/workflows/
│   └── alerta.yml             # Workflow do GitHub Actions
├── README.md                   # Este arquivo
└── GUIA_WEB.md                # Guia completo da interface web
```

---

## 🚨 Troubleshooting

### "ModuleNotFoundError"
```bash
pip install -r requirements.txt
```

### "Playwright browser not found"
```bash
python -m playwright install
```

### "Connection refused" ao acessar localhost:5000
```bash
# Verificar se a porta 5000 está em uso
# Windows: netstat -ano | findstr :5000
# Linux/Mac: lsof -i :5000

# Usar porta diferente
python app.py --port 5001
```

### Login não funciona
- Verifique se o RA, dígito e senha estão corretos
- Tente fazer login manualmente no site primeiro
- Verifique a estrutura HTML do site (pode ter mudado)

---

## 📊 Logs

### Interface Web
Logs aparecem no terminal onde rodou `python app.py`

### GitHub Actions
Logs aparecem em: Actions → [Seu workflow] → Build → ver logs

---

## ⚙️ Deploy em Produção

### Vercel
```bash
npm install -g vercel
vercel
```

### Heroku
```bash
heroku login
heroku create seu-app-name
git push heroku main
```

### Railway/Render
Similar ao Heroku - conecte seu GitHub e deploy automaticamente

---

## 📞 Suporte

Problemas? Abra uma issue: [GitHub Issues](https://github.com/Verdao-Sempre/sala-futuro-alerta/issues)

---

## 📜 Licença

MIT License - veja LICENSE.md

---

## 🙏 Créditos

Desenvolvido para ajudar estudantes a economizar tempo com tarefas repetitivas.

**Não use para colar em provas ou avaliações!** ⚠️

Use para estudar, aprender e praticar. A responsabilidade de como você usa essa ferramenta é sua.

---

**Última atualização:** 25 de junho de 2026
