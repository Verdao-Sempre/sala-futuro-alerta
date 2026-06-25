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

TITULOS_IGNORAR = {
    "tarefa sp", "home", "status", "a fazer", "componente", "turmas",
    "entregar", "tarefas", "atividades", "menu", "inicio", "voltar"
}


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


def _e_titulo_valido(titulo: str) -> bool:
    t = titulo.strip().lower()
    if len(t) < 4:
        return False
    if t in TITULOS_IGNORAR:
        return False
    if any(ignorar in t for ignorar in TITULOS_IGNORAR):
        return False
    if re.fullmatch(r'[\d/\-\s:]+', t):
        return False
    return True


def _normalizar_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    return f"https://saladofuturo.educacao.sp.gov.br{href}"


def _e_url_especifica(url: str) -> bool:
    """Retorna True se a URL for de uma atividade especifica, nao a pagina de listagem."""
    return bool(url) and url.rstrip("/") != URL_TAREFAS.rstrip("/")


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

    campo_digito = page.get_by_placeholder("0").first
    campo_digito.wait_for(state="visible", timeout=10_000)
    campo_digito.fill(config["DIGITO"])

    campo_senha = page.get_by_placeholder("Digite sua senha")
    campo_senha.wait_for(state="visible", timeout=10_000)
    campo_senha.fill(config["SENHA"])

    btn = page.get_by_role("button", name="Acessar")
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()
    log.info("Botao Acessar clicado. Aguardando redirecionamento...")

    try:
        page.wait_for_url(lambda url: "login" not in url, timeout=30_000)
        log.info("Login realizado com sucesso.")
    except PlaywrightTimeout:
        raise RuntimeError("Login falhou: pagina nao redirecionou apos 30s.")


# --- 3. Diagnostico da pagina de tarefas ---
def diagnosticar_pagina(page: Page, config: dict) -> None:
    """
    Modo debug: envia para o Telegram um dump dos links e texto da pagina
    para ajudar a identificar os seletores corretos.
    """
    log.info("[DEBUG] Coletando diagnostico da pagina...")

    # Todos os links da pagina
    todos_links = page.locator("a[href]").all()
    links_info = []
    for link in todos_links[:40]:
        try:
            href = link.get_attribute("href") or ""
            texto = link.inner_text().strip()[:60]
            if href and texto:
                links_info.append(f"  [{texto}] -> {href}")
        except Exception:
            pass

    # Primeiras linhas do corpo
    corpo = page.inner_text("body").strip()
    primeiras_linhas = "\n".join(
        [l for l in corpo.split("\n") if l.strip()][:40]
    )

    msg_debug = (
        "<b>[DEBUG] Links encontrados na pagina de tarefas:</b>\n"
        + "\n".join(links_info[:25])
        + "\n\n<b>Primeiras linhas do texto da pagina:</b>\n"
        + primeiras_linhas[:1500]
    )
    enviar_telegram(msg_debug, config)
    log.info("[DEBUG] Diagnostico enviado ao Telegram.")


# --- 4. Listar atividades pendentes ---
def listar_atividades_pendentes(page: Page) -> list:
    log.info("Acessando pagina de tarefas...")
    page.goto(URL_TAREFAS, wait_until="domcontentloaded")

    try:
        page.wait_for_function("document.body.innerText.length > 100", timeout=30_000)
    except PlaywrightTimeout:
        log.warning("Pagina de tarefas demorou para carregar.")

    atividades = []

    # Tenta varios seletores, do mais especifico ao mais generico
    # AJUSTE conforme os hrefs reais do site (use o debug para ver)
    seletores_tentativa = [
        "a[href*='/tarefa/']",
        "a[href*='/atividade/']",
        "a[href*='/task/']",
        "a[href*='/tarefa']",      # mais amplo: captura /tarefa123 etc
        "a[href*='/questao/']",
        "a[href*='/exercicio/']",
    ]

    links = []
    seletor_usado = None
    for sel in seletores_tentativa:
        encontrados = page.locator(sel).all()
        # Filtra links que nao sejam a propria pagina de tarefas
        validos = []
        for l in encontrados:
            try:
                href = l.get_attribute("href") or ""
                url_norm = _normalizar_url(href)
                if _e_url_especifica(url_norm):
                    validos.append(l)
            except Exception:
                pass
        if validos:
            links = validos
            seletor_usado = sel
            log.info("Seletor '%s' encontrou %d links.", sel, len(links))
            break

    if links:
        for link in links:
            try:
                titulo = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                url_ativ = _normalizar_url(href)

                if not _e_titulo_valido(titulo):
                    log.debug("Titulo ignorado: %r", titulo)
                    continue

                card = link.locator(
                    "xpath=ancestor::article | xpath=ancestor::li | xpath=ancestor::div[@class]"
                ).first
                disciplina, prazo = "", ""
                try:
                    disciplina = card.locator(
                        ".disciplina, [class*='subject'], [class*='component']"
                    ).first.inner_text().strip()
                except Exception:
                    pass
                try:
                    prazo = card.locator(
                        ".prazo, .data, [class*='deadline'], [class*='date']"
                    ).first.inner_text().strip()
                except Exception:
                    pass

                atividades.append({"titulo": titulo, "url": url_ativ,
                                   "disciplina": disciplina, "prazo": prazo})
            except Exception as exc:
                log.debug("Erro ao processar link: %s", exc)
    else:
        # Fallback: leitura linha a linha do texto da pagina
        log.info("Nenhum link especifico encontrado. Usando leitura de texto (fallback).")
        corpo = page.inner_text("body")
        linhas = [l.strip() for l in corpo.split("\n") if l.strip()]

        log.info("[FALLBACK] Total de linhas na pagina: %d", len(linhas))
        if MODO_DEBUG:
            for idx, linha in enumerate(linhas[:60]):
                log.info("[FALLBACK] linha[%d]: %r", idx, linha)

        for i, linha in enumerate(linhas):
            if linha == "A Fazer" and i + 1 < len(linhas):
                nome = linhas[i + 1]
                if _e_titulo_valido(nome):
                    atividades.append({"titulo": nome, "url": URL_TAREFAS,
                                       "disciplina": "", "prazo": ""})

    vistos: set = set()
    resultado = []
    for a in atividades:
        if a["titulo"] not in vistos:
            vistos.add(a["titulo"])
            resultado.append(a)

    log.info("%d atividade(s) encontrada(s).", len(resultado))
    return resultado


# --- 5. Abrir atividade ---
def abrir_atividade(page: Page, url: str) -> bool:
    if not _e_url_especifica(url):
        return False
    try:
        log.info("Abrindo atividade: %s", url)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_function("document.body.innerText.length > 50", timeout=20_000)
        return True
    except PlaywrightTimeout:
        log.warning("Timeout ao abrir atividade: %s", url)
        return False
    except Exception as exc:
        log.warning("Erro ao abrir atividade %s: %s", url, exc)
        return False


# --- 6. Extrair conteudo ---
def extrair_conteudo_atividade(page: Page) -> dict:
    conteudo = {
        "titulo": "", "disciplina": "", "prazo": "",
        "enunciado": "", "alternativas": [], "textos_apoio": [],
        "texto_completo": "", "leitura_ok": False
    }
    try:
        for sel in ["h1", "h2.titulo", ".titulo-atividade", "[class*='title']"]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    conteudo["titulo"] = el.inner_text().strip()
                    break
            except Exception:
                pass

        for sel in [".disciplina", "[class*='subject']", "[class*='component']", ".componente"]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    conteudo["disciplina"] = el.inner_text().strip()
                    break
            except Exception:
                pass

        for sel in [".prazo", ".data-entrega", "[class*='deadline']", "[class*='due']"]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    conteudo["prazo"] = el.inner_text().strip()
                    break
            except Exception:
                pass

        for sel in [".enunciado", ".questao", ".conteudo-atividade", "[class*='statement']",
                    "[class*='question']", "p.descricao", ".descricao"]:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    conteudo["enunciado"] = el.inner_text().strip()
                    break
            except Exception:
                pass

        for sel in [".alternativa", "[class*='option']", "[class*='choice']", "li.item-alternativa"]:
            try:
                els = page.locator(sel).all()
                if els:
                    conteudo["alternativas"] = [e.inner_text().strip() for e in els
                                                if e.inner_text().strip()]
                    break
            except Exception:
                pass

        for sel in [".texto-apoio", "[class*='support']", ".leitura", "[class*='reading']"]:
            try:
                els = page.locator(sel).all()
                if els:
                    conteudo["textos_apoio"] = [e.inner_text().strip() for e in els
                                                if e.inner_text().strip()]
                    break
            except Exception:
                pass

        conteudo["texto_completo"] = page.inner_text("main, article, .conteudo, body").strip()[:3000]
        conteudo["leitura_ok"] = bool(
            conteudo["titulo"] or conteudo["enunciado"] or conteudo["texto_completo"]
        )
    except Exception as exc:
        log.warning("Erro ao extrair conteudo: %s", exc)
    return conteudo


# --- 7. Identificador unico ---
def gerar_id_atividade(atividade: dict) -> str:
    chave = f"{atividade['titulo']}|{atividade['url']}"
    return hashlib.sha256(chave.encode()).hexdigest()[:16]


# --- 8. Estado persistente ---
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


# --- 9. Resposta educacional ---
def gerar_resposta_educacional(conteudo: dict, api_key: str) -> dict:
    resultado = {
        "resposta_sugerida": "",
        "explicacao": "",
        "nivel_confianca": "baixo",
        "observacao": ""
    }
    if not api_key:
        resultado["observacao"] = (
            "Resposta automatica nao gerada: ANTHROPIC_API_KEY nao configurada."
        )
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
        "- Se o conteudo estiver incompleto, diga isso.\n"
        "- NUNCA invente informacoes.\n"
        "- Responda sempre em portugues brasileiro.\n\n"
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
    except requests.HTTPError as exc:
        log.warning("Erro na API Anthropic: %s", exc)
        resultado["observacao"] = f"Erro ao gerar resposta: {exc}"
    except Exception as exc:
        log.warning("Erro inesperado na geracao de resposta: %s", exc)
        resultado["observacao"] = "Erro inesperado ao gerar resposta educacional."
    return resultado


# --- 10. Telegram ---
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
            log.info("Mensagem Telegram enviada.")
        else:
            log.warning("Erro Telegram %d: %s", resp.status_code, resp.text[:200])
    except requests.RequestException as exc:
        log.error("Falha ao enviar Telegram: %s", exc)


def formatar_mensagem_atividade(atividade: dict, conteudo: dict, resposta: dict) -> str:
    icone = {"alto": "OK", "medio": "ATENCAO", "baixo": "INCERTO"}.get(
        resposta.get("nivel_confianca", "baixo"), "INCERTO"
    )
    partes = ["<b>Nova atividade encontrada</b>\n"]
    partes.append(f"<b>Titulo:</b>\n{conteudo['titulo'] or atividade['titulo']}\n")
    if conteudo["disciplina"] or atividade["disciplina"]:
        partes.append(f"<b>Disciplina:</b>\n{conteudo['disciplina'] or atividade['disciplina']}\n")
    if conteudo["prazo"] or atividade["prazo"]:
        partes.append(f"<b>Prazo:</b>\n{conteudo['prazo'] or atividade['prazo']}\n")
    if conteudo["enunciado"]:
        enunciado = conteudo["enunciado"]
        if len(enunciado) > 600:
            enunciado = enunciado[:600] + "..."
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
    partes.append(f"<b>Link:</b>\n{atividade['url']}")
    return "\n".join(partes)


# --- 11. Main ---
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

                # Modo debug: envia dump da pagina para o Telegram
                if MODO_DEBUG:
                    page.goto(URL_TAREFAS, wait_until="domcontentloaded")
                    try:
                        page.wait_for_function("document.body.innerText.length > 100", timeout=30_000)
                    except PlaywrightTimeout:
                        pass
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
                        "titulo": atividade["titulo"], "disciplina": atividade["disciplina"],
                        "prazo": atividade["prazo"], "enunciado": "", "alternativas": [],
                        "textos_apoio": [], "texto_completo": "", "leitura_ok": False
                    }

                    abriu = abrir_atividade(page, atividade["url"])
                    if abriu:
                        conteudo = extrair_conteudo_atividade(page)
                        conteudo["titulo"] = conteudo["titulo"] or atividade["titulo"]
                        conteudo["disciplina"] = conteudo["disciplina"] or atividade["disciplina"]
                        conteudo["prazo"] = conteudo["prazo"] or atividade["prazo"]

                    hash_atual = gerar_hash_conteudo(conteudo)
                    registro = estado.get(id_ativ, {})
                    ja_processada = bool(registro)
                    conteudo_mudou = registro.get("hash_conteudo") != hash_atual

                    if ja_processada and not conteudo_mudou:
                        log.info("Sem alteracoes: %s", atividade["titulo"])
                        continue

                    tipo = "Atualizacao" if (ja_processada and conteudo_mudou) else "Nova atividade"
                    log.info("%s: %s", tipo, atividade["titulo"])
                    novas_ou_alteradas += 1

                    resposta = gerar_resposta_educacional(conteudo, config["ANTHROPIC_API_KEY"])

                    if not abriu and not conteudo["leitura_ok"]:
                        if _e_url_especifica(atividade["url"]):
                            mensagem = (
                                f"Atividade encontrada, mas nao lida\n\n"
                                f"Titulo: {atividade['titulo']}\n"
                                f"Link: {atividade['url']}\n\n"
                                "Nao foi possivel abrir a atividade para leitura completa."
                            )
                            enviar_telegram(mensagem, config)
                        else:
                            log.warning("Atividade sem URL especifica ignorada: %s", atividade["titulo"])
                    else:
                        mensagem = formatar_mensagem_atividade(atividade, conteudo, resposta)
                        if ja_processada and conteudo_mudou:
                            mensagem = "Atividade atualizada\n\n" + mensagem
                        enviar_telegram(mensagem, config)

                    estado[id_ativ] = {
                        "titulo": atividade["titulo"],
                        "url": atividade["url"],
                        "processado_em": datetime.now().isoformat(),
                        "hash_conteudo": hash_atual
                    }

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