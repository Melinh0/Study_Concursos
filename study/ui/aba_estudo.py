from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from .. import ia
from . import responsivo

LETRAS = ("A", "B", "C", "D", "E")


class AbaEstudo(ctk.CTkFrame):
    def __init__(self, master, banco, ao_salvar=None, publicar=None):
        super().__init__(master, fg_color="transparent")
        self.banco = banco
        self.ao_salvar = ao_salvar or (lambda: None)
        self.publicar = publicar or (lambda p: None)
        self.questoes: list[dict] = []
        self.filtradas: list[dict] = []
        self.indice = 0
        self.modo_edicao = "nenhum"
        self.respostas: dict[int, dict] = banco.carregar_respostas()
        self.selecao = tk.StringVar(value="")
        self.gerando_ia = False
        self._wraplength = 800

        self._criar_filtros()
        self._criar_conteudo()
        self._criar_acoes()
        self.atualizar_estatisticas()

    def _criar_filtros(self):
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", pady=(0, 4))

        itens = []
        itens.append((ctk.CTkLabel(barra, text="Tema:"), 0))
        self.filtro_tema = ctk.CTkOptionMenu(
            barra, width=220, values=["Todas"], command=lambda _: self.aplicar_filtros()
        )
        itens.append((self.filtro_tema, (6, 14)))
        itens.append((ctk.CTkLabel(barra, text="Concurso:"), 0))
        self.filtro_concurso = ctk.CTkOptionMenu(
            barra, width=220, values=["Todos"], command=lambda _: self.aplicar_filtros()
        )
        itens.append((self.filtro_concurso, (6, 14)))
        self.botao_anterior = ctk.CTkButton(
            barra, text="← Anterior", width=95, command=self.questao_anterior
        )
        itens.append((self.botao_anterior, (0, 6)))
        self.botao_proxima = ctk.CTkButton(
            barra, text="Próxima →", width=95, command=self.questao_proxima
        )
        itens.append((self.botao_proxima, 0))
        responsivo.vigiar(barra, lambda: responsivo.refluir(barra, itens))

        barra2 = ctk.CTkFrame(self, fg_color="transparent")
        barra2.pack(fill="x", pady=(0, 8))
        self.rotulo_stats = ctk.CTkLabel(barra2, text="Acertos: 0/0 (0%)", text_color="#F26B21")
        self.rotulo_stats.pack(side="left")
        self.rotulo_posicao = ctk.CTkLabel(barra2, text="Nenhuma questão carregada")
        self.rotulo_posicao.pack(side="right", padx=(14, 0))

    def _criar_conteudo(self):
        envol = ctk.CTkFrame(self, fg_color="transparent", height=80)
        envol.pack(fill="both", expand=True)
        envol.pack_propagate(False)
        rolagem = ctk.CTkScrollableFrame(envol)
        rolagem.pack(fill="both", expand=True)
        rolagem.columnconfigure(0, weight=1)

        self.rotulo_meta = ctk.CTkLabel(rolagem, text="", text_color="gray55", anchor="w")
        self.rotulo_meta.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.frame_exibicao_meta = ctk.CTkFrame(rolagem, fg_color="transparent")
        self.frame_exibicao_meta.grid(row=1, column=0, sticky="ew")
        self.frame_exibicao_meta.columnconfigure(1, weight=1)
        self.rotulo_cargo = ctk.CTkLabel(self.frame_exibicao_meta, text="Cargo:", anchor="w")
        self.rotulo_cargo.grid(row=0, column=0, sticky="nw", padx=(0, 8))
        self.texto_cargo = ctk.CTkLabel(self.frame_exibicao_meta, text="", anchor="w")
        self.texto_cargo.grid(row=0, column=1, sticky="ew")

        self.frame_edicao_meta = ctk.CTkFrame(rolagem, fg_color="transparent")
        self.frame_edicao_meta.grid(row=1, column=0, sticky="ew")
        self.frame_edicao_meta.columnconfigure(1, weight=1)
        self.campos_meta: dict[str, ctk.CTkEntry] = {}
        for i, campo in enumerate(
            ("codigo", "banca", "concurso", "cargo", "tema", "assunto", "gabarito")
        ):
            ctk.CTkLabel(self.frame_edicao_meta, text=f"{campo.capitalize()}:", anchor="w").grid(
                row=i, column=0, sticky="nw", padx=(0, 8), pady=1
            )
            entrada = ctk.CTkEntry(self.frame_edicao_meta)
            entrada.grid(row=i, column=1, sticky="ew", pady=1)
            self.campos_meta[campo] = entrada
            self.cor_texto_entry = entrada.cget("text_color")
        self.frame_edicao_meta.grid_remove()

        ctk.CTkLabel(rolagem, text="Enunciado:", anchor="w").grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.caixa_enunciado = ctk.CTkTextbox(rolagem, height=170, wrap="word")
        self.caixa_enunciado.grid(row=3, column=0, sticky="ew", pady=(2, 8))
        self.cor_enunciado = self.caixa_enunciado.cget("fg_color")
        self.cor_texto_enunciado = self.caixa_enunciado.cget("text_color")

        self.alternativas: dict[str, ctk.CTkRadioButton] = {}
        self.rotulos_alternativas: dict[str, ctk.CTkLabel] = {}
        self.campos_alternativa: dict[str, ctk.CTkEntry] = {}
        for indice, letra in enumerate(LETRAS, start=4):
            linha = ctk.CTkFrame(rolagem, fg_color="transparent")
            linha.grid(row=indice, column=0, sticky="ew", pady=3)
            linha.columnconfigure(1, weight=1)
            radio = ctk.CTkRadioButton(
                linha, text=letra, width=40, variable=self.selecao, value=letra,
                command=self.ao_selecionar, border_width_checked=6, border_width_unchecked=3,
            )
            radio.grid(row=0, column=0, sticky="nw", padx=(0, 8))
            rotulo = ctk.CTkLabel(linha, text="", anchor="w", justify="left", wraplength=800, font=("Segoe UI", 12))
            rotulo.grid(row=0, column=1, sticky="ew", padx=(8, 0))
            entrada = ctk.CTkEntry(linha, font=("Segoe UI", 12))
            entrada.grid(row=0, column=1, sticky="ew", padx=(8, 0))
            entrada.grid_remove()
            self.alternativas[letra] = radio
            self.rotulos_alternativas[letra] = rotulo
            self.campos_alternativa[letra] = entrada

        caixa_resposta = ctk.CTkFrame(rolagem, fg_color="transparent")
        caixa_resposta.grid(row=9, column=0, sticky="ew", pady=(10, 0))
        caixa_resposta.columnconfigure(0, weight=1)
        ctk.CTkLabel(caixa_resposta, text="RESPOSTA E EXPLICAÇÃO", anchor="w").grid(
            row=0, column=0, sticky="ew"
        )
        self.caixa_resposta = ctk.CTkTextbox(caixa_resposta, height=170, wrap="word")
        self.caixa_resposta.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        caixa_resposta.rowconfigure(1, weight=1)
        self.cor_resposta = self.caixa_resposta.cget("fg_color")
        self.cor_texto_resposta = self.caixa_resposta.cget("text_color")

    def _criar_acoes(self):
        acoes = ctk.CTkFrame(self, fg_color="transparent")
        acoes.pack(fill="x", pady=(8, 0))

        self.botao_editar = ctk.CTkButton(
            acoes, text="Editar enunciado", width=140, command=lambda: self.alternar_edicao("basico")
        )
        self.botao_editar_completo = ctk.CTkButton(
            acoes, text="Edição completa", width=130, command=lambda: self.alternar_edicao("completo")
        )
        self.botao_editar_gabarito = ctk.CTkButton(
            acoes, text="Gabarito/Explicação", width=140, command=lambda: self.alternar_edicao("gabarito")
        )
        self.cor_padrao_botao = self.botao_editar.cget("fg_color")
        self.cor_padrao_botao_hover = self.botao_editar.cget("hover_color")

        self.botao_confirmar = ctk.CTkButton(
            acoes, text="Confirmar", width=100, command=self.confirmar_resposta, state="disabled"
        )
        self.botao_ver_resposta = ctk.CTkButton(
            acoes, text="Ver resposta", width=110, command=self.mostrar_resposta
        )
        itens_acoes = [
            (self.botao_editar, (0, 5)),
            (self.botao_editar_completo, (0, 5)),
            (self.botao_editar_gabarito, (0, 5)),
            (self.botao_confirmar, (0, 5)),
            (self.botao_ver_resposta, 0),
        ]
        responsivo.vigiar(acoes, lambda: responsivo.refluir(acoes, itens_acoes))

        acoes2 = ctk.CTkFrame(self, fg_color="transparent")
        acoes2.pack(fill="x", pady=(5, 0))
        self.botao_ia = ctk.CTkButton(
            acoes2, text="Gerar resolução com IA", width=180, fg_color="#2E7D32", hover_color="#1B5E20",
            command=self.gerar_resolucao_ia,
        )
        self.botao_abrir_site = ctk.CTkButton(
            acoes2, text="Abrir no QConcursos", width=160, command=self.abrir_no_site
        )
        self.botao_limpar = ctk.CTkButton(
            acoes2, text="Limpar progresso", width=130, fg_color="#8B2E2E", hover_color="#6E2323",
            command=self.limpar_progresso,
        )
        itens_acoes2 = [
            (self.botao_ia, (0, 5)),
            (self.botao_abrir_site, (0, 5)),
            (self.botao_limpar, 0),
        ]
        responsivo.vigiar(acoes2, lambda: responsivo.refluir(acoes2, itens_acoes2))

    def definir_wraplength(self, largura: int):
        if largura == self._wraplength:
            return
        self._wraplength = largura
        for rotulo in self.rotulos_alternativas.values():
            rotulo.configure(wraplength=largura)

    def trocar_banco(self, banco):
        self.banco = banco
        self.respostas = banco.carregar_respostas()
        self.indice = 0
        self.selecao.set("")
        self.atualizar_estatisticas()

    def _valores_filtros(self) -> tuple[list[str], list[str]]:
        temas = ["Todas"] + sorted({q.get("tema", "Sem Tema") for q in self.questoes})
        concursos = ["Todos"] + sorted(
            {q.get("concurso", "Não informado") for q in self.questoes}
        )
        return temas, concursos

    def definir_questoes(self, questoes: list[dict]):
        self.questoes = list(questoes)
        temas, concursos = self._valores_filtros()
        self.filtro_tema.configure(values=temas)
        self.filtro_concurso.configure(values=concursos)
        self.filtro_tema.set("Todas")
        self.filtro_concurso.set("Todos")
        self.aplicar_filtros()

    def aplicar_filtros(self):
        tema = self.filtro_tema.get()
        concurso = self.filtro_concurso.get()
        self.filtradas = [
            q for q in self.questoes
            if (tema == "Todas" or q.get("tema") == tema)
            and (concurso == "Todos" or q.get("concurso") == concurso)
        ]
        self.indice = 0
        self.mostrar_questao()

    def _questao_atual(self) -> dict | None:
        if not self.filtradas:
            return None
        return self.filtradas[self.indice]

    def _gabarito_de(self, questao: dict) -> str:
        return (questao.get("gabarito") or questao.get("gabarito_copilot") or "").strip()

    def _explicacao_de(self, questao: dict) -> str:
        return (questao.get("explicacao") or questao.get("explicacao_copilot") or "").strip()

    def mostrar_questao(self):
        questao = self._questao_atual()
        if questao is None:
            self.rotulo_posicao.configure(text="Nenhuma questão encontrada")
            self.rotulo_meta.configure(text="")
            self.caixa_enunciado.configure(state="normal")
            self.caixa_enunciado.delete("1.0", "end")
            self.caixa_enunciado.configure(state="disabled")
            self.caixa_resposta.configure(state="normal")
            self.caixa_resposta.delete("1.0", "end")
            self.caixa_resposta.configure(state="disabled")
            return

        if self.modo_edicao != "nenhum":
            self._sair_edicao(salvar=False)

        numero = questao.get("numero", 0)
        ja_respondida = self.respostas.get(numero)
        situacao = ""
        if ja_respondida:
            situacao = " ✅" if ja_respondida["correta"] else " ❌"
        filtro = self.filtro_tema.get()
        sufixo = f" ({filtro})" if filtro != "Todas" else ""
        self.rotulo_posicao.configure(
            text=f"Questão {self.indice + 1}/{len(self.filtradas)} de {len(self.questoes)}{sufixo}{situacao}"
        )
        self.rotulo_meta.configure(
            text=f"Código: {questao.get('codigo', '')}  |  Banca: {questao.get('banca', '')}"
            f"  |  Concurso: {questao.get('concurso', '')}  |  Assunto: {questao.get('assunto', '')}"
        )
        self.texto_cargo.configure(text=questao.get("cargo") or "—")

        self.caixa_enunciado.configure(state="normal")
        self.caixa_enunciado.delete("1.0", "end")
        self.caixa_enunciado.insert("1.0", questao.get("enunciado", ""))
        self.caixa_enunciado.configure(state="disabled")

        alternativas = questao.get("alternativas", {})
        for letra, radio in self.alternativas.items():
            texto = alternativas.get(letra, "")
            cor = "white" if texto else "gray70"
            radio.configure(state="normal" if texto else "disabled", text_color=cor)
            self.rotulos_alternativas[letra].configure(text=texto if texto else "—", text_color=cor)
            if not texto and self.selecao.get() == letra:
                self.selecao.set("")

        if ja_respondida:
            self.selecao.set(ja_respondida["resposta"])
        else:
            self.selecao.set("")

        self.caixa_resposta.configure(state="normal")
        self.caixa_resposta.delete("1.0", "end")
        self.caixa_resposta.configure(state="disabled")
        self.botao_confirmar.configure(state="disabled")
        self.atualizar_navegacao()

    def atualizar_navegacao(self):
        self.botao_anterior.configure(state="normal" if self.indice > 0 else "disabled")
        self.botao_proxima.configure(
            state="normal" if self.indice < len(self.filtradas) - 1 else "disabled"
        )

    def questao_proxima(self):
        if self.indice < len(self.filtradas) - 1:
            self.indice += 1
            self.mostrar_questao()

    def questao_anterior(self):
        if self.indice > 0:
            self.indice -= 1
            self.mostrar_questao()

    def ao_selecionar(self):
        questao = self._questao_atual()
        if questao and questao.get("numero") not in self.respostas:
            self.botao_confirmar.configure(state="normal")

    def confirmar_resposta(self):
        questao = self._questao_atual()
        if questao is None:
            return
        escolhida = self.selecao.get()
        if not escolhida:
            messagebox.showwarning("Atenção", "Selecione uma alternativa antes de confirmar.")
            return
        correta = self._gabarito_de(questao)
        if not correta:
            messagebox.showinfo(
                "Sem gabarito",
                "Esta questão não tem gabarito cadastrado.\nUse 'Gabarito/Explicação' para preencher "
                "ou gere a resolução com IA.",
            )
            return
        acertou = escolhida == correta
        numero = questao["numero"]
        self.banco.salvar_resposta(numero, escolhida, acertou)
        self.respostas[numero] = {"resposta": escolhida, "correta": acertou}
        self.botao_confirmar.configure(state="disabled")
        self.atualizar_estatisticas()
        if acertou:
            messagebox.showinfo("Resultado", "✅ Parabéns! Você acertou!")
        else:
            messagebox.showerror("Resultado", f"❌ Resposta incorreta!\nA resposta correta é: {correta}")
        self.mostrar_questao()

    def mostrar_resposta(self):
        questao = self._questao_atual()
        if questao is None:
            return
        if self.modo_edicao == "gabarito":
            self._sair_edicao(salvar=False)
        numero = questao.get("numero", 0)
        sua = self.respostas.get(numero, {}).get("resposta", "Nenhuma")
        texto = f"RESPOSTA CORRETA: {self._gabarito_de(questao) or 'não cadastrada'}\n"
        texto += f"SUA RESPOSTA: {sua}\n\n"
        explicacao = self._explicacao_de(questao)
        texto += f"EXPLICAÇÃO:\n{explicacao}" if explicacao else "Sem explicação. Gere com a IA ou edite."
        self.caixa_resposta.configure(state="normal")
        self.caixa_resposta.delete("1.0", "end")
        self.caixa_resposta.insert("1.0", texto)
        self.caixa_resposta.configure(state="disabled")

    def gerar_resolucao_ia(self):
        questao = self._questao_atual()
        if questao is None or self.gerando_ia:
            return
        self.gerando_ia = True
        self.botao_ia.configure(state="disabled", text="Gerando…")
        self.publicar(("log", f"IA: gerando resolução da {questao.get('codigo', '')}…", "info"))
        threading.Thread(target=self._gerar_ia_thread, args=(questao,), daemon=True).start()

    def _gerar_ia_thread(self, questao: dict):
        try:
            resultado = ia.resolver_questao(questao)
            self.publicar(("ia_pronta", questao, resultado))
        except Exception as erro:
            self.publicar(("ia_erro", str(erro)))

    def aplicar_resolucao_ia(self, questao: dict, resultado: dict):
        self.gerando_ia = False
        self.botao_ia.configure(state="normal", text="Gerar resolução com IA")
        explicacao = resultado.get("explicacao_ia", "")
        letra = resultado.get("gabarito_ia", "")
        questao["explicacao"] = explicacao
        if letra and not (questao.get("gabarito") or questao.get("gabarito_copilot")):
            questao["gabarito"] = letra
        self.ao_salvar()
        self.mostrar_questao()
        self.caixa_resposta.configure(state="normal")
        self.caixa_resposta.delete("1.0", "end")
        self.caixa_resposta.insert(
            "1.0", f"RESOLUÇÃO GERADA PELA IA (gabarito sugerido: {letra or 'n/d'})\n\n{explicacao}"
        )
        self.caixa_resposta.configure(state="disabled")
        self.publicar(("log", f"IA: resolução da {questao.get('codigo', '')} salva.", "info"))

    def falha_ia(self, mensagem: str):
        self.gerando_ia = False
        self.botao_ia.configure(state="normal", text="Gerar resolução com IA")
        self.publicar(("log", f"IA falhou: {mensagem}", "erro"))

    def abrir_no_site(self):
        questao = self._questao_atual()
        if questao and questao.get("url"):
            webbrowser.open(questao["url"])
        else:
            messagebox.showinfo("Sem endereço", "Esta questão não possui link para o QConcursos.")

    def atualizar_estatisticas(self):
        respondidas, acertos = self.banco.estatisticas()
        porcentagem = (acertos / respondidas * 100) if respondidas else 0.0
        self.rotulo_stats.configure(text=f"Acertos: {acertos}/{respondidas} ({porcentagem:.1f}%)")

    def alternar_edicao(self, modo: str):
        if self._questao_atual() is None:
            return
        if self.modo_edicao == modo:
            self._sair_edicao(salvar=True)
            return
        if self.modo_edicao != "nenhum":
            self._sair_edicao(salvar=True)
        self.modo_edicao = modo
        questao = self._questao_atual()
        cor_destaque = "#FFF6D5"

        if modo == "basico":
            self.botao_editar.configure(text="Salvar enunciado", fg_color="#2E7D32", hover_color="#1B5E20")
            self.caixa_enunciado.configure(state="normal", fg_color=cor_destaque, text_color="gray14")

        elif modo == "completo":
            self.botao_editar_completo.configure(text="Salvar tudo", fg_color="#2E7D32", hover_color="#1B5E20")
            self.frame_exibicao_meta.grid_remove()
            self.frame_edicao_meta.grid()
            for campo, entrada in self.campos_meta.items():
                entrada.delete(0, "end")
                valor = self._gabarito_de(questao) if campo == "gabarito" else questao.get(campo, "")
                entrada.insert(0, valor)
                entrada.configure(fg_color=cor_destaque, text_color="gray14")
            self.caixa_enunciado.configure(state="normal", fg_color=cor_destaque, text_color="gray14")
            for letra, entrada in self.campos_alternativa.items():
                entrada.delete(0, "end")
                entrada.insert(0, questao.get("alternativas", {}).get(letra, ""))
                entrada.configure(fg_color=cor_destaque, text_color="gray14")
                entrada.grid()
                self.rotulos_alternativas[letra].grid_remove()
                self.alternativas[letra].configure(state="disabled")

        elif modo == "gabarito":
            self.botao_editar_gabarito.configure(text="Salvar gabarito", fg_color="#2E7D32", hover_color="#1B5E20")
            self.caixa_resposta.configure(state="normal", fg_color=cor_destaque, text_color="gray14")
            gabarito = self._gabarito_de(questao)
            explicacao = self._explicacao_de(questao)
            self.caixa_resposta.delete("1.0", "end")
            self.caixa_resposta.insert(
                "1.0",
                f"Gabarito (letra A-E): {gabarito}\n\nEXPLICAÇÃO (edite abaixo):\n{explicacao}",
            )

    def _sair_edicao(self, salvar: bool):
        modo = self.modo_edicao
        if salvar:
            self._salvar_edicao(modo)
        questao = self._questao_atual()

        if modo == "basico":
            self.botao_editar.configure(
                text="Editar enunciado", fg_color=self.cor_padrao_botao, hover_color=self.cor_padrao_botao_hover
            )
            self.caixa_enunciado.configure(state="disabled", fg_color=self.cor_enunciado, text_color=self.cor_texto_enunciado)

        elif modo == "completo":
            self.botao_editar_completo.configure(
                text="Edição completa", fg_color=self.cor_padrao_botao, hover_color=self.cor_padrao_botao_hover
            )
            self.frame_edicao_meta.grid_remove()
            self.frame_exibicao_meta.grid()
            self.caixa_enunciado.configure(state="disabled", fg_color=self.cor_enunciado, text_color=self.cor_texto_enunciado)
            for letra, entrada in self.campos_alternativa.items():
                entrada.grid_remove()
                self.rotulos_alternativas[letra].grid()
                self.alternativas[letra].configure(state="normal")

        elif modo == "gabarito":
            self.botao_editar_gabarito.configure(
                text="Gabarito/Explicação", fg_color=self.cor_padrao_botao, hover_color=self.cor_padrao_botao_hover
            )
            self.caixa_resposta.configure(state="disabled", fg_color=self.cor_resposta, text_color=self.cor_texto_resposta)

        self.modo_edicao = "nenhum"
        if questao:
            self.mostrar_questao()

    def _salvar_edicao(self, modo: str):
        questao = self._questao_atual()
        if questao is None:
            return
        numero = questao["numero"]
        salvo = False

        def aplicar(campo, valor):
            nonlocal salvo
            if valor and valor != questao.get(campo, ""):
                self.banco.salvar_edicao(numero, campo, questao.get(campo, ""), valor)
                questao[campo] = valor
                salvo = True

        if modo in ("basico", "completo"):
            aplicar("enunciado", self.caixa_enunciado.get("1.0", "end").strip())

        if modo == "completo":
            for campo, entrada in self.campos_meta.items():
                valor = entrada.get().strip()
                if campo == "gabarito":
                    achado = next((c for c in valor.upper() if c in "ABCDE"), "")
                    if achado and achado != self._gabarito_de(questao):
                        self.banco.salvar_edicao(
                            numero, "gabarito_copilot", self._gabarito_de(questao), achado
                        )
                        questao["gabarito"] = achado
                        questao["gabarito_copilot"] = achado
                        salvo = True
                    continue
                aplicar(campo, valor)
            alternativas = questao.setdefault("alternativas", {})
            for letra, entrada in self.campos_alternativa.items():
                novo = entrada.get().strip()
                if novo and novo != alternativas.get(letra, ""):
                    self.banco.salvar_edicao(numero, f"alternativa_{letra}", alternativas.get(letra, ""), novo)
                    alternativas[letra] = novo
                    salvo = True

        if modo == "gabarito":
            texto = self.caixa_resposta.get("1.0", "end")
            aplicar("explicacao", texto.split("EXPLICAÇÃO", 1)[-1].replace("(edite abaixo):", "", 1).strip())
            for linha in texto.splitlines():
                if linha.strip().lower().startswith("gabarito"):
                    _, _, resto = linha.partition(":")
                    achado = next((c for c in resto.strip().upper() if c in "ABCDE"), "")
                    if achado and achado != self._gabarito_de(questao):
                        self.banco.salvar_edicao(numero, "gabarito_copilot", self._gabarito_de(questao), achado)
                        questao["gabarito"] = achado
                        questao["gabarito_copilot"] = achado
                        salvo = True
                    break

        if salvo:
            self.ao_salvar()
            temas, concursos = self._valores_filtros()
            self.filtro_tema.configure(values=temas)
            self.filtro_concurso.configure(values=concursos)
            if self.filtro_tema.get() not in temas:
                self.filtro_tema.set("Todas")
            if self.filtro_concurso.get() not in concursos:
                self.filtro_concurso.set("Todos")

    def limpar_progresso(self):
        confirmado = messagebox.askyesno(
            "Confirmar", "Tem certeza que deseja limpar todo o seu progresso?\nEsta ação não pode ser desfeita."
        )
        if not confirmado:
            return
        self.banco.limpar_respostas()
        self.respostas.clear()
        self.atualizar_estatisticas()
        self.mostrar_questao()
        messagebox.showinfo("Sucesso", "Progresso limpo com sucesso!")
