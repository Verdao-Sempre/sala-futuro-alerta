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

# Credenciais lidas de variaveis de ambiente (GitHub Secrets)
RA               = os.environ.get("RA",               "000110134488")
DIGITO           = os.environ.get("DIGITO",           "x")
SENHA            = os.environ.get("SENHA",            "mj13112008")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

ARQUIVO_ATIVIDADES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atividades_salvas.json")


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
    """Busca todas as atividades 'A Fazer' na pagina de tarefas."""
    print("  -> Verificando tarefas...")
    page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", wait_until="domcontentloaded")
    time.sleep(4)

    # Rola a pagina para forcar carregamento de todos os cards (lazy loading)
    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(2)

    corpo = page.inner_text("body")
    linhas = [l.strip() for l in corpo.split("\n") if l.strip()]

    print(f"  -> Total de linhas na pagina: {len(linhas)}")

    atividades = []
    palavras_ignorar = ["Entregar", " dia", "2025", "2026", "Tarefa SP",
                        "Home", "Status", "A Fazer", "Componente", "Turmas"]

    for i, linha in enumerate(linhas):
        if linha == "A Fazer" and i + 1 < len(linhas):
            nome = linhas[i + 1]
            print(f"  -> Candidato encontrado: '{nome}'")
            if nome and len(nome.strip()) > 3 and not any(p in nome for p in palavras_ignorar) and nome not in atividades:
                atividades.append(nome)

    print(f"  -> {len(atividades)} tarefa(s) em aberto: {atividades}")
    return atividades


def abrir_atividade(page, nome_atividade):
    """
    Clica no card da atividade, depois clica em 'Prosseguir para a tarefa'.
    Retorna (url_final, conteudo_texto) ou (None, None) se falhar.
    """
    print(f"  -> Abrindo atividade: {nome_atividade}")

    # Volta para /tarefas
    page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", wait_until="domcontentloaded")
    time.sleep(3)

    # Rola para carregar todos os cards
    for _ in range(2):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1)
    page.evaluate("window.scrollTo(0, 0)")
    time.sleep(1)

    # Clica no card pelo nome da atividade
    clicou = False
    try:
        card = page.get_by_text(nome_atividade, exact=True).first
        card.scroll_into_view_if_needed()
        time.sleep(0.5)
        card.click()
        clicou = True
        print(f"  -> Card clicado (texto exato)")
        time.sleep(2)
    except Exception as e:
        print(f"  -> Falhou texto exato: {e}")

    if not clicou:
        try:
            card = page.locator(f"text={nome_atividade}").first
            card.scroll_into_view_if_needed()
            time.sleep(0.5)
            card.click()
            clicou = True
            print(f"  -> Card clicado (texto parcial)")
            time.sleep(2)
        except Exception as e:
            print(f"  -> Falhou texto parcial: {e}")
            return None, None

    # Procura e clica em "Prosseguir para a tarefa"
    url_atividade = None
    conteudo = ""

    # Tenta variacoes do texto do botao
    textos_botao = ["Prosseguir para a tarefa", "Prosseguir", "Acessar tarefa", "Iniciar"]
    botao_clicado = False

    for texto in textos_botao:
        try:
            btn = page.get_by_role("button", name=texto)
            btn.wait_for(state="visible", timeout=5000)
            btn.click()
            botao_clicado = True
            print(f"  -> Botao '{texto}' clicado!")
            time.sleep(4)
            break
        except Exception:
            pass

    if not botao_clicado:
        # Tenta por get_by_text
        for texto in textos_botao:
            try:
                btn = page.get_by_text(texto).first
                btn.wait_for(state="visible", timeout=3000)
                btn.click()
                botao_clicado = True
                print(f"  -> Botao '{texto}' clicado via get_by_text!")
                time.sleep(4)
                break
            except Exception:
                pass

    if not botao_clicado:
        print(f"  -> Nenhum botao de prosseguir encontrado.")
        return None, None

    url_atividade = page.url
    conteudo = page.inner_text("body")[:4000]
    print(f"  -> URL final: {url_atividade}")

    return url_atividade, conteudo


def enviar_telegram(mensagem):
    """Envia mensagem via Telegram Bot API."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID nao configurado.")
        print(f"  Mensagem que seria enviada:\n{mensagem}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}, timeout=30)
    if resp.status_code == 200:
        print("  -> Telegram enviado!")
    else:
        print(f"  Erro ao enviar Telegram: {resp.status_code} - {resp.text}")


def main():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M")
    print(f"\n{'='*50}")
    print(f"  Verificacao iniciada: {agora}")
    print(f"{'='*50}")

    atividades_salvas = carregar_atividades_salvas()

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

            # Novas = atividades que ainda nao estao salvas
            novas = [a for a in atividades_atuais if a not in atividades_salvas]

            # Removidas = atividades salvas que sumiram da lista (entregues/expiradas)
            removidas = [a for a in atividades_salvas if a not in atividades_atuais]
            if removidas:
                print(f"  -> {len(removidas)} atividade(s) concluida(s)/removida(s): {removidas}")

            if novas:
                print(f"\n  {len(novas)} NOVA(S) ATIVIDADE(S):")

                # Mensagem resumo
                resumo = f"Sala do Futuro - {len(novas)} nova(s) atividade(s)!\n\n"
                for a in novas:
                    resumo += f"- {a}\n"
                resumo += f"\nTotal em aberto: {len(atividades_atuais)}"
                resumo += "\nhttps://saladofuturo.educacao.sp.gov.br/tarefas"
                enviar_telegram(resumo)

                # Entra em cada atividade nova e envia detalhes
                for nome in novas:
                    print(f"\n  -> Processando: {nome}")
                    url_atv, conteudo_atv = abrir_atividade(page, nome)

                    if url_atv and conteudo_atv:
                        # Filtra linhas com conteudo relevante
                        linhas_conteudo = [l.strip() for l in conteudo_atv.split("\n")
                                           if len(l.strip()) > 10]
                        trecho = "\n".join(linhas_conteudo[:35])

                        mensagem_detalhe = (
                            f"Atividade: {nome}\n\n"
                            f"Link: {url_atv}\n\n"
                            f"--- Conteudo ---\n{trecho[:1800]}"
                        )
                    else:
                        mensagem_detalhe = (
                            f"Atividade: {nome}\n\n"
                            f"Nao foi possivel abrir automaticamente.\n"
                            f"Acesse: https://saladofuturo.educacao.sp.gov.br/tarefas"
                        )

                    enviar_telegram(mensagem_detalhe)

            else:
                print("\n  Nenhuma atividade nova. Tudo em dia!")
                enviar_telegram(
                    f"Sala do Futuro - OK\n\n"
                    f"Nenhuma tarefa nova.\n"
                    f"Total em aberto: {len(atividades_atuais)}\n"
                    f"Horario: {agora}"
                )

            browser.close()

        # Salva apenas as atividades que ainda estao em aberto
        salvar_atividades(atividades_atuais)

    except Exception as erro:
        print(f"\n  Erro: {erro}")
        raise

    print(f"\n  Verificacao concluida: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
