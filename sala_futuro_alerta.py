"""
Sala do Futuro - Alerta de Atividades com Resposta Educacional
GitHub Actions | Playwright | Telegram Bot API
"""

import os
import re
import json
import hashlib
import logging
import sys
import unicodedata
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout

# --- Logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger(__name__)

# --- Config ---
ARQUIVO_ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atividades_salvas.json")
URL_LOGIN      = "https://saladofuturo.educacao.sp.gov.br/login-alunos"
URL_TAREFAS    = "https://saladofuturo.educacao.sp.gov.br/tarefas"
TELEGRAM_MAX   = int(os.environ.get("TELEGRAM_MAX_LENGTH", "4000"))
ENVIAR_OK      = os.environ.get("ENVIAR_OK", "false").lower() == "true"
IS_CLOUD       = os.environ.get("GITHUB_ACTIONS") == "true"
MODO_DEBUG     = os.environ.get("MODO_DEBUG", "false").lower() == "true"

# Textos que sao itens de navegacao, filtros ou rodape — nunca titulos de tarefa
NAV_IGNORAR = {
    "tarefa sp", "home", "status", "a fazer", "componente", "turmas",
    "entregar", "tarefas", "atividades", "menu", "inicio", "voltar",
    "redacao paulista", "provas", "avaliacao diagnostica", "presenca",
    "boletim e avaliacoes", "agenda", "mensagens", "pesquisa", "perfil",
    "minhas conquistas", "copa da escola", "configuracoes", "sair da conta",
    "plataformas de aprendizagem", "materiais digitais", "inscricao aulas olimpicas",
    "portal de atendimento", "suporte", "ouvidoria", "termos de uso",
    "politica de privacidade", "sobre", "todas as turmas", "central de atendimento",
    "apps", "prosseguir", "prosseguir para a tarefa", "cancelar", "fechar",
    "voltar para tarefas"
}


# --- Utilidades ---
def _remover_acentos(texto: str) -> str:
    s = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _e_titulo_valido(titulo: str) -> bool:
    t = _remover_acentos(titulo.strip())
    if len(t) < 4:
        return False
    if t in NAV_IGNORAR:
        return False
    if any(nav in t for nav in NAV_IGNORAR):
        return False
    if re.fullmatch(r'[\d/\-\s:.,]+', t):
        return False
    return True


# --- 1. Variaveis obrigatorias ---
def carregar_variaveis() -> dict:
    obrigatorias = ["RA", "DIGITO", "SENHA", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
    config = {}
    faltando = []
    for var in obrigatorias:
        val = os.environ.get(var, "").strip()
        if not val:
            faltando.append(var)
        config[var] = val
    if faltando:
        raise ValueError(f"Variaveis de ambiente ausentes: {', '.join(faltando)}")
    config["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    log.info("Variaveis carregadas. API Anthropic: %s",
             "configurada" if config["ANTHROPIC_API_KEY"] else "nao configurada")
    return config


# --- 2. Login ---
def fazer_login(page: Page, config: dict) -> None:
    log.info("Abrindo pagina de login...")
    page.goto(URL_LOGIN, wait_until="domcontentloaded")

    try:
        campo_ra = page.get_by_placeholder("Ex.: 186735683")
        campo_ra.wait_for(state="visible", timeout=30_000)
    except PlaywrightTimeout:
        raise RuntimeError("Pagina de login nao carregou: campo RA nao encontrado em 30s.")

    campo_ra.fill(config["RA"])
    page.get_by_placeholder("0").first.fill(config["DIGITO"])
    page.get_by_placeholder("Digite sua senha").fill(config["SENHA"])
    page.get_by_role("button", name="Acessar").click()
    log.info("Credenciais enviadas. Aguardando redirecionamento...")

    try:
        page.wait_for_url(lambda url: "login" not in url, timeout=30_000)
        log.info("Login realizado com sucesso.")
    except PlaywrightTimeout:
        raise RuntimeError("Login falhou: pagina nao redirecionou apos 30s.")


# --- 3. Aguardar carregamento da SPA ---
def _aguardar_pagina_estavel(page: Page, minimo_chars: int = 300, tentativas: int = 6) -> None:
    """Aguarda o texto da pagina parar de crescer (SPA terminou de renderizar)."""
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(800)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(800)

    anterior = 0
    for _ in range(tentativas):
        atual = page.evaluate("document.body.innerText.length")
        if atual >= minimo_chars and atual == anterior:
            break
        anterior = atual
        page.wait_for_timeout(1500)
    log.info("Pagina estabilizada com %d chars.", anterior)


# --- 4. Diagnostico (modo debug) ---
def diagnosticar_pagina(page: Page, config: dict) -> None:
    """Envia ao Telegram um dump completo da pagina para ajudar a identificar seletores."""
    log.info("[DEBUG] Coletando diagnostico...")

    # Todos os elementos visiveis e clicaveis (nao so links)
    script_elementos = """
    () => {
        const sels = ['button', 'li', '[role="button"]', '[role="listitem"]',
                      '[class*="card"]', '[class*="task"]', '[class*="tarefa"]',
                      '[class*="item"]', '[class*="atividade"]'];
        const vistos = new Set();
        const resultado = [];
        for (const sel of sels) {
            for (const el of document.querySelectorAll(sel)) {
                const txt = el.innerText ? el.innerText.trim().slice(0, 80) : '';
                const cls = el.className ? el.className.toString().slice(0, 60) : '';
                const tag = el.tagName.toLowerCase();
                if (txt && !vistos.has(txt)) {
                    vistos.add(txt);
                    resultado.push(tag + ' [' + cls + ']: ' + txt);
                }
                if (resultado.length >= 50) break;
            }
            if (resultado.length >= 50) break;
        }
        return resultado;
    }
    """
    elementos = page.evaluate(script_elementos)

    # Texto completo da pagina
    corpo = page.inner_text("body").strip()
    linhas = [l for l in corpo.split("\n") if l.strip()]

    msg1 = "<b>[DEBUG] Elementos clicaveis na pagina:</b>\n" + "\n".join(elementos[:40])
    msg2 = "<b>[DEBUG] Texto completo da pagina (100 linhas):</b>\n" + "\n".join(linhas[:100])

    enviar_telegram(msg1[:TELEGRAM_MAX], config)
    enviar_telegram(msg2[:TELEGRAM_MAX], config)
    log.info("[DEBUG] Diagnostico enviado.")


# --- 5. Listar tarefas pendentes ---
def listar_atividades_pendentes(page: Page) -> list:
    """
    Navega para /tarefas, aguarda carregamento e retorna lista de tarefas.
    Cada item: {titulo, disciplina, prazo}
    URL nao e usada pois o acesso requer click no card + click em Prosseguir.
    """
    log.info("Acessando pagina de tarefas...")
    page.goto(URL_TAREFAS, wait_until="domcontentloaded")
    _aguardar_pagina_estavel(page)

    atividades = []

    # Tenta encontrar cards de tarefas por seletores comuns
    # AJUSTE estes seletores apos ver o debug com tarefas reais na pagina
    # Seletores MUI para cards de tarefa.
    # MuiMenuItem-root sao itens de NAVEGACAO — excluir.
    # Cards de tarefa serao MuiCard, MuiPaper ou MuiListItem sem ser MenuItem.
    # Seletores MUI para cards de tarefa.
    # MuiMenuItem-root = navegacao lateral (excluir).
    # MuiPaper-elevation foi removido — era generico demais e capturava o botao de perfil.
    seletores_card = [
        "[class*='MuiCard-root']",
        "[class*='MuiPaper-root'][class*='MuiCard']",
        "li[class*='MuiListItem-root']:not([class*='MuiMenuItem-root'])",
        "div[class*='MuiListItem-root']:not([class*='MuiMenuItem-root'])",
        "[class*='task-card']",
        "[class*='tarefa-card']",
        "[class*='activity-card']",
    ]

    cards_encontrados = []
    seletor_usado = None
    for sel in seletores_card:
        candidatos = page.locator(sel).all()
        validos = [c for c in candidatos if _e_titulo_valido(c.inner_text().strip()[:80])]
        if validos:
            cards_encontrados = validos
            seletor_usado = sel
            log.info("Cards encontrados com seletor: %s (%d items)", sel, len(validos))
            break

    if cards_encontrados:
        for card in cards_encontrados:
            try:
                texto = card.inner_text().strip()
                linhas = [l.strip() for l in texto.split("\n") if l.strip()]
                # Card valido precisa de pelo menos 2 linhas de conteudo
                # (titulo + disciplina ou prazo). Evita capturar botao de perfil.
                if len(linhas) < 2:
                    log.debug("Card ignorado (poucas linhas): %r", linhas)
                    continue
                titulo = next((l for l in linhas if _e_titulo_valido(l)), "")
                if not titulo:
                    continue
                disciplina = ""
                prazo = ""
                # Tenta inferir disciplina e prazo das outras linhas do card
                for l in linhas:
                    if re.search(r'\d{2}/\d{2}/\d{4}', l) and not prazo:
                        prazo = l
                    elif l != titulo and _e_titulo_valido(l) and not disciplina:
                        disciplina = l
                atividades.append({"titulo": titulo, "disciplina": disciplina, "prazo": prazo})
            except Exception as exc:
                log.debug("Erro ao ler card: %s", exc)
    else:
        # Fallback: leitura de texto apos secao de filtros
        log.info("Cards nao encontrados via seletor. Usando leitura de texto.")
        corpo = page.inner_text("body")
        linhas = [l.strip() for l in corpo.split("\n") if l.strip()]
        log.info("Total de linhas: %d", len(linhas))

        marcos_filtro = {"turmas:", "status", "componente", "a fazer", "todas as turmas"}
        ultimo_filtro = -1
        for i, linha in enumerate(linhas):
            if _remover_acentos(linha) in marcos_filtro:
                ultimo_filtro = i

        rodape_inicio = {"sobre", "suporte", "ouvidoria", "termos de uso",
                         "politica de privacidade", "central de atendimento",
                         "portal de atendimento", "apps"}

        if ultimo_filtro >= 0:
            log.info("Buscando tarefas apos linha %d.", ultimo_filtro)
            for linha in linhas[ultimo_filtro + 1:]:
                if _remover_acentos(linha) in rodape_inicio:
                    break
                if _e_titulo_valido(linha):
                    atividades.append({"titulo": linha, "disciplina": "", "prazo": ""})

    # Remove duplicatas
    vistos: set = set()
    resultado = []
    for a in atividades:
        if a["titulo"] not in vistos:
            vistos.add(a["titulo"])
            resultado.append(a)

    log.info("%d atividade(s) encontrada(s).", len(resultado))
    return resultado


# --- 6. Abrir atividade (click no card + Prosseguir) ---
def abrir_atividade(page: Page, titulo: str) -> bool:
    """
    Navega para /tarefas, clica no card da tarefa e depois em Prosseguir.
    Retorna True se chegou na pagina da tarefa com sucesso.
    """
    log.info("Abrindo tarefa: %s", titulo)

    # Volta para /tarefas se nao estiver la
    if URL_TAREFAS not in page.url:
        page.goto(URL_TAREFAS, wait_until="domcontentloaded")
        _aguardar_pagina_estavel(page)

    # Tenta encontrar o card pelo titulo
    # AJUSTE o seletor se necessario apos ver o debug
    card = None
    seletores_card = [
        f"text={titulo}",
        f"[title='{titulo}']",
    ]
    for sel in seletores_card:
        try:
            candidato = page.locator(sel).first
            if candidato.is_visible():
                card = candidato
                break
        except Exception:
            pass

    if not card:
        log.warning("Card da tarefa nao encontrado: %s", titulo)
        return False

    try:
        card.click()
        log.info("Card clicado. Aguardando botao Prosseguir...")

        # Aguarda o botao Prosseguir aparecer
        # AJUSTE o seletor se o texto do botao for diferente
        # Botao MUI — pode ser MuiButton ou MuiButtonBase com texto Prosseguir
        btn_prosseguir = page.locator(
            "button[class*='MuiButton']:has-text('Prosseguir'), "
            "button[class*='MuiButtonBase']:has-text('Prosseguir'), "
            "button:has-text('Prosseguir'), "
            "a:has-text('Prosseguir')"
        ).first
        btn_prosseguir.wait_for(state="visible", timeout=10_000)
        btn_prosseguir.click()
        log.info("Prosseguir clicado. Aguardando conteudo da tarefa...")

        # Aguarda conteudo da tarefa carregar
        _aguardar_pagina_estavel(page, minimo_chars=200, tentativas=5)
        return True

    except PlaywrightTimeout:
        log.warning("Timeout aguardando botao Prosseguir para: %s", titulo)
        return False
    except Exception as exc:
        log.warning("Erro ao abrir tarefa %s: %s", titulo, exc)
        return False


# --- 7. Extrair conteudo da tarefa ---
def extrair_conteudo_atividade(page: Page) -> dict:
    """
    Extrai titulo, disciplina, prazo, enunciado, alternativas e texto de apoio.
    AJUSTE OS SELETORES apos ver o debug numa tarefa aberta.
    """
    conteudo = {
        "titulo": "", "disciplina": "", "prazo": "",
        "enunciado": "", "alternativas": [], "textos_apoio": [],
        "texto_completo": "", "leitura_ok": False
    }
    try:
        for sel in ["h1", "h2", "[class*='MuiTypography-h']", "[class*='title']", "[class*='titulo']"]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    t = el.inner_text().strip()
                    if _e_titulo_valido(t):
                        conteudo["titulo"] = t
                        break
            except Exception:
                pass

        for sel in [".disciplina", "[class*='subject']", "[class*='component']",
                    "[class*='componente']", "[class*='disciplina']"]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    conteudo["disciplina"] = el.inner_text().strip()
                    break
            except Exception:
                pass

        for sel in [".prazo", "[class*='deadline']", "[class*='prazo']", "[class*='due']"]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    conteudo["prazo"] = el.inner_text().strip()
                    break
            except Exception:
                pass

        for sel in [".enunciado", ".questao", "[class*='MuiTypography-body']",
                    "[class*='statement']", "[class*='question']",
                    "[class*='enunciado']", "[class*='descricao']", "p"]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    t = el.inner_text().strip()
                    if len(t) > 20:
                        conteudo["enunciado"] = t
                        break
            except Exception:
                pass

        for sel in [".alternativa", "[class*='option']", "[class*='choice']",
                    "[class*='alternativa']", "li[class*='item']"]:
            try:
                els = page.locator(sel).all()
                if els:
                    conteudo["alternativas"] = [e.inner_text().strip() for e in els
                                                if e.inner_text().strip()]
                    if conteudo["alternativas"]:
                        break
            except Exception:
                pass

        for sel in [".texto-apoio", "[class*='support']", "[class*='reading']",
                    "[class*='leitura']", "[class*='apoio']"]:
            try:
                els = page.locator(sel).all()
                if els:
                    conteudo["textos_apoio"] = [e.inner_text().strip() for e in els
                                                if e.inner_text().strip()]
                    if conteudo["textos_apoio"]:
                        break
            except Exception:
                pass

        conteudo["texto_completo"] = page.inner_text("main, article, body").strip()[:3000]
        conteudo["leitura_ok"] = bool(
            conteudo["titulo"] or conteudo["enunciado"] or conteudo["texto_completo"]
        )
    except Exception as exc:
        log.warning("Erro ao extrair conteudo: %s", exc)
    return conteudo


# --- 8. Identificador unico ---
def gerar_id_atividade(atividade: dict) -> str:
    chave = f"{atividade['titulo']}"
    return hashlib.sha256(chave.encode()).hexdigest()[:16]


# --- 9. Estado persistente ---
def carregar_estado() -> dict:
    if os.path.exists(ARQUIVO_ESTADO):
        try:
            with open(ARQUIVO_ESTADO, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as exc:
            log.warning("Erro ao ler estado: %s. Iniciando do zero.", exc)
    return {}


def salvar_estado(estado: dict) -> None:
    with open(ARQUIVO_ESTADO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    log.info("Estado salvo.")


def gerar_hash_conteudo(conteudo: dict) -> str:
    texto = f"{conteudo['enunciado']}|{conteudo['texto_completo'][:500]}"
    return hashlib.md5(texto.encode()).hexdigest()


# --- 10. Resposta educacional ---
def gerar_resposta_educacional(conteudo: dict, api_key: str) -> dict:
    resultado = {
        "resposta_sugerida": "",
        "explicacao": "",
        "nivel_confianca": "baixo",
        "observacao": ""
    }
    if not api_key:
        resultado["observacao"] = "Resposta automatica nao gerada: ANTHROPIC_API_KEY nao configurada."
        return resultado

    texto_atividade = f"Titulo: {conteudo['titulo']}\n"
    if conteudo["disciplina"]:
        texto_atividade += f"Disciplina: {conteudo['disciplina']}\n"
    if conteudo["enunciado"]:
        texto_atividade += f"\nEnunciado:\n{conteudo['enunciado']}\n"
    if conteudo["alternativas"]:
        texto_atividade += "\nAlternativas:\n" + "\n".join(conteudo["alternativas"]) + "\n"
    if conteudo["textos_apoio"]:
        texto_atividade += "\nTextos de apoio:\n" + "\n".join(conteudo["textos_apoio"][:2]) + "\n"
    if not conteudo["enunciado"] and conteudo["texto_completo"]:
        texto_atividade += f"\nConteudo extraido:\n{conteudo['texto_completo'][:1500]}\n"

    prompt_sistema = (
        "Voce e um tutor educacional que ajuda estudantes a entender atividades escolares. "
        "Sua funcao e EXPLICAR e ENSINAR, nunca apenas dar o gabarito seco.\n\n"
        "Regras:\n"
        "- Se parecer prova formal, sinalize claramente.\n"
        "- Se houver alternativas, indique a mais provavel e justifique.\n"
        "- Se for discursiva, escreva resposta modelo em linguagem simples.\n"
        "- Se houver calculo, mostre o passo a passo.\n"
        "- Se for interpretacao de texto, explique onde a resposta aparece.\n"
        "- NUNCA invente informacoes.\n"
        "- Responda em portugues brasileiro.\n\n"
        "Responda em JSON:\n"
        '{"resposta_sugerida":"...","explicacao":"...","nivel_confianca":"alto|medio|baixo","observacao":"..."}'
    )

    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system": prompt_sistema,
                "messages": [{"role": "user", "content": texto_atividade}]
            },
            timeout=30
        )
        resp.raise_for_status()
        texto_resp = resp.json()["content"][0]["text"]
        match = re.search(r'\{.*\}', texto_resp, re.DOTALL)
        if match:
            dados = json.loads(match.group())
            resultado.update({k: dados.get(k, "") for k in resultado})
        else:
            resultado["resposta_sugerida"] = texto_resp[:500]
    except Exception as exc:
        log.warning("Erro na geracao de resposta: %s", exc)
        resultado["observacao"] = f"Erro ao gerar resposta: {exc}"
    return resultado


# --- 11. Telegram ---
def enviar_telegram(mensagem: str, config: dict) -> None:
    if not config.get("TELEGRAM_TOKEN") or not config.get("TELEGRAM_CHAT_ID"):
        log.warning("Telegram nao configurado.\n%s", mensagem)
        return
    if len(mensagem) > TELEGRAM_MAX:
        mensagem = mensagem[:TELEGRAM_MAX - 50] + "\n\n[mensagem truncada]"
    url = f"https://api.telegram.org/bot{config['TELEGRAM_TOKEN']}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": config["TELEGRAM_CHAT_ID"], "text": mensagem, "parse_mode": "HTML"},
            timeout=30
        )
        if resp.status_code == 200:
            log.info("Telegram enviado.")
        else:
            log.warning("Erro Telegram %d: %s", resp.status_code, resp.text[:200])
    except requests.RequestException as exc:
        log.error("Falha Telegram: %s", exc)


def formatar_mensagem_atividade(atividade: dict, conteudo: dict, resposta: dict) -> str:
    icone = {"alto": "OK", "medio": "ATENCAO", "baixo": "INCERTO"}.get(
        resposta.get("nivel_confianca", "baixo"), "INCERTO"
    )
    partes = ["<b>Nova atividade encontrada</b>\n"]
    partes.append(f"<b>Titulo:</b>\n{conteudo['titulo'] or atividade['titulo']}\n")
    if conteudo["disciplina"] or atividade.get("disciplina"):
        partes.append(f"<b>Disciplina:</b>\n{conteudo['disciplina'] or atividade.get('disciplina', '')}\n")
    if conteudo["prazo"] or atividade.get("prazo"):
        partes.append(f"<b>Prazo:</b>\n{conteudo['prazo'] or atividade.get('prazo', '')}\n")
    if conteudo["enunciado"]:
        enunciado = conteudo["enunciado"][:600] + ("..." if len(conteudo["enunciado"]) > 600 else "")
        partes.append(f"<b>Enunciado:</b>\n{enunciado}\n")
    elif not conteudo["leitura_ok"]:
        partes.append("<b>Enunciado:</b>\nNao foi possivel ler o conteudo desta atividade.\n")
    if conteudo["alternativas"]:
        partes.append("<b>Alternativas:</b>\n" + "\n".join(conteudo["alternativas"][:6]) + "\n")
    if resposta["resposta_sugerida"]:
        partes.append(f"[{icone}] <b>Resposta sugerida:</b>\n{resposta['resposta_sugerida']}\n")
    if resposta["explicacao"]:
        partes.append(f"<b>Explicacao:</b>\n{resposta['explicacao']}\n")
    if resposta["observacao"]:
        partes.append(f"<b>Observacao:</b>\n{resposta['observacao']}\n")
    partes.append(f"<b>Link:</b>\n{URL_TAREFAS}")
    return "\n".join(partes)


# --- 12. Main ---
def main():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    log.info("=" * 50)
    log.info("Verificacao iniciada: %s", agora)
    log.info("=" * 50)

    config = carregar_variaveis()
    estado = carregar_estado()
    atividades = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
            ) if IS_CLOUD else p.chromium.launch(headless=False)

            page = browser.new_page()
            try:
                try:
                    fazer_login(page, config)
                except RuntimeError as exc:
                    log.error("Falha no login: %s", exc)
                    enviar_telegram(f"Erro critico\n\nFalha no login: {exc}", config)
                    sys.exit(1)

                if MODO_DEBUG:
                    page.goto(URL_TAREFAS, wait_until="domcontentloaded")
                    _aguardar_pagina_estavel(page)
                    diagnosticar_pagina(page, config)

                try:
                    atividades = listar_atividades_pendentes(page)
                except Exception as exc:
                    log.error("Falha ao listar atividades: %s", exc)
                    enviar_telegram(f"Erro ao listar atividades\n\n{exc}", config)
                    sys.exit(1)

                novas_ou_alteradas = 0
                for atividade in atividades:
                    id_ativ = gerar_id_atividade(atividade)

                    conteudo = {
                        "titulo": atividade["titulo"],
                        "disciplina": atividade.get("disciplina", ""),
                        "prazo": atividade.get("prazo", ""),
                        "enunciado": "", "alternativas": [],
                        "textos_apoio": [], "texto_completo": "", "leitura_ok": False
                    }

                    # Clica no card e em Prosseguir
                    abriu = abrir_atividade(page, atividade["titulo"])
                    if abriu:
                        conteudo = extrair_conteudo_atividade(page)
                        conteudo["titulo"] = conteudo["titulo"] or atividade["titulo"]
                        conteudo["disciplina"] = conteudo["disciplina"] or atividade.get("disciplina", "")
                        conteudo["prazo"] = conteudo["prazo"] or atividade.get("prazo", "")

                        # Em modo debug, envia o dump da pagina da tarefa aberta
                        if MODO_DEBUG:
                            diagnosticar_pagina(page, config)

                    hash_atual = gerar_hash_conteudo(conteudo)
                    registro = estado.get(id_ativ, {})
                    ja_processada = bool(registro)
                    conteudo_mudou = registro.get("hash_conteudo") != hash_atual

                    if ja_processada and not conteudo_mudou:
                        log.info("Sem alteracoes: %s", atividade["titulo"])
                        # Volta para /tarefas para proxima iteracao
                        page.goto(URL_TAREFAS, wait_until="domcontentloaded")
                        _aguardar_pagina_estavel(page)
                        continue

                    tipo = "Atualizacao" if (ja_processada and conteudo_mudou) else "Nova atividade"
                    log.info("%s: %s", tipo, atividade["titulo"])
                    novas_ou_alteradas += 1

                    resposta = gerar_resposta_educacional(conteudo, config["ANTHROPIC_API_KEY"])

                    if not abriu and not conteudo["leitura_ok"]:
                        mensagem = (
                            f"Atividade encontrada, mas nao lida\n\n"
                            f"Titulo: {atividade['titulo']}\n"
                            f"Link: {URL_TAREFAS}\n\n"
                            "Nao foi possivel abrir a atividade para leitura completa."
                        )
                    else:
                        mensagem = formatar_mensagem_atividade(atividade, conteudo, resposta)
                        if ja_processada and conteudo_mudou:
                            mensagem = "Atividade atualizada\n\n" + mensagem

                    enviar_telegram(mensagem, config)

                    estado[id_ativ] = {
                        "titulo": atividade["titulo"],
                        "processado_em": datetime.now().isoformat(),
                        "hash_conteudo": hash_atual
                    }

                    # Volta para /tarefas para proxima iteracao
                    page.goto(URL_TAREFAS, wait_until="domcontentloaded")
                    _aguardar_pagina_estavel(page)

            finally:
                browser.close()

        if novas_ou_alteradas == 0:
            log.info("Nenhuma atividade nova ou alterada.")
            if ENVIAR_OK:
                enviar_telegram(
                    f"Sala do Futuro - OK\n\nNenhuma atividade nova.\n"
                    f"Total em aberto: {len(atividades)}\nHorario: {agora}",
                    config
                )

        salvar_estado(estado)

    except SystemExit:
        raise
    except Exception as exc:
        log.exception("Erro critico nao tratado: %s", exc)
        try:
            enviar_telegram(f"Erro critico\n\n{type(exc).__name__}: {exc}", config)
        except Exception:
            pass
        sys.exit(1)

    log.info("Verificacao concluida: %s", datetime.now().strftime("%H:%M:%S"))
    log.info("=" * 50)


if __name__ == "__main__":
    main()