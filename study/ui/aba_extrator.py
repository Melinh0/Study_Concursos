from __future__ import annotations

import threading
from tkinter import messagebox

import customtkinter as ctk

from .. import concursos, dados, ia
from ..extrator import api, cursos
from ..extrator.extrator import ConfigExtracao, ExtratorQConcursos, abrir_navegador_para_login


class CampoFiltro(ctk.CTkFrame):
    def __init__(self, master, rotulo: str, tipo: str, publicar, largura: int = 300):
        super().__init__(master, fg_color="transparent")
        self.tipo = tipo
        self.publicar = publicar
        self.selecionado: dict | None = None
        self._resultados: list[dict] = []

        ctk.CTkLabel(self, text=rotulo, width=90, anchor="w").pack(side="left")
        self.entrada = ctk.CTkEntry(
            self, width=largura, placeholder_text=f"Nome do(a) {rotulo.lower().rstrip(':')}"
        )
        self.entrada.pack(side="left", padx=(0, 6))
        self.botao = ctk.CTkButton(self, text="Buscar", width=70, command=self.buscar)
        self.botao.pack(side="left")
        self.menu = ctk.CTkOptionMenu(self, width=largura, command=self.ao_escolher)
        self.rotulo_status = ctk.CTkLabel(self, text="", text_color="#F26B21")

    def buscar(self):
        termo = self.entrada.get().strip()
        if not termo:
            return
        self.botao.configure(state="disabled", text="…")
        self.rotulo_status.pack_forget()
        threading.Thread(target=self._buscar_thread, args=(termo,), daemon=True).start()

    def _buscar_thread(self, termo: str):
        try:
            resultados = api.buscar(termo, self.tipo)
        except Exception as erro:
            self.publicar(("busca_erro", self.tipo, str(erro)))
            return
        self.publicar(("busca", self.tipo, resultados))

    def aplicar_resultado(self, resultados: list[dict]):
        self.botao.configure(state="normal", text="Buscar")
        self._resultados = resultados
        if not resultados:
            self.rotulo_status.configure(text="Nada encontrado")
            self.rotulo_status.pack(side="left", padx=(8, 0))
            return
        rotulos = [f"{item['rotulo']} — {item['descricao']}" for item in resultados]
        self.menu.configure(values=rotulos)
        self.menu.set(rotulos[0])
        self.menu.pack(side="left", padx=(8, 0))
        self.ao_escolher(rotulos[0])

    def mostrar_erro(self, mensagem: str):
        self.botao.configure(state="normal", text="Buscar")
        self.rotulo_status.configure(text=f"Erro: {mensagem[:40]}")
        self.rotulo_status.pack(side="left", padx=(8, 0))

    def ao_escolher(self, rotulo: str):
        for item in self._resultados:
            if f"{item['rotulo']} — {item['descricao']}" == rotulo or item.get("rotulo") == rotulo:
                self.selecionado = item
                return

    def aplicar_direto(self, item: dict):
        self._resultados = [item]
        self.selecionado = item
        self.menu.configure(values=[item["rotulo"]])
        self.menu.set(item["rotulo"])
        self.menu.pack(side="left", padx=(8, 0))
        self.rotulo_status.pack_forget()

    def limpar(self):
        self.selecionado = None
        self._resultados = []
        self.menu.pack_forget()
        self.rotulo_status.pack_forget()
        self.entrada.delete(0, "end")


class AbaExtrator(ctk.CTkFrame):
    def __init__(self, master, publicar, ao_importar, obter_caminho=None, obter_chave=None):
        super().__init__(master, fg_color="transparent")
        self.publicar = publicar
        self.ao_importar = ao_importar
        self.obter_caminho = obter_caminho or dados.CAMINHO_PADRAO
        self.obter_chave = obter_chave or (lambda: None)
        self.parar = threading.Event()
        self.extraindo = False
        self._thread_extracao: threading.Thread | None = None
        self.extraidas: list[dict] = []
        self.driver_login = None
        self._concurso_alvo: str | None = None
        self._disciplina_assuntos: str | None = None

        self._criar_filtros()
        self._criar_opcoes()
        self._criar_acoes()
        self._criar_saida()

    def _criar_filtros(self):
        painel = ctk.CTkFrame(self)
        painel.pack(fill="x", pady=(0, 8))
        painel.columnconfigure(1, weight=1)

        busca_frame = ctk.CTkFrame(painel, fg_color="transparent")
        busca_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        busca_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(busca_frame, text="Busca completa:", width=110, anchor="w").grid(
            row=0, column=0, sticky="w"
        )
        self.entrada_busca_completa = ctk.CTkEntry(
            busca_frame, placeholder_text="Ex.: Transpetro - Profissional Nível Superior - Análise Sistemas - Segurança Cibernética"
        )
        self.entrada_busca_completa.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.entrada_busca_completa.bind("<Return>", lambda e: self._buscar_e_extrair())
        ctk.CTkButton(
            busca_frame, text="Ano atual", width=80,
            command=self._preencher_ano_atual
        ).grid(row=0, column=2)

        self.entrada_ano = ctk.CTkEntry(busca_frame, width=80, placeholder_text="ex.: 2024")
        self.entrada_ano.grid(row=0, column=3, padx=(6, 0))

        self.botao_buscar_extrair = ctk.CTkButton(
            busca_frame, text="🔍 Buscar curso", width=160,
            command=self._buscar_e_extrair, fg_color="#2E7D32", hover_color="#1B5E20"
        )
        self.botao_buscar_extrair.grid(row=0, column=4, padx=(8, 0))

        ctk.CTkLabel(busca_frame, text="URL do guia:", width=110, anchor="w").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.entrada_url_guia = ctk.CTkEntry(
            busca_frame,
            placeholder_text="https://app.qconcursos.com/b/guia-de-estudos/…/videoaulas/questoes",
        )
        self.entrada_url_guia.grid(row=1, column=1, columnspan=4, sticky="ew", pady=(6, 0))

        self.frame_disciplina_curso = ctk.CTkFrame(busca_frame, fg_color="transparent")
        self.frame_disciplina_curso.grid(
            row=2, column=0, columnspan=5, sticky="ew", pady=(6, 0)
        )
        linha_disciplina = ctk.CTkFrame(self.frame_disciplina_curso, fg_color="transparent")
        linha_disciplina.pack(fill="x")
        ctk.CTkLabel(
            linha_disciplina, text="Disciplinas do curso:", width=110, anchor="w"
        ).pack(side="left")
        self.menu_disciplina_curso = ctk.CTkOptionMenu(
            linha_disciplina, width=420, command=self._ao_escolher_disciplina_curso
        )
        self.menu_disciplina_curso.pack(side="left", padx=(8, 0))

        self.frame_assunto_curso = ctk.CTkFrame(self.frame_disciplina_curso, fg_color="transparent")
        ctk.CTkLabel(
            self.frame_assunto_curso, text="Assuntos da disciplina:", width=110, anchor="w"
        ).pack(side="left")
        self.menu_assunto_curso = ctk.CTkOptionMenu(
            self.frame_assunto_curso, width=420, command=self._ao_escolher_assunto_curso
        )
        self.menu_assunto_curso.pack(side="left", padx=(8, 0))
        self.frame_disciplina_curso.grid_remove()

        self.campos: dict[str, CampoFiltro] = {}
        linhas = [
            ("concurso_instituicao", "Concurso:", "instituicao"),
            ("disciplina", "Disciplina:", "disciplina"),
            ("banca", "Banca:", "banca"),
            ("cargo", "Cargo:", "cargo"),
            ("assunto", "Assunto:", "assunto"),
        ]
        for indice, (chave, rotulo, tipo) in enumerate(linhas):
            campo = CampoFiltro(painel, rotulo, tipo, self.publicar)
            campo.grid(row=indice + 1, column=0, sticky="w", pady=3)
            self.campos[chave] = campo

        extras = ctk.CTkFrame(painel, fg_color="transparent")
        extras.grid(row=1, column=1, sticky="ne", padx=(20, 0), rowspan=len(linhas) + 1)

        quantidade = ctk.CTkFrame(extras, fg_color="transparent")
        quantidade.pack(anchor="e", pady=3)
        ctk.CTkLabel(quantidade, text="Máx. questões:", width=90, anchor="w").pack(side="left")
        self.entrada_quantidade = ctk.CTkEntry(quantidade, width=100)
        self.entrada_quantidade.insert(0, "20")
        self.entrada_quantidade.pack(side="left")

    def _preencher_ano_atual(self):
        from datetime import datetime
        ano_atual = str(datetime.now().year)
        self.entrada_ano.delete(0, "end")
        self.entrada_ano.insert(0, ano_atual)
        self.registrar(f"Ano preenchido automaticamente: {ano_atual}")

    def preencher_ano(self, ano):
        ano = str(ano or "").strip()
        if not ano or self.entrada_ano.get().strip() == ano:
            return
        self.entrada_ano.delete(0, "end")
        self.entrada_ano.insert(0, ano)
        self.registrar(f"Ano da prova preenchido automaticamente: {ano}")

    def _buscar_e_extrair(self):
        termo = self.entrada_busca_completa.get().strip()
        if not termo:
            if self.entrada_url_guia.get().strip():
                self.iniciar()
                return
            self.registrar(
                "Digite o nome completo do curso (ex.: 'Transpetro - Profissional de Nível "
                "Superior - Análise de Sistemas - Segurança Cibernética e da Informação')"
            )
            return
        self.registrar(f"Procurando o curso no QConcursos: {termo}")
        self._limpar_assunto_curso()
        self.frame_disciplina_curso.grid_remove()
        self._set_loading(True)
        threading.Thread(target=self._buscar_curso_thread, args=(termo,), daemon=True).start()

    def _buscar_curso_thread(self, termo: str):
        visivel = not bool(self.chk_headless.get())
        try:
            curso = cursos.buscar_curso(
                termo,
                visivel=visivel,
                ao_logar=lambda texto: self.publicar(("log", texto, "info")),
            )
        except Exception as erro:
            self.publicar(("log", f"Busca de curso falhou: {erro}", "aviso"))
            self.publicar(("curso", None, termo))
            return
        if curso:
            self.publicar(("log", f"Curso encontrado: {curso['nome']}", "info"))
        else:
            self.publicar(("log", "Curso não encontrado na busca do QConcursos.", "aviso"))
        self.publicar(("curso", curso, termo))

    def ao_encontrar_curso(self, curso: dict | None, termo: str):
        self._set_loading(False)
        if not curso:
            self._buscar_e_extrair_classico(termo)
            return
        tinha_filtro = bool(
            self.campos["disciplina"].selecionado or self.campos["assunto"].selecionado
        )
        self.campos["disciplina"].limpar()
        self.campos["assunto"].limpar()
        self._limpar_assunto_curso()
        if tinha_filtro:
            self.registrar("Filtros anteriores de disciplina/assunto limpos.")
        self.entrada_url_guia.delete(0, "end")
        self.entrada_url_guia.insert(0, curso["url_guia"])
        self.registrar(f"URL do guia preenchida: {curso['url_guia']}")
        self.preencher_ano(curso.get("ano"))
        instituicao = curso.get("instituicao") or {}
        self._concurso_alvo = instituicao.get("rotulo")
        for chave in ("concurso_instituicao", "banca", "cargo"):
            item = curso.get({"concurso_instituicao": "instituicao"}.get(chave, chave))
            if item:
                self.campos[chave].aplicar_resultado([item])
                self.registrar(f"{chave} preenchido: {item['rotulo']}")
        disciplinas = curso.get("disciplinas") or []
        if disciplinas:
            opcoes = ["Todas as disciplinas"] + disciplinas
            self.menu_disciplina_curso.configure(values=opcoes)
            self.menu_disciplina_curso.set(opcoes[0])
            self.frame_disciplina_curso.grid()
            self.registrar(
                f"Disciplinas disponíveis ({len(disciplinas)}): {', '.join(disciplinas)}"
            )
            self.registrar(
                "Escolha uma disciplina no seletor (ou mantenha 'Todas') "
                "e clique em 'Iniciar extração'."
            )
        else:
            self.frame_disciplina_curso.grid()
            self.menu_disciplina_curso.configure(values=["Todas as disciplinas", "Digite manualmente…"])
            self.menu_disciplina_curso.set("Todas as disciplinas")
            self.registrar(
                "Não foi possível listar as disciplinas automaticamente. "
                "Selecione 'Digite manualmente…' para informar a disciplina, "
                "ou mantenha 'Todas as disciplinas' para extrair sem filtro.",
                "aviso",
            )

    def _ao_escolher_disciplina_curso(self, nome: str):
        self._limpar_assunto_curso()
        if nome == "Todas as disciplinas":
            self.campos["disciplina"].limpar()
            self.registrar("Disciplina: todas (sem filtro).")
            return
        if nome == "Digite manualmente…":
            self._solicitar_disciplina_manual()
            return
        item = {
            "id": "",
            "tipo": "disciplina",
            "rotulo": nome,
            "nome": nome,
            "descricao": "",
            "pontuacao": 100.0,
        }
        self.campos["disciplina"].aplicar_direto(item)
        self.registrar(f"Disciplina filtrada: {nome}")
        url_guia = self.entrada_url_guia.get().strip()
        if not url_guia:
            return
        self._disciplina_assuntos = nome
        visivel = not bool(self.chk_headless.get())
        threading.Thread(
            target=self._carregar_assuntos_thread, args=(url_guia, nome, visivel), daemon=True
        ).start()

    def _carregar_assuntos_thread(self, url_guia: str, disciplina: str, visivel: bool):
        try:
            assuntos = cursos.listar_assuntos(
                url_guia,
                disciplina,
                visivel=visivel,
                ao_logar=lambda texto: self.publicar(("log", texto, "info")),
            )
        except Exception as erro:
            self.publicar(("log", f"Assuntos de {disciplina} falharam: {erro}", "aviso"))
            self.publicar(("assuntos_curso", disciplina, []))
            return
        self.publicar(("assuntos_curso", disciplina, assuntos))

    def ao_receber_assuntos(self, disciplina: str, assuntos: list[str]):
        if disciplina != self._disciplina_assuntos:
            return
        if not assuntos:
            self.registrar(
                f"Não listei os assuntos de {disciplina} — selecione 'Digite manualmente…' ou mantenha 'Todos os assuntos'.",
                "aviso",
            )
            self.menu_assunto_curso.configure(values=["Todos os assuntos", "Digite manualmente…"])
            self.menu_assunto_curso.set("Todos os assuntos")
            self.frame_assunto_curso.pack(fill="x", pady=(4, 0))
            return
        opcoes = ["Todos os assuntos"] + assuntos
        self.menu_assunto_curso.configure(values=opcoes)
        self.menu_assunto_curso.set(opcoes[0])
        self.frame_assunto_curso.pack(fill="x", pady=(4, 0))
        preview = assuntos[:8]
        mais = "…" if len(assuntos) > 8 else ""
        self.registrar(
            f"Assuntos de {disciplina} ({len(assuntos)}): {', '.join(preview)}{mais}"
        )

    def _ao_escolher_assunto_curso(self, nome: str):
        if nome == "Todos os assuntos":
            self.campos["assunto"].limpar()
            self.registrar("Assunto: todos (sem filtro).")
            return
        if nome == "Digite manualmente…":
            self._solicitar_assunto_manual()
            return
        item = {
            "id": "",
            "tipo": "assunto",
            "rotulo": nome,
            "nome": nome,
            "descricao": "",
            "pontuacao": 100.0,
        }
        self.campos["assunto"].aplicar_direto(item)
        self.registrar(f"Assunto filtrado: {nome}")

    def _solicitar_disciplina_manual(self):
        dialogo = ctk.CTkToplevel(self)
        dialogo.title("Disciplina manual")
        dialogo.geometry("400x150")
        dialogo.grab_set()
        dialogo.transient(self)
        ctk.CTkLabel(dialogo, text="Nome da disciplina:").pack(pady=(15, 5), anchor="w", padx=20)
        entrada = ctk.CTkEntry(dialogo, width=360)
        entrada.pack(pady=(0, 15), padx=20)
        entrada.focus()

        def confirmar():
            nome = entrada.get().strip()
            dialogo.destroy()
            if not nome:
                self.menu_disciplina_curso.set("Todas as disciplinas")
                self.campos["disciplina"].limpar()
                self.registrar("Disciplina: todas (sem filtro).")
                return
            item = {
                "id": "",
                "tipo": "disciplina",
                "rotulo": nome,
                "nome": nome,
                "descricao": "",
                "pontuacao": 100.0,
            }
            self.campos["disciplina"].aplicar_direto(item)
            self.registrar(f"Disciplina filtrada (manual): {nome}")
            self.menu_disciplina_curso.configure(values=["Todas as disciplinas", "Digite manualmente…", nome])
            self.menu_disciplina_curso.set(nome)
            url_guia = self.entrada_url_guia.get().strip()
            if url_guia:
                self._disciplina_assuntos = nome
                visivel = not bool(self.chk_headless.get())
                threading.Thread(
                    target=self._carregar_assuntos_thread, args=(url_guia, nome, visivel), daemon=True
                ).start()

        entrada.bind("<Return>", lambda e: confirmar())
        ctk.CTkButton(dialogo, text="Confirmar", command=confirmar).pack(pady=(0, 15))
        ctk.CTkButton(dialogo, text="Cancelar", command=lambda: (self.menu_disciplina_curso.set("Todas as disciplinas"), dialogo.destroy()), fg_color="#8B2E2E").pack()

    def _solicitar_assunto_manual(self):
        dialogo = ctk.CTkToplevel(self)
        dialogo.title("Assunto manual")
        dialogo.geometry("400x150")
        dialogo.grab_set()
        dialogo.transient(self)
        ctk.CTkLabel(dialogo, text="Nome do assunto:").pack(pady=(15, 5), anchor="w", padx=20)
        entrada = ctk.CTkEntry(dialogo, width=360)
        entrada.pack(pady=(0, 15), padx=20)
        entrada.focus()

        def confirmar():
            nome = entrada.get().strip()
            dialogo.destroy()
            if not nome:
                self.menu_assunto_curso.set("Todos os assuntos")
                self.campos["assunto"].limpar()
                self.registrar("Assunto: todos (sem filtro).")
                return
            item = {
                "id": "",
                "tipo": "assunto",
                "rotulo": nome,
                "nome": nome,
                "descricao": "",
                "pontuacao": 100.0,
            }
            self.campos["assunto"].aplicar_direto(item)
            self.registrar(f"Assunto filtrado (manual): {nome}")
            self.menu_assunto_curso.configure(values=["Todos os assuntos", "Digite manualmente…", nome])
            self.menu_assunto_curso.set(nome)

        entrada.bind("<Return>", lambda e: confirmar())
        ctk.CTkButton(dialogo, text="Confirmar", command=confirmar).pack(pady=(0, 15))
        ctk.CTkButton(dialogo, text="Cancelar", command=lambda: (self.menu_assunto_curso.set("Todos os assuntos"), dialogo.destroy()), fg_color="#8B2E2E").pack()

    def _limpar_assunto_curso(self):
        self._disciplina_assuntos = None
        self.frame_assunto_curso.pack_forget()
        self.menu_assunto_curso.configure(values=["Todos os assuntos"])
        self.menu_assunto_curso.set("Todos os assuntos")
        self.campos["assunto"].limpar()

    def _buscar_e_extrair_classico(self, termo: str):
        partes = [p.strip() for p in termo.split(" - ") if p.strip()]
        if not partes:
            self._set_loading(False)
            return
        instituicao_termo = partes[0]
        restante = " - ".join(partes[1:])

        self.registrar(
            f"Busca por filtros: instituição='{instituicao_termo}', restante='{restante}'"
        )
        self._set_loading(True)

        self._buscas_pendentes = 3
        self._cargo_selecionado = None

        def _finalizar():
            self._buscas_pendentes -= 1
            if self._buscas_pendentes > 0:
                return
            self._set_loading(False)
            if self._cargo_selecionado and self._cargo_selecionado.get("pontuacao", 0) < 80:
                self.registrar(f"Cargo com baixa confiança ({self._cargo_selecionado.get('pontuacao', 0):.1f}) — usando apenas instituição")
                self.campos["cargo"].selecionado = None
                self.campos["cargo"].menu.pack_forget()
            self.iniciar()

        def on_inst_ok():
            if not restante:
                self._buscas_pendentes = 1
                _finalizar()
                return
            self._buscar_e_preencher_melhor("cargo", restante, on_ok=_finalizar)
            self._buscar_e_preencher_melhor("disciplina", restante, on_ok=_finalizar)
            self._buscar_e_preencher_melhor("assunto", restante, on_ok=_finalizar)

        def on_inst_vazio():
            self._buscas_pendentes = 1
            _finalizar()

        self._buscar_e_preencher(
            "concurso_instituicao", instituicao_termo, on_ok=on_inst_ok, on_vazio=on_inst_vazio
        )

    def _buscar_e_preencher_melhor(self, tipo: str, termo: str, on_ok=None):
        campo = self.campos[tipo] if tipo in self.campos else None
        if not campo:
            if on_ok:
                on_ok()
            return

        def callback(resultados):
            if resultados:
                melhor = max(resultados, key=lambda r: r.get("pontuacao", 0))
                campo.aplicar_resultado(resultados)
                for item in resultados:
                    if item.get("pontuacao", 0) == melhor.get("pontuacao", 0):
                        campo.selecionado = item
                        break
                self.registrar(f"{tipo} encontrado: {melhor['rotulo']} ({melhor.get('pontuacao', 0):.1f})")
                if tipo == "cargo":
                    self._cargo_selecionado = melhor
                    melhor["termo_original"] = termo
            else:
                self.registrar(f"Nenhum {tipo} encontrado para: {termo}")
            if on_ok:
                on_ok()

        threading.Thread(
            target=self._buscar_thread_com_callback, args=(termo, campo.tipo, callback), daemon=True
        ).start()

    def _set_loading(self, loading: bool):
        if loading:
            self.botao_buscar_extrair.configure(state="disabled", text="⏳ Buscando...")
        else:
            self.botao_buscar_extrair.configure(state="normal", text="🔍 Buscar curso")

    def _buscar_e_preencher(self, tipo: str, termo: str, on_ok=None, on_vazio=None):
        campo = self.campos[tipo] if tipo in self.campos else None
        if not campo:
            if on_vazio:
                on_vazio()
            return

        def callback(resultados):
            if resultados:
                campo.aplicar_resultado(resultados)
                self.registrar(f"{tipo} encontrado: {campo.selecionado['rotulo']}")
                if on_ok:
                    on_ok()
            else:
                self.registrar(f"Nenhum {tipo} encontrado para: {termo}")
                if on_vazio:
                    on_vazio()

        threading.Thread(
            target=self._buscar_thread_com_callback, args=(termo, campo.tipo, callback), daemon=True
        ).start()

    def _buscar_thread_com_callback(self, termo: str, tipo: str, callback):
        try:
            resultados = api.buscar(termo, tipo)
        except Exception as erro:
            self.publicar(("busca_erro", tipo, str(erro)))
            self.publicar(("busca_callback", callback, []))
            return
        self.publicar(("busca_callback", callback, resultados))

    def _criar_opcoes(self):
        opcoes = ctk.CTkFrame(self, fg_color="transparent")
        opcoes.pack(fill="x", pady=(0, 8))

        self.chk_gabarito = ctk.CTkCheckBox(opcoes, text="Extrair gabarito (requer login)")
        self.chk_gabarito.select()
        self.chk_gabarito.pack(side="left", padx=(0, 16))
        self.chk_explicacao = ctk.CTkCheckBox(opcoes, text="Extrair explicação (requer login)")
        self.chk_explicacao.select()
        self.chk_explicacao.pack(side="left", padx=(0, 16))
        self.chk_ia = ctk.CTkCheckBox(
            opcoes, text="Gerar resolução com IA", fg_color="#2E7D32", hover_color="#1B5E20"
        )
        self.chk_ia.select()
        self.chk_ia.pack(side="left", padx=(0, 16))
        self.chk_headless = ctk.CTkCheckBox(opcoes, text="Modo invisível (headless)")
        self.chk_headless.pack(side="left", padx=(0, 16))
        ctk.CTkButton(
            opcoes, text="Entrar no QConcursos", width=180, command=self.entrar_no_site
        ).pack(side="right")

    def _criar_acoes(self):
        acoes = ctk.CTkFrame(self, fg_color="transparent")
        acoes.pack(fill="x", pady=(0, 8))

        self.botao_iniciar = ctk.CTkButton(
            acoes, text="Iniciar extração", width=160, command=self.iniciar
        )
        self.botao_iniciar.pack(side="left", padx=(0, 6))
        self.botao_parar = ctk.CTkButton(
            acoes,
            text="Parar",
            width=90,
            fg_color="#8B2E2E",
            hover_color="#6E2323",
            command=self.parar_extracao,
            state="disabled",
        )
        self.botao_parar.pack(side="left")

        self.rotulo_progresso = ctk.CTkLabel(acoes, text="Pronto")
        self.rotulo_progresso.pack(side="right", padx=(0, 12))
        self.barra = ctk.CTkProgressBar(acoes)
        self.barra.pack(side="right", fill="x", expand=True, padx=(20, 0))
        self.barra.set(0)

    def _criar_saida(self):
        ctk.CTkLabel(self, text="PRÉVIA DA EXTRAÇÃO", anchor="w").pack(fill="x")
        self.caixa_log = ctk.CTkTextbox(self, height=190, wrap="none")
        self.caixa_log.pack(fill="both", expand=True, pady=(4, 6))

        rodape = ctk.CTkFrame(self, fg_color="transparent")
        rodape.pack(fill="x")
        self.rotulo_total = ctk.CTkLabel(rodape, text="0 questão(ões) extraída(s)", text_color="#F26B21")
        self.rotulo_total.pack(side="left")
        self.botao_importar = ctk.CTkButton(
            rodape,
            text="Adicionar ao meu banco",
            width=200,
            command=self.importar,
            state="disabled",
        )
        self.botao_importar.pack(side="right")

    def _resolver_chave_destino(self, criar: bool = False) -> str | None:
        campo_inst = self.campos["concurso_instituicao"].selecionado
        alvo = campo_inst.get("rotulo") if campo_inst else self._concurso_alvo
        if not alvo:
            return self.obter_chave()
        chave = concursos.chave_para(alvo)
        if chave is None and criar:
            descricao = campo_inst.get("descricao", "") if campo_inst else ""
            chave = concursos.adicionar(alvo, descricao)
            self.registrar(f"Novo concurso no seletor: {alvo}", "info")
        return chave

    def iniciar(self):
        recuperacao = False
        if self.extraindo:
            thread = self._thread_extracao
            if thread is not None and thread.is_alive():
                return
            recuperacao = True
            self.extraindo = False
            self.botao_parar.configure(state="disabled")
        instituicao = self.campos["concurso_instituicao"].selecionado
        url_direta = self.entrada_url_guia.get().strip()
        if instituicao is None and not url_direta:
            messagebox.showwarning(
                "Atenção",
                "Busque e selecione o concurso (instituição) ou informe a URL do guia de estudos.",
            )
            return

        try:
            maximo = int(self.entrada_quantidade.get().strip() or "20")
        except ValueError:
            maximo = 20
        ano = self.entrada_ano.get().strip() or None

        extrair_gabarito = bool(self.chk_gabarito.get())
        extrair_explicacao = bool(self.chk_explicacao.get())
        codigos_salvos: set[str] = set()
        incompletas = 0
        chave_destino = self._resolver_chave_destino(criar=True)
        try:
            caminho_banco = (
                concursos.caminho_json(chave_destino)
                if chave_destino
                else (self.obter_caminho() if callable(self.obter_caminho) else self.obter_caminho)
            )
            for existente in dados.carregar_questoes(caminho_banco):
                codigo = existente.get("codigo")
                if not codigo:
                    continue
                tem_gabarito = bool(
                    existente.get("gabarito") or existente.get("gabarito_copilot")
                )
                tem_explicacao = bool(
                    existente.get("explicacao") or existente.get("explicacao_copilot")
                )
                incompleta = (extrair_gabarito and not tem_gabarito) or (
                    extrair_explicacao and not tem_explicacao
                )
                if incompleta and existente.get("url"):
                    incompletas += 1
                    continue
                codigos_salvos.add(codigo)
        except Exception:
            codigos_salvos = set()
            incompletas = 0

        configuracao = ConfigExtracao(
            instituicao=instituicao,
            disciplina=self.campos["disciplina"].selecionado,
            banca=self.campos["banca"].selecionado,
            cargo=self.campos["cargo"].selecionado,
            assunto=self.campos["assunto"].selecionado,
            ano=ano,
            url_direta=url_direta,
            max_questoes=max(1, maximo),
            extrair_gabarito=extrair_gabarito,
            extrair_explicacao=extrair_explicacao,
            visivel=not bool(self.chk_headless.get()),
            codigos_salvos=codigos_salvos,
        )
        gerar_ia = bool(self.chk_ia.get())
        self.parar.clear()
        self.extraindo = True
        self.extraidas = []
        self.botao_iniciar.configure(state="disabled")
        self.botao_parar.configure(state="normal")
        self.botao_importar.configure(state="disabled")
        self.caixa_log.delete("1.0", "end")
        if recuperacao:
            self.registrar(
                "Extração anterior ficou presa — liberando para uma nova tentativa.",
                "aviso",
            )
        if codigos_salvos:
            self.registrar(
                f"{len(codigos_salvos)} questão(ões) já neste banco — "
                "a extração trará apenas novas.",
                "info",
            )
        if incompletas:
            self.registrar(
                f"{incompletas} questão(ões) já salvas estão sem gabarito/explicação — "
                "serão reextraídas para completar os dados que faltam.",
                "aviso",
            )

        extrator = ExtratorQConcursos(
            configuracao,
            ao_logar=lambda texto, nivel: self.publicar(("log", texto, nivel)),
            ao_progresso=lambda atual, total, texto: self.publicar(("progresso", atual, total, texto)),
            ao_atualizar=lambda lista: self.publicar(("atualizar", lista)),
            ao_pedir_login=self._esperar_login,
            ao_ano=lambda ano: self.publicar(("ano", ano)),
            parar=self.parar,
        )
        self._thread_extracao = threading.Thread(
            target=self._executar, args=(extrator, gerar_ia), daemon=True
        )
        self._thread_extracao.start()

    def _executar(self, extrator: ExtratorQConcursos, gerar_ia: bool):
        try:
            questoes = extrator.executar()
            if gerar_ia and questoes and not self.parar.is_set():
                self.publicar(("log", f"IA: gerando resolução de {len(questoes)} questão(ões)…", "info"))
                for indice, questao in enumerate(questoes, start=1):
                    if self.parar.is_set():
                        break
                    self.publicar(("progresso", indice, len(questoes), f"IA {indice}/{len(questoes)}"))
                    try:
                        resolvido = ia.resolver_questao(questao)
                    except Exception as erro:
                        self.publicar(("log", f"IA falhou na questão {questao.get('codigo', '')}: {erro}", "aviso"))
                        continue
                    questao["explicacao"] = resolvido["explicacao_ia"]
                    if resolvido["gabarito_ia"] and not (
                        questao.get("gabarito") or questao.get("gabarito_copilot")
                    ):
                        questao["gabarito"] = resolvido["gabarito_ia"]
                    self.publicar(("atualizar", questoes))
                self.publicar(("log", "IA: resoluções geradas.", "info"))
            self.publicar(("fim", questoes))
        except Exception as erro:
            self.publicar(("erro_extracao", str(erro)))

    def _esperar_login(self) -> bool:
        evento = threading.Event()
        self.publicar(("login", evento))
        return evento.wait(timeout=1200)

    def parar_extracao(self):
        self.parar.set()
        self.registrar("Parada solicitada — encerrando após a questão atual…", "aviso")

    def entrar_no_site(self):
        def abrir():
            try:
                self.driver_login = abrir_navegador_para_login()
            except Exception as erro:
                self.publicar(("log", f"Não foi possível abrir o navegador: {erro}", "erro"))

        threading.Thread(target=abrir, daemon=True).start()

    def registrar(self, texto: str, nivel: str = "info"):
        prefixo = {"erro": "❌", "aviso": "⚠️"}.get(nivel, "›")
        self.caixa_log.insert("end", f"{prefixo} {texto}\n")
        self.caixa_log.see("end")

    def definir_progresso(self, atual: int, total: int, texto: str = ""):
        self.barra.set(0 if total <= 0 else atual / total)
        self.rotulo_progresso.configure(text=texto or f"{atual}/{total}")

    def atualizar_previa(self, lista: list[dict]):
        self.extraidas = list(lista)
        self.rotulo_total.configure(text=f"{len(self.extraidas)} questão(ões) extraída(s)")

    def receber_busca(self, tipo: str, resultados: list[dict]):
        for campo in self.campos.values():
            if campo.tipo == tipo:
                campo.aplicar_resultado(resultados)

    def receber_erro_busca(self, tipo: str, mensagem: str):
        for campo in self.campos.values():
            if campo.tipo == tipo:
                campo.mostrar_erro(mensagem)

    def finalizar(self, questoes: list[dict]):
        self.extraindo = False
        self.botao_iniciar.configure(state="normal")
        self.botao_parar.configure(state="disabled")
        self.barra.set(1)
        self.rotulo_progresso.configure(text=f"Concluído: {len(questoes)} questão(ões)")
        if questoes:
            self.botao_importar.configure(state="normal")

    def falha(self, mensagem: str):
        self.extraindo = False
        self.botao_iniciar.configure(state="normal")
        self.botao_parar.configure(state="disabled")
        if self.extraidas:
            self.botao_importar.configure(state="normal")
            self.registrar(
                f"{len(self.extraidas)} questão(ões) parciais podem ser adicionadas ao banco.",
                "aviso",
            )
        self.registrar(f"Extração interrompida: {mensagem}", "erro")
        messagebox.showerror("Erro na extração", mensagem)

    def importar(self):
        if not self.extraidas:
            return
        chave = self._resolver_chave_destino(criar=True)
        if chave:
            caminho = concursos.caminho_json(chave)
        else:
            caminho = self.obter_caminho() if callable(self.obter_caminho) else self.obter_caminho
        existentes = dados.carregar_questoes(caminho)
        mescladas, resumo = dados.mesclar(existentes, self.extraidas)
        dados.salvar_questoes(mescladas, caminho)
        destino = (
            concursos.obter(chave)["arquivo"] if chave else str(caminho)
        )
        self.ao_importar(chave)
        messagebox.showinfo(
            "Importação concluída",
            f"Novas: {resumo['novas']}\nAtualizadas: {resumo['atualizadas']}\n"
            f"Total no banco: {resumo['total']}\nBanco: {destino}",
        )
        self.registrar(
            f"Importadas {resumo['novas']} e atualizadas {resumo['atualizadas']} "
            f"questões em {destino}.",
            "info",
        )
