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
    print("  -> RA preenchido.")

    page.get_by_placeholder("0").first.click()
    page.get_by_placeholder("0").first.type(DIGITO)
    print("  -> Digito preenchido.")

    page.get_by_placeholder("Digite sua senha").click()
    page.get_by_placeholder("Digite sua senha").type(SENHA)
    print("  -> Senha preenchida.")
    time.sleep(1)

    page.get_by_role("button", name="Acessar").click()
    time.sleep(5)
    print("  -> Login realizado!")


def buscar_atividades(page):
    print("  -> Verificando tarefas...")
    page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", wait_until="domcontentloaded")
    time.sleep(5)

    corpo = page.inner_text("body")
    linhas = [l.strip() for l in corpo.split("\n") if l.strip()]

    atividades = []
    palavras_ignorar = ["Entregar", " dia", "2025", "2026", "Tarefa SP",
                        "Home", "Status", "A Fazer", "Componente", "Turmas"]

    for i, linha in enumerate(linhas):
        if linha == "A Fazer" and i + 1 < len(linhas):
            nome = linhas[i + 1]
            if nome and len(nome.strip()) > 3 and not any(p in nome for p in palavras_ignorar) and nome not in atividades:
                atividades.append(nome)

    print(f"  -> {len(atividades)} tarefa(s) em aberto.")
    return atividades


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
            browser.close()

        novas = [a for a in atividades_atuais if a not in atividades_salvas]

        if novas:
            print(f"\n  {len(novas)} NOVA(S) ATIVIDADE(S):")
            for a in novas:
                print(f"     - {a}")

            mensagem = "Sala do Futuro - Novas Atividades!\n\n"
            mensagem += f"Voce tem {len(novas)} nova(s) atividade(s):\n\n"
            for a in novas:
                mensagem += f"- {a}\n"
            mensagem += "\nhttps://saladofuturo.educacao.sp.gov.br/tarefas"

            enviar_telegram(mensagem)
        else:
            print("\n  Nenhuma atividade nova. Tudo em dia!")
            enviar_telegram(f"Sala do Futuro - OK\n\nNenhuma tarefa nova.\nTotal em aberto: {len(atividades_atuais)}\nHorario: {agora}")

        salvar_atividades(atividades_atuais)

    except Exception as erro:
        print(f"\n  Erro: {erro}")
        raise

    print(f"\n  Verificacao concluida: {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
