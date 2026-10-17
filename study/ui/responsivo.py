from __future__ import annotations

from typing import Callable, Iterable

Item = tuple[object, "int | tuple[int, int]"]


def _intervalos(padx: int | tuple[int, int]) -> tuple[int, int]:
    if isinstance(padx, tuple):
        return int(padx[0]), int(padx[1])
    return int(padx), 0


def _escalar(widget, valor: int) -> int:
    try:
        return int(widget._apply_widget_scaling(valor))
    except Exception:
        return valor


def _fator(widget) -> float:
    try:
        return float(widget._apply_widget_scaling(1.0))
    except Exception:
        return 1.0


def refluir(container, itens: Iterable[Item]) -> None:
    """Posiciona os itens em linhas (place), quebrando linha quando não cabem na largura.

    Usa place em vez de grid porque o grid compartilha colunas entre linhas: um item
    que quebra a linha não volta à esquerda (continua na coluna seguinte) ou infla a
    largura das colunas usadas por outras linhas. O place dá controle total de x/y e a
    altura do container é configurada manualmente (place não alimenta o req do frame).

    Coordenadas são calculadas em pixels físicos (unidades de winfo) e convertidas
    antes de chamar place, pois o customtkinter escala x/y internamente.
    """
    largura = container.winfo_width()
    if largura <= 1:
        return

    linhas: list[list[tuple[object, int, int]]] = []
    x = 0
    atual: list[tuple[object, int, int]] = []
    for widget, padx in itens:
        esquerda, direita = _intervalos(padx)
        esquerda, direita = _escalar(widget, esquerda), _escalar(widget, direita)
        consumo = esquerda + widget.winfo_reqwidth() + direita
        if atual and x + consumo > largura:
            linhas.append(atual)
            atual = []
            x = 0
        atual.append((widget, esquerda, direita))
        x += consumo
    if atual:
        linhas.append(atual)

    primeiro = linhas[0][0] if linhas and linhas[0] else container
    pady_vertical = _escalar(primeiro, 2)

    altura_total = 0
    for linha in linhas:
        altura_linha = max(
            widget.winfo_reqheight() + 2 * pady_vertical for widget, *_ in linha
        )
        x = 0
        for widget, esquerda, direita in linha:
            fator = _fator(widget)
            widget.place(
                x=round((x + esquerda) / fator),
                y=round((altura_total + pady_vertical) / fator),
                anchor="nw",
            )
            x += esquerda + widget.winfo_reqwidth() + direita
        altura_total += altura_linha

    container.configure(height=round(altura_total / _fator(container)))


def vigiar(container, acao: Callable[[], None]) -> None:
    """Executa `acao` quando a largura do container muda (Configure do canvas interno)."""
    ultima_largura = {"valor": -1}

    def tratar(event):
        if event.width == ultima_largura["valor"]:
            return
        ultima_largura["valor"] = event.width
        acao()

    container.bind("<Configure>", tratar, add=True)
