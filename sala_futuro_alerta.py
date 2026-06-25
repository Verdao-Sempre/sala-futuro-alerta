# ============================================================
#  ALERTA SALA DO FUTURO - NOVAS ATIVIDADES
#  Versao GitHub Actions (roda na nuvem, sem computador)
# ============================================================

import os
import json
import time
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime
import unicodedata
import sys

RA               = os.environ.get("RA")
DIGITO           = os.environ.get("DIGITO")
SENHA            = os.environ.get("SENHA")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

ARQUIVO_ATIVIDADES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atividades_salvas.json")

NAV_IGNORAR = {
    "redacao paulista", "avaliacao diagnostica", "materiais digitais",
    "plataformas de aprendizagem", "boletim e avaliacoes", "minhas conquistas",
    "copa da escola", "inscricao aulas olimpicas", "configuracoes",
    "sair da conta", "home", "tarefas", "agenda", "mensagens", "pesquisa",
    "perfil", "portal de atendimento", "suporte", "sobre", "termos de uso",
    "politica de privacidade", "central de atendimento", "apps"
}


# ============================================================
#  VALIDACAO DE CREDENCIAIS
# ============================================================

def validar_credenciais():
    """Falha imediatamente se credenciais obrigatorias estao faltando."""
    erros = []
    if not RA:
        erros.append("RA nao configurada")
    if not DIGITO:
        erros.append("DIGITO nao configurada")
    if not SENHA:
        erros.append("SENHA nao configurada")
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  ⚠️  AVISO: Telegram nao configurado - alertas nao serao enviados")
    
    if erros:
        msg = "ERRO - Credenciais obrigatorias faltando:\n" + "\n".join(erros)
        print(f"  {msg}")
        enviar_telegram(msg)
        sys.exit(1)


def carregar_atividades_salvas():
    if os.path.exists(ARQUIVO_ATIVIDADES):
        try:
            with open(ARQUIVO_ATIVIDADES, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  ⚠️  Erro ao carregar historico: {e}")
            return []
    return []


def salvar_atividades(atividades):
    try:
        with open(ARQUIVO_ATIVIDADES, "w", encoding="utf-8") as f:
            json.dump(atividades, f, ensure_ascii=False, indent=2)
        print(f"  ✓ Historico salvo ({len(atividades)} atividades)")
    except Exception as e:
        print(f"  ✗ Erro ao salvar historico: {e}")


def fazer_login(page):
    print("  → Abrindo pagina de login...")
    page.goto("https://saladofuturo.educacao.sp.gov.br/login-alunos", wait_until="domcontentloaded")
    time.sleep(6)
    
    try:
        page.get_by_placeholder("Ex.: 186735683").click()
        page.get_by_placeholder("Ex.: 186735683").type(RA)
        page.get_by_placeholder("0").first.click()
        page.get_by_placeholder("0").first.type(DIGITO)
        page.get_by_placeholder("Digite sua senha").click()
        page.get_by_placeholder("Digite sua senha").type(SENHA)
        time.sleep(1)
        page.get_by_role("button", name="Acessar").click()
        time.sleep(5)
        
        url_atual = page.url
        print(f"  ✓ Login realizado! URL: {url_atual}")
        time.sleep(3)
    except Exception as e:
        print(f"  ✗ Erro no login: {e}")
        raise


def buscar_atividades(page):
    print("  → Verificando tarefas...")
    page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", wait_until="domcontentloaded")
    time.sleep(5)
    
    url_tarefas = page.url
    print(f"  ✓ URL da pagina de tarefas: {url_tarefas}")
    
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    corpo = page.inner_text("body")
    linhas = [l.strip() for l in corpo.split("\n") if l.strip()]
    print(f"  ✓ Total de linhas na pagina: {len(linhas)}")

    atividades = []
    STATUS_ABERTO = {"A Fazer", "Rascunho", "Em andamento", "Em Andamento",
                     "Em progresso", "Em Progresso", "Iniciado", "Iniciada"}
    palavras_ignorar = ["Entregar", " dia", "2025", "2026", "Tarefa SP",
                        "Home", "Status", "A Fazer", "Rascunho", "Componente", "Turmas",
                        "Em andamento", "Em Andamento", "Em progresso"]

    for i, linha in enumerate(linhas):
        if linha in STATUS_ABERTO:
            for j in range(i + 1, min(i + 4, len(linhas))):
                nome = linhas[j]
                if (nome and len(nome.strip()) > 5
                        and not any(p in nome for p in palavras_ignorar)
                        and not nome.strip().isdigit()
                        and nome not in atividades):
                    atividades.append(nome)
                    break

    print(f"  ✓ {len(atividades)} tarefa(s) em aberto: {atividades}")
    return atividades


def abrir_atividade(page, nome_atividade):
    print(f"  → Abrindo atividade: {nome_atividade}")
    page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", wait_until="domcontentloaded")
    time.sleep(3)
    for _ in range(2):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)

    clicou = False
    try:
        card = page.get_by_text(nome_atividade, exact=True).first
        card.scroll_into_view_if_needed()
        time.sleep(0.5)
        card.click()
        clicou = True
        time.sleep(2)
    except Exception as e:
        print(f"  ⚠️  Falhou texto exato: {e}")

    if not clicou:
        try:
            card = page.locator(f"text={nome_atividade}").first
            card.scroll_into_view_if_needed()
            card.click()
            clicou = True
            time.sleep(2)
        except Exception as e:
            print(f"  ⚠️  Falhou texto parcial: {e}")
            return None, None

    textos_botao = ["Prosseguir para a tarefa", "Prosseguir", "Acessar tarefa", "Iniciar"]
    for texto in textos_botao:
        try:
            btn = page.get_by_role("button", name=texto)
            btn.wait_for(state="visible", timeout=5000)
            btn.click()
            print(f"  ✓ Botao '{texto}' clicado!")
            time.sleep(4)
            break
        except Exception:
            try:
                btn = page.get_by_text(texto).first
                btn.wait_for(state="visible", timeout=3000)
                btn.click()
                print(f"  ✓ Botao '{texto}' clicado via texto!")
                time.sleep(4)
                break
            except Exception:
                pass
    else:
        print(f"  ✗ Nenhum botao de prosseguir encontrado.")
        return None, None

    url_atividade = page.url
    conteudo = page.inner_text("body")
    print(f"  ✓ URL final: {url_atividade}")
    return url_atividade, conteudo


def filtrar_conteudo(texto_bruto, nome_atividade=""):
    linhas = [l.strip() for l in texto_bruto.split("\n") if l.strip()]

    fim_marcadores = ["voltar", "salvar rascunho", "finalizar", "ouvidoria",
                      "politica de privacidade", "0800-", "tentativas restantes"]

    inicio = 0
    for i, linha in enumerate(linhas):
        linha_lower = linha.lower()
        if nome_atividade and nome_atividade.lower()[:20] in linha_lower:
            inicio = i
            break
        if "introdução" in linha_lower or "questão 01" in linha_lower or "questao 01" in linha_lower:
            inicio = i
            break

    resultado = []
    for linha in linhas[inicio:]:
        linha_lower = linha.lower()
        if any(m in linha_lower for m in fim_marcadores):
            break
        if len(linha) < 3:
            continue
        resultado.append(linha)

    return resultado


# ============================================================
#  INTEGRACAO COM IA (GROQ)
# ============================================================

def chamar_groq(prompt, max_tokens=2048, temperature=0.3):
    if not GROQ_API_KEY:
        print("  ⚠️  GROQ_API_KEY nao configurada.")
        return None
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.1-8b-instant",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        if resp.status_code == 200:
            resultado = resp.json()["choices"][0]["message"]["content"].strip()
            print(f"  ✓ IA respondeu ({len(resultado)} chars)")
            return resultado
        else:
            print(f"  ✗ Erro Groq {resp.status_code}: {resp.text[:200]}")
            enviar_telegram(f"Erro Groq: {resp.status_code}\n{resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  ✗ Falha Groq: {e}")
        enviar_telegram(f"Falha Groq: {e}")
        return None


def responder_com_ia(conteudo_atividade, nome_atividade):
    """Retorna respostas em texto legivel para enviar no Telegram."""
    print(f"  → IA (respostas texto)...")
    prompt = f"""Voce e um assistente que ajuda estudantes do ensino medio brasileiro.
Responda APENAS as questoes, sem repetir o enunciado.

Formato:
Q01: [letra(s) ou termo correto]
Motivo: [explicacao breve 1-2 linhas]

Q02: [resposta]
Motivo: [explicacao]

Para checkbox (multipla escolha), indique TODAS as letras corretas.
Para dropdown (completar lacunas), indique os termos na ordem.
Para radio (unica escolha), indique a letra.
NAO repita as questoes.

CONTEUDO DA ATIVIDADE "{nome_atividade}":
{conteudo_atividade[:6000]}
"""
    resposta = chamar_groq(prompt, max_tokens=2048, temperature=0.3)
    return resposta


def obter_respostas_json(conteudo_atividade, nome_atividade, opcoes_dropdowns=None):
    """Retorna JSON estruturado para clicar automaticamente."""
    print(f"  → IA (JSON para cliques)...")

    opcoes_info = ""
    if opcoes_dropdowns:
        opcoes_info = "OPCOES DISPONIVEIS NOS DROPDOWNS (use EXATAMENTE um destes textos por lacuna):\n"
        for idx, ops in sorted(opcoes_dropdowns.items()):
            opcoes_info += f"  Dropdown {idx+1}: {ops}\n"
        opcoes_info += "\n"

    prompt = f"""Analise esta atividade escolar brasileira do ensino medio.
Retorne SOMENTE JSON valido, sem markdown, sem texto extra.

REGRAS OBRIGATORIAS:
- multipla_escolha: respostas sao APENAS letras maiusculas (A, B, C, D, E). Nunca use textos.
- unica_escolha: resposta e APENAS uma letra maiuscula (A, B, C, D, E). Nunca use textos.
- dropdown: use EXATAMENTE um dos textos listados nas "OPCOES DOS DROPDOWNS" abaixo.
- verdadeiro_falso: resposta e "Certo" ou "Errado" (exato).

Exemplo de formato:
{{
  "1": {{"tipo": "multipla_escolha", "respostas": ["B", "D"]}},
  "2": {{"tipo": "unica_escolha", "respostas": ["C"]}},
  "3": {{"tipo": "dropdown", "respostas": ["termo1", "termo2"]}},
  "4": {{"tipo": "verdadeiro_falso", "respostas": ["Certo"]}}
}}

{opcoes_info}CONTEUDO "{nome_atividade}":
{conteudo_atividade[:3000]}

JSON:"""

    resposta = chamar_groq(prompt, max_tokens=2000, temperature=0.1)
    if not resposta:
        return None

    try:
        texto = resposta.strip()
        if "```" in texto:
            for parte in texto.split("```"):
                parte = parte.strip()
                if parte.startswith("json"):
                    parte = parte[4:].strip()
                if parte.startswith("{"):
                    texto = parte
                    break
        resultado = json.loads(texto)
        print(f"  ✓ JSON: {resultado}")
        return resultado
    except Exception as e:
        print(f"  ✗ Erro JSON: {e} | Resposta: {resposta[:200]}")
        return None


# ============================================================
#  CLICAR NAS RESPOSTAS
# ============================================================

def _norm(s):
    """Remove acentos e normaliza para comparacao flexivel."""
    nfkd = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def clicar_checkbox_radio(page, letra_ou_texto, num_questao):
    """Clica no checkbox/radio. Aceita letra (A/B/C) ou texto (Certo/Errado)."""
    termo = letra_ou_texto.strip()
    termo_norm = _norm(termo)
    clicou = page.evaluate("""
    ([termo, termoNorm]) => {
        function norm(s) {
            return s.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
        }
        const inputs = document.querySelectorAll('input[type="checkbox"], input[type="radio"]');
        for (const inp of inputs) {
            let el = inp;
            for (let i = 0; i < 5; i++) {
                el = el.parentElement;
                if (!el) break;
                const texto = (el.innerText || el.textContent || '').trim();
                if (!texto) continue;
                const tn = norm(texto);
                // 1) Como letra: A), A., A<espaco>
                const padrao = new RegExp('^' + termo + '[).\\\\s]');
                if (padrao.test(texto) || texto.startsWith(termo + ')') || texto.startsWith(termo + '.')) {
                    if (!inp.checked) inp.click();
                    return true;
                }
                // 2) Por texto (ex: "Certo", "Errado")
                if (tn === termoNorm || tn.startsWith(termoNorm + ' ') || tn.startsWith(termoNorm + ')')) {
                    if (!inp.checked) inp.click();
                    return true;
                }
            }
        }
        return false;
    }
    """, [termo, termo_norm])

    if clicou:
        print(f"    ✓ Clicou '{letra_ou_texto}' (Q{num_questao})")
        time.sleep(0.4)
    else:
        print(f"    ⚠️  Nao achou '{letra_ou_texto}' (Q{num_questao})")
    return clicou


def clicar_dropdown(page, indice, termo):
    """
    Abre select NATIVO (ou combobox React) e seleciona o termo.
    Usa matching flexivel (ignora acentos).
    """
    termo_norm = _norm(termo)

    try:
        # 1) Primeiro tenta select nativo HTML
        selects = page.query_selector_all("select")
        if indice < len(selects):
            print(f"    → Select nativo {indice+1} encontrado")
            opcoes = selects[indice].query_selector_all("option")
            for opcao in opcoes:
                texto = opcao.inner_text().strip()
                t_norm = _norm(texto)
                if t_norm == termo_norm or termo_norm in t_norm or t_norm in termo_norm:
                    try:
                        selects[indice].select_option(value=opcao.get_attribute("value"))
                    except Exception:
                        selects[indice].select_option(label=texto)
                    print(f"    ✓ Select {indice+1}: '{texto}'")
                    time.sleep(0.3)
                    return True
            print(f"    ⚠️  Opcao '{termo}' nao encontrada no select {indice+1}")
            return False

        # 2) Se nao tem select, tenta combobox React
        cbs = page.query_selector_all(
            '[role="combobox"], [aria-haspopup="listbox"], [aria-haspopup="true"]')
        if indice >= len(cbs):
            print(f"    ⚠️  Select/Combobox {indice+1} nao encontrado")
            return False

        cb = cbs[indice]
        cb.scroll_into_view_if_needed()
        time.sleep(0.5)
        cb.click()
        time.sleep(1.5)

        clicou = page.evaluate("""
        (termoNorm) => {
            function norm(s) {
                return s.toLowerCase()
                    .normalize("NFD")
                    .replace(/[\u0300-\u036f]/g, "");
            }
            const seletores = [
                '[role="option"]',
                '.MuiMenuItem-root',
                '.MuiListItem-root',
                '[class*="MenuItem"]',
                '[class*="option"]',
                'li'
            ];
            for (const sel of seletores) {
                const els = Array.from(document.querySelectorAll(sel));
                for (const el of els) {
                    if (el.offsetWidth === 0 && el.offsetHeight === 0) continue;
                    const texto = (el.innerText || el.textContent || "").trim();
                    if (!texto) continue;
                    const tn = norm(texto);
                    if (tn === termoNorm || termoNorm.includes(tn)) {
                        el.click();
                        return texto;
                    }
                }
            }
            return null;
        }
        """, termo_norm)

        if clicou:
            print(f"    ✓ Combobox {indice+1}: '{clicou}'")
            time.sleep(0.4)
            return True
        else:
            print(f"    ⚠️  Opcao '{termo}' nao encontrada no combobox {indice+1}")
            page.keyboard.press("Escape")
            time.sleep(0.3)
            return False

    except Exception as e:
        print(f"    ✗ Erro dropdown {indice+1}: {e}")
        return False


def extrair_opcoes_dropdowns(page):
    """Extrai opcoes de SELECT nativos e comboboxes React."""
    opcoes_por_dd = {}
    try:
        # Primeiro: SELECT nativos
        selects = page.query_selector_all("select")
        print(f"  → Encontrado {len(selects)} select(s) nativo(s)")
        
        for i, select in enumerate(selects):
            try:
                opcoes = select.query_selector_all("option")
                opcoes_texto = [op.inner_text().strip() for op in opcoes if op.inner_text().strip()]
                if opcoes_texto:
                    opcoes_por_dd[i] = opcoes_texto
                    print(f"  ✓ Select {i+1} opcoes: {opcoes_texto[:3]}...")
            except Exception as e:
                print(f"  ⚠️  Erro ao ler select {i+1}: {e}")

        # Segundo: Comboboxes React (caso nao tenha encontrado selects)
        if not opcoes_por_dd:
            cbs = page.query_selector_all(
                '[role="combobox"], [aria-haspopup="listbox"], [aria-haspopup="true"]')
            print(f"  → Encontrado {len(cbs)} combobox(es) React")
            
            for i, cb in enumerate(cbs):
                try:
                    cb.scroll_into_view_if_needed()
                    time.sleep(0.3)
                    cb.click()
                    time.sleep(1.2)
                    opcoes = page.evaluate("""
                    () => {
                        const sels = ['[role="option"]', '.MuiMenuItem-root', 'li[data-value]',
                                      '[class*="MenuItem"]'];
                        for (const s of sels) {
                            const els = Array.from(document.querySelectorAll(s))
                                .filter(e => e.offsetWidth > 0 || e.offsetHeight > 0);
                            if (els.length > 0)
                                return els.map(e => (e.innerText || e.textContent || '').trim()).filter(t => t);
                        }
                        return [];
                    }
                    """)
                    if opcoes:
                        opcoes_por_dd[len(opcoes_por_dd)] = opcoes
                        print(f"  ✓ Combobox {i+1} opcoes: {opcoes[:3]}...")
                    page.keyboard.press("Escape")
                    time.sleep(0.5)
                except Exception as e:
                    print(f"  ⚠️  Erro ao ler combobox {i+1}: {e}")
                    try:
                        page.keyboard.press("Escape")
                    except:
                        pass
    except Exception as e:
        print(f"  ✗ Erro ao extrair dropdowns: {e}")
    
    return opcoes_por_dd


def clicar_respostas_pagina(page, respostas_json):
    """Clica nas respostas corretas baseado no JSON da IA. Retorna total de cliques."""
    if not respostas_json:
        return 0

    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.5)
    total = 0
    dropdown_indice = 0

    for num_q_str, dados in sorted(respostas_json.items(), key=lambda x: int(x[0])):
        num_q = int(num_q_str)
        tipo = dados.get("tipo", "multipla_escolha")
        respostas = dados.get("respostas", [])

        print(f"  → Q{num_q} ({tipo}): {respostas}")

        if tipo in ("multipla_escolha", "unica_escolha", "verdadeiro_falso"):
            for letra in respostas:
                if clicar_checkbox_radio(page, letra, num_q):
                    total += 1

        elif tipo == "dropdown":
            for termo in respostas:
                if clicar_dropdown(page, dropdown_indice, termo):
                    total += 1
                dropdown_indice += 1

    return total


def salvar_rascunho_pagina(page):
    """Clica em Salvar Rascunho."""
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(1)

    tentativas = [
        lambda: page.get_by_role("button", name="Salvar rascunho"),
        lambda: page.get_by_role("button", name="Salvar Rascunho"),
        lambda: page.get_by_text("Salvar rascunho").first,
        lambda: page.get_by_text("Salvar Rascunho").first,
        lambda: page.locator("button:has-text('rascunho')").first,
        lambda: page.locator("button:has-text('Rascunho')").first,
    ]

    for fn in tentativas:
        try:
            btn = fn()
            if btn.is_visible(timeout=2000):
                btn.click()
                print("  ✓ Rascunho salvo!")
                time.sleep(2)
                return True
        except Exception:
            pass

    print("  ⚠️  Botao Salvar Rascunho nao encontrado")
    return False


# ============================================================
#  TELEGRAM
# ============================================================

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"  [TELEGRAM DESATIVADO] {mensagem[:100]}...")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}, timeout=30)
        if resp.status_code == 200:
            print("  ✓ Telegram enviado!")
        else:
            print(f"  ✗ Erro Telegram: {resp.status_code}")
    except Exception as e:
        print(f"  ✗ Falha Telegram: {e}")


def enviar_telegram_longo(titulo, linhas):
    LIMITE = 3800
    msg_atual = titulo + "\n\n"
    for linha in linhas:
        adicao = linha + "\n"
        if len(msg_atual) + len(adicao) > LIMITE:
            enviar_telegram(msg_atual)
            msg_atual = "(continuacao)\n\n" + adicao
        else:
            msg_atual += adicao
    if msg_atual.strip():
        enviar_telegram(msg_atual)


# ============================================================
#  MAIN
# ============================================================

def main():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'='*60}")
    print(f"  🚀 Verificacao iniciada: {agora}")
    print(f"{'='*60}")

    # Validar credenciais
    validar_credenciais()

    # Carregar historico
    atividades_salvas = carregar_atividades_salvas()
    print(f"  📋 Historico carregado: {len(atividades_salvas)} atividades ja processadas")

    is_cloud = os.environ.get("GITHUB_ACTIONS") == "true"

    try:
        with sync_playwright() as p:
            if is_cloud:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )
            else:
                browser = p.chromium.launch(headless=False)

            page = browser.new_page()
            fazer_login(page)
            atividades_atuais = buscar_atividades(page)

            novas = [a for a in atividades_atuais if a not in atividades_salvas]

            if novas:
                print(f"\n  📌 {len(novas)} NOVA(S) ATIVIDADE(S):")

                resumo = f"🎯 Sala do Futuro - {len(novas)} nova(s) atividade(s)!\n\n"
                for a in novas:
                    resumo += f"  • {a}\n"
                resumo += f"\n📊 Total em aberto: {len(atividades_atuais)}"
                resumo += "\n🔗 https://saladofuturo.educacao.sp.gov.br/tarefas"
                enviar_telegram(resumo)

                for nome in novas:
                    print(f"\n  📝 Processando: {nome}")
                    url_atv, conteudo_atv = abrir_atividade(page, nome)

                    if url_atv and conteudo_atv:
                        linhas_filtradas = filtrar_conteudo(conteudo_atv, nome)
                        conteudo_limpo = "\n".join(linhas_filtradas)

                        # Extrai opcoes reais dos dropdowns
                        opcoes_dd = extrair_opcoes_dropdowns(page)

                        # JSON de respostas para clicar
                        respostas_json = obter_respostas_json(conteudo_limpo, nome, opcoes_dd)

                        cliques = 0
                        rascunho_salvo = False

                        if respostas_json:
                            time.sleep(2)
                            cliques = clicar_respostas_pagina(page, respostas_json)
                            if cliques > 0:
                                rascunho_salvo = salvar_rascunho_pagina(page)

                        # Respostas em texto para Telegram
                        time.sleep(8)  # evita rate limit TPM do Groq
                        resposta_ia = responder_com_ia(conteudo_limpo, nome)

                        # Status do auto-responder
                        if cliques > 0:
                            status = f"\n\n✅ Respondido automaticamente: {cliques} questao(oes)"
                            status += " | ✓ Rascunho salvo!" if rascunho_salvo else " | ⚠️  (salve o rascunho manualmente)"
                        else:
                            status = "\n\n⚠️  Auto-responder nao clicou — confira manualmente"

                        if resposta_ia:
                            cab = f"📚 Atividade: {nome}\n🔗 Link: {url_atv}{status}\n\n--- 📋 Respostas ---\n"
                            enviar_telegram_longo(cab, resposta_ia.split("\n"))
                        else:
                            enviar_telegram(
                                f"📚 Atividade: {nome}\n🔗 Link: {url_atv}{status}\n\n"
                                f"(Acesse o link para confirmar)"
                            )

                        # Adicionar ao historico
                        atividades_salvas.append(nome)
                    else:
                        enviar_telegram(
                            f"📚 Atividade: {nome}\n\n"
                            f"⚠️  Nao foi possivel abrir automaticamente.\n"
                            f"🔗 Acesse: https://saladofuturo.educacao.sp.gov.br/tarefas"
                        )
                        atividades_salvas.append(nome)

                # Salvar estado
                salvar_atividades(atividades_salvas)

            else:
                print("\n  ✓ Nenhuma atividade nova. Tudo em dia!")
                enviar_telegram(
                    f"✓ Sala do Futuro - OK\n\n"
                    f"Nenhuma tarefa nova.\n"
                    f"Total em aberto: {len(atividades_atuais)}\n"
                    f"Horario: {agora}"
                )

            browser.close()

    except Exception as erro:
        print(f"\n  ✗ Erro: {erro}")
        enviar_telegram(f"❌ ERRO na automacao:\n\n{str(erro)[:500]}")
        raise

    print(f"\n  ✓ Verificacao concluida: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
