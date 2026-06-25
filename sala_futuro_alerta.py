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

RA               = os.environ.get("RA",               "000110134488")
DIGITO           = os.environ.get("DIGITO",           "x")
SENHA            = os.environ.get("SENHA",            "mj13112008")
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

ARQUIVO_ATIVIDADES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "atividades_salvas.json")

# Linhas de navegacao para ignorar no conteudo
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
    palavras_ignorar = ["Entregar", " dia", "2025", "2026", "Tarefa SP",
                        "Home", "Status", "A Fazer", "Componente", "Turmas"]

    for i, linha in enumerate(linhas):
        if linha == "A Fazer" and i + 1 < len(linhas):
            nome = linhas[i + 1]
            print(f"  -> Candidato encontrado: '{nome}'")
            if nome and len(nome.strip()) > 3 and not any(p in nome for p in palavras_ignorar) and nome not in atividades:
                atividades.append(nome)

    print(f"  -> {len(atividades)} tarefa(s) em aberto: {atividades}")

    # Se nao achou nada, envia debug pelo Telegram
    if len(atividades) == 0:
        linhas_aFazer = [f"linha {i}: '{linhas[i]}' -> '{linhas[i+1] if i+1<len(linhas) else ''}'" 
                         for i, l in enumerate(linhas) if "fazer" in l.lower() or "tarefa" in l.lower()]
        debug_msg = f"DEBUG: 0 atividades encontradas.\nTotal linhas: {len(linhas)}\n\nLinhas com 'fazer'/'tarefa':\n"
        debug_msg += "\n".join(linhas_aFazer[:20]) or "(nenhuma)"
        debug_msg += "\n\nPrimeiras 30 linhas:\n" + "\n".join(linhas[:30])
        enviar_telegram(debug_msg)

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
    """Extrai apenas o conteudo da atividade, do titulo ate o rodape."""
    linhas = [l.strip() for l in texto_bruto.split("\n") if l.strip()]
    
    # Marcadores de fim do conteudo util
    fim_marcadores = ["voltar", "salvar rascunho", "finalizar", "ouvidoria",
                      "politica de privacidade", "0800-", "tentativas restantes"]
    
    # Encontra onde o conteudo da atividade comeca
    # Procura pelo nome da atividade ou por "Introducao" / primeira questao
    inicio = 0
    for i, linha in enumerate(linhas):
        linha_lower = linha.lower()
        # Inicio quando achar o nome da atividade ou disciplina (ex: "Matematica - 2700")
        if nome_atividade and nome_atividade.lower()[:20] in linha_lower:
            inicio = i
            break
        # Fallback: começa em "Introducao" ou "Questao 01"
        if "introdução" in linha_lower or "questão 01" in linha_lower or "questao 01" in linha_lower:
            inicio = i
            break
    
    # Extrai do inicio ate os marcadores de fim
    resultado = []
    for linha in linhas[inicio:]:
        linha_lower = linha.lower()
        if any(m in linha_lower for m in fim_marcadores):
            break
        # Ignora linhas muito curtas
        if len(linha) < 3:
            continue
        resultado.append(linha)
    
    return resultado


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
    """Envia conteudo longo dividido em mensagens de ate 3800 chars."""
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
                        titulo_msg = f"Atividade: {nome}\nLink: {url_atv}\n\n--- Conteudo ---"
                        enviar_telegram_longo(titulo_msg, linhas_filtradas)
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
