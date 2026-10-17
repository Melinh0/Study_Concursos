from __future__ import annotations

import queue
import threading

import customtkinter as ctk

from .. import concursos, dados
from ..banco import BancoProgresso
from . import tema
from .aba_estudo import AbaEstudo
from .aba_extrator import AbaExtrator


class Aplicacao(ctk.CTk):
    def __init__(self):
        super().__init__()
        tema.aplicar()
        self.title("Study Concursos")
        self._definir_limites()

        self.chave_concurso = concursos.listar()[0]["chave"]
        self.banco = BancoProgresso(concursos.caminho_banco(self.chave_concurso))
        self.questoes: list[dict] = []
        self.fila: queue.Queue = queue.Queue()
        self._total_questoes = 0
        self._wrap_atual = 0
        self._status_atual: str | None = None

        self._criar_barra_concurso()

        abas = ctk.CTkTabview(self, anchor="nw")
        abas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        abas.add("Estudo")
        abas.add("Extrator QConcursos")

        self.aba_estudo = AbaEstudo(
            abas.tab("Estudo"), self.banco, ao_salvar=self.salvar_banco_questoes, publicar=self.fila.put
        )
        self.aba_estudo.pack(fill="both", expand=True)
        self.aba_extrator = AbaExtrator(
            abas.tab("Extrator QConcursos"),
            self.fila.put,
            self._ao_importar,
            obter_caminho=lambda: concursos.caminho_json(self.chave_concurso),
            obter_chave=lambda: self.chave_concurso,
        )
        self.aba_extrator.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self.ao_fechar)
        self.recarregar_questoes()
        self.bind("<Configure>", self._ao_redimensionar, add=True)
        self.after(200, self.processar_fila)

    def _definir_limites(self):
        escala = self._get_window_scaling()
        largura_tela = self.winfo_screenwidth() / escala
        altura_tela = self.winfo_screenheight() / escala
        largura = int(min(1240, max(640, largura_tela * 0.6)))
        altura = int(min(880, max(400, altura_tela * 0.75)))
        self.geometry(f"{largura}x{altura}")
        self.minsize(
            min(640, int(largura_tela / 2)),
            min(430, int(altura_tela / 2)),
        )

    def _ao_redimensionar(self, event):
        if event.widget is not self:
            return
        self._atualizar_status_concurso()
        wrap = max(220, event.width - 150)
        if abs(wrap - self._wrap_atual) >= 24:
            self._wrap_atual = wrap
            self.aba_estudo.definir_wraplength(wrap)

    def _atualizar_status_concurso(self):
        info = concursos.obter(self.chave_concurso)
        if self.winfo_width() >= 1000:
            texto = f"{self._total_questoes} questão(ões) — banco: {info['arquivo']}"
        else:
            texto = f"{self._total_questoes} questão(ões)"
        if texto != self._status_atual:
            self._status_atual = texto
            self.rotulo_concurso.configure(text=texto)

    def _rotulos_concursos(self) -> list[str]:
        return [f"{item['rotulo']} — {item['descricao']}" for item in concursos.listar()]

    def _criar_barra_concurso(self):
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=12, pady=12)
        barra.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(barra, text="Concurso:", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w"
        )
        rotulos = self._rotulos_concursos()
        self.menu_concurso = ctk.CTkOptionMenu(
            barra, values=rotulos, command=self._ao_trocar_concurso
        )
        self.menu_concurso.set(rotulos[0])
        self.menu_concurso.grid(row=0, column=1, sticky="ew", padx=8)
        self.rotulo_concurso = ctk.CTkLabel(barra, text="", text_color="#F26B21", anchor="e")
        self.rotulo_concurso.grid(row=0, column=2, sticky="e")

    def _ao_importar(self, chave: str | None):
        if not chave:
            self.recarregar_questoes()
            return
        self._focar_concurso(chave)

    def _focar_concurso(self, chave: str):
        info = concursos.obter(chave)
        exibicao = f"{info['rotulo']} — {info['descricao']}"
        self.menu_concurso.configure(values=self._rotulos_concursos())
        self.menu_concurso.set(exibicao)
        if chave == self.chave_concurso:
            self.recarregar_questoes()
        else:
            self._ao_trocar_concurso(exibicao)

    def _chave_do_rotulo(self, rotulo: str) -> str:
        for item in concursos.listar():
            if f"{item['rotulo']} — {item['descricao']}" == rotulo:
                return item["chave"]
        return self.chave_concurso

    def _ao_trocar_concurso(self, rotulo: str):
        nova_chave = self._chave_do_rotulo(rotulo)
        if nova_chave == self.chave_concurso:
            return
        if self.aba_extrator.extraindo:
            self.menu_concurso.set(
                f"{concursos.obter(self.chave_concurso)['rotulo']} — "
                f"{concursos.obter(self.chave_concurso)['descricao']}"
            )
            return
        self.chave_concurso = nova_chave
        self.banco.fechar()
        self.banco = BancoProgresso(concursos.caminho_banco(nova_chave))
        self.aba_estudo.trocar_banco(self.banco)
        self.recarregar_questoes()

    def recarregar_questoes(self):
        caminho = concursos.caminho_json(self.chave_concurso)
        self.questoes = dados.carregar_questoes(caminho)
        edicoes = self.banco.carregar_edicoes()
        for questao in self.questoes:
            for campo, valor in edicoes.get(questao.get("numero", 0), {}).items():
                if campo in questao:
                    questao[campo] = valor
        self._total_questoes = len(self.questoes)
        self._atualizar_status_concurso()
        self.aba_estudo.definir_questoes(self.questoes)

    def salvar_banco_questoes(self):
        caminho = concursos.caminho_json(self.chave_concurso)
        dados.salvar_questoes(self.questoes, caminho, com_backup=True)

    def processar_fila(self):
        try:
            while True:
                pacote = self.fila.get_nowait()
                try:
                    self._despachar(pacote)
                except Exception as erro:
                    self.aba_extrator.registrar(
                        f"Falha ao processar a mensagem '{pacote[0]}': {erro}", "erro"
                    )
        except queue.Empty:
            pass
        finally:
            self.after(200, self.processar_fila)

    def _despachar(self, pacote: tuple):
        tipo = pacote[0]
        if tipo == "log":
            self.aba_extrator.registrar(pacote[1], pacote[2])
        elif tipo == "progresso":
            self.aba_extrator.definir_progresso(pacote[1], pacote[2], pacote[3])
        elif tipo == "atualizar":
            self.aba_extrator.atualizar_previa(pacote[1])
        elif tipo == "fim":
            self.aba_extrator.finalizar(pacote[1])
        elif tipo == "erro_extracao":
            self.aba_extrator.falha(pacote[1])
        elif tipo == "busca":
            self.aba_extrator.receber_busca(pacote[1], pacote[2])
        elif tipo == "busca_erro":
            self.aba_extrator.receber_erro_busca(pacote[1], pacote[2])
        elif tipo == "busca_callback":
            callback = pacote[1]
            resultados = pacote[2]
            callback(resultados)
        elif tipo == "curso":
            self.aba_extrator.ao_encontrar_curso(pacote[1], pacote[2])
        elif tipo == "assuntos_curso":
            self.aba_extrator.ao_receber_assuntos(pacote[1], pacote[2])
        elif tipo == "ano":
            self.aba_extrator.preencher_ano(pacote[1])
        elif tipo == "login":
            self._dialogar_login(pacote[1])
        elif tipo == "ia_pronta":
            self.aba_estudo.aplicar_resolucao_ia(pacote[1], pacote[2])
        elif tipo == "ia_erro":
            self.aba_estudo.falha_ia(pacote[1])

    def _dialogar_login(self, evento: threading.Event):
        dialogo = ctk.CTkToplevel(self)
        dialogo.title("Login necessário")
        dialogo.geometry("500x220")
        dialogo.grab_set()
        ctk.CTkLabel(
            dialogo,
            text=(
                "O QConcursos pediu login para revelar o gabarito.\n\n"
                "Faça login na janela do Chrome e clique em Continuar.\n"
                "Sem login a extração continua, mas sem gabarito/explicação."
            ),
            justify="left",
        ).pack(padx=20, pady=20, anchor="w")
        ctk.CTkButton(
            dialogo, text="Continuar", command=lambda: (evento.set(), dialogo.destroy())
        ).pack(pady=10)
        dialogo.protocol("WM_DELETE_WINDOW", lambda: (evento.set(), dialogo.destroy()))

    def ao_fechar(self):
        self.aba_extrator.parar.set()
        self.banco.fechar()
        self.destroy()


def main():
    Aplicacao().mainloop()


if __name__ == "__main__":
    main()
