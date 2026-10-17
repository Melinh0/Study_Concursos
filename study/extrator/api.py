from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request, urlopen

URL_LISTAGEM = "https://www.qconcursos.com/questoes-de-concursos/questoes"
BASE_API = "https://brokk.qconcursos.com/product/1"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

TIPOS = {
    "instituicao": ("institutes", ("sigla", "nome")),
    "disciplina": ("disciplines", ("nome",)),
    "banca": ("examining_boards", ("sigla", "nome")),
    "cargo": ("jobs", ("nome",)),
    "assunto": ("subjects", ("nome",)),
}


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-zA-Z0-9]+", " ", texto).lower()
    return re.sub(r"\s+", " ", texto).strip()


def _get_json(url: str, timeout: float = 25.0) -> list:
    requisicao = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(requisicao, timeout=timeout) as resposta:
        dados = json.loads(resposta.read().decode("utf-8"))
    if not isinstance(dados, list):
        raise ValueError(f"Resposta inesperada da API: {url}")
    return dados


@lru_cache(maxsize=16)
def listar(tipo: str) -> tuple:
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de filtro desconhecido: {tipo}")
    recurso, campos = TIPOS[tipo]
    itens = _get_json(f"{BASE_API}/{recurso}")
    return tuple(itens), campos


def _pontuar(termo: str, item: dict, campos: tuple[str, ...]) -> float:
    alvo = normalizar(termo)
    if not alvo:
        return 0.0
    melhor = 0.0
    for campo in campos:
        valor = normalizar(item.get(campo))
        if not valor:
            continue
        if valor == alvo:
            melhor = max(melhor, 100.0)
        elif alvo == normalizar(item.get("id")):
            melhor = max(melhor, 100.0)
        elif alvo in valor:
            cobertura = len(alvo) / max(len(valor), 1)
            melhor = max(melhor, 70 + 25 * cobertura)
        elif valor in alvo and len(valor) >= 3:
            melhor = max(melhor, 60 + 30 * (len(valor) / len(alvo)))
        else:
            parecido = SequenceMatcher(None, alvo, valor).ratio()
            tokens_alvo = set(alvo.split())
            tokens_valor = set(valor.split())
            sobreposicao = len(tokens_alvo & tokens_valor) / max(len(tokens_alvo), 1)
            melhor = max(melhor, 55 * parecido + 40 * sobreposicao)
    return melhor


def buscar(termo: str, tipo: str = "instituicao", limite: int = 8) -> list[dict]:
    itens, campos = listar(tipo)
    pontuados = []
    for item in itens:
        nota = _pontuar(termo, item, campos)
        if nota >= 45:
            pontuados.append((nota, item))
    pontuados.sort(key=lambda par: (-par[0], str(par[1].get("nome", ""))))
    saida = []
    for nota, item in pontuados[:limite]:
        rotulo = (item.get("sigla") or item.get("nome") or "").strip()
        descricao = (item.get("nome") or "").strip()
        saida.append(
            {
                "id": item.get("id"),
                "tipo": tipo,
                "rotulo": rotulo,
                "descricao": descricao,
                "pontuacao": round(nota, 1),
            }
        )
    return saida


def resolver(termo: str, tipo: str = "instituicao") -> dict | None:
    encontrados = buscar(termo, tipo, limite=1)
    return encontrados[0] if encontrados else None


def por_id(tipo: str, identificador) -> dict | None:
    if identificador in (None, "", 0, "0"):
        return None
    itens, _campos = listar(tipo)
    alvo = str(identificador)
    for item in itens:
        if str(item.get("id")) == alvo:
            rotulo = (item.get("sigla") or item.get("nome") or "").strip()
            descricao = (item.get("nome") or "").strip()
            return {
                "id": item.get("id"),
                "tipo": tipo,
                "rotulo": rotulo,
                "descricao": descricao,
                "pontuacao": 100.0,
            }
    return None


def montar_url(
    instituicao: dict | None = None,
    disciplina: dict | None = None,
    banca: dict | None = None,
    cargo: dict | None = None,
    assunto: dict | None = None,
    ano: int | str | None = None,
    somente_com_gabarito: bool = False,
    ordenacao: str = "",
    pagina: int = 1,
    por_pagina: int = 20,
) -> str:
    parametros: list[tuple[str, object]] = []

    def adicionar_lista(nome: str, valor) -> None:
        if valor in (None, "", 0, "0"):
            return
        parametros.append((f"{nome}[]", valor))

    adicionar_lista("institute_ids", (instituicao or {}).get("id"))
    adicionar_lista("discipline_ids", (disciplina or {}).get("id"))
    adicionar_lista("examining_board_ids", (banca or {}).get("id"))
    adicionar_lista("job_ids", (cargo or {}).get("id"))
    adicionar_lista("subject_ids", (assunto or {}).get("id"))
    adicionar_lista("publication_year", ano)

    if somente_com_gabarito:
        parametros.append(("has_professor_commentaries", "true"))
    if ordenacao:
        parametros.append(("sort", ordenacao))

    parametros.append(("per_page", int(por_pagina)))
    parametros.append(("page", max(int(pagina), 1)))
    return f"{URL_LISTAGEM}?{urlencode(parametros)}"
