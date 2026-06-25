# Guia de instalação e execução da interface web

## 📋 Pré-requisitos

- Python 3.8+
- pip
- Git

## 🚀 Instalação Local

### 1. Clonar o repositório
```bash
git clone https://github.com/Verdao-Sempre/sala-futuro-alerta.git
cd sala-futuro-alerta
```

### 2. Criar ambiente virtual
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependências
```bash
pip install -r requirements.txt
python -m playwright install
```

### 4. Configurar variáveis de ambiente (opcional)
```bash
# Criar arquivo .env na raiz do projeto
GROQ_API_KEY=sua_chave_aqui
FLASK_ENV=development
```

### 5. Executar a aplicação
```bash
python app.py
```

A aplicação estará disponível em: **http://localhost:5000**

---

## 🌐 Deploy (Vercel/Heroku)

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

---

## 📚 Estrutura do projeto

```
sala-futuro-alerta/
├── app.py                    # Backend Flask
├── requirements.txt          # Dependências
├── sala_futuro_alerta.py     # Script original (GitHub Actions)
├── static/
│   ├── style.css            # Estilos
│   └── script.js            # JavaScript frontend
├── templates/
│   └── index.html           # Página principal
├── atividades_salvas.json   # Histórico (GitHub Actions)
└── README.md                # Este arquivo
```

---

## 🔒 Segurança

✅ **Credenciais NÃO são armazenadas**
- São usadas apenas na sessão
- Enviadas via HTTPS em produção
- Nunca salvadas em banco de dados

✅ **HTTPS obrigatório em produção**

✅ **Rate limiting recomendado**

---

## 🐛 Troubleshooting

### "ModuleNotFoundError: No module named 'flask'"
```bash
pip install Flask
```

### "Playwright browser not found"
```bash
python -m playwright install
```

### "Port 5000 already in use"
```bash
python app.py --port 5001
```

---

## 📞 Suporte

Abra uma issue no GitHub: https://github.com/Verdao-Sempre/sala-futuro-alerta/issues

---

## 📜 Licença

MIT License
