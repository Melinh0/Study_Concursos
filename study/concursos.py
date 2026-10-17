from __future__ import annotations

import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_QUESTOES = RAIZ / "questões"
PASTA_BACKUP = RAIZ / "backup"

CONCURSOS = {
    "CPRM": {
        "rotulo": "CPRM",
        "descricao": "Serviço Geológico do Brasil",
        "arquivo": "questoes_cprm_com_gabarito_corrigidas.json",
        "banco": "study_progress_cprm.db",
        "concurso": "CPRM",
    },
    "IBGE": {
        "rotulo": "IBGE",
        "descricao": "Instituto Brasileiro de Geografia e Estatística",
        "arquivo": "questoes_ibge_com_gabarito.json",
        "banco": "study_progress_ibge.db",
        "concurso": "IBGE",
    },
    "TJ-CE": {
        "rotulo": "TJ-CE",
        "descricao": "Tribunal de Justiça do Ceará",
        "arquivo": "questoes_tj_ce_com_gabarito.json",
        "banco": "study_progress_tj-ce.db",
        "concurso": "TJ-CE",
    },
}


def _slug(texto: str) -> str:
    normal = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in normal if not unicodedata.combining(c))
    slug = re.sub(r"[^A-Za-z0-9]+", "-", sem_acento).strip("-").upper()
    return slug or "CONCURSO"


def rotulo_exibicao(info: dict) -> str:
    rotulo = (info.get("rotulo") or "").strip()
    descricao = (info.get("descricao") or "").strip()
    if descricao and descricao != rotulo:
        return f"{rotulo} — {descricao}"
    return rotulo


def _detectar_arquivos() -> None:
    if not PASTA_QUESTOES.exists():
        return
    registrados = {info.get("arquivo") for info in CONCURSOS.values()}
    for caminho in sorted(PASTA_QUESTOES.glob("questoes_*.json")):
        if caminho.name in registrados:
            continue
        base = caminho.name[len("questoes_"): -len(".json")]
        chave = _slug(base)
        if not chave or chave in CONCURSOS:
            continue
        CONCURSOS[chave] = {
            "rotulo": chave,
            "descricao": "",
            "arquivo": caminho.name,
            "banco": f"study_progress_{chave.lower()}.db",
            "concurso": chave,
        }
        registrados.add(caminho.name)


def listar() -> list[dict]:
    return [{"chave": chave, **info} for chave, info in CONCURSOS.items()]


def obter(chave: str) -> dict:
    if chave not in CONCURSOS:
        raise KeyError(f"Concurso desconhecido: {chave}")
    return {"chave": chave, **CONCURSOS[chave]}


def chave_para(rotulo: str) -> str | None:
    procurado = (rotulo or "").strip().lower()
    if not procurado:
        return None
    for chave, info in CONCURSOS.items():
        if info.get("concurso", "").strip().lower() == procurado:
            return chave
        if info.get("rotulo", "").strip().lower() == procurado:
            return chave
    return None


def adicionar(rotulo: str, descricao: str = "") -> str:
    rotulo = (rotulo or "").strip()
    if not rotulo:
        raise ValueError("Rótulo do concurso vazio")
    existente = chave_para(rotulo)
    if existente:
        return existente
    base = _slug(rotulo)
    chave = base
    sufixo = 2
    while chave in CONCURSOS:
        chave = f"{base}-{sufixo}"
        sufixo += 1
    CONCURSOS[chave] = {
        "rotulo": rotulo,
        "descricao": descricao.strip() or rotulo,
        "arquivo": f"questoes_{chave.lower()}.json",
        "banco": f"study_progress_{chave.lower()}.db",
        "concurso": rotulo,
    }
    return chave


def caminho_json(chave: str) -> Path:
    return PASTA_QUESTOES / obter(chave)["arquivo"]


def caminho_banco(chave: str) -> Path:
    return PASTA_BACKUP / obter(chave)["banco"]


_detectar_arquivos()
