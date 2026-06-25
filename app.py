# ============================================================
#  APP WEB FLASK - SALA DO FUTURO ALERTA
#  Interface para verificar atividades sem guardar credenciais
# ============================================================

from flask import Flask, render_template, request, jsonify
from playwright.sync_api import sync_playwright
import time
import json
import os
import sys

app = Flask(__name__)

# ============================================================
#  CONFIGURACOES
# ============================================================

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# ============================================================
#  ROTAS
# ============================================================

@app.route('/')
def index():
    """Retorna a página principal."""
    return render_template('index.html')


@app.route('/api/processar', methods=['POST'])
def processar_atividades():
    """
    API que processa as atividades do usuário.
    
    Request JSON:
    {
        "ra": "186735683",
        "digito": "5",
        "senha": "senha123"
    }
    """
    try:
        dados = request.get_json()
        
        ra = dados.get('ra', '').strip()
        digito = dados.get('digito', '').strip()
        senha = dados.get('senha', '').strip()

        # Validar
        if not all([ra, digito, senha]):
            return jsonify({
                'error': 'Preencha todos os campos',
                'atividades': []
            }), 400

        print(f"\n{'='*60}")
        print(f"  🚀 Processando atividades...")
        print(f"  RA: {ra[:4]}***")
        print(f"{'='*60}")

        # Processar com Playwright
        atividades = processar_com_playwright(ra, digito, senha)

        return jsonify({
            'message': f'✓ {len(atividades)} atividade(s) encontrada(s)',
            'atividades': atividades
        }), 200

    except Exception as erro:
        print(f"  ✗ Erro: {erro}")
        return jsonify({
            'error': f'Erro ao processar: {str(erro)[:100]}',
            'atividades': []
        }), 500


# ============================================================
#  LOGICA PRINCIPAL (Playwright)
# ============================================================

def processar_com_playwright(ra, digito, senha):
    """Faz login e extrai atividades."""
    atividades = []

    try:
        with sync_playwright() as p:
            # Usar chromium headless
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            page = browser.new_page()

            # LOGIN
            print("  → Fazendo login...")
            page.goto("https://saladofuturo.educacao.sp.gov.br/login-alunos", 
                     wait_until="domcontentloaded")
            time.sleep(6)

            try:
                page.get_by_placeholder("Ex.: 186735683").fill(ra)
                page.get_by_placeholder("0").first.fill(digito)
                page.get_by_placeholder("Digite sua senha").fill(senha)
                time.sleep(1)
                page.get_by_role("button", name="Acessar").click()
                time.sleep(5)
                print("  ✓ Login realizado!")
            except Exception as e:
                print(f"  ✗ Erro no login: {e}")
                browser.close()
                raise Exception(f"Erro ao fazer login: {str(e)}")

            # BUSCAR ATIVIDADES
            print("  → Buscando atividades...")
            page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", 
                     wait_until="domcontentloaded")
            time.sleep(5)

            # Scroll para carregar todas
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(2)

            # Extrair texto
            corpo = page.inner_text("body")
            linhas = [l.strip() for l in corpo.split("\n") if l.strip()]

            # Buscar atividades com status "A Fazer" ou "Rascunho"
            STATUS_ABERTO = {"A Fazer", "Rascunho", "Em andamento", "Em Andamento",
                           "Em progresso", "Em Progresso"}
            palavras_ignorar = ["Entregar", "2025", "2026", "Tarefa SP",
                              "Home", "Status", "A Fazer", "Rascunho"]

            for i, linha in enumerate(linhas):
                if linha in STATUS_ABERTO:
                    for j in range(i + 1, min(i + 4, len(linhas))):
                        nome = linhas[j]
                        if (nome and len(nome.strip()) > 5
                            and not any(p in nome for p in palavras_ignorar)
                            and not nome.strip().isdigit()):
                            
                            atividade = {
                                'nome': nome,
                                'url': 'https://saladofuturo.educacao.sp.gov.br/tarefas',
                                'status': 'sucesso',
                                'cliques': 1,
                                'descricao': 'Atividade encontrada e processada'
                            }
                            atividades.append(atividade)
                            break

            print(f"  ✓ {len(atividades)} atividade(s) encontrada(s)")
            browser.close()

    except Exception as e:
        print(f"  ✗ Erro ao processar: {e}")
        raise

    return atividades


# ============================================================
#  TRATAMENTO DE ERROS
# ============================================================

@app.errorhandler(404)
def nao_encontrado(e):
    return jsonify({'error': 'Página não encontrada'}), 404


@app.errorhandler(500)
def erro_servidor(e):
    return jsonify({'error': 'Erro interno do servidor'}), 500


# ============================================================
#  MAIN
# ============================================================

if __name__ == '__main__':
    # Para desenvolvimento
    app.run(debug=True, host='127.0.0.1', port=5000)
    
    # Para produção (Vercel/Heroku), descomente:
    # app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))