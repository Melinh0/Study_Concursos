from __future__ import annotations

from pathlib import Path

import customtkinter as ctk

ARQUIVO_TEMA = Path(__file__).resolve().parent / "tema_laranja.json"
MODOS = ("dark", "light", "system")


def aplicar(modo: str = "dark") -> None:
    if modo not in MODOS:
        modo = "dark"
    ctk.set_appearance_mode(modo)
    ctk.set_default_color_theme(str(ARQUIVO_TEMA))
