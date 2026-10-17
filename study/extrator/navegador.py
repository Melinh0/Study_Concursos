from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as condicao
from selenium.webdriver.support.ui import WebDriverWait

RAIZ = Path(__file__).resolve().parent.parent.parent
PERFIL_PADRAO = RAIZ / "perfil_navegador"

SELECIONADORES = {
    "item": ".js-question-item",
    "codigo": ".q-id a",
    "enunciado": ".q-question-enunciation",
    "alternativas": "input.js-question-answer",
    "gabarito": ".js-question-right-answer",
    "botao_responder": "button.js-answer-btn",
    "aba_comentado": 'a[href*="-teacher-tab"]',
    "conteudo_comentado": ".js-content",
    "modal_login": "#js-login-register-modal",
    "link_entrar": 'a[href="/conta/entrar"]',
    "menu_usuario": ".q-user-menu--desktop",
}

TITULOS_DESAFIO = ("um momento", "just a moment", "checking your browser", "attention required")

STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
if (!window.chrome) { window.chrome = {runtime: {}, app: {isInstalled: false}}; }
const permQuery = navigator.permissions.query.bind(navigator.permissions);
navigator.permissions.query = (p) => (p && p.name === 'notifications'
  ? Promise.resolve({state: Notification.permission})
  : permQuery(p));
"""

CANDIDATOS_CHROME = {
    "linux": [
        "/opt/google/chrome/chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/microsoft-edge",
    ],
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
}

CANDIDATOS_DRIVER = [
    os.environ.get("CHROMEDRIVER", ""),
    str(Path.home() / ".local" / "bin" / "chromedriver"),
    str(RAIZ / "chromedriver"),
]

PLATAFORMAS_CFT = {
    "linux": "linux64",
    "win32": "win64",
    "darwin": ("mac-arm64" if platform.machine().lower() in ("arm64", "aarch64") else "mac-x64"),
}


class LoginNecessario(Exception):
    pass


class LimiteAtingido(Exception):
    pass


def _eh_binario(caminho: str) -> bool:
    try:
        with open(caminho, "rb") as arquivo:
            cabecalho = arquivo.read(4)
    except OSError:
        return False
    if sys.platform.startswith("win"):
        return cabecalho[:2] == b"MZ"
    return cabecalho == b"\x7fELF"


def localizar_chrome() -> str | None:
    for candidato in CANDIDATOS_CHROME.get(sys.platform, CANDIDATOS_CHROME["linux"]):
        if os.path.exists(candidato) and _eh_binario(candidato):
            return candidato
    for nome in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        caminho = shutil.which(nome)
        if caminho and _eh_binario(caminho):
            return caminho
    return None


def _versao_chrome(binario: str | None) -> str:
    if not binario:
        return ""
    try:
        saida = subprocess.run(
            [binario, "--version"], capture_output=True, text=True, timeout=15
        ).stdout
        achado = re.search(r"(\d+)\.(\d+)\.(\d+)\.(\d+)", saida)
        return achado.group(0) if achado else ""
    except Exception:
        return ""


def _url_chromedriver(versao_chrome: str) -> str | None:
    plataforma = PLATAFORMAS_CFT.get(sys.platform, "linux64")
    raiz = "https://storage.googleapis.com/chrome-for-testing-public"

    if versao_chrome:
        url = f"{raiz}/{versao_chrome}/{plataforma}/chromedriver-{plataforma}.zip"
        try:
            with urllib.request.urlopen(url, timeout=10) as resposta:
                if resposta.status == 200:
                    return url
        except Exception:
            pass

    try:
        endereco = (
            "https://googlechromelabs.github.io/chrome-for-testing/"
            "last-known-good-versions-with-downloads.json"
        )
        with urllib.request.urlopen(endereco, timeout=15) as resposta:
            dados = json.load(resposta)
        estavel = dados["channels"]["Stable"]
        baixados = [
            item["url"]
            for item in estavel["downloads"].get("chromedriver", [])
            if item["platform"] == plataforma
        ]
        return baixados[0] if baixados else None
    except Exception:
        return None


def _baixar_chromedriver(destino: Path, binario_chrome: str | None) -> Path | None:
    url = _url_chromedriver(_versao_chrome(binario_chrome))
    if not url:
        return None
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        arquivo = destino.with_suffix(".zip")
        urllib.request.urlretrieve(url, arquivo)
        with zipfile.ZipFile(arquivo) as pacote:
            nome = next(n for n in pacote.namelist() if n.endswith("chromedriver"))
            with pacote.open(nome) as origem, open(destino, "wb") as alvo:
                alvo.write(origem.read())
        arquivo.unlink(missing_ok=True)
        destino.chmod(0o755)
        return destino
    except Exception:
        return None


def _servico_chromedriver(binario_chrome: str | None) -> Service | None:
    for caminho in CANDIDATOS_DRIVER:
        if caminho and os.path.isfile(caminho) and os.access(caminho, os.X_OK):
            return Service(caminho)

    baixado = _baixar_chromedriver(Path.home() / ".local" / "bin" / "chromedriver", binario_chrome)
    if baixado:
        return Service(str(baixado))

    caminho = shutil.which("chromedriver")
    if caminho and _eh_binario(caminho):
        return Service(caminho)
    return None


def criar_driver(
    perfil: str | Path | None = None,
    visivel: bool = True,
    tamanho: tuple[int, int] = (1440, 1000),
    temporario: bool = False,
) -> webdriver.Chrome:
    if temporario or not visivel:
        pasta_perfil = Path(tempfile.mkdtemp(prefix="perfil_qc_"))
    else:
        pasta_perfil = Path(perfil) if perfil else PERFIL_PADRAO
        pasta_perfil.mkdir(parents=True, exist_ok=True)

    opcoes = Options()
    opcoes.add_argument(f"--user-data-dir={pasta_perfil.resolve()}")
    opcoes.add_argument("--lang=pt-BR")
    opcoes.add_argument(f"--window-size={tamanho[0]},{tamanho[1]}")
    opcoes.add_argument("--disable-notifications")
    opcoes.add_argument("--disable-popup-blocking")
    opcoes.add_argument("--no-first-run")
    opcoes.add_argument("--no-default-browser-check")
    opcoes.add_argument("--disable-blink-features=AutomationControlled")
    opcoes.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    opcoes.add_experimental_option("useAutomationExtension", False)
    opcoes.page_load_strategy = "eager"
    if not visivel:
        opcoes.add_argument("--headless=new")
        opcoes.add_argument("--disable-gpu")
        opcoes.add_argument("--no-sandbox")
        opcoes.add_argument("--disable-dev-shm-usage")
        opcoes.add_argument("--disable-extensions")
        opcoes.add_argument("--disable-software-rasterizer")
        opcoes.add_argument("--remote-debugging-port=0")
        opcoes.add_argument("--disable-features=VizDisplayCompositor")
        opcoes.add_argument("--disable-background-timer-throttling")
        opcoes.add_argument("--disable-backgrounding-occluded-windows")
        opcoes.add_argument("--disable-renderer-backgrounding")
        opcoes.add_argument("--disable-ipc-flooding-protection")
        opcoes.add_argument("--disable-background-networking")
        opcoes.add_argument("--disable-default-apps")
        opcoes.add_argument("--disable-sync")
        opcoes.add_argument("--metrics-recording-only")
        opcoes.add_argument("--no-report-upload")
        opcoes.add_argument("--disable-crash-reporter")
        opcoes.add_argument("--disable-breakpad")

    binario = localizar_chrome()
    if binario:
        opcoes.binary_location = binario

    ultimo_erro: Exception | None = None
    for servico in (_servico_chromedriver(binario), None):
        try:
            driver = (
                webdriver.Chrome(options=opcoes)
                if servico is None
                else webdriver.Chrome(service=servico, options=opcoes)
            )
            driver.set_page_load_timeout(70)
            try:
                driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {"source": STEALTH_JS},
                )
                user_agent = driver.execute_script("return navigator.userAgent") or ""
                if "HeadlessChrome" in user_agent:
                    driver.execute_cdp_cmd(
                        "Network.setUserAgentOverride",
                        {
                            "userAgent": user_agent.replace("HeadlessChrome", "Chrome"),
                            "acceptLanguage": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
                            "platform": "Win32",
                        },
                    )
            except WebDriverException:
                pass
            return driver
        except Exception as erro:
            ultimo_erro = erro
    raise RuntimeError(
        "Não foi possível iniciar o Chrome. Instale o Google Chrome/Chromium "
        f"ou o chromedriver. Detalhe: {ultimo_erro}"
    )


def fechar(driver) -> None:
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass


def aguardar_desafio(driver, timeout: float = 60.0, ao_atualizar=None) -> bool:
    limite = time.time() + timeout
    while time.time() < limite:
        try:
            titulo = (driver.title or "").lower()
        except WebDriverException:
            titulo = ""
        if not any(pista in titulo for pista in TITULOS_DESAFIO):
            return True
        if ao_atualizar:
            ao_atualizar("Aguardando o site liberar o acesso…")
        time.sleep(1)
    return False


def aguardar(driver, seletor: str, timeout: float = 20.0):
    try:
        return WebDriverWait(driver, timeout).until(
            condicao.presence_of_element_located((By.CSS_SELECTOR, seletor))
        )
    except Exception:
        return None


def elemento(driver, seletor: str, timeout: float = 0):
    if timeout:
        return aguardar(driver, seletor, timeout)
    try:
        return driver.find_element(By.CSS_SELECTOR, seletor)
    except Exception:
        return None


def clicar_js(driver, alvo) -> bool:
    try:
        driver.execute_script("arguments[0].click();", alvo)
        return True
    except Exception:
        try:
            alvo.click()
            return True
        except Exception:
            return False


def modal_login_visivel(driver) -> bool:
    try:
        modal = driver.find_element(By.CSS_SELECTOR, SELECIONADORES["modal_login"])
        return bool(modal.is_displayed())
    except Exception:
        return False


def limite_atingido(driver) -> bool:
    try:
        return bool(
            driver.execute_script(
                """
                const m = document.querySelector('#js-account-limit-questions-modal');
                return !!(m && m.offsetParent !== null);
                """
            )
        )
    except Exception:
        return False


def ir_para(driver, url: str, ao_atualizar=None, timeout_desafio: float = 60.0) -> bool:
    driver.get(url)
    return aguardar_desafio(driver, timeout_desafio, ao_atualizar)


JS_CABECALHOS = r"""
const incluirAninhados = arguments[0];
const seletor = 'h2 > button[aria-expanded], h3 > button[aria-expanded], h4 > button[aria-expanded], h5 > button[aria-expanded], h6 > button[aria-expanded]';
const lista = [];
for (const b of document.querySelectorAll(seletor)) {
    if (b.closest('[role="region"]') && !incluirAninhados) continue;
    const nome = (b.innerText || '').trim().replace(/\s+/g, ' ');
    if (nome && nome.length < 150 && !lista.includes(nome)) lista.push(nome);
}
return lista;
"""

JS_DISCIPLINA_ABERTA = r"""
function norm(s) {
    return (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}
const alvo = norm(arguments[0]);
const seletor = 'h2 > button[aria-expanded], h3 > button[aria-expanded], h4 > button[aria-expanded], h5 > button[aria-expanded]';
for (const b of document.querySelectorAll(seletor)) {
    if (b.closest('[role="region"]')) continue;
    if (norm(b.innerText) !== alvo) continue;
    if (b.getAttribute('aria-expanded') === 'false') {
        b.scrollIntoView({block: 'center'});
        b.click();
        return 'abriu';
    }
    return 'aberto';
}
return 'nao_achou';
"""

JS_ASSUNTOS = r"""
function norm(s) {
    return (s || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}
const alvo = norm(arguments[0]);
const seletor = 'h2 > button[aria-expanded], h3 > button[aria-expanded], h4 > button[aria-expanded], h5 > button[aria-expanded], h6 > button[aria-expanded]';
let regiao = null;
for (const b of document.querySelectorAll(seletor)) {
    if (b.closest('[role="region"]')) continue;
    if (norm(b.innerText) !== alvo) continue;
    const controle = b.getAttribute('aria-controls');
    regiao = controle ? document.getElementById(controle) : null;
    if (!regiao) {
        const cabecalho = b.parentElement;
        regiao = cabecalho && cabecalho.parentElement ? cabecalho.parentElement.querySelector('[role="region"]') : null;
    }
    break;
}
const diretos = [];
const todos = [];
if (regiao) {
    for (const b of regiao.querySelectorAll(seletor)) {
        const nome = (b.innerText || '').trim().replace(/\s+/g, ' ');
        if (!nome || nome.length >= 150) continue;
        if (b.closest('[role="region"]') === regiao && !diretos.includes(nome)) diretos.push(nome);
        if (!todos.includes(nome)) todos.push(nome);
    }
}
return {diretos: diretos, todos: todos};
"""

JS_CARREGAR_MAIS = r"""
const botoes = Array.from(document.querySelectorAll('button, a'));
let count = 0;
for (const b of botoes) {
    const t = (b.innerText || '').trim().toLowerCase();
    if (t && (t.includes('carregar mais') || t.includes('ver mais') || t.includes('mostrar mais')
        || t.includes('load more') || t.includes('show more') || t.includes('veja mais')
        || t.includes('mais disciplinas') || t.includes('mais assuntos'))) {
        try {
            b.scrollIntoView({block: 'center'});
            b.click();
            count++;
        } catch (e) {}
    }
}
return count;
"""

JS_EXPANDIR_TODOS = r"""
const botoes = Array.from(document.querySelectorAll('button[aria-expanded="false"]'));
let count = 0;
for (const b of botoes) {
    try {
        b.scrollIntoView({block: 'center', behavior: 'instant'});
        b.click();
        count++;
    } catch (e) {}
}
return count;
"""


JS_ANO_ABERTURA = r"""
const texto = (document.body && document.body.innerText || '').replace(/\s+/g, ' ');
const achado = texto.match(/Aberto em\s*(\d{1,2})\/(\d{1,2})\/(\d{4})/i);
return achado ? achado[3] : '';
"""


def _extrair_ano(texto: str) -> str:
    achado = re.search(r"\b(?:19|20)\d{2}\b", texto or "")
    return achado.group(0) if achado else ""


def descobrir_ano_prova(driver) -> str:
    try:
        fonte = driver.page_source or ""
    except WebDriverException:
        fonte = ""
    prova = re.search(r'\\"exam\\",\{\\"_\d+\\":\d+\},\\"([^"\\]+)\\"', fonte)
    if prova:
        ano = _extrair_ano(prova.group(1))
        if ano:
            return ano
    try:
        abertura = driver.execute_script(JS_ANO_ABERTURA) or ""
    except WebDriverException:
        abertura = ""
    return _extrair_ano(abertura)


def _rolar_pagina(driver) -> None:
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1.5)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5)


def _expandir_acordeons(driver) -> int:
    expandidos = driver.execute_script(JS_EXPANDIR_TODOS) or 0
    if expandidos:
        time.sleep(2.0)
    return expandidos


def descobrir_disciplinas(driver) -> list[str]:
    for _ in range(3):
        _rolar_pagina(driver)
        if driver.execute_script(JS_CARREGAR_MAIS) or 0:
            time.sleep(2.5)
    disciplinas = driver.execute_script(JS_CABECALHOS, False) or []
    if not disciplinas:
        for _ in range(3):
            _expandir_acordeons(driver)
            _rolar_pagina(driver)
        disciplinas = driver.execute_script(JS_CABECALHOS, False) or []
    if not disciplinas:
        disciplinas = driver.execute_script(JS_CABECALHOS, True) or []
    return [nome for nome in disciplinas if len(nome) <= 150]


def descobrir_assuntos(driver, disciplina: str) -> list[str]:
    estado = driver.execute_script(JS_DISCIPLINA_ABERTA, disciplina)
    if estado == "nao_achou":
        return []
    if estado == "abriu":
        time.sleep(3.0)
    dados = driver.execute_script(JS_ASSUNTOS, disciplina) or {}
    nomes = dados.get("diretos") or dados.get("todos") or []
    if not nomes:
        for _ in range(2):
            _expandir_acordeons(driver)
            time.sleep(1.0)
        dados = driver.execute_script(JS_ASSUNTOS, disciplina) or {}
        nomes = dados.get("diretos") or dados.get("todos") or []
    return list(nomes)
