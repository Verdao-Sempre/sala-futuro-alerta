import os
import json
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright


def env_obrigatoria(nome: str) -> str:
    valor = os.environ.get(nome)
    if not valor:
        raise RuntimeError(f"Variavel obrigatoria ausente: {nome}")
    return valor


RA = env_obrigatoria("RA")
DIGITO = env_obrigatoria("DIGITO")
SENHA = env_obrigatoria("SENHA")
TELEGRAM_TOKEN = env_obrigatoria("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = env_obrigatoria("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
DEBUG_DOM = os.environ.get("DEBUG_DOM", "true").lower() == "true"
MOSTRAR_ALTERNATIVAS = os.environ.get("MOSTRAR_ALTERNATIVAS", "true").lower() == "true"
EXPLICAR_RACIOCINIO = os.environ.get("EXPLICAR_RACIOCINIO", "true").lower() == "true"
TELEGRAM_MAX_LENGTH = int(os.environ.get("TELEGRAM_MAX_LENGTH", "3800"))


def enviar_telegram(mensagem: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={"chat_id": TELEGRAM_CHAT_ID, "text": mensagem},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"Erro Telegram: {resp.status_code} - {resp.text[:500]}")


def enviar_telegram_longo(titulo: str, texto: str) -> None:
    bloco = titulo.strip() + "\n\n"
    for linha in texto.split("\n"):
        adicao = linha + "\n"
        if len(bloco) + len(adicao) > TELEGRAM_MAX_LENGTH:
            enviar_telegram(bloco)
            bloco = "(continuacao)\n\n" + adicao
        else:
            bloco += adicao
    if bloco.strip():
        enviar_telegram(bloco)


def fazer_login(page) -> None:
    print("  -> Abrindo login...")
    page.goto("https://saladofuturo.educacao.sp.gov.br/login-alunos", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)

    page.get_by_placeholder("Ex.: 186735683").click()
    page.get_by_placeholder("Ex.: 186735683").type(RA)
    page.get_by_placeholder("0").first.click()
    page.get_by_placeholder("0").first.type(DIGITO)
    page.get_by_placeholder("Digite sua senha").click()
    page.get_by_placeholder("Digite sua senha").type(SENHA)
    page.wait_for_timeout(1000)
    page.get_by_role("button", name="Acessar").click()
    page.wait_for_timeout(7000)

    if "login" in page.url.lower():
        raise RuntimeError("Login aparentemente falhou: ainda estou na pagina de login.")

    print(f"  -> Login ok: {page.url}")


def buscar_atividades(page):
    print("  -> Buscando atividades...")
    page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", wait_until="domcontentloaded")
    page.wait_for_timeout(6000)

    for _ in range(3):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    linhas = [l.strip() for l in page.inner_text("body").split("\n") if l.strip()]
    status_aberto = {
        "A Fazer", "Rascunho", "Em andamento", "Em Andamento",
        "Em progresso", "Em Progresso", "Iniciado", "Iniciada"
    }
    ignorar = [
        "Entregar", " dia", "2025", "2026", "Tarefa SP", "Home", "Status",
        "A Fazer", "Rascunho", "Componente", "Turmas", "Em andamento", "Em progresso"
    ]

    atividades = []
    for i, linha in enumerate(linhas):
        if linha in status_aberto:
            for j in range(i + 1, min(i + 5, len(linhas))):
                nome = linhas[j].strip()
                if nome and len(nome) > 5 and not nome.isdigit() and not any(p in nome for p in ignorar):
                    if nome not in atividades:
                        atividades.append(nome)
                    break

    print(f"  -> Atividades encontradas: {atividades}")
    return atividades


def abrir_atividade(page, nome_atividade: str) -> str:
    print(f"  -> Abrindo atividade: {nome_atividade}")
    page.goto("https://saladofuturo.educacao.sp.gov.br/tarefas", wait_until="domcontentloaded")
    page.wait_for_timeout(4000)

    for _ in range(2):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(1000)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1000)

    clicou = False
    for seletor_exato in [True, False]:
        try:
            alvo = page.get_by_text(nome_atividade, exact=seletor_exato).first
            alvo.scroll_into_view_if_needed()
            alvo.click()
            clicou = True
            break
        except Exception:
            pass

    if not clicou:
        alvo = page.locator(f"text={nome_atividade}").first
        alvo.scroll_into_view_if_needed()
        alvo.click()

    page.wait_for_timeout(2500)

    for texto in ["Prosseguir para a tarefa", "Prosseguir", "Acessar tarefa", "Iniciar"]:
        try:
            btn = page.get_by_role("button", name=texto)
            btn.wait_for(state="visible", timeout=4000)
            btn.click()
            page.wait_for_timeout(5000)
            print(f"  -> Botao '{texto}' clicado")
            return page.url
        except Exception:
            try:
                btn = page.get_by_text(texto).first
                btn.wait_for(state="visible", timeout=2500)
                btn.click()
                page.wait_for_timeout(5000)
                print(f"  -> Botao '{texto}' clicado via texto")
                return page.url
            except Exception:
                pass

    print("  -> Nao encontrei botao de prosseguir; usando pagina atual")
    return page.url


def extrair_questoes_estruturadas(page):
    print("  -> Extraindo questoes estruturadas...")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(1500)

    return page.evaluate(r'''
    () => {
        const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
        const vis = (el) => {
            const r = el.getBoundingClientRect();
            const st = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden';
        };
        const textOf = (el) => norm(el.innerText || el.textContent || '');
        const all = Array.from(document.querySelectorAll('body *')).filter(vis);
        const bodyText = textOf(document.body);

        const headers = all.map(el => ({el, txt: textOf(el), rect: el.getBoundingClientRect()}))
            .filter(x => /^Quest[aã]o\s+\d+\s+de\s+\d+/i.test(x.txt) && x.txt.length <= 90)
            .sort((a, b) => a.rect.top - b.rect.top);

        if (!headers.length) {
            return [{numero: 1, tipo: 'texto_extraido', texto: bodyText.slice(0, 8000), controles: []}];
        }

        function labelFor(el) {
            const aria = el.getAttribute('aria-label');
            if (aria) return norm(aria);
            if (el.id) {
                const label = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
                if (label) return textOf(label);
            }
            const label = el.closest('label');
            if (label) return textOf(label);
            const parent = el.closest('[role="radio"], [role="checkbox"], li, .MuiFormControlLabel-root, div');
            return parent ? textOf(parent) : '';
        }

        const resultado = [];
        for (let i = 0; i < headers.length; i++) {
            const y1 = headers[i].rect.top;
            const y2 = i + 1 < headers.length ? headers[i + 1].rect.top : Infinity;
            const m = headers[i].txt.match(/(\d+)/);
            const numero = m ? Number(m[1]) : i + 1;

            const linhas = [];
            all.map(el => ({txt: textOf(el), rect: el.getBoundingClientRect()}))
                .filter(x => x.txt && x.rect.top >= y1 && x.rect.top < y2 && x.txt.length < 2500)
                .forEach(x => {
                    x.txt.split('\n').map(norm).filter(Boolean).forEach(l => {
                        if (!linhas.includes(l) && !/^\*?\s*10\s+PONTOS$/i.test(l) && !/^Tentativas restantes/i.test(l)) {
                            linhas.push(l);
                        }
                    });
                });

            const controles = Array.from(document.querySelectorAll('input, textarea, select, [role="combobox"], [role="radio"], [role="checkbox"]'))
                .filter(vis)
                .map((el, idx) => ({el, idx, rect: el.getBoundingClientRect()}))
                .filter(x => x.rect.top >= y1 && x.rect.top < y2)
                .map(x => {
                    const el = x.el;
                    let tipo = el.getAttribute('role') || el.getAttribute('type') || el.tagName.toLowerCase();
                    let opcoes = [];
                    if (el.tagName.toLowerCase() === 'select') {
                        opcoes = Array.from(el.options).map(o => norm(o.textContent)).filter(Boolean);
                    }
                    return {index_dom: x.idx, tipo, nome: labelFor(el), valor: el.value || '', checked: !!el.checked, opcoes};
                });

            const tipos = new Set(controles.map(c => c.tipo));
            let tipoQuestao = 'dissertativa';
            if (tipos.has('checkbox')) tipoQuestao = 'multipla_escolha';
            else if (tipos.has('radio')) {
                const nomes = controles.map(c => (c.nome || '').toLowerCase()).join(' | ');
                tipoQuestao = (nomes.includes('certo') && nomes.includes('errado')) ? 'certo_errado' : 'unica_escolha';
            }
            else if (tipos.has('select') || tipos.has('combobox')) tipoQuestao = 'dropdown_inline';
            else if (tipos.has('textarea') || tipos.has('text')) tipoQuestao = 'dissertativa';

            resultado.push({numero, tipo: tipoQuestao, texto: linhas.join('\n'), controles});
        }
        return resultado;
    }
    ''')


def coletar_opcoes_dropdowns(page):
    opcoes_por_dropdown = []
    loc = page.locator('[role="combobox"], [aria-haspopup="listbox"], select')
    total = loc.count()

    for i in range(total):
        try:
            item = loc.nth(i)
            item.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            tag = item.evaluate("el => el.tagName.toLowerCase()")

            if tag == "select":
                opcoes = item.evaluate("el => Array.from(el.options).map(o => (o.innerText || o.textContent || '').trim()).filter(Boolean)")
                opcoes_por_dropdown.append(opcoes)
                continue

            item.click()
            page.wait_for_timeout(800)
            opcoes = page.evaluate(r'''
            () => {
                const seletores = ['[role="option"]', '.MuiMenuItem-root', 'li[data-value]', '[class*="MenuItem"]', '[class*="option"]', 'li'];
                for (const sel of seletores) {
                    const els = Array.from(document.querySelectorAll(sel)).filter(e => {
                        const r = e.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                    });
                    const textos = els.map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean);
                    if (textos.length) return [...new Set(textos)];
                }
                return [];
            }
            ''')
            opcoes_por_dropdown.append(opcoes)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
        except Exception as e:
            print(f"  -> Erro dropdown {i + 1}: {e}")
            opcoes_por_dropdown.append([])
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

    return opcoes_por_dropdown


def anexar_opcoes_dropdowns(questoes, opcoes_por_dropdown):
    idx = 0
    for q in questoes:
        for c in q.get("controles", []):
            if c.get("tipo") in ("combobox", "select"):
                if idx < len(opcoes_por_dropdown):
                    c["opcoes"] = opcoes_por_dropdown[idx]
                idx += 1
    return questoes


def chamar_groq(prompt: str) -> str:
    if not GROQ_API_KEY:
        return "GROQ_API_KEY nao configurada. A extracao foi feita, mas nao foi possivel gerar orientacao com IA."

    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={
            "model": "llama-3.1-8b-instant",
            "temperature": 0.2,
            "max_tokens": 2600,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )

    if resp.status_code != 200:
        return f"Erro Groq {resp.status_code}: {resp.text[:500]}"

    return resp.json()["choices"][0]["message"]["content"].strip()


def montar_resumo_extraido(questoes) -> str:
    linhas = []
    for q in questoes:
        linhas.append(f"Q{q.get('numero')} - tipo detectado: {q.get('tipo')}")
        texto = q.get("texto", "")
        if texto:
            linhas.append(texto[:1200])
        if MOSTRAR_ALTERNATIVAS:
            controles = q.get("controles", [])
            for c in controles[:20]:
                nome = c.get("nome") or "controle sem rotulo claro"
                tipo = c.get("tipo")
                opcoes = c.get("opcoes") or []
                linhas.append(f"- controle: {tipo} | {nome[:300]}")
                if opcoes:
                    linhas.append(f"  opcoes: {opcoes}")
        linhas.append("")
    return "\n".join(linhas)


def gerar_orientacao_tutor(nome_atividade: str, questoes) -> str:
    modo = "com raciocinio" if EXPLICAR_RACIOCINIO else "objetivo"
    prompt = f"""
Voce e um tutor de estudos. Analise as questoes extraidas de uma atividade escolar.

Regras obrigatorias:
- Nao forneca gabarito direto.
- Nao diga quais alternativas marcar.
- Nao escreva resposta final pronta para copiar.
- Explique os conceitos e o metodo de resolucao.
- Mostre criterios para o aluno conferir cada alternativa.
- Para questao dissertativa, entregue um roteiro de resposta, nao um texto final.
- Para dropdown/lacunas, explique como decidir o termo correto, sem listar a sequencia final pronta.
- Para certo/errado, explique os sinais para julgar as afirmacoes, sem classificar cada item como final.

Modo: {modo}
Atividade: {nome_atividade}

Questoes extraidas em JSON:
{json.dumps(questoes, ensure_ascii=False, indent=2)[:9000]}
"""
    return chamar_groq(prompt)


def main():
    print("=" * 60)
    print(f"Tutor avancado iniciado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print("=" * 60)

    is_cloud = os.environ.get("GITHUB_ACTIONS") == "true"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=is_cloud,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"] if is_cloud else [],
        )
        page = browser.new_page()

        fazer_login(page)
        atividades = buscar_atividades(page)

        if not atividades:
            enviar_telegram("Sala do Futuro - Tutor Avancado\n\nNenhuma atividade aberta encontrada.")
            browser.close()
            return

        for nome in atividades:
            try:
                url = abrir_atividade(page, nome)
                questoes = extrair_questoes_estruturadas(page)
                opcoes = coletar_opcoes_dropdowns(page)
                questoes = anexar_opcoes_dropdowns(questoes, opcoes)

                if DEBUG_DOM:
                    resumo = montar_resumo_extraido(questoes)
                    enviar_telegram_longo(
                        f"Extracao detectada\nAtividade: {nome}\nLink: {url}",
                        resumo,
                    )

                orientacao = gerar_orientacao_tutor(nome, questoes)
                enviar_telegram_longo(
                    f"Tutor Avancado - Guia de resolucao\nAtividade: {nome}\nLink: {url}",
                    orientacao,
                )
            except Exception as e:
                enviar_telegram(f"Erro ao analisar atividade '{nome}': {e}")
                print(f"Erro atividade {nome}: {e}")

        browser.close()

    print("Tutor avancado concluido.")


if __name__ == "__main__":
    main()
