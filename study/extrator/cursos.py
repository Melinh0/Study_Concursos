from __future__ import annotations

import json
import re
import time
import urllib.parse
from difflib import SequenceMatcher

from selenium.common.exceptions import WebDriverException

from . import api, navegador

URL_BUSCA = "https://app.qconcursos.com/b/guia-de-estudos/busca/todos"

JS_CARTOES = r"""
return Array.from(document.querySelectorAll('#studyGuidesList > div[data-objectid]'))
    .map(function (cartao, i) {
        return {indice: i, nome: (cartao.innerText || '').trim().replace(/\s+/g, ' ')};
    });
"""

JS_CLIQUE = r"""
const cartoes = document.querySelectorAll('#studyGuidesList > div[data-objectid]');
const alvo = cartoes[arguments[0]];
if (!alvo) return '';
const botoes = alvo.querySelectorAll('button');
const botao = botoes[botoes.length - 1];
if (!botao) return '';
botao.scrollIntoView({block: 'center'});
['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(function (tipo) {
    botao.dispatchEvent(new MouseEvent(tipo, {bubbles: true, cancelable: true, view: window}));
});
return (alvo.innerText || '').trim().replace(/\s+/g, ' ');
"""


def pontuar(termo: str, nome: str) -> float:
    alvo = api.normalizar(termo)
    texto = api.normalizar(nome)
    if not texto:
        return 0.0
    if alvo == texto:
        return 100.0
    if alvo and alvo in texto:
        return 70.0 + 30.0 * (len(alvo) / max(len(texto), 1))
    tokens_alvo = set(alvo.split())
    tokens_texto = set(texto.split())
    sobreposicao = len(tokens_alvo & tokens_texto) / max(len(tokens_alvo), 1)
    return 55.0 * SequenceMatcher(None, alvo, texto).ratio() + 45.0 * sobreposicao


def _id_do_fonte(fonte: str, chave: str) -> str:
    achado = re.search(re.escape(chave) + r"[^0-9]{0,8}(\d+)", fonte)
    return achado.group(1) if achado else ""


def buscar_curso(
    termo: str,
    perfil: str | None = None,
    visivel: bool = False,
    ao_logar=None,
    descobrir: bool = True,
) -> dict | None:
    url = f"{URL_BUSCA}?q={urllib.parse.quote(termo)}"
    driver = navegador.criar_driver(perfil, visivel)
    try:
        if not navegador.ir_para(driver, url, ao_atualizar=None):
            return None
        if not navegador.aguardar(driver, "#studyGuidesList > div[data-objectid]", 30):
            if ao_logar:
                ao_logar("Lista de cursos não carregou a tempo.", "aviso")
            return None
        cartoes = driver.execute_script(JS_CARTOES) or []
        if not cartoes:
            if ao_logar:
                ao_logar("Nenhum curso encontrado na busca.", "aviso")
            return None
        melhor = max(cartoes, key=lambda cartao: pontuar(termo, cartao["nome"]))
        if pontuar(termo, melhor["nome"]) < 45:
            if ao_logar:
                ao_logar(f"Melhor correspondência com pontuação baixa: {melhor['nome']}", "aviso")
            return None
        if ao_logar:
            ao_logar(f"Curso selecionado: {melhor['nome']}")
        driver.execute_script(JS_CLIQUE, melhor["indice"])
        guid = ""
        ultimo_clique = time.time()
        limite = time.time() + 45
        while time.time() < limite:
            atual = driver.current_url
            achado = re.search(r"guia-de-estudos/(\d+)", atual)
            if achado and "busca" not in atual:
                guid = achado.group(1)
                break
            if time.time() - ultimo_clique > 12:
                try:
                    driver.execute_script(JS_CLIQUE, melhor["indice"])
                except WebDriverException:
                    pass
                ultimo_clique = time.time()
            time.sleep(1)
        if not guid:
            if ao_logar:
                ao_logar("Não foi possível obter o ID do guia de estudos.", "aviso")
            return None
        nome = melhor["nome"]
        sessao = driver.execute_script(
            "return window.__userSession"
            " ? JSON.stringify(window.__userSession.studyGuide || null) : 'null';"
        )
        try:
            dados_sessao = json.loads(sessao or "null")
        except ValueError:
            dados_sessao = None
        if isinstance(dados_sessao, dict) and dados_sessao.get("name"):
            nome = dados_sessao["name"]
        ano = navegador.descobrir_ano_prova(driver)
        if ano and ao_logar:
            ao_logar(f"Ano da prova identificado: {ano}")
        fonte = driver.page_source
        instituicao = api.por_id("instituicao", _id_do_fonte(fonte, "old_institute_id"))
        banca = api.por_id("banca", _id_do_fonte(fonte, "old_examining_board_id"))
        cargo = api.por_id("cargo", _id_do_fonte(fonte, "old_job_id"))
        partes = [p.strip() for p in nome.split(" - ") if p.strip()]
        if instituicao is None and partes:
            instituicao = api.resolver(partes[0], "instituicao")
        if cargo is None and len(partes) > 1:
            cargo = api.resolver(partes[1], "cargo")
        url_guia = f"https://app.qconcursos.com/b/guia-de-estudos/{guid}/videoaulas/questoes"
        disciplinas: list[str] = []
        if descobrir:
            if ao_logar:
                ao_logar("Acessando o guia de estudos para listar disciplinas…")
            try:
                if navegador.ir_para(driver, url_guia, ao_atualizar=None):
                    time.sleep(4)
                    if not ano:
                        ano = navegador.descobrir_ano_prova(driver)
                    disciplinas = navegador.descobrir_disciplinas(driver)
                    if ao_logar:
                        if disciplinas:
                            ao_logar(f"Disciplinas encontradas ({len(disciplinas)}): {', '.join(disciplinas)}")
                        else:
                            ao_logar("Nenhuma disciplina listada no guia (pode ser estrutura diferente).", "aviso")
            except Exception as erro:
                if ao_logar:
                    ao_logar(f"Erro ao descobrir disciplinas: {erro}", "aviso")
                disciplinas = []
        return {
            "id": guid,
            "nome": nome,
            "url_guia": url_guia,
            "instituicao": instituicao,
            "banca": banca,
            "cargo": cargo,
            "disciplinas": disciplinas,
            "ano": ano,
        }
    finally:
        navegador.fechar(driver)


def listar_assuntos(
    url_guia: str,
    disciplina: str,
    perfil: str | None = None,
    visivel: bool = False,
    ao_logar=None,
) -> list[str]:
    driver = navegador.criar_driver(perfil, visivel)
    try:
        if not navegador.ir_para(driver, url_guia, ao_atualizar=None):
            return []
        time.sleep(4)
        if ao_logar:
            ao_logar(f"Listando os assuntos de {disciplina}…")
        assuntos = navegador.descobrir_assuntos(driver, disciplina)
        if ao_logar:
            if assuntos:
                ao_logar(f"Assuntos encontrados ({len(assuntos)}): {', '.join(assuntos[:10])}{'...' if len(assuntos) > 10 else ''}")
            else:
                ao_logar(f"Nenhum assunto listado para '{disciplina}' — extraindo a disciplina inteira.", "aviso")
        return assuntos
    except Exception as erro:
        if ao_logar:
            ao_logar(f"Erro ao listar assuntos: {erro}", "aviso")
        return []
    finally:
        navegador.fechar(driver)
