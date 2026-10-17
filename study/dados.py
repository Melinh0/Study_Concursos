from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from . import concursos

RAIZ = Path(__file__).resolve().parent.parent
PASTA_QUESTOES = concursos.PASTA_QUESTOES
PASTA_BACKUP = concursos.PASTA_BACKUP
CAMINHO_PADRAO = concursos.caminho_json("CPRM")

LETRAS = ("A", "B", "C", "D", "E")


def _texto(valor, padrao="") -> str:
    if valor is None:
        return padrao
    return str(valor).strip()


def _sanitizar_cargo(cargo: str, enunciado: str) -> str:
    cargo = re.sub(r"\s+", " ", cargo).strip()
    if not cargo:
        return ""
    enunciado_colapsado = re.sub(r"\s+", " ", enunciado).strip()
    if len(enunciado_colapsado) >= 20:
        posicao = cargo.lower().find(enunciado_colapsado[:40].lower())
        if posicao == 0:
            return ""
        if posicao > 0:
            cargo = cargo[:posicao].strip(" -–,;:")
    if len(cargo) > 90:
        return ""
    return cargo


def normalizar_questao(bruta: dict, numero: int | None = None) -> dict:
    if not isinstance(bruta, dict):
        raise TypeError("questão deve ser um dicionário")

    questao = dict(bruta)

    questao["codigo"] = _texto(questao.get("codigo")) or _texto(questao.get("id"))
    questao["enunciado"] = _texto(questao.get("enunciado"))
    questao["banca"] = _texto(questao.get("banca"), "Não informado")
    questao["tema"] = _texto(questao.get("tema"), "Sem Tema")
    questao["assunto"] = _texto(questao.get("assunto"), "Não informado")
    questao["concurso"] = _texto(questao.get("concurso"), "Não informado")
    questao["cargo"] = _sanitizar_cargo(
        _texto(questao.get("cargo")), questao.get("enunciado", "")
    )

    alternativas = questao.get("alternativas") or {}
    if isinstance(alternativas, dict):
        alternativas = {
            str(chave).strip().upper(): _texto(valor)
            for chave, valor in alternativas.items()
            if _texto(valor)
        }
        alternativas = {k: v for k, v in alternativas.items() if k in LETRAS}
    else:
        alternativas = {}
    questao["alternativas"] = dict(sorted(alternativas.items()))

    gabarito = _texto(questao.get("gabarito")) or _texto(questao.get("gabarito_copilot"))
    explicacao = _texto(questao.get("explicacao")) or _texto(questao.get("explicacao_copilot"))

    if gabarito:
        achado = re.search(r"[A-E]", gabarito.upper())
        gabarito = achado.group(0) if achado else gabarito[:1].upper()

    questao["gabarito"] = gabarito
    questao["gabarito_copilot"] = gabarito
    questao["explicacao"] = explicacao
    questao["explicacao_copilot"] = explicacao

    if numero is not None:
        questao["numero"] = numero
    else:
        questao.setdefault("numero", 0)

    questao.setdefault("imagens", [])
    questao.setdefault("possui_imagem", bool(questao.get("imagens")))
    questao.setdefault("url", "")
    return questao


def renumerar(questoes: list[dict]) -> list[dict]:
    for indice, questao in enumerate(questoes, start=1):
        questao["numero"] = indice
    return questoes


def carregar_questoes(caminho: str | Path | None = None) -> list[dict]:
    alvo = Path(caminho) if caminho else CAMINHO_PADRAO
    if not alvo.exists():
        return []
    with alvo.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados, list):
        raise ValueError(f"Estrutura inesperada em {alvo}: era esperada uma lista")
    return [normalizar_questao(item, indice) for indice, item in enumerate(dados, start=1)]


def salvar_questoes(
    questoes: list[dict],
    caminho: str | Path | None = None,
    com_backup: bool = True,
) -> Path:
    alvo = Path(caminho) if caminho else CAMINHO_PADRAO
    alvo.parent.mkdir(parents=True, exist_ok=True)

    if com_backup and alvo.exists():
        PASTA_BACKUP.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        destino = PASTA_BACKUP / f"{alvo.stem}_{carimbo}{alvo.suffix}"
        shutil.copy2(alvo, destino)

    renumerar(questoes)
    temporario = alvo.with_suffix(alvo.suffix + ".tmp")
    with temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(questoes, arquivo, ensure_ascii=False, indent=2)
    temporario.replace(alvo)
    return alvo


def mesclar(existentes: list[dict], novas: list[dict]) -> tuple[list[dict], dict]:
    indice = {q.get("codigo"): q for q in existentes if q.get("codigo")}
    criadas = atualizadas = 0

    for bruta in novas:
        nova = normalizar_questao(bruta)
        codigo = nova.get("codigo")
        if not codigo:
            continue
        atual = indice.get(codigo)
        if atual is None:
            indice[codigo] = nova
            existentes.append(nova)
            criadas += 1
            continue
        atualizadas += 1
        for campo in ("gabarito", "gabarito_copilot"):
            if not atual.get(campo) and nova.get(campo):
                atual[campo] = nova[campo]
        for campo in ("explicacao", "explicacao_copilot"):
            if not atual.get(campo) and nova.get(campo):
                atual[campo] = nova[campo]
        if nova.get("imagens") and not atual.get("imagens"):
            atual["imagens"] = nova["imagens"]
            atual["possui_imagem"] = True
        for campo in ("tema", "assunto", "concurso", "cargo", "banca", "url"):
            if (not atual.get(campo) or atual.get(campo) in ("", "Não informado")) and nova.get(campo):
                atual[campo] = nova[campo]

    renumerar(existentes)
    return existentes, {"novas": criadas, "atualizadas": atualizadas, "total": len(existentes)}
