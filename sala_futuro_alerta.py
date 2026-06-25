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
    """Faz login no Sala do Futuro. Usa waits por elemento, nao networkidle."""
    log.info("Abrindo pagina de login...")
    page.goto(URL_LOGIN, wait_until="domcontentloaded")

    # Aguarda o campo de RA aparecer — indica que o formulario carregou
    # AJUSTE O SELETOR se o placeholder mudar
    try:
        campo_ra = page.get_by_placeholder("Ex.: 186735683")
        campo_ra.wait_for(state="visible", timeout=30_000)
    except PlaywrightTimeout:
        raise RuntimeError("Pagina de login nao carregou: campo RA nao encontrado em 30s.")

    campo_ra.fill(config["RA"])
    log.info("RA preenchido.")

    # AJUSTE O SELETOR se o placeholder do digito mudar
    campo_digito = page.get_by_placeholder("0").first
    campo_digito.wait_for(state="visible", timeout=10_000)
    campo_digito.fill(config["DIGITO"])

    # AJUSTE O SELETOR se o placeholder da senha mudar
    campo_senha = page.get_by_placeholder("Digite sua senha")
    campo_senha.wait_for(state="visible", timeout=10_000)
    campo_senha.fill(config["SENHA"])

    btn = page.get_by_role("button", name="Acessar")
    btn.wait_for(state="visible", timeout=10_000)
    btn.click()
    log.info("Botao Acessar clicado. Aguardando redirecionamento...")

    # Aguarda sair da pagina de login
    try:
        page.wait_for_url(lambda url: "login" not in url, timeout=30_000)
        log.info("Login realizado com sucesso.")
    except PlaywrightTimeout:
        raise RuntimeError("Login falhou: pagina nao redirecionou apos 30s. Verifique as credenciais.")


# --- 3. Listar atividades pendentes ---
def listar_atividades_pendentes(page: Page) -> list:
    """
    Acessa /tarefas e retorna lista de dicts com titulo, url, disciplina, prazo.

    AJUSTE OS SELETORES conforme o HTML real do site.
    Inspecione no Chrome DevTools (F12) para encontrar os seletores corretos.
    """
    log.info("Acessando pagina de tarefas...")
    page.goto(URL_TAREFAS, wait_until="domcontentloaded")

    # Aguarda o corpo da pagina ter conteudo relevante (sem networkidle)
    try:
        page.wait_for_function("document.body.innerText.length > 100", timeout=30_000)
    except PlaywrightTimeout:
        log.warning("Pagina de tarefas demorou para carregar conteudo.")

    atividades = []

    # Tenta localizar links de atividades — AJUSTE ESTE SELETOR
    links = page.locator("a[href*='/tarefa'], a[href*='/atividade'], a[href*='/task']").all()

    if links:
        for link in links:
            try:
                titulo = link.inner_text().strip()
                href = link.get_attribute("href") or ""
                if not titulo or len(titulo) < 3:
                    continue
                url_ativ = href if href.startswith("http") else f"https://saladofuturo.educacao.sp.gov.br{href}"

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
                log.debug("Erro ao processar link de atividade: %s", exc)
    else:
        # Fallback: leitura de texto simples
        log.info("Nenhum link encontrado via seletor. Usando leitura de texto.")
        corpo = page.inner_text("body")
        linhas = [l.strip() for l in corpo.split("\n") if l.strip()]
        ignorar = ["Entregar", " dia", "2025", "2026", "Tarefa SP",
                   "Home", "Status", "A Fazer", "Componente", "Turmas"]
        for i, linha in enumerate(linhas):
            if linha == "A Fazer" and i + 1 < len(linhas):
                nome = linhas[i + 1]
                if nome and len(nome) > 3 and not any(p in nome for p in ignorar):
                    atividades.append({"titulo": nome, "url": URL_TAREFAS,
                                       "disciplina": "", "prazo": ""})

    vistos: set = set()
    resultado = []
    for a in atividades:
        if a["titulo"] not in vistos:
            vistos.add(a["titulo"])
            resultado.append(a)

    log.info("%d atividade(s) pendente(s) encontrada(s).", len(resultado))
    return resultado


# --- 4. Abrir atividade ---
def abrir_atividade(page: Page, url: str) -> bool:
    if url == URL_TAREFAS:
        return False
    try:
        log.info("Abrindo atividade: %s", url)
        page.goto(url, wait_until="domcontentloaded")
        # Aguarda conteudo minimo aparecer, sem networkidle
        page.wait_for_function("document.body.innerText.length > 50", timeout=20_000)
        return True
    except PlaywrightTimeout:
        log.warning("Timeout ao abrir atividade: %s", url)
        return False
    except Exception as exc:
        log.warning("Erro ao abrir atividade %s: %s", url, exc)
        return False


# --- 5. Extrair conteudo ---
def extrair_conteudo_atividade(page: Page) -> dict:
    """
    Extrai titulo, disciplina, prazo, enunciado, alternativas e textos de apoio.

    AJUSTE OS SELETORES conforme o HTML real do Sala do Futuro.
    Inspecione cada elemento no DevTools e substitua os seletores abaixo.
    """
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


# --- 6. Identificador unico ---
def gerar_id_atividade(atividade: dict) -> str:
    chave = f"{atividade['titulo']}|{atividade['url']}"
    return hashlib.sha256(chave.encode()).hexdigest()[:16]


# --- 7. Estado persistente ---
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


# --- 8. Resposta educacional ---
def gerar_resposta_educacional(conteudo: dict, api_key: str) -> dict:
    resultado = {
        "resposta_sugerida": "",
        "explicacao": "",
        "nivel_confianca": "baixo",
        "observacao": ""
    }

    if not api_key:
        resultado["observacao"] = (
            "Resposta automatica nao gerada: ANTHROPIC_API_KEY nao configurada. "
            "Configure o secret para ativar esta funcionalidade."
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
        "Regras obrigatorias:\n"
        "- Se a atividade parecer prova formal ou avaliacao, sinalize claramente.\n"
        "- Se houver alternativas, indique a mais provavel e justifique com base no texto.\n"
        "- Se for discursiva, escreva uma resposta modelo em linguagem simples.\n"
        "- Se houver calculo, mostre o passo a passo.\n"
        "- Se for interpretacao de texto, explique onde a resposta aparece.\n"
        "- Se o conteudo estiver incompleto, diga isso claramente.\n"
        "- NUNCA invente informacoes que nao estejam na atividade.\n"
        "- Responda sempre em portugues brasileiro.\n\n"
        "Responda em JSON com este formato exato:\n"
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
        resultado["observacao"] = f"Erro ao gerar resposta automatica: {exc}"
    except Exception as exc:
        log.warning("Erro inesperado na geracao de resposta: %s", exc)
        resultado["observacao"] = "Erro inesperado ao gerar resposta educacional."
    return resultado


# --- 9. Telegram ---
def enviar_telegram(mensagem: str, config: dict) -> None:
    if not config.get("TELEGRAM_TOKEN") or not config.get("TELEGRAM_CHAT_ID"):
        log.warning("Telegram nao configurado. Mensagem:\n%s", mensagem)
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


# --- 10. Main ---
def main():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    log.info("=" * 50)
    log.info("Verificacao iniciada: %s", agora)
    log.info("=" * 50)

    config = carregar_variaveis()
    estado = carregar_estado()

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
                    enviar_telegram(
                        f"Erro critico - Sala do Futuro\n\nFalha no login: {exc}", config
                    )
                    sys.exit(1)

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

                    if not conteudo["leitura_ok"] and not abriu:
                        mensagem = (
                            f"Atividade encontrada, mas nao lida\n\n"
                            f"Titulo: {atividade['titulo']}\n"
                            f"Link: {atividade['url']}\n\n"
                            "Nao foi possivel abrir a atividade para leitura completa."
                        )
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