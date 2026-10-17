from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

MODELOS_FREE = ("gpt-oss:120b", "gpt-oss:20b", "nemotron-3-nano:30b", "gemma4:31b")

PROMPT_RESOLUCAO = (
    "Você é um professor preparador de concursos públicos. Responda em português do Brasil.\n"
    "Analise a questão abaixo, identifique a alternativa correta e explique o raciocínio de forma clara e objetiva.\n"
    "Cite os conceitos-chave e, se possível, a lei ou fundamento que sustenta a resposta.\n"
    "Formato da resposta:\n"
    "1) Comece com uma linha no formato 'Resposta: X' (a letra correta).\n"
    "2) Depois, apresente a explicação em parágrafos curtos.\n\n"
    "QUESTÃO:\n{enunciado}\n\nALTERNATIVAS:\n{alternativas}\n\n"
    "GABARITO OFICIAL (se conhecido): {gabarito}\n"
)

_chaves_esgotadas: set[int] = set()


class ErroIA(Exception):
    pass


class ErroLimite(Exception):
    pass


def base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "https://ollama.com").rstrip("/")


def listar_chaves() -> list[str]:
    bruto = os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_API_KEYS", "")
    return [parte.strip() for parte in bruto.split(",") if parte.strip()]


def modelo_padrao() -> str:
    return os.environ.get("OLLAMA_MODEL", MODELOS_FREE[0])


def _montar_prompt(questao: dict) -> str:
    enunciado = (questao.get("enunciado") or "").strip()
    alternativas = questao.get("alternativas") or {}
    linhas = [f"{letra}) {texto}" for letra, texto in alternativas.items() if texto]
    gabarito = (questao.get("gabarito") or questao.get("gabarito_copilot") or "").strip()
    return PROMPT_RESOLUCAO.format(
        enunciado=enunciado or "(sem enunciado)",
        alternativas="\n".join(linhas) or "(sem alternativas)",
        gabarito=gabarito or "desconhecido",
    )


def _corpo_de_erro(erro: urllib.error.HTTPError) -> dict:
    try:
        return json.loads(erro.read().decode("utf-8"))
    except Exception:
        return {"error": str(erro)}


def _eh_limite(mensagem: str) -> bool:
    baixo = mensagem.lower()
    return "limit" in baixo or "free plan" in baixo or "usage" in baixo


def _chamar_chat(chave: str, modelo: str, prompt: str, timeout: float) -> str:
    payload = {
        "model": modelo,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    dados = json.dumps(payload).encode("utf-8")
    requisicao = urllib.request.Request(
        f"{base_url()}/api/chat",
        data=dados,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {chave}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            corpo = json.loads(resposta.read().decode("utf-8"))
    except urllib.error.HTTPError as erro:
        corpo = _corpo_de_erro(erro)
    except urllib.error.URLError as erro:
        raise ErroIA(f"Falha ao contatar o Ollama Cloud ({base_url()}): {erro}") from erro

    if "error" in corpo:
        mensagem = str(corpo["error"])
        if _eh_limite(mensagem):
            raise ErroLimite(mensagem)
        raise ErroIA(mensagem)

    return (corpo.get("message", {}).get("content") or "").strip()


def gerar_resolucao(
    questao: dict,
    modelo: str | None = None,
    ao_atualizar: Callable[[str], None] | None = None,
    timeout: float = 180.0,
) -> str:
    modelo = modelo or modelo_padrao()
    prompt = _montar_prompt(questao)
    chaves = listar_chaves()
    if not chaves:
        raise ErroIA("Nenhuma OLLAMA_API_KEY configurada no arquivo .env.")
    if len(_chaves_esgotadas) >= len(chaves):
        _chaves_esgotadas.clear()

    ultima = None
    for indice, chave in enumerate(chaves):
        if indice in _chaves_esgotadas:
            continue
        try:
            texto = _chamar_chat(chave, modelo, prompt, timeout)
        except ErroLimite as erro:
            _chaves_esgotadas.add(indice)
            ultima = erro
            continue
        if not texto:
            raise ErroIA("O modelo devolveu uma resposta vazia.")
        if ao_atualizar:
            ao_atualizar(texto)
        return texto

    if ultima:
        raise ErroIA(
            f"Todas as chaves atingiram o limite do Ollama Cloud. Último erro: {ultima}"
        )
    raise ErroIA("Nenhuma chave disponível para uso. Verifique o .env.")


def extrair_letra(texto: str) -> str:
    isolada = re.compile(r"(?<![A-Za-zÀ-ÿ])([A-E])(?![A-Za-zÀ-ÿ])")
    for linha in (texto or "").splitlines():
        limpo = linha.strip().upper()
        if limpo.startswith("RESPOSTA"):
            _, _, resto = limpo.partition(":")
            achado = isolada.search(resto)
            if achado:
                return achado.group(1)
    forte = _fallback_padroes(texto)
    if forte:
        return forte
    for linha in (texto or "").splitlines():
        if linha.strip().upper().startswith("RESPOSTA"):
            continue
        achado = isolada.search(linha)
        if achado:
            return achado.group(1)
    return ""


def _fallback_padroes(texto: str) -> str:
    padroes = (
        r"LETRA\s+([A-E])\b",
        r"ALTERNATIVA\s+([A-E])\b",
        r"É\s+A\s+([A-E])\b",
        r"RESPOSTA\s+[ÉE]\s+A?\s*([A-E])\b",
        r"CORRETA\s+[ÉE]\s+A?\s*([A-E])\b",
    )
    alto = (texto or "").upper()
    for padrao in padroes:
        achado = re.search(padrao, alto)
        if achado:
            return achado.group(1)
    return ""


def resolver_questao(questao: dict, modelo: str | None = None) -> dict:
    explicacao = gerar_resolucao(questao, modelo=modelo)
    letra = extrair_letra(explicacao)
    return {"explicacao_ia": explicacao, "gabarito_ia": letra}
