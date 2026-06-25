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

RA               = os.environ.get("RA",               "000110134488")
DIGITO           = os.environ.get("DIGITO",           "x")
SENHA            = os.environ.get("SENHA",            "mj13112008")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
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


def carregar_atividades_salvas():
    if os.path.exists(ARQUIVO_ATIVIDADES):
        with open(ARQUIVO_ATIVIDADES, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def salvar_atividades(atividades):
    with open(ARQUIVO_ATIVIDADES, "w", encoding="utf-8") as f:
        json.dump(atividades, f, ensure_ascii=False, indent=2)


def fazer_login(page):
    print("  -> Abrindo pagina de login...")
    page.goto("https://saladofuturo.educacao.sp.gov.br/login-alunos", wait_until="domcontentloaded")
    time.sleep(6)
    page.get_by_placeholder("Ex.: 186735683").click()
    page.get_by_placeholder("Ex.: 186735683").type(RA)
    page.get_by_placeholder("0").first.click()
    page.get_by_placeholder("0").first.type(DIGITO)
    page.get_by_placeholder("Digite sua senha").click()
    page.get_by_placeholder("Digite sua senha").type(SENHA)
    time.sleep(1)
    page.get_by_role("button", name="Acessar").click()
    time.sleep(5)
    print("  -> Login realizado!")


def buscar_atividades(page):
    print("  -> Verificando tarefas...")
    page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", wait_until="domcontentloaded")
    time.sleep(4)
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    corpo = page.inner_text("body")
    linhas = [l.strip() for l in corpo.split("\n") if l.strip()]
    print(f"  -> Total de linhas na pagina: {len(linhas)}")

    atividades = []
    # Todos os status possiveis de tarefas em aberto
    STATUS_ABERTO = {"A Fazer", "Rascunho", "Em andamento", "Em Andamento",
                     "Em progresso", "Em Progresso", "Iniciado", "Iniciada"}
    palavras_ignorar = ["Entregar", " dia", "2025", "2026", "Tarefa SP",
                        "Home", "Status", "A Fazer", "Rascunho", "Componente", "Turmas",
                        "Em andamento", "Em Andamento", "Em progresso"]

    for i, linha in enumerate(linhas):
        if linha in STATUS_ABERTO:
            # Procura o nome nas proximas 3 linhas (ignora linhas curtas/numericas)
            for j in range(i + 1, min(i + 4, len(linhas))):
                nome = linhas[j]
                print(f"  -> Candidato [{linha}] linha {j}: '{nome}'")
                if (nome and len(nome.strip()) > 5
                        and not any(p in nome for p in palavras_ignorar)
                        and not nome.strip().isdigit()
                        and nome not in atividades):
                    atividades.append(nome)
                    break

    print(f"  -> {len(atividades)} tarefa(s) em aberto: {atividades}")

    if len(atividades) == 0:
        # Mostra TODAS as linhas para diagnostico
        todas = "\n".join([f"{i:02d}: {linhas[i]}" for i in range(len(linhas))])
        debug_msg = f"DEBUG: 0 atividades.\nTotal linhas: {len(linhas)}\n\n{todas}"
        enviar_telegram_longo("", debug_msg.split("\n"))

    return atividades


def abrir_atividade(page, nome_atividade):
    print(f"  -> Abrindo atividade: {nome_atividade}")
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
        print(f"  -> Falhou texto exato: {e}")

    if not clicou:
        try:
            card = page.locator(f"text={nome_atividade}").first
            card.scroll_into_view_if_needed()
            card.click()
            clicou = True
            time.sleep(2)
        except Exception as e:
            print(f"  -> Falhou texto parcial: {e}")
            return None, None

    textos_botao = ["Prosseguir para a tarefa", "Prosseguir", "Acessar tarefa", "Iniciar"]
    for texto in textos_botao:
        try:
            btn = page.get_by_role("button", name=texto)
            btn.wait_for(state="visible", timeout=5000)
            btn.click()
            print(f"  -> Botao '{texto}' clicado!")
            time.sleep(4)
            break
        except Exception:
            try:
                btn = page.get_by_text(texto).first
                btn.wait_for(state="visible", timeout=3000)
                btn.click()
                print(f"  -> Botao '{texto}' clicado via texto!")
                time.sleep(4)
                break
            except Exception:
                pass
    else:
        print(f"  -> Nenhum botao de prosseguir encontrado.")
        return None, None

    url_atividade = page.url
    conteudo = page.inner_text("body")
    print(f"  -> URL final: {url_atividade}")
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
        enviar_telegram("Aviso: GROQ_API_KEY nao configurada.")
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
            return resp.json()["choices"][0]["message"]["content"].strip()
        else:
            print(f"  -> Erro Groq {resp.status_code}: {resp.text[:200]}")
            enviar_telegram(f"Erro Groq: {resp.status_code}\n{resp.text[:200]}")
            return None
    except Exception as e:
        print(f"  -> Falha Groq: {e}")
        enviar_telegram(f"Falha Groq: {e}")
        return None


def responder_com_ia(conteudo_atividade, nome_atividade):
    """Retorna respostas em texto legivel para enviar no Telegram."""
    print(f"  -> IA (respostas texto)... chave: {GROQ_API_KEY[:8]}...")
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
    if resposta:
        print("  -> IA respondeu (texto)!")
    return resposta


def obter_respostas_json(conteudo_atividade, nome_atividade):
    """Retorna JSON estruturado para clicar automaticamente."""
    print(f"  -> IA (JSON para cliques)...")
    prompt = f"""Analise esta atividade escolar brasileira do ensino medio.
Retorne SOMENTE JSON valido, sem markdown, sem texto extra:

{{
  "1": {{"tipo": "multipla_escolha", "respostas": ["B", "D"]}},
  "2": {{"tipo": "unica_escolha", "respostas": ["C"]}},
  "3": {{"tipo": "dropdown", "respostas": ["nao vazia", "vazia", "mutuamente excludentes"]}}
}}

Tipos:
- multipla_escolha: checkboxes, pode ter varias letras corretas
- unica_escolha: radio button, so uma letra
- dropdown: completar lacunas no texto, lista de termos na ordem das lacunas

CONTEUDO "{nome_atividade}":
{conteudo_atividade[:5000]}

JSON:"""

    resposta = chamar_groq(prompt, max_tokens=1024, temperature=0.1)
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
        print(f"  -> JSON: {resultado}")
        return resultado
    except Exception as e:
        print(f"  -> Erro JSON: {e} | Resposta: {resposta[:200]}")
        return None


# ============================================================
#  CLICAR NAS RESPOSTAS
# ============================================================

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
                const texto = (el.innerText || el.textContent || \'\').trim();
                if (!texto) continue;
                const tn = norm(texto);
                // 1) Como letra: A), A., A<espaco>
                const padrao = new RegExp(\'^\' + termo + \'[).\\\\s]\');
                if (padrao.test(texto) || texto.startsWith(termo + \')\') || texto.startsWith(termo + \'.\')) {
                    if (!inp.checked) inp.click();
                    return true;
                }
                // 2) Por texto (ex: "Certo", "Errado")
                if (tn === termoNorm || tn.startsWith(termoNorm + \' \') || tn.startsWith(termoNorm + \')\')) {
                    if (!inp.checked) inp.click();
                    return true;
                }
            }
        }
        return false;
    }
    """, [termo, termo_norm])

    if clicou:
        print(f"    -> Clicou '{letra_ou_texto}' (Q{num_questao})")
        time.sleep(0.4)
    else:
        print(f"    -> Nao achou '{letra_ou_texto}' (Q{num_questao})")
    return clicou

def _norm(s):
    """Remove acentos e normaliza para comparacao flexivel."""
    nfkd = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def clicar_dropdown(page, indice, termo):
    """
    Abre o dropdown de indice dado e seleciona o termo usando matching flexivel
    (ignora acentos, maiusculas/minusculas e correspondencia parcial).
    """
    termo_norm = _norm(termo)

    try:
        # 1) Tenta select nativo
        selects = page.query_selector_all("select")
        if indice < len(selects):
            opcoes = selects[indice].query_selector_all("option")
            for opcao in opcoes:
                texto = opcao.inner_text().strip()
                t_norm = _norm(texto)
                if t_norm == termo_norm or termo_norm in t_norm or t_norm in termo_norm:
                    try:
                        selects[indice].select_option(value=opcao.get_attribute("value"))
                    except Exception:
                        selects[indice].select_option(label=texto)
                    print(f"    -> Select {indice+1}: '{texto}'")
                    time.sleep(0.3)
                    return True

        # 2) Dropdown customizado React
        cbs = page.query_selector_all(
            '[role="combobox"], [aria-haspopup="listbox"], [aria-haspopup="true"]')
        if indice >= len(cbs):
            print(f"    -> Combobox {indice+1} nao encontrado (total: {len(cbs)})")
            return False

        cb = cbs[indice]
        cb.scroll_into_view_if_needed()
        time.sleep(0.5)
        cb.click()
        time.sleep(1.5)  # aguarda animacao do dropdown

        # Debug: ver quais opcoes aparecem
        debug_ops = page.evaluate("""
        () => {
            const sels = ['[role="option"]', '.MuiMenuItem-root', 'li[data-value]',
                          '[class*="MenuItem"]', '[class*="option"]'];
            for (const s of sels) {
                const els = Array.from(document.querySelectorAll(s))
                    .filter(e => e.offsetWidth > 0 || e.offsetHeight > 0);
                if (els.length > 0) {
                    return els.slice(0,5).map(e=>(e.innerText||e.textContent||'').trim()).join(' | ');
                }
            }
            return 'nenhuma';
        }
        """)
        print(f"    -> Opcoes: {debug_ops[:120]}")

        # 3) JS: percorre TODOS os elementos visiveis buscando o texto
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
                '[class*="Option"]',
                '[class*="item"]',
                '[class*="Item"]',
                '[role="listbox"] *',
                'ul[role] li',
                'li'
            ];
            for (const sel of seletores) {
                const els = Array.from(document.querySelectorAll(sel));
                for (const el of els) {
                    // Usa offsetWidth/Height em vez de offsetParent para detectar visibilidade
                    if (el.offsetWidth === 0 && el.offsetHeight === 0) continue;
                    const texto = (el.innerText || el.textContent || "").trim();
                    if (!texto) continue;
                    const tn = norm(texto);
                    if (tn === termoNorm || tn.includes(termoNorm) || termoNorm.includes(tn)) {
                        el.click();
                        return texto;
                    }
                }
            }
            return null;
        }
        """, termo_norm)

        if clicou:
            print(f"    -> Dropdown {indice+1}: '{clicou}' (JS match)")
            time.sleep(0.4)
            return True
        else:
            print(f"    -> Opcao '{termo}' nao encontrada no dropdown {indice+1}")
            page.keyboard.press("Escape")
            time.sleep(0.3)
            return False

    except Exception as e:
        print(f"    -> Erro dropdown {indice+1}: {e}")
        return False


def clicar_respostas_pagina(page, respostas_json):
    """Clica nas respostas corretas baseado no JSON da IA. Retorna total de cliques."""
    if not respostas_json:
        return 0

    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(0.5)
    total = 0
    dropdown_indice = 0  # contador global de dropdowns na pagina

    for num_q_str, dados in sorted(respostas_json.items(), key=lambda x: int(x[0])):
        num_q = int(num_q_str)
        tipo = dados.get("tipo", "multipla_escolha")
        respostas = dados.get("respostas", [])

        print(f"  -> Q{num_q} ({tipo}): {respostas}")

        if tipo in ("multipla_escolha", "unica_escolha"):
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
                print("  -> Rascunho salvo!")
                time.sleep(2)
                return True
        except Exception:
            pass

    print("  -> Botao Salvar Rascunho nao encontrado")
    return False


# ============================================================
#  TELEGRAM
# ============================================================

def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"  Telegram nao configurado. Mensagem:\n{mensagem}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}, timeout=30)
    if resp.status_code == 200:
        print("  -> Telegram enviado!")
    else:
        print(f"  Erro Telegram: {resp.status_code} - {resp.text}")


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
    print(f"\n{'='*50}")
    print(f"  Verificacao iniciada: {agora}")
    print(f"{'='*50}")

    atividades_salvas = []  # TEMP: ignorar historico

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
                print(f"\n  {len(novas)} NOVA(S) ATIVIDADE(S):")

                resumo = f"Sala do Futuro - {len(novas)} nova(s) atividade(s)!\n\n"
                for a in novas:
                    resumo += f"- {a}\n"
                resumo += f"\nTotal em aberto: {len(atividades_atuais)}"
                resumo += "\nhttps://saladofuturo.educacao.sp.gov.br/tarefas"
                enviar_telegram(resumo)

                for nome in novas:
                    print(f"\n  -> Processando: {nome}")
                    url_atv, conteudo_atv = abrir_atividade(page, nome)

                    if url_atv and conteudo_atv:
                        linhas_filtradas = filtrar_conteudo(conteudo_atv, nome)
                        conteudo_limpo = "\n".join(linhas_filtradas)

                        # Passo 1: JSON de respostas para clicar
                        respostas_json = obter_respostas_json(conteudo_limpo, nome)

                        cliques = 0
                        rascunho_salvo = False

                        if respostas_json:
                            time.sleep(2)
                            cliques = clicar_respostas_pagina(page, respostas_json)
                            if cliques > 0:
                                rascunho_salvo = salvar_rascunho_pagina(page)

                        # Passo 2: Respostas em texto para Telegram
                        resposta_ia = responder_com_ia(conteudo_limpo, nome)

                        # Status do auto-responder
                        if cliques > 0:
                            status = f"\n\nRespondido automaticamente: {cliques} questao(oes)"
                            status += " | Rascunho salvo!" if rascunho_salvo else " | (salve o rascunho manualmente)"
                        else:
                            status = "\n\n(Auto-responder nao clicou — confira manualmente)"

                        if resposta_ia:
                            cab = f"Atividade: {nome}\nLink: {url_atv}{status}\n\n--- Respostas ---\n"
                            enviar_telegram_longo(cab, resposta_ia.split("\n"))
                        else:
                            enviar_telegram(
                                f"Atividade: {nome}\nLink: {url_atv}{status}\n\n"
                                f"(Acesse o link para confirmar)"
                            )
                    else:
                        enviar_telegram(
                            f"Atividade: {nome}\n\n"
                            f"Nao foi possivel abrir automaticamente.\n"
                            f"Acesse: https://saladofuturo.educacao.sp.gov.br/tarefas"
                        )

            else:
                print("\n  Nenhuma atividade nova. Tudo em dia!")
                enviar_telegram(
                    f"Sala do Futuro - OK\n\n"
                    f"Nenhuma tarefa nova.\n"
                    f"Total em aberto: {len(atividades_atuais)}\n"
                    f"Horario: {agora}"
                )

            browser.close()

        pass  # TEMP: nao salvar historico

    except Exception as erro:
        print(f"\n  Erro: {erro}")
        raise

    print(f"\n  Verificacao concluida: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
