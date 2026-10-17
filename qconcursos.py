from __future__ import annotations

import argparse
import sys

from study import concursos, dados
from study.extrator import api
from study.extrator.extrator import ConfigExtracao, ExtratorQConcursos


def log(mensagem: str, nivel: str = "info") -> None:
    prefixo = {"erro": "ERRO", "aviso": "AVISO"}.get(nivel, "INFO")
    print(f"[{prefixo}] {mensagem}", flush=True)


def progresso(atual: int, total: int, texto: str) -> None:
    print(f"[PROGRESSO] {texto} ({atual}/{total})", flush=True)


def resolver_ou_falhar(termo: str, tipo: str) -> dict:
    item = api.resolver(termo, tipo)
    if item is None:
        log(f"Nada encontrado para '{termo}' ({tipo}).", "erro")
        sys.exit(1)
    log(f"{tipo.capitalize()}: {item['rotulo']} — {item['descricao']} (id {item['id']})")
    return item


def cmd_buscar(argumentos) -> None:
    for item in api.buscar(argumentos.termo, argumentos.tipo, limite=10):
        print(f"{item['id']:>8}  {item['rotulo']:<20} {item['descricao']}  ({item['pontuacao']})")


def cmd_extrair(argumentos) -> None:
    url_direta = ""
    if argumentos.url:
        url_direta = argumentos.url
    elif argumentos.concurso.startswith("http"):
        url_direta = argumentos.concurso
        argumentos.concurso = ""
    
    instituicao = None
    if argumentos.concurso:
        instituicao = resolver_ou_falhar(argumentos.concurso, "instituicao")

    if argumentos.apenas_listar:
        caminho_destino = None
    elif argumentos.arquivo:
        caminho_destino = argumentos.arquivo
    elif argumentos.banco:
        caminho_destino = concursos.caminho_json(argumentos.banco)
    else:
        rotulo = (instituicao or {}).get("rotulo", "")
        chave = concursos.chave_para(rotulo) if rotulo else None
        if chave is None and rotulo:
            chave = concursos.adicionar(rotulo, (instituicao or {}).get("descricao", ""))
            log(f"Novo concurso no seletor: {rotulo}")
        caminho_destino = (
            concursos.caminho_json(chave) if chave else dados.CAMINHO_PADRAO
        )
    codigos_salvos: set[str] = set()
    if caminho_destino:
        for existente in dados.carregar_questoes(caminho_destino):
            codigo = existente.get("codigo")
            if codigo:
                codigos_salvos.add(codigo)
        if codigos_salvos:
            log(
                f"{len(codigos_salvos)} questão(ões) já em {caminho_destino} "
                "— a extração trará apenas novas."
            )

    configuracao = ConfigExtracao(
        instituicao=instituicao,
        disciplina=resolver_ou_falhar(argumentos.disciplina, "disciplina") if argumentos.disciplina else None,
        banca=resolver_ou_falhar(argumentos.banca, "banca") if argumentos.banca else None,
        cargo=resolver_ou_falhar(argumentos.cargo, "cargo") if argumentos.cargo else None,
        assunto=resolver_ou_falhar(argumentos.assunto, "assunto") if argumentos.assunto else None,
        ano=argumentos.ano,
        url_direta=url_direta,
        max_questoes=argumentos.maximo,
        extrair_gabarito=not argumentos.sem_gabarito,
        extrair_explicacao=not argumentos.sem_explicacao,
        visivel=not argumentos.oculto,
        codigos_salvos=codigos_salvos,
    )
    extrator = ExtratorQConcursos(
        configuracao,
        ao_logar=log,
        ao_progresso=progresso,
    )
    questoes = extrator.executar()

    if not questoes:
        log("Nenhuma questão extraída.", "aviso")
        return
    if argumentos.apenas_listar:
        for questao in questoes:
            print(f"{questao['codigo']}  {questao['tema']}  gabarito={questao['gabarito'] or '-'}")
        return

    existentes = dados.carregar_questoes(caminho_destino)
    mescladas, resumo = dados.mesclar(existentes, questoes)
    destino = dados.salvar_questoes(mescladas, caminho_destino)
    log(f"Novas: {resumo['novas']} | Atualizadas: {resumo['atualizadas']} | Total: {resumo['total']}")
    log(f"Arquivo atualizado: {destino}")


def montar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrai questões do QConcursos e as adiciona ao banco de estudo."
    )
    subcomandos = parser.add_subparsers(dest="comando", required=True)

    buscar = subcomandos.add_parser("buscar", help="Procura um filtro (concurso, disciplina, banca…)")
    buscar.add_argument("termo", help="Nome ou sigla digitados pelo usuário")
    buscar.add_argument(
        "--tipo",
        default="instituicao",
        choices=("instituicao", "disciplina", "banca", "cargo", "assunto"),
    )
    buscar.set_defaults(func=cmd_buscar)

    extrair = subcomandos.add_parser("extrair", help="Extrai questões filtradas e atualiza o JSON")
    extrair.add_argument("concurso", help="Nome ou sigla do concurso (órgão/instituição)")
    extrair.add_argument("--disciplina", default="", help="Disciplina (ex.: Direito Administrativo)")
    extrair.add_argument("--banca", default="", help="Banca (ex.: FGV)")
    extrair.add_argument("--cargo", default="", help="Cargo (ex.: Analista)")
    extrair.add_argument("--assunto", default="", help="Assunto (ex.: Licitações)")
    extrair.add_argument("--ano", default=None, help="Ano de publicação da prova (ex.: 2024)")
    extrair.add_argument("--maximo", type=int, default=20, help="Quantidade máxima de questões")
    extrair.add_argument("--sem-gabarito", action="store_true", help="Não revela o gabarito (sem login)")
    extrair.add_argument("--sem-explicacao", action="store_true", help="Não coleta a explicação")
    extrair.add_argument("--oculto", action="store_true", help="Executa com o Chrome em segundo plano")
    extrair.add_argument("--apenas-listar", action="store_true", help="Mostra as questões sem salvar")
    extrair.add_argument("--url", default="", help="URL de listagem do QConcursos com filtros aplicados")
    extrair.add_argument(
        "--arquivo", default="", help="Caminho alternativo do JSON de questões (sobrepõe --banco)"
    )
    extrair.add_argument(
        "--banco",
        default="",
        choices=tuple(concursos.CONCURSOS),
        help="Banco local de destino (CPRM, IBGE ou TJ-CE)",
    )
    extrair.set_defaults(func=cmd_extrair)
    return parser


def main() -> None:
    argumentos = montar_parser().parse_args()
    argumentos.func(argumentos)


if __name__ == "__main__":
    main()
