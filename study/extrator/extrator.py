from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from selenium.common.exceptions import WebDriverException

from ..dados import normalizar_questao
from . import api, navegador
from .navegador import LimiteAtingido, LoginNecessario

JS_LER_ITENS = r"""
const itens = [];
const limpar = (texto) => (texto || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();
document.querySelectorAll('.js-question-item').forEach(function (item) {
  const caixa = item.querySelector('.js-question');
  if (!caixa) return;
  const link = item.querySelector('.q-id a');
  const info = {};
  item.querySelectorAll('.q-question-info > span').forEach(function (sp) {
    const forte = sp.querySelector('strong');
    if (!forte) return;
    const rotulo = forte.textContent.replace(/\s*:\s*$/, '').trim().toLowerCase();
    const copia = sp.cloneNode(true);
    const marca = copia.querySelector('strong');
    if (marca && marca.parentNode) marca.parentNode.removeChild(marca);
    info[rotulo] = limpar(copia.textContent.replace(/\s*\|/g, ' '));
  });
  const migalha = [];
  item.querySelectorAll('.q-question-breadcrumb a').forEach(function (a) {
    const texto = limpar(a.textContent);
    if (texto) migalha.push(texto);
  });
  const imagens = [];
  const coletarImagens = function (raiz) {
    if (!raiz) return;
    raiz.querySelectorAll('img').forEach(function (img) {
      const src = img.getAttribute('src') || img.getAttribute('data-src') || '';
      if (src && imagens.indexOf(src) === -1) imagens.push(src);
    });
  };
  const enunciado = item.querySelector('.q-question-enunciation');
  coletarImagens(enunciado);
  const textoEl = item.querySelector('.q-question-text .collapse');
  coletarImagens(textoEl);
  const textoAssociado = function (raiz) {
    if (!raiz) return '';
    const copia = raiz.cloneNode(true);
    const pilha = [copia];
    while (pilha.length) {
      const no = pilha.pop();
      if (no.nodeType === Node.TEXT_NODE) {
        no.nodeValue = no.nodeValue.replace(/\s+/g, ' ');
      } else if (no.nodeType === Node.ELEMENT_NODE) {
        for (let i = 0; i < no.childNodes.length; i += 1) pilha.push(no.childNodes[i]);
      }
    }
    copia.querySelectorAll('br').forEach(function (el) {
      el.replaceWith(document.createTextNode('\n'));
    });
    copia.querySelectorAll('p, div, li, h1, h2, h3, h4, h5, h6, tr').forEach(function (el) {
      el.appendChild(document.createTextNode('\n'));
    });
    return copia.textContent.replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ')
      .replace(/ *\n */g, '\n').replace(/\n{3,}/g, '\n\n').trim();
  };
  const alternativas = {};
  item.querySelectorAll('input.js-question-answer').forEach(function (campo) {
    const rotulo = campo.closest('label') || campo.parentElement;
    const conteudo = rotulo
      ? (rotulo.querySelector('.js-alternative-content') || rotulo.querySelector('.q-item-enum'))
      : null;
    const letra = limpar(campo.value).toUpperCase();
    if (!letra) return;
    alternativas[letra] = conteudo ? limpar(conteudo.innerText) : '';
    coletarImagens(conteudo);
  });
  if (Object.keys(alternativas).length === 0) {
    let indice = 0;
    item.querySelectorAll('.q-question-options label, .q-question-options .q-radio-button').forEach(function (rotulo) {
      const letraEl = rotulo.querySelector('.q-option-item');
      const conteudo = rotulo.querySelector('.q-item-enum');
      if (!conteudo) return;
      const letra = limpar(letraEl ? letraEl.innerText : 'ABCDE'[indice]).toUpperCase().slice(0, 1);
      alternativas[letra] = limpar(conteudo.innerText);
      coletarImagens(conteudo);
      indice += 1;
    });
  }
  const gabarito = item.querySelector('.js-question-right-answer');
  itens.push({
    id: caixa.getAttribute('data-question-id') || '',
    codigo: link ? limpar(link.textContent) : '',
    url: link ? link.href : '',
    migalha: migalha,
    info: info,
    enunciado: enunciado ? limpar(enunciado.innerText) : '',
    texto: textoAssociado(textoEl),
    alternativas: alternativas,
    imagens: imagens,
    gabarito: gabarito ? limpar(gabarito.textContent) : '',
    status: caixa.getAttribute('data-status') || ''
  });
});
return itens;
"""

JS_LER_ITENS_PLAYGROUND = r"""
const limpar = (texto) => (texto || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();
const coletarImagens = function (raiz, lista) {
  if (!raiz) return;
  raiz.querySelectorAll('img').forEach(function (img) {
    const src = img.getAttribute('src') || img.getAttribute('data-src') || '';
    if (src && lista.indexOf(src) === -1) lista.push(src);
  });
};
const itens = [];
document.querySelectorAll('div.mb-4').forEach(function (card) {
  const codigoEl = card.querySelector('div.pl-2.font-size-1');
  const codigo = codigoEl ? limpar(codigoEl.innerText) : '';
  if (!/^Q\d+$/.test(codigo)) return;
  const cabecalho = card.querySelector('header .info');
  const negritos = cabecalho ? Array.from(cabecalho.querySelectorAll('div.font-weight-bold'))
    .filter(function (e) { return !e.closest('.index') && !e.closest('.pl-2'); })
    .map(function (e) { return limpar(e.innerText); })
    .filter(function (t) { return t && !/^\d+$/.test(t); }) : [];
  const normais = cabecalho ? Array.from(cabecalho.querySelectorAll('div.font-weight-normal'))
    .map(function (e) { return limpar(e.innerText); })
    .filter(Boolean) : [];
  const partes = (negritos[0] || '').split(' - ');
  const enunciado = card.querySelector('.statement-container');
  const imagens = [];
  coletarImagens(enunciado, imagens);
  const alternativas = {};
  card.querySelectorAll('div.alternative-container').forEach(function (alt) {
    const caixa = alt.querySelector('.alternative-toggle');
    const letra = caixa ? limpar(caixa.innerText).toUpperCase() : '';
    const conteudo = alt.querySelector('.text');
    if (!letra) return;
    alternativas[letra] = conteudo ? limpar(conteudo.innerText) : '';
    coletarImagens(conteudo, imagens);
  });
  itens.push({
    id: '',
    codigo: codigo,
    url: '',
    migalha: [negritos[1] || '', normais[0] || ''],
    info: {
      banca: partes[0] || '',
      ano: (partes[1] || '').trim(),
      orgao: negritos[2] || '',
      cargo: normais[1] || ''
    },
    enunciado: enunciado ? limpar(enunciado.innerText) : '',
    texto: '',
    alternativas: alternativas,
    imagens: imagens,
    gabarito: '',
    status: ''
  });
});
return itens;
"""


@dataclass
class ConfigExtracao:
    instituicao: dict | None = None
    disciplina: dict | None = None
    banca: dict | None = None
    cargo: dict | None = None
    assunto: dict | None = None
    ano: int | str | None = None
    somente_com_gabarito: bool = False
    ordenacao: str = ""
    url_direta: str = ""
    termo: str = ""
    max_questoes: int = 60
    extrair_gabarito: bool = True
    extrair_explicacao: bool = True
    por_pagina: int = 20
    perfil: str | None = None
    visivel: bool = True
    esperar_gabarito: float = 12.0
    esperar_explicacao: float = 15.0
    espera_login: bool = True
    codigos_salvos: set[str] = field(default_factory=set)

    def tem_filtro(self) -> bool:
        return bool(
            self.url_direta
            or self.instituicao
            or self.disciplina
            or self.banca
            or self.cargo
            or self.assunto
            or self.ano
        )


class ExtratorQConcursos:
    def __init__(
        self,
        config: ConfigExtracao,
        ao_logar: Callable[[str, str], None] | None = None,
        ao_progresso: Callable[[int, int, str], None] | None = None,
        ao_atualizar: Callable[[list[dict]], None] | None = None,
        ao_pedir_login: Callable[[], bool] | None = None,
        ao_ano: Callable[[str], None] | None = None,
        parar: threading.Event | None = None,
    ):
        self.config = config
        self._log_cb = ao_logar
        self._progresso_cb = ao_progresso
        self._atualizar_cb = ao_atualizar
        self._pedir_login_cb = ao_pedir_login
        self._ano_cb = ao_ano
        self.parar = parar or threading.Event()

        self.driver = None
        self.questoes: list[dict] = []
        self.codigos_vistos: set[str] = set()
        self.login_pendente = False
        self.limite_diario = False
        self.erros: list[str] = []
        self.tentativas_login = 0

    def log(self, mensagem: str, nivel: str = "info") -> None:
        if self._log_cb:
            self._log_cb(mensagem, nivel)

    def progresso(self, atual: int, total: int, texto: str = "") -> None:
        if self._progresso_cb:
            self._progresso_cb(atual, total, texto)

    def atualizar(self) -> None:
        if self._atualizar_cb:
            self._atualizar_cb(list(self.questoes))

    def url_da_pagina(self, pagina: int) -> str:
        cfg = self.config
        if cfg.url_direta:
            base = cfg.url_direta.split("#", 1)[0]
            separador = "&" if "?" in base else "?"
            if re.search(r"[?&]page=\d+", base):
                base = re.sub(r"([?&])page=\d+", rf"\g<1>page={pagina}", base)
            else:
                base = f"{base}{separador}page={pagina}"
            if "per_page=" not in base:
                base += f"&per_page={cfg.por_pagina}"
            return base
        return api.montar_url(
            instituicao=cfg.instituicao,
            disciplina=cfg.disciplina,
            banca=cfg.banca,
            cargo=cfg.cargo,
            assunto=cfg.assunto,
            ano=cfg.ano,
            somente_com_gabarito=cfg.somente_com_gabarito,
            ordenacao=cfg.ordenacao,
            pagina=pagina,
            por_pagina=cfg.por_pagina,
        )

    def _termos_disciplina(self) -> str:
        disciplina = self.config.disciplina or {}
        termo = (
            disciplina.get("termo_original")
            or disciplina.get("nome")
            or disciplina.get("rotulo")
            or ""
        )
        return str(termo).strip()

    def _termo_assunto(self) -> str:
        assunto = self.config.assunto or {}
        termo = assunto.get("nome") or assunto.get("rotulo") or ""
        return str(termo).strip()

    def _alvos_do_guia(self, driver) -> list[str]:
        termo = self._termos_disciplina()
        candidatos = self._descobrir_disciplinas(driver)
        if termo and candidatos:
            alvo = api.normalizar(termo)
            tokens = [t for t in alvo.split() if len(t) >= 4] or ([alvo] if alvo else [])
            melhor, nota = "", 0
            for candidato in candidatos:
                nome = api.normalizar(candidato)
                pontos = sum(len(t) for t in tokens if t in nome)
                if pontos > nota:
                    melhor, nota = candidato, pontos
            if nota > 0:
                return [melhor]
            self.log(
                f"Disciplina '{termo}' não aparece no guia; extraindo todas as disciplinas.",
                "aviso",
            )
        return candidatos

    def _descobrir_disciplinas(self, driver) -> list[str]:
        return navegador.descobrir_disciplinas(driver)

    def _abrir_cabecalho(self, driver, nome: str) -> str:
        estado = driver.execute_script(
            """
            function norm(s) {
                return (s || '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                    .replace(/\\s+/g, ' ').trim().toLowerCase();
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
            """,
            nome,
        )
        return estado or "nao_achou"

    def _clicar_assunto(self, driver, disciplina: str, assunto: str) -> str:
        texto = driver.execute_script(
            """
            const norm = function (s) {
                return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                    .replace(/\\s+/g, ' ').trim().toLowerCase();
            };
            const disc = norm(arguments[0]);
            const alvo = norm(arguments[1]);
            const seletor = 'h2 > button[aria-expanded], h3 > button[aria-expanded], h4 > button[aria-expanded], h5 > button[aria-expanded]';
            let regiao = null;
            for (const b of document.querySelectorAll(seletor)) {
                if (b.closest('[role="region"]')) continue;
                if (norm(b.innerText) !== disc) continue;
                const controle = b.getAttribute('aria-controls');
                regiao = controle ? document.getElementById(controle) : null;
                if (!regiao) {
                    const cabecalho = b.parentElement;
                    regiao = cabecalho && cabecalho.parentElement
                        ? cabecalho.parentElement.querySelector('[role="region"]')
                        : null;
                }
                break;
            }
            const escopo = regiao || document;
            for (const b of escopo.querySelectorAll('button[aria-expanded]')) {
                const texto = (b.innerText || '').trim().replace(/\\s+/g, ' ');
                if (!texto) continue;
                if (norm(texto).indexOf(alvo) === -1) continue;
                if (b.getAttribute('aria-expanded') === 'false') {
                    b.scrollIntoView({block: 'center'});
                    b.click();
                }
                return texto;
            }
            return '';
            """,
            disciplina,
            assunto,
        )
        if not texto:
            return ""
        time.sleep(2)
        clicado = driver.execute_script(
            """
            const norm = function (s) {
                return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '')
                    .replace(/\\s+/g, ' ').trim().toLowerCase();
            };
            const alvo = norm(arguments[0]);
            const botao = Array.from(document.querySelectorAll('button')).find(function (b) {
                const t = norm((b.innerText || '').replace(/\\s+/g, ' '));
                return t.indexOf('todo o assunto') !== -1 && t.indexOf(alvo) !== -1;
            });
            if (!botao) return 0;
            botao.scrollIntoView({block: 'center'});
            botao.click();
            return 1;
            """,
            texto,
        )
        return texto if clicado else ""

    def _voltar_ao_guia(self, driver, guia_url: str) -> None:
        try:
            driver.back()
        except WebDriverException:
            pass
        limite = time.time() + 30
        while time.time() < limite:
            if "videoaulas" in driver.current_url:
                time.sleep(1.5)
                return
            time.sleep(1)
        navegador.ir_para(driver, guia_url, ao_atualizar=None)
        time.sleep(3)

    def _url_disciplina(self, driver, guia_url: str, nome: str) -> str:
        estado = self._abrir_cabecalho(driver, nome)
        if estado == "nao_achou":
            if not navegador.ir_para(driver, guia_url, ao_atualizar=lambda t: self.log(t)):
                return ""
            time.sleep(3)
            estado = self._abrir_cabecalho(driver, nome)
            if estado == "nao_achou":
                return ""
        if estado == "abriu":
            time.sleep(2)
        assunto = self._termo_assunto()
        clicado = 0
        if assunto:
            nome_assunto = self._clicar_assunto(driver, nome, assunto)
            if nome_assunto:
                clicado = 1
                self.log(f"Assunto do guia: {nome_assunto} ({nome})")
            else:
                self.log(
                    f"Assunto '{assunto}' não aparece em {nome}; extraindo a disciplina inteira.",
                    "aviso",
                )
        if not clicado:
            clicado = driver.execute_script(
                """
                const alvo = arguments[0].toLowerCase();
                const lista = Array.from(document.querySelectorAll('button')).filter(function (b) {
                    const t = (b.innerText || '').replace(/\\s+/g, ' ').toLowerCase();
                    return t.includes('toda a disciplina de ' + alvo);
                });
                if (!lista.length) return 0;
                lista[0].scrollIntoView({block: 'center'});
                lista[0].click();
                return 1;
                """,
                nome,
            )
        if not clicado:
            return ""
        capturada = ""
        limite = time.time() + 30
        while time.time() < limite:
            if self.parar.is_set():
                return ""
            atual = driver.current_url
            if "/playground/questoes" in atual:
                capturada = re.sub(r"[?&]limit=\d+", "", atual)
                capturada = re.sub(r"(\?|&)sort=&", r"\g<1>", capturada)
                break
            time.sleep(1)
        if not capturada:
            return ""
        self._voltar_ao_guia(driver, guia_url)
        return capturada

    def _abrir_guia_de_estudos(self, driver, url: str) -> list[str]:
        self.log(f"Abrindo o guia de estudos: {url}")
        if not navegador.ir_para(driver, url, ao_atualizar=lambda t: self.log(t)):
            return []
        time.sleep(3)
        ano = navegador.descobrir_ano_prova(driver)
        if ano:
            self.log(f"Ano da prova no guia: {ano}")
            if self._ano_cb:
                self._ano_cb(ano)
        if self.config.assunto:
            self.log(f"Filtrando pelo assunto do guia: {self._termo_assunto()}")
        alvos = self._alvos_do_guia(driver)
        if not alvos:
            self.log("Não encontrei links de disciplina no guia de estudos.", "erro")
            return []
        if len(alvos) == 1:
            self.log(f"Disciplina selecionada: {alvos[0]}")
        else:
            self.log(f"Disciplinas do guia ({len(alvos)}): {', '.join(alvos)}")
        urls: list[str] = []
        total = len(alvos)
        for indice, nome in enumerate(alvos, start=1):
            if self.parar.is_set():
                break
            capturada = self._url_disciplina(driver, url, nome)
            if capturada:
                urls.append(capturada)
                self.log(f"[{indice}/{total}] Filtro de {nome} capturado.")
            else:
                self.log(f"[{indice}/{total}] Sem link de questões para {nome}.", "aviso")
        return urls

    def executar(self) -> list[dict]:
        cfg = self.config
        if not cfg.tem_filtro():
            raise ValueError("Informe um concurso (ou uma URL de filtro) antes de extrair.")

        self.log("Iniciando o navegador…")
        driver = navegador.criar_driver(cfg.perfil, cfg.visivel)
        self.driver = driver
        try:
            bases = [cfg.url_direta]
            if "guia-de-estudos" in cfg.url_direta:
                guias = self._abrir_guia_de_estudos(driver, cfg.url_direta)
                if not guias:
                    self.log("Nenhuma disciplina do guia pôde ser aberta.", "erro")
                    return list(self.questoes)
                bases = guias
            estado: dict = {"tentou_perfil": False, "avisou_gabarito": False}
            for posicao, base in enumerate(bases, start=1):
                if self.parar.is_set():
                    break
                if len(self.questoes) >= cfg.max_questoes:
                    break
                cfg.url_direta = base
                limite = cfg.max_questoes
                if len(bases) > 1:
                    restantes_bases = len(bases) - posicao + 1
                    pendentes = cfg.max_questoes - len(self.questoes)
                    orcamento = -(-pendentes // restantes_bases)
                    limite = len(self.questoes) + orcamento
                    self.log(
                        f"Filtro {posicao}/{len(bases)} do guia "
                        f"— até {orcamento} questão(ões) desta disciplina"
                    )
                self._extrair_base(base, estado, limite)

            self.log(f"Extração finalizada: {len(self.questoes)} questão(ões).")
            if not self.questoes and cfg.codigos_salvos:
                self.log(
                    "Nenhuma questão nova — todas as disponíveis já estão salvas.",
                    "aviso",
                )
            return list(self.questoes)
        finally:
            navegador.fechar(self.driver)
            self.driver = None

    def _extrair_base(self, base: str, estado: dict, limite: int | None = None) -> None:
        cfg = self.config
        if limite is None:
            limite = cfg.max_questoes
        limite = min(limite, cfg.max_questoes)
        pagina = 1
        pode_simplificar = bool(cfg.instituicao) and not base
        simplificaveis = ["assunto", "cargo", "disciplina", "ano"]
        while not self.parar.is_set():
            driver = self.driver
            url = self.url_da_pagina(pagina)
            self.log(f"Página {pagina}: {url}")
            if not navegador.ir_para(driver, url, ao_atualizar=lambda t: self.log(t)):
                if pagina == 1 and not estado["tentou_perfil"]:
                    estado["tentou_perfil"] = True
                    self.log(
                        "Desafio de segurança não liberou; tentando com perfil temporário…",
                        "aviso",
                    )
                    navegador.fechar(driver)
                    self.driver = navegador.criar_driver(None, cfg.visivel, temporario=True)
                    continue
                raise RuntimeError(
                    "O site não liberou o acesso (desafio de segurança). "
                    "Abra o navegador manualmente uma vez e tente de novo."
                )
            playground = "/playground/" in url
            seletor = ".statement-container" if playground else ".js-question-item"
            if not navegador.aguardar(driver, seletor, 25):
                removido = None
                if pagina == 1 and pode_simplificar:
                    while simplificaveis:
                        nome = simplificaveis.pop(0)
                        if getattr(cfg, nome):
                            setattr(cfg, nome, None)
                            removido = nome
                            break
                if removido:
                    self.log(
                        f"Nenhuma questão com o filtro de {removido}; tentando sem ele…",
                        "aviso",
                    )
                    continue
                self.log("Nenhuma questão encontrada com esses filtros.", "aviso")
                break
            if (
                playground
                and pagina == 1
                and cfg.extrair_gabarito
                and not estado["avisou_gabarito"]
            ):
                estado["avisou_gabarito"] = True
                self.log(
                    "O guia de estudos não exibe gabaritos; use "
                    "'Gerar resolução com IA' ou responda no site para obtê-los.",
                    "aviso",
                )
            time.sleep(0.6)

            itens = driver.execute_script(
                JS_LER_ITENS_PLAYGROUND if playground else JS_LER_ITENS
            ) or []
            if not itens:
                self.log("Fim das questões nesta página.", "aviso")
                break
            novos = [
                item
                for item in itens
                if item.get("codigo") and item["codigo"] not in self.codigos_vistos
            ]
            if not novos:
                self.log("A página só repetia questões já extraídas — encerrando.", "aviso")
                break
            ja_salvos = [
                item for item in novos if item["codigo"] in cfg.codigos_salvos
            ]
            para_extrair = [
                item for item in novos if item["codigo"] not in cfg.codigos_salvos
            ]
            if not para_extrair:
                for item in novos:
                    self.codigos_vistos.add(item["codigo"])
                self.log(
                    f"{len(novos)} questões desta página já estão salvas "
                    "— indo para a próxima página.",
                    "aviso",
                )
                pagina += 1
                continue
            if ja_salvos:
                self.log(
                    f"{len(ja_salvos)} questões desta página já estão salvas — ignoradas.",
                    "aviso",
                )

            restantes = limite - len(self.questoes)
            if restantes <= 0:
                break
            para_extrair = para_extrair[:restantes]

            self._processar_itens(driver, para_extrair)
            self.log(
                f"Página {pagina} concluída "
                f"({len(self.questoes)}/{limite} questões)."
            )
            if len(self.questoes) >= limite:
                if limite >= cfg.max_questoes:
                    self.log("Limite de questões solicitadas atingido.")
                break
            pagina += 1

    def _processar_itens(self, driver, itens: list[dict]) -> None:
        cfg = self.config
        extrair_gabarito = cfg.extrair_gabarito
        extrair_explicacao = cfg.extrair_explicacao

        for indice, bruta in enumerate(itens, start=1):
            if self.parar.is_set():
                break
            codigo = bruta.get("codigo", "?")
            identificador = bruta.get("id", "")

            if extrair_gabarito and not bruta.get("gabarito"):
                try:
                    gabarito = self._obter_gabarito(driver, identificador)
                    if gabarito:
                        bruta["gabarito"] = gabarito
                except LoginNecessario as erro:
                    self.log(str(erro), "erro")
                    extrair_gabarito = False
                    self.login_pendente = True
                except LimiteAtingido as erro:
                    self.log(str(erro), "aviso")
                    extrair_gabarito = False
                    self.limite_diario = True
                except WebDriverException as erro:
                    self.erros.append(f"{codigo}: {erro.__class__.__name__}")
                    self.log(f"Falha ao obter gabarito de {codigo}: {erro}", "aviso")

            if extrair_explicacao and not bruta.get("explicacao"):
                try:
                    explicacao = self._obter_explicacao(driver, identificador)
                    if explicacao:
                        bruta["explicacao"] = explicacao
                except LoginNecessario as erro:
                    self.log(str(erro), "erro")
                    extrair_explicacao = False
                    self.login_pendente = True
                except WebDriverException as erro:
                    self.erros.append(f"{codigo}: {erro.__class__.__name__}")
                    self.log(f"Falha ao obter explicação de {codigo}: {erro}", "aviso")

            questao = self.montar_questao(bruta)
            self.codigos_vistos.add(questao["codigo"])
            self.questoes.append(questao)
            self.progresso(
                len(self.questoes),
                self.config.max_questoes,
                f"Extraídas {len(self.questoes)} de até {self.config.max_questoes}",
            )
            self.atualizar()
            self.log(
                f"[{indice}/{len(itens)}] {questao['codigo']} — {questao['tema'] or 'sem tema'}"
                + (" • gabarito " + questao["gabarito"] if questao.get("gabarito") else "")
            )

    def _texto_js(self, driver, seletor: str) -> str:
        try:
            return (
                driver.execute_script(
                    "const alvo = document.querySelector(arguments[0]);"
                    "return alvo ? alvo.textContent.replace(/\\u00a0/g,' ').trim() : '';",
                    seletor,
                )
                or ""
            ).strip()
        except WebDriverException:
            return ""

    def _obter_gabarito(self, driver, identificador: str) -> str:
        if not identificador:
            return ""
        seletor_item = f'[data-question-id="{identificador}"]'
        seletor_gabarito = f"{seletor_item} .js-question-right-answer"

        existente = self._texto_js(driver, seletor_gabarito)
        if existente:
            return self._limpar_gabarito(existente)

        rotulo = navegador.elemento(driver, f"{seletor_item} label.q-radio-button", 6)
        if rotulo is None:
            return ""
        navegador.clicar_js(driver, rotulo)
        time.sleep(0.4)

        botao = navegador.elemento(driver, f"{seletor_item} button.js-answer-btn", 4)
        if botao is None:
            return ""
        if navegador.modal_login_visivel(driver):
            self._solicitar_login()
            return self._obter_gabarito(driver, identificador)
        navegador.clicar_js(driver, botao)

        limite = time.time() + self.config.esperar_gabarito
        while time.time() < limite:
            if self.parar.is_set():
                return ""
            if navegador.modal_login_visivel(driver):
                self._solicitar_login()
                return self._obter_gabarito(driver, identificador)
            if navegador.limite_atingido(driver):
                raise LimiteAtingido(
                    "O plano gratuito atingiu o limite diário de questões: "
                    "gabaritos não serão coletados agora."
                )
            texto = self._texto_js(driver, seletor_gabarito)
            if texto:
                return self._limpar_gabarito(texto)
            time.sleep(0.5)
        self.log(f"Gabarito não revelado a tempo para {identificador}.", "aviso")
        return ""

    @staticmethod
    def _limpar_gabarito(texto: str) -> str:
        achado = re.search(r"[A-E]", (texto or "").upper())
        return achado.group(0) if achado else ""

    def _obter_explicacao(self, driver, identificador: str) -> str:
        if not identificador:
            return ""
        seletor_conteudo = f"#question-belt-{identificador}-teacher-tab .js-content"
        texto = self._texto_js(driver, seletor_conteudo)
        if len(texto) >= 40:
            return texto

        ancora = navegador.elemento(
            driver, f'a[href="#question-belt-{identificador}-teacher-tab"]', 5
        )
        if ancora is None:
            return ""
        navegador.clicar_js(driver, ancora)

        limite = time.time() + self.config.esperar_explicacao
        while time.time() < limite:
            if self.parar.is_set():
                return ""
            if navegador.modal_login_visivel(driver):
                self._solicitar_login()
                nova_ancora = navegador.elemento(
                    driver, f'a[href="#question-belt-{identificador}-teacher-tab"]'
                )
                navegador.clicar_js(driver, nova_ancora or ancora)
                continue
            texto = self._texto_js(driver, seletor_conteudo)
            if len(texto) >= 40:
                return texto
            time.sleep(0.6)
        self.log(f"Explicação não carregou para {identificador}.", "aviso")
        return ""

    def _solicitar_login(self) -> None:
        self.tentativas_login += 1
        if self.tentativas_login > 2:
            raise LoginNecessario("Login não foi concluído; gabaritos ignorados nesta execução.")
        if self.config.espera_login and self._pedir_login_cb is not None:
            self.log("Login necessário: autentique-se no navegador.", "aviso")
            if self._pedir_login_cb():
                return
        raise LoginNecessario(
            "Faça login no QConcursos (aba 'Extrator' → 'Entrar no navegador') "
            "para obter gabaritos e explicações."
        )

    def montar_questao(self, bruta: dict) -> dict:
        info = bruta.get("info") or {}
        migalha = [
            parte.strip(" ,") for parte in (bruta.get("migalha") or []) if parte.strip(" ,")
        ]

        banca = info.get("banca", "")
        ano = info.get("ano", "")
        orgao = info.get("orgao", "")
        prova = info.get("prova") or info.get("provas") or ""

        tema = migalha[0] if migalha else ""
        assunto = " / ".join(migalha[1:]) if len(migalha) > 1 else ""

        cargo = info.get("cargo", "")
        partes_prova = [p.strip() for p in prova.split(" - ") if p.strip()]
        if not cargo and len(partes_prova) >= 4:
            cargo = " - ".join(partes_prova[3:])
        if not orgao and len(partes_prova) >= 3:
            orgao = partes_prova[2]

        registro = {
            "codigo": bruta.get("codigo", ""),
            "banca": " - ".join(x for x in (banca, ano) if x) or "Não informado",
            "tema": tema or "Sem Tema",
            "assunto": assunto or "Não informado",
            "concurso": orgao or (partes_prova[2] if len(partes_prova) >= 3 else "Não informado"),
            "cargo": cargo,
            "enunciado": bruta.get("enunciado", ""),
            "texto": bruta.get("texto", ""),
            "alternativas": bruta.get("alternativas") or {},
            "gabarito": self._limpar_gabarito(bruta.get("gabarito", "")),
            "explicacao": bruta.get("explicacao", ""),
            "imagens": bruta.get("imagens") or [],
            "possui_imagem": bool(bruta.get("imagens")),
            "url": bruta.get("url", ""),
            "id": bruta.get("id", ""),
        }
        cargo_registro = re.sub(r"\s+", " ", registro.get("cargo", "")).strip()
        if len(cargo_registro) > 90:
            rotulo = ""
            if self.config.cargo:
                rotulo = re.sub(
                    r"\s+", " ", str(self.config.cargo.get("rotulo") or "")
                ).strip()
            if rotulo and cargo_registro.lower().startswith(rotulo.lower()):
                registro["cargo"] = cargo_registro[: len(rotulo)]
            else:
                registro["cargo"] = ""
        return normalizar_questao(registro)


def abrir_navegador_para_login(perfil: str | None = None, visivel: bool = True):
    driver = navegador.criar_driver(perfil, visivel)
    driver.get("https://www.qconcursos.com/conta/entrar")
    navegador.aguardar_desafio(driver)
    return driver
