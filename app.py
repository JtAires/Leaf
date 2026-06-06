import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
from datetime import datetime, timedelta
import uuid
import calendar
import base64
import ctypes
import sys
import shutil
import re

# ─────────────────────────────────────────────
#  CONSTANTES DE CONFIGURAÇÃO
# ─────────────────────────────────────────────
MAX_BACKUPS = 30          # Número máximo de pastas de backup a manter
JANELA_GERACAO_DIAS = 15  # Quantos dias à frente gerar recorrências

DATE_FMT = "%d/%m/%Y"
DATE_RE  = re.compile(r"^\d{2}/\d{2}/\d{4}$")


def caminho_recurso(caminho_relativo: str) -> str:
    """Localiza ficheiros tanto em modo .py como em .exe (PyInstaller)."""
    try:
        caminho_base = sys._MEIPASS
    except AttributeError:
        caminho_base = os.path.abspath(".")
    return os.path.join(caminho_base, caminho_relativo)


# ─────────────────────────────────────────────
#  PASTAS NA APPDATA
# ─────────────────────────────────────────────
appdata_path = os.getenv("APPDATA", os.path.expanduser("~"))
PASTA_APP    = os.path.join(appdata_path, "Leaf")
PASTA_BACKUP = os.path.join(PASTA_APP, "backup")

os.makedirs(PASTA_APP,    exist_ok=True)
os.makedirs(PASTA_BACKUP, exist_ok=True)

ARQUIVO_PENDENTES   = os.path.join(PASTA_APP, "pendentes.json")
ARQUIVO_CONCLUIDAS  = os.path.join(PASTA_APP, "concluidas.json")
ARQUIVO_DIARIO      = os.path.join(PASTA_APP, "diario.json")
ARQUIVO_RECORRENTES = os.path.join(PASTA_APP, "recorrentes.json")


# ─────────────────────────────────────────────
#  PERSISTÊNCIA
# ─────────────────────────────────────────────
def carregar_dados_seguros(arquivo: str, tipo_padrao):
    """Carrega JSON codificado em base64; aceita JSON puro como fallback."""
    if not os.path.exists(arquivo):
        return tipo_padrao
    try:
        with open(arquivo, "r", encoding="utf-8") as f:
            conteudo = f.read().strip()
        if not conteudo:
            return tipo_padrao
        try:
            return json.loads(base64.b64decode(conteudo).decode("utf-8"))
        except Exception:
            return json.loads(conteudo)
    except Exception:
        return tipo_padrao


def salvar_dados_seguros(arquivo: str, dados) -> None:
    """Salva dados como JSON codificado em base64."""
    texto_codificado = base64.b64encode(
        json.dumps(dados, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")

    caminho_abs = os.path.abspath(arquivo)

    # Remove atributo somente-leitura no Windows antes de escrever
    if os.name == "nt" and os.path.exists(caminho_abs):
        try:
            ctypes.windll.kernel32.SetFileAttributesW(caminho_abs, 128)
        except Exception:
            pass

    with open(arquivo, "w", encoding="utf-8") as f:
        f.write(texto_codificado)

    # Marca como oculto no Windows após salvar
    if os.name == "nt":
        try:
            ctypes.windll.kernel32.SetFileAttributesW(caminho_abs, 2)
        except Exception:
            pass


# ─────────────────────────────────────────────
#  UTILITÁRIOS
# ─────────────────────────────────────────────
def converter_data(data_str: str) -> datetime:
    """Converte 'DD/MM/AAAA' para datetime; retorna datetime.max se inválida."""
    try:
        return datetime.strptime(data_str, DATE_FMT)
    except (ValueError, TypeError):
        return datetime.max


def validar_data(data_str: str) -> bool:
    """Retorna True se a string for uma data válida no formato DD/MM/AAAA."""
    if not DATE_RE.match(data_str):
        return False
    try:
        datetime.strptime(data_str, DATE_FMT)
        return True
    except ValueError:
        return False


def limpar_backups_antigos(pasta_backup: str, max_backups: int) -> None:
    """Remove as pastas de backup mais antigas, mantendo até max_backups."""
    try:
        entradas = sorted([
            e for e in os.scandir(pasta_backup) if e.is_dir()
        ], key=lambda e: e.name)
        while len(entradas) > max_backups:
            shutil.rmtree(entradas.pop(0).path, ignore_errors=True)
    except Exception:
        pass


# ─────────────────────────────────────────────
#  APLICAÇÃO PRINCIPAL
# ─────────────────────────────────────────────
class AppOrganizacao:

    # ── Inicialização ────────────────────────
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Leaf v.1.2")
        self.root.geometry("1000x550")

        try:
            self.root.iconbitmap(caminho_recurso("icone.ico"))
        except Exception as e:
            print("Erro ao carregar ícone:", e)

        # Dados em memória
        self.pendentes   = carregar_dados_seguros(ARQUIVO_PENDENTES,   [])
        self.concluidas  = carregar_dados_seguros(ARQUIVO_CONCLUIDAS,  [])
        self.diario      = carregar_dados_seguros(ARQUIVO_DIARIO,      {})
        self.recorrentes = carregar_dados_seguros(ARQUIVO_RECORRENTES, [])

        # Garante que todas as atividades têm 'id' e 'keywords'
        for ativ in self.pendentes + self.concluidas:
            ativ.setdefault("id",       str(uuid.uuid4()))
            ativ.setdefault("keywords", [])

        self.pendentes.sort(key=lambda x: converter_data(x.get("deadline", "")))

        # Timers de debounce
        self.timer_salvamento = None
        self.timer_graficos   = None

        # Estado do calendário
        self.ano_cal  = datetime.today().year
        self.mes_cal  = datetime.today().month
        self.data_calendario_selecionada = None

        self.processar_recorrencias()
        self.iniciar_sistema_backup()
        self.configurar_interface_principal()
        self.atualizar_relogio()
        self.atualizar_tabela_principal()

    # ── Backup diário ────────────────────────
    def iniciar_sistema_backup(self) -> None:
        hoje_str   = datetime.now().strftime("%Y-%m-%d")
        pasta_hoje = os.path.join(PASTA_BACKUP, hoje_str)

        if not os.path.exists(pasta_hoje):
            os.makedirs(pasta_hoje, exist_ok=True)
            for arq in (ARQUIVO_PENDENTES, ARQUIVO_CONCLUIDAS,
                        ARQUIVO_DIARIO, ARQUIVO_RECORRENTES):
                if os.path.exists(arq):
                    shutil.copy2(arq, pasta_hoje)
            limpar_backups_antigos(PASTA_BACKUP, MAX_BACKUPS)

        # Reagenda para 00:00:05 do dia seguinte
        agora   = datetime.now()
        amanha  = agora + timedelta(days=1)
        proxima = datetime(amanha.year, amanha.month, amanha.day, 0, 0, 5)
        ms_rest = int((proxima - agora).total_seconds() * 1000)
        self.root.after(ms_rest, self.iniciar_sistema_backup)

    # ── Interface principal ──────────────────
    def configurar_interface_principal(self) -> None:
        # Barra de relógio
        self.lbl_relogio = tk.Label(
            self.root, text="", font=("Arial", 11, "bold"),
            bg="#bbbbbb", fg="#14532d", pady=6
        )
        self.lbl_relogio.pack(fill=tk.X, side=tk.TOP)

        # Barra de botões
        frame_botoes = tk.Frame(self.root)
        frame_botoes.pack(fill=tk.X, padx=10, pady=10)

        tk.Button(frame_botoes, text="+ Nova atividade",
                  command=self.nova_atividade_popup,
                  bg="#16a34a", fg="white", font=("Arial", 10, "bold")
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(frame_botoes, text="✓ Concluir selecionada(s)",
                  command=lambda: self.concluir_atividade(self.tabela)
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(frame_botoes, text="➔ Agendar para hoje",
                  command=self.adicionar_ao_dia
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(frame_botoes, text="📋 Atividades do dia",
                  command=self.abrir_menu_dia
                  ).pack(side=tk.LEFT, padx=5)

        tk.Button(frame_botoes, text="📅 Calendário",
                  command=self.abrir_calendario_popup,
                  bg="#15803d", fg="white"
                  ).pack(side=tk.RIGHT, padx=5)

        tk.Button(frame_botoes, text="🔄 Recorrentes",
                  command=self.abrir_recorrentes,
                  bg="#15803d", fg="white"
                  ).pack(side=tk.RIGHT, padx=5)

        tk.Button(frame_botoes, text="📁 Atividades concluídas",
                  command=self.abrir_concluidas
                  ).pack(side=tk.RIGHT, padx=5)

        # Título + barra de busca
        frame_titulo_busca = tk.Frame(self.root)
        frame_titulo_busca.pack(fill=tk.X, padx=15, pady=(5, 0))

        tk.Label(frame_titulo_busca, text="📌 To-do",
                 font=("Arial", 11, "bold"), fg="#166534"
                 ).pack(side=tk.LEFT)

        self.entry_busca_todo = tk.Entry(frame_titulo_busca, width=30)
        self.entry_busca_todo.pack(side=tk.RIGHT)
        self.entry_busca_todo.bind("<KeyRelease>",
                                   lambda e: self.atualizar_tabela_principal())

        tk.Label(frame_titulo_busca, text="🔍 Buscar:").pack(side=tk.RIGHT, padx=5)

        # Rodapé com legenda e copyright
        frame_rodape = tk.Frame(self.root)
        frame_rodape.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)

        frame_legenda = tk.Frame(frame_rodape)
        frame_legenda.pack(side=tk.LEFT)

        tk.Label(frame_legenda, text="Legenda de prazos:",
                 font=("Arial", 9, "bold"), fg="#14532d"
                 ).pack(side=tk.LEFT, padx=(0, 5))
        for texto, bg, fg in [
            (" Atrasada ",         "#052e16", "#ffffff"),
            (" Hoje ",             "#15803d", "#ffffff"),
            (" Amanhã ",           "#22c55e", "#ffffff"),
            (" Essa semana ",      "#86efac", "#064e3b"),
            (" Semana que vem ",   "#bbf7d0", "#064e3b"),
            (" Esse mês ",         "#f0fdf4", "#064e3b"),
            (" Depois desse mês ", "#e2e8f0", "#0f172a"),
        ]:
            tk.Label(frame_legenda, text=texto, bg=bg, fg=fg,
                     font=("Arial", 8)
                     ).pack(side=tk.LEFT, padx=2)
        tk.Label(frame_legenda, text=" Sem data ", bg="#ffffff", fg="#000000",
                 borderwidth=1, relief="solid", font=("Arial", 8)
                 ).pack(side=tk.LEFT, padx=2)

        tk.Label(frame_rodape,
                 text="© 2026 João Victor Aires. All rights reserved.",
                 font=("Arial", 8), fg="#64748b"
                 ).pack(side=tk.RIGHT)

        # Tabela principal (definição única, corrigida)
        colunas = ("id", "Atividade", "Deadline", "Comentários", "Palavras-chave")
        self.tabela = ttk.Treeview(self.root, columns=colunas, show="headings")

        self.tabela.heading("Atividade",      text="Atividade")
        self.tabela.heading("Deadline",       text="Deadline")
        self.tabela.heading("Comentários",    text="Comentários")
        self.tabela.heading("Palavras-chave", text="Palavras-chave")

        self.tabela.column("id",             width=0,   stretch=tk.NO)
        self.tabela.column("Atividade",      width=250)
        self.tabela.column("Deadline",       width=110, anchor=tk.CENTER)
        self.tabela.column("Comentários",    width=300)
        self.tabela.column("Palavras-chave", width=150)

        for tag, bg, fg in [
            ("atrasada",         "#052e16", "#ffffff"),
            ("hoje",             "#15803d", "#ffffff"),
            ("amanha",           "#22c55e", "#ffffff"),
            ("essa_semana",      "#86efac", "#064e3b"),
            ("semana_que_vem",   "#bbf7d0", "#064e3b"),
            ("esse_mes",         "#f0fdf4", "#064e3b"),
            ("depois_desse_mes", "#e2e8f0", "#0f172a"),
            ("sem_data",         "#ffffff", "#000000"),
        ]:
            self.tabela.tag_configure(tag, background=bg, foreground=fg)

        self.tabela.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 10))

        # Menu de contexto
        self.menu_contexto = tk.Menu(self.root, tearoff=0)
        self.menu_contexto.add_command(label="➔ Agendar para hoje",
                                       command=self.adicionar_ao_dia)
        self.menu_contexto.add_separator()
        self.menu_contexto.add_command(label="Editar atividade",
                                       command=self.editar_atividade_popup)
        self.menu_contexto.add_command(
            label="Gerenciar palavras-chave",
            command=lambda: self.gerenciar_palavras_chave_popup(
                self.tabela, self.pendentes, ARQUIVO_PENDENTES))
        self.menu_contexto.add_command(label="Marcar como concluída(s)",
                                       command=lambda: self.concluir_atividade(self.tabela))
        self.menu_contexto.add_separator()
        self.menu_contexto.add_command(label="❌ Excluir atividade(s)",
                                       command=self.excluir_atividade)

        self.tabela.bind("<Button-3>", self.mostrar_menu_contexto)
        self.tabela.bind("<Button-1>", self.desmarcar_clique_vazio)

        # Atalhos de teclado (sem duplicatas)
        for seq in ("<Control-n>", "<Control-N>"):
            self.root.bind(seq, self.nova_atividade_popup)
        for seq in ("<Control-k>", "<Control-K>"):
            self.root.bind(seq, self.abrir_calendario_popup)
        for seq in ("<Control-r>", "<Control-R>"):
            self.root.bind(seq, self.abrir_recorrentes)
        for seq in ("<Control-h>", "<Control-H>"):
            self.root.bind(seq, self.adicionar_ao_dia)

    # ── Relógio ──────────────────────────────
    def atualizar_relogio(self) -> None:
        DIAS   = ["Segunda-feira", "Terça-feira", "Quarta-feira",
                  "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
        MESES  = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
                  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        agora  = datetime.now()
        texto  = (f"📅 {DIAS[agora.weekday()]}, {agora.day} de "
                  f"{MESES[agora.month - 1]} de {agora.year}"
                  f"   |   🕓 {agora.strftime('%H:%M:%S')}")
        self.lbl_relogio.config(text=texto)
        self.root.after(1000, self.atualizar_relogio)

    # ── Tabela principal ─────────────────────
    # ── Tabela principal ─────────────────────
    def atualizar_tabela_principal(self) -> None:
        for item in self.tabela.get_children():
            self.tabela.delete(item)

        hoje   = datetime.today().date()
        amanha = hoje + timedelta(days=1)
        sabado = hoje + timedelta(days=(5 - hoje.weekday()) % 7)
        prox_sabado = sabado + timedelta(days=7)

        busca = self.entry_busca_todo.get().lower() \
                if hasattr(self, "entry_busca_todo") else ""

        for ativ in self.pendentes:
            titulo = ativ.get("atividade", "").lower()
            tags   = " ".join(ativ.get("keywords", [])).lower()
            if busca and busca not in titulo and busca not in tags:
                continue

            prazo     = converter_data(ativ.get("deadline", ""))
            tag_linha = "sem_data"

            if prazo != datetime.max:
                d = prazo.date()
                if d < hoje:
                    tag_linha = "atrasada"
                elif d == hoje:
                    tag_linha = "hoje"
                elif d == amanha:
                    tag_linha = "amanha"
                elif d <= sabado:
                    tag_linha = "essa_semana"
                elif d <= prox_sabado:
                    tag_linha = "semana_que_vem"
                elif d.month == hoje.month and d.year == hoje.year:
                    tag_linha = "esse_mes"
                else:
                    tag_linha = "depois_desse_mes"

            str_tags = ", ".join(ativ.get("keywords", []))
            self.tabela.insert("", tk.END, values=(
                ativ["id"], ativ.get("atividade", ""),
                ativ.get("deadline", ""), ativ.get("comentarios", ""),
                str_tags
            ), tags=(tag_linha,))

    # ── Máscara de data ──────────────────────
    def setup_mascara_data(self, entry_widget: tk.Entry,
                           string_var: tk.StringVar) -> None:
        def formatar_data(*_):
            texto   = string_var.get()
            digitos = "".join(c for c in texto if c.isdigit())
            partes  = []
            if len(digitos) >= 1:  partes.append(digitos[:2])
            if len(digitos) >= 3:  partes.append(digitos[2:4])
            if len(digitos) >= 5:  partes.append(digitos[4:8])
            formatado = "/".join(partes)
            if texto != formatado:
                string_var.set(formatado)
            entry_widget.after(2, lambda: entry_widget.icursor(tk.END))

        string_var.trace_add("write", formatar_data)

    # ── Menus de contexto ────────────────────
    def mostrar_menu_contexto(self, event) -> None:
        row = self.tabela.identify_row(event.y)
        if row:
            if row not in self.tabela.selection():
                self.tabela.selection_set(row)
            self.menu_contexto.post(event.x_root, event.y_root)

    def desmarcar_clique_vazio(self, event) -> None:
        tabela = event.widget
        if tabela.identify_region(event.x, event.y) == "nothing":
            tabela.selection_remove(tabela.selection())

    # ── Editar atividade ─────────────────────
    def editar_atividade_popup(self) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            return
        if len(selecao) > 1:
            messagebox.showinfo("Info", "Selecione apenas UMA atividade para editar.")
            return

        id_ativ  = self.tabela.item(selecao[0])["values"][0]
        ativ_idx = next((i for i, x in enumerate(self.pendentes)
                         if x["id"] == id_ativ), None)
        if ativ_idx is None:
            return
        ativ = self.pendentes[ativ_idx]

        popup = tk.Toplevel(self.root)
        popup.title("Editar atividade")
        popup.geometry("350x250")
        popup.transient(self.root)
        popup.grab_set()
        popup.bind("<Escape>", lambda e: popup.destroy())

        tk.Label(popup, text="Atividade:").pack(pady=(10, 0))
        entry_atividade = tk.Entry(popup, width=40)
        entry_atividade.insert(0, ativ["atividade"])
        entry_atividade.pack(pady=5)
        entry_atividade.focus_set()

        tk.Label(popup, text="Deadline (DD/MM/AAAA):").pack()
        var_deadline  = tk.StringVar(value=ativ["deadline"])
        entry_deadline = tk.Entry(popup, width=40, textvariable=var_deadline)
        entry_deadline.pack(pady=5)
        self.setup_mascara_data(entry_deadline, var_deadline)

        tk.Label(popup, text="Comentários:").pack()
        entry_comentarios = tk.Entry(popup, width=40)
        entry_comentarios.insert(0, ativ.get("comentarios", ""))
        entry_comentarios.pack(pady=5)

        def salvar_edicao(_event=None):
            novo_nome     = entry_atividade.get().strip()
            novo_deadline = var_deadline.get().strip()
            novos_coment  = entry_comentarios.get().strip()

            if not novo_nome:
                messagebox.showwarning("Aviso", "O nome da atividade não pode ser vazio.",
                                       parent=popup)
                return
            if novo_deadline and not validar_data(novo_deadline):
                messagebox.showwarning("Aviso",
                                       "Formato de data inválido.\nUse DD/MM/AAAA.",
                                       parent=popup)
                return

            ativ["atividade"]  = novo_nome
            ativ["deadline"]   = novo_deadline
            ativ["comentarios"] = novos_coment

            self.pendentes.sort(key=lambda x: converter_data(x.get("deadline", "")))
            salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
            self.atualizar_tabela_principal()
            popup.destroy()

        tk.Button(popup, text="Salvar Alterações", command=salvar_edicao,
                  bg="#15803d", fg="white").pack(pady=15)
        popup.bind("<Return>", salvar_edicao)

    # ── Excluir atividade ────────────────────
    def excluir_atividade(self) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            return
        if not messagebox.askyesno(
            "Confirmar Exclusão",
            f"Excluir definitivamente {len(selecao)} atividade(s)?"
        ):
            return

        ids = {self.tabela.item(s)["values"][0] for s in selecao}
        self.pendentes = [x for x in self.pendentes if x["id"] not in ids]
        salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
        self.atualizar_tabela_principal()

    # ── Concluir atividade ───────────────────
    def concluir_atividade(self, tabela_origem: ttk.Treeview) -> None:
        selecao = tabela_origem.selection()
        if not selecao:
            messagebox.showinfo("Info",
                                "Selecione pelo menos uma atividade para concluir.")
            return

        hoje_str  = datetime.today().strftime(DATE_FMT)
        concluidas_agora = 0

        for sel_item in selecao:
            id_ativ = tabela_origem.item(sel_item)["values"][0]
            ativ    = next((x for x in self.pendentes if x["id"] == id_ativ), None)
            if ativ:
                ativ["data_conclusao"] = hoje_str
                self.pendentes.remove(ativ)
                self.concluidas.append(ativ)
                concluidas_agora += 1

        salvar_dados_seguros(ARQUIVO_PENDENTES,  self.pendentes)
        salvar_dados_seguros(ARQUIVO_CONCLUIDAS, self.concluidas)
        self.atualizar_tabela_principal()

        if hasattr(self, "win_conc") and self.win_conc.winfo_exists():
            self.atualizar_tabela_concluidas()

        messagebox.showinfo("Sucesso",
                            f"{concluidas_agora} atividade(s) marcada(s) como concluída(s)!")

        if tabela_origem is not self.tabela:
            for sel_item in selecao:
                if tabela_origem.exists(sel_item):
                    tabela_origem.delete(sel_item)

    # ── Agendar para hoje ────────────────────
    def adicionar_ao_dia(self, _event=None) -> None:
        selecao = self.tabela.selection()
        if not selecao:
            messagebox.showinfo("Info",
                                "Selecione pelo menos uma atividade na planilha principal.")
            return

        hoje_str = datetime.today().strftime(DATE_FMT)
        ids      = {self.tabela.item(s)["values"][0] for s in selecao}
        contador = 0

        for ativ in self.pendentes:
            if ativ["id"] in ids:
                ativ["data_dia"] = hoje_str
                contador += 1

        salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
        messagebox.showinfo("Sucesso",
                            f"{contador} atividade(s) agendada(s) para hoje!")

    # ── Remover do dia ───────────────────────
    def remover_do_dia(self, tabela_origem: ttk.Treeview) -> None:
        selecao = tabela_origem.selection()
        if not selecao:
            messagebox.showinfo("Info",
                                "Selecione pelo menos uma atividade para remover do dia.")
            return

        ids      = {tabela_origem.item(s)["values"][0] for s in selecao}
        contador = 0

        for ativ in self.pendentes:
            if ativ["id"] in ids:
                ativ["data_dia"] = None
                contador += 1

        salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)

        for sel_item in selecao:
            if tabela_origem.exists(sel_item):
                tabela_origem.delete(sel_item)

        messagebox.showinfo("Sucesso",
                            f"{contador} atividade(s) removida(s) das tarefas do dia!")

    # ── Janela: Atividades concluídas ────────
    def abrir_concluidas(self) -> None:
        self.win_conc = tk.Toplevel(self.root)
        self.win_conc.title("Atividades concluídas")
        self.win_conc.geometry("850x450")
        self.win_conc.bind("<Escape>", lambda e: self.win_conc.destroy())
        self.win_conc.focus_set()

        frame_top = tk.Frame(self.win_conc)
        frame_top.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(frame_top, text="🔍 Buscar:").pack(side=tk.LEFT)
        self.entry_busca = tk.Entry(frame_top, width=25)
        self.entry_busca.pack(side=tk.LEFT, padx=5)
        self.entry_busca.bind("<KeyRelease>",
                              lambda e: self.atualizar_tabela_concluidas())

        tk.Label(frame_top, text="  |  Ordenar por:").pack(side=tk.LEFT)
        self.combo_ordem = ttk.Combobox(
            frame_top,
            values=["Padrão", "Atividade (A-Z)", "Atividade (Z-A)",
                    "Deadline (Mais novas)", "Deadline (Mais antigas)"],
            state="readonly", width=22
        )
        self.combo_ordem.current(0)
        self.combo_ordem.pack(side=tk.LEFT, padx=5)
        self.combo_ordem.bind("<<ComboboxSelected>>",
                              lambda e: self.atualizar_tabela_concluidas())

        tk.Button(frame_top, text="📥 Exportar para .txt",
                  command=self.exportar_concluidas,
                  bg="#10b981", fg="white", font=("Arial", 9, "bold")
                  ).pack(side=tk.RIGHT, padx=(5, 0))

        tk.Button(frame_top, text="📊 Estatísticas",
                  command=self.abrir_estatisticas,
                  bg="#047857", fg="white", font=("Arial", 9, "bold")
                  ).pack(side=tk.RIGHT, padx=5)

        colunas = ("id", "Atividade", "Deadline", "Comentários",
                   "Palavras-chave", "Concluída em")
        self.tabela_conc = ttk.Treeview(self.win_conc,
                                        columns=colunas, show="headings")

        for col, w, anchor in [
            ("id",             0,   tk.W),
            ("Atividade",      220, tk.W),
            ("Deadline",       100, tk.CENTER),
            ("Comentários",    240, tk.W),
            ("Palavras-chave", 130, tk.W),
            ("Concluída em",   100, tk.CENTER),
        ]:
            self.tabela_conc.heading(col, text=col)
            self.tabela_conc.column(col, width=w, anchor=anchor,
                                    stretch=(col != "id"))
        self.tabela_conc.column("id", stretch=tk.NO)

        self.tabela_conc.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.menu_contexto_conc = tk.Menu(self.win_conc, tearoff=0)
        self.menu_contexto_conc.add_command(label="↩️ Voltar para To-do",
                                            command=self.desconcluir_atividade)
        self.menu_contexto_conc.add_separator()
        self.menu_contexto_conc.add_command(
            label="Gerenciar palavras-chave",
            command=lambda: self.gerenciar_palavras_chave_popup(
                self.tabela_conc, self.concluidas, ARQUIVO_CONCLUIDAS))

        self.tabela_conc.bind("<Button-3>", self.mostrar_menu_contexto_conc)
        self.tabela_conc.bind("<Button-1>", self.desmarcar_clique_vazio)

        self.atualizar_tabela_concluidas()

    def mostrar_menu_contexto_conc(self, event) -> None:
        row = self.tabela_conc.identify_row(event.y)
        if row:
            if row not in self.tabela_conc.selection():
                self.tabela_conc.selection_set(row)
            self.menu_contexto_conc.post(event.x_root, event.y_root)

    def atualizar_tabela_concluidas(self) -> None:
        for item in self.tabela_conc.get_children():
            self.tabela_conc.delete(item)

        busca  = self.entry_busca.get().lower()
        ordem  = self.combo_ordem.get()

        lista = [
            a for a in self.concluidas
            if busca in a.get("atividade", "").lower()
            or busca in " ".join(a.get("keywords", [])).lower()
        ]

        if ordem == "Atividade (A-Z)":
            lista.sort(key=lambda x: x.get("atividade", "").lower())
        elif ordem == "Atividade (Z-A)":
            lista.sort(key=lambda x: x.get("atividade", "").lower(), reverse=True)
        elif ordem == "Deadline (Mais novas)":
            lista.sort(key=lambda x: converter_data(x.get("deadline", "")),
                       reverse=True)
        elif ordem == "Deadline (Mais antigas)":
            lista.sort(key=lambda x: converter_data(x.get("deadline", "")))

        for a in lista:
            self.tabela_conc.insert("", tk.END, values=(
                a.get("id", ""),
                a.get("atividade", ""),
                a.get("deadline", ""),
                a.get("comentarios", ""),
                ", ".join(a.get("keywords", [])),
                a.get("data_conclusao", "—"),
            ))

    # ── Palavras-chave ───────────────────────
    def gerenciar_palavras_chave_popup(self, tabela_alvo: ttk.Treeview,
                                       lista_dados: list,
                                       arquivo_alvo: str) -> None:
        selecao = tabela_alvo.selection()
        if not selecao:
            return
        if len(selecao) > 1:
            messagebox.showinfo("Info",
                                "Selecione apenas UMA atividade para gerenciar tags.")
            return

        id_ativ  = tabela_alvo.item(selecao[0])["values"][0]
        ativ_idx = next((i for i, x in enumerate(lista_dados)
                         if x.get("id") == id_ativ), None)
        if ativ_idx is None:
            return

        ativ = lista_dados[ativ_idx]
        ativ.setdefault("keywords", [])

        popup = tk.Toplevel(self.root)
        popup.title("Gerenciar palavras-chave")
        popup.geometry("300x320")
        popup.transient(self.root)
        popup.grab_set()
        popup.bind("<Escape>", lambda e: popup.destroy())

        tk.Label(popup, text=f"Tags para:\n{ativ.get('atividade', '')}",
                 font=("Arial", 9, "bold"), wraplength=280).pack(pady=10)

        frame_list = tk.Frame(popup)
        frame_list.pack(fill=tk.BOTH, expand=True, padx=10)

        listbox_tags = tk.Listbox(frame_list)
        listbox_tags.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(frame_list, orient="vertical",
                          command=listbox_tags.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        listbox_tags.config(yscrollcommand=sb.set)

        def atualizar_listbox():
            listbox_tags.delete(0, tk.END)
            for tag in ativ["keywords"]:
                listbox_tags.insert(tk.END, f" #{tag}")

        atualizar_listbox()

        def _persistir():
            salvar_dados_seguros(arquivo_alvo, lista_dados)
            if tabela_alvo is self.tabela:
                self.atualizar_tabela_principal()
            elif hasattr(self, "tabela_conc") and tabela_alvo is self.tabela_conc:
                self.atualizar_tabela_concluidas()

        frame_ctrl = tk.Frame(popup)
        frame_ctrl.pack(fill=tk.X, padx=10, pady=10)

        entry_nova_tag = tk.Entry(frame_ctrl)
        entry_nova_tag.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        entry_nova_tag.focus_set()

        def add_tag(_event=None):
            nova = entry_nova_tag.get().strip().replace("#", "")
            if nova and nova not in ativ["keywords"]:
                ativ["keywords"].append(nova)
                atualizar_listbox()
                entry_nova_tag.delete(0, tk.END)
                _persistir()

        tk.Button(frame_ctrl, text=" + ", command=add_tag,
                  bg="#16a34a", fg="white", font=("Arial", 10, "bold")
                  ).pack(side=tk.LEFT)
        popup.bind("<Return>", add_tag)

        def remove_tag():
            sel = listbox_tags.curselection()
            if sel:
                tag_real = listbox_tags.get(sel[0]).replace(" #", "")
                if tag_real in ativ["keywords"]:
                    ativ["keywords"].remove(tag_real)
                atualizar_listbox()
                _persistir()

        tk.Button(popup, text="Remover tag selecionada",
                  command=remove_tag, bg="#ef4444", fg="white"
                  ).pack(pady=(0, 10))

    # ── Exportar concluídas ──────────────────
    def exportar_concluidas(self) -> None:
        if not self.concluidas:
            messagebox.showinfo("Info",
                                "Não há atividades concluídas para exportar.")
            return

        caminho = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Arquivo de Texto", "*.txt")],
            initialfile="atividades_concluidas.txt",
            title="Salvar Histórico"
        )
        if not caminho:
            return

        try:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write("=== HISTÓRICO DE ATIVIDADES CONCLUÍDAS ===\n")
                f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}\n")
                f.write("=" * 42 + "\n\n")
                for a in self.concluidas:
                    f.write(f"ATIVIDADE:  {a.get('atividade', 'Sem título')}\n")
                    f.write(f"PRAZO:      {a.get('deadline', 'Sem data')}\n")
                    f.write(f"CONCLUÍDA:  {a.get('data_conclusao', '—')}\n")
                    if a.get("comentarios"):
                        f.write(f"COMENTÁRIOS: {a['comentarios']}\n")
                    tags = ", ".join(a.get("keywords", []))
                    if tags:
                        f.write(f"TAGS:       {tags}\n")
                    f.write("-" * 42 + "\n")
            messagebox.showinfo("Sucesso",
                                f"Exportado com sucesso para:\n{caminho}")
        except Exception as e:
            messagebox.showerror("Erro", f"Erro ao salvar arquivo:\n{e}")

    # ── Menu do dia ──────────────────────────
    def abrir_menu_dia(self) -> None:
        janela = tk.Toplevel(self.root)
        janela.title("Atividades do dia")
        janela.geometry("750x450")
        janela.bind("<Escape>", lambda e: janela.destroy())
        janela.focus_set()

        frame_leg = tk.Frame(janela)
        frame_leg.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        tk.Label(frame_leg, text="Prioridades:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        for txt, bg in [(" Alta ", "#fca5a5"), (" Média ", "#fde047"),
                        (" Baixa ", "#86efac"), (" Nenhuma ", "#dcfce7")]:
            tk.Label(frame_leg, text=txt, bg=bg, fg="black",
                     font=("Arial", 9)).pack(side=tk.LEFT, padx=5)

        notebook     = ttk.Notebook(janela)
        aba_hoje     = tk.Frame(notebook)
        aba_antigas  = tk.Frame(notebook)
        notebook.add(aba_hoje,    text="Para hoje")
        notebook.add(aba_antigas, text="Atividades não concluídas (Antigas)")
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        colunas = ("id", "Atividade", "Deadline", "Comentários")

        def _make_tb(frame):
            tb = ttk.Treeview(frame, columns=colunas, show="headings")
            for col, w in [("Atividade", 250), ("Deadline", 100),
                           ("Comentários", 250)]:
                tb.heading(col, text=col)
                tb.column(col, width=w, anchor=tk.CENTER if col == "Deadline" else tk.W)
            tb.column("id", width=0, stretch=tk.NO)
            for tag, bg in [("alta", "#fca5a5"), ("media", "#fde047"),
                             ("baixa", "#86efac"), ("normal", "#dcfce7")]:
                tb.tag_configure(tag, background=bg, foreground="black")
            tb.bind("<Button-1>", self.desmarcar_clique_vazio)
            tb.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
            return tb

        tb_hoje    = _make_tb(aba_hoje)
        tb_antigas = _make_tb(aba_antigas)

        for frame_pai, tb in [(aba_hoje, tb_hoje), (aba_antigas, tb_antigas)]:
            f = tk.Frame(frame_pai)
            f.pack(pady=5)
            tk.Button(f, text="✓ Concluir selecionada(s)",
                      command=lambda t=tb: [self.concluir_atividade(t),
                                            carregar_listas()]
                      ).pack(side=tk.LEFT, padx=5)
            tk.Button(f, text="❌ Remover do dia",
                      command=lambda t=tb: [self.remover_do_dia(t),
                                            carregar_listas()]
                      ).pack(side=tk.LEFT, padx=5)

        PESOS = {"Alta": 0, "Média": 1, "Baixa": 2}

        def chave_ord(x):
            return (PESOS.get(x.get("prioridade", ""), 3),
                    converter_data(x.get("deadline", "")))

        def carregar_listas():
            for tb in (tb_hoje, tb_antigas):
                for item in tb.get_children():
                    tb.delete(item)

            hoje_str    = datetime.today().strftime(DATE_FMT)
            lista_hoje  = []
            lista_antig = []

            for a in self.pendentes:
                dd = a.get("data_dia")
                if dd == hoje_str:
                    lista_hoje.append(a)
                elif dd:
                    lista_antig.append(a)

            lista_hoje.sort(key=chave_ord)
            lista_antig.sort(key=chave_ord)

            def _inserir(tb, lista):
                for a in lista:
                    pri = a.get("prioridade", "")
                    tag = ("alta"  if pri == "Alta"  else
                           "media" if pri == "Média" else
                           "baixa" if pri == "Baixa" else "normal")
                    tb.insert("", tk.END, values=(
                        a["id"], a["atividade"],
                        a.get("deadline", ""), a.get("comentarios", "")
                    ), tags=(tag,))

            _inserir(tb_hoje,    lista_hoje)
            _inserir(tb_antigas, lista_antig)

            notebook.tab(0, text=f"Para hoje ({len(lista_hoje)})")
            notebook.tab(1, text=f"Atividades não concluídas ({len(lista_antig)})")

        carregar_listas()

        # Menu de contexto da janela do dia
        menu_ctx    = tk.Menu(janela, tearoff=0)
        tabela_alvo = [None]

        def abrir_popup_prioridade():
            if not tabela_alvo[0]:
                return
            selecao = tabela_alvo[0].selection()
            if not selecao:
                return

            pop = tk.Toplevel(janela)
            pop.title("Prioridade")
            pop.geometry("260x140")
            pop.transient(janela)
            pop.grab_set()
            pop.bind("<Escape>", lambda e: pop.destroy())
            pop.focus_set()

            tk.Label(pop, text="Defina a prioridade:",
                     font=("Arial", 10, "bold")).pack(pady=10)

            def salvar_pri(nivel):
                for sel in selecao:
                    id_a = tabela_alvo[0].item(sel)["values"][0]
                    for a in self.pendentes:
                        if a["id"] == id_a:
                            a["prioridade"] = nivel
                            break
                salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
                carregar_listas()
                pop.destroy()

            f = tk.Frame(pop)
            f.pack()
            for txt, bg, col, kwargs in [
                ("Alta",    "#fca5a5", 0, {}),
                ("Média",   "#fde047", 1, {}),
                ("Baixa",   "#86efac", 2, {}),
            ]:
                tk.Button(f, text=txt, bg=bg, fg="black",
                          command=lambda n=txt: salvar_pri(n),
                          width=8).grid(row=0, column=col, padx=2)
            tk.Button(f, text="Nenhuma", bg="#dcfce7", fg="#14532d",
                      command=lambda: salvar_pri("")).grid(
                row=1, column=0, columnspan=3, pady=10, sticky="ew")

        def promover_para_hoje():
            if not tabela_alvo[0]:
                return
            selecao = tabela_alvo[0].selection()
            if not selecao:
                return
            hoje_str = datetime.today().strftime(DATE_FMT)
            for sel in selecao:
                id_a = tabela_alvo[0].item(sel)["values"][0]
                for a in self.pendentes:
                    if a["id"] == id_a:
                        a["data_dia"] = hoje_str
                        break
            salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
            carregar_listas()
            messagebox.showinfo("Sucesso",
                                f"{len(selecao)} atividade(s) movida(s) para hoje!",
                                parent=janela)

        menu_ctx.add_command(label="✓ Concluir selecionada(s)",
                             command=lambda: [self.concluir_atividade(tabela_alvo[0]),
                                              carregar_listas()] if tabela_alvo[0] else None)
        menu_ctx.add_command(label="❌ Remover do dia",
                             command=lambda: [self.remover_do_dia(tabela_alvo[0]),
                                              carregar_listas()] if tabela_alvo[0] else None)
        menu_ctx.add_separator()
        menu_ctx.add_command(label="🎯 Adicionar/editar prioridade",
                             command=abrir_popup_prioridade)
        menu_ctx.add_command(label="➔ Trazer para Hoje",
                             command=promover_para_hoje)

        def capturar_clique_direito(event):
            tb   = event.widget
            row  = tb.identify_row(event.y)
            if row:
                if row not in tb.selection():
                    tb.selection_set(row)
                tabela_alvo[0] = tb
                estado = tk.NORMAL if tb is tb_antigas else tk.DISABLED
                menu_ctx.entryconfig("➔ Trazer para Hoje", state=estado)
                menu_ctx.post(event.x_root, event.y_root)

        tb_hoje.bind("<Button-3>",    capturar_clique_direito)
        tb_antigas.bind("<Button-3>", capturar_clique_direito)

    # ── Calendário ───────────────────────────
    def abrir_calendario_popup(self, _event=None) -> None:
        self.win_cal = tk.Toplevel(self.root)
        self.win_cal.title("Calendário")
        self.win_cal.geometry("500x680")
        self.win_cal.transient(self.root)
        self.win_cal.bind("<Escape>", lambda e: self.win_cal.destroy())
        self.win_cal.focus_set()

        self.frame_ctrl_cal = tk.Frame(self.win_cal)
        self.frame_ctrl_cal.pack(fill=tk.X, pady=10)
        tk.Button(self.frame_ctrl_cal, text="◀",
                  command=self.mes_anterior).pack(side=tk.LEFT, padx=20)
        self.lbl_mes_ano = tk.Label(self.frame_ctrl_cal, text="",
                                    font=("Arial", 12, "bold"))
        self.lbl_mes_ano.pack(side=tk.LEFT, expand=True)
        tk.Button(self.frame_ctrl_cal, text="▶",
                  command=self.mes_proximo).pack(side=tk.RIGHT, padx=20)

        self.frame_dias_cal = tk.Frame(self.win_cal)
        self.frame_dias_cal.pack(pady=5)

        frame_res = tk.Frame(self.win_cal)
        frame_res.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.lbl_info_data = tk.Label(frame_res,
                                      text="Clique em um dia para ver as entregas",
                                      font=("Arial", 10, "italic"))
        self.lbl_info_data.pack(anchor=tk.W, pady=2)

        self.list_cal_tarefas = tk.Listbox(frame_res, height=4,
                                           font=("Arial", 10))
        self.list_cal_tarefas.pack(fill=tk.X, pady=(0, 10))

        tk.Label(frame_res, text="Diário de bordo:",
                 font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5, 2))

        self.text_diario = tk.Text(frame_res, height=10, font=("Arial", 10),
                                   wrap=tk.WORD, bg="#f8fafc", state=tk.DISABLED)
        self.text_diario.pack(fill=tk.BOTH, expand=True)
        self.text_diario.bind("<KeyRelease>", self.salvar_diario_auto)

        self.desenhar_calendario()

    def desenhar_calendario(self) -> None:
        for w in self.frame_dias_cal.winfo_children():
            w.destroy()

        MESES = ["Jan","Fev","Mar","Abr","Mai","Jun",
                 "Jul","Ago","Set","Out","Nov","Dez"]
        self.lbl_mes_ano.config(
            text=f"{MESES[self.mes_cal - 1]} / {self.ano_cal}")

        for col, dia in enumerate(["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"]):
            tk.Label(self.frame_dias_cal, text=dia,
                     font=("Arial", 9, "bold"), width=6
                     ).grid(row=0, column=col, pady=2)

        hoje = datetime.today()
        cal  = calendar.Calendar(firstweekday=6)

        for r_idx, semana in enumerate(
                cal.monthdayscalendar(self.ano_cal, self.mes_cal)):
            for c_idx, dia in enumerate(semana):
                if dia == 0:
                    tk.Label(self.frame_dias_cal, text="", width=6
                             ).grid(row=r_idx + 1, column=c_idx)
                    continue

                data_str  = f"{dia:02d}/{self.mes_cal:02d}/{self.ano_cal}"
                tem_tarefa = any(x["deadline"] == data_str for x in self.pendentes)
                tem_diario = bool(self.diario.get(data_str, "").strip())
                eh_hoje    = (dia == hoje.day and
                              self.mes_cal == hoje.month and
                              self.ano_cal == hoje.year)

                if eh_hoje:
                    cor_bg, cor_fg = "#16a34a", "white"
                elif tem_tarefa:
                    cor_bg, cor_fg = "#bbf7d0", "black"
                else:
                    cor_bg, cor_fg = "#f1f5f9", "black"

                txt_btn    = f"{dia}*" if tem_diario else str(dia)
                font_estilo = ("Arial", 9, "bold") if (tem_tarefa or tem_diario or eh_hoje) \
                              else ("Arial", 9)

                tk.Button(
                    self.frame_dias_cal, text=txt_btn, width=5,
                    bg=cor_bg, fg=cor_fg, font=font_estilo,
                    command=lambda d=data_str: self.mostrar_tarefas_do_dia(d)
                ).grid(row=r_idx + 1, column=c_idx, padx=2, pady=2)

    def mes_anterior(self) -> None:
        self.mes_cal -= 1
        if self.mes_cal < 1:
            self.mes_cal = 12
            self.ano_cal -= 1
        self.desenhar_calendario()

    def mes_proximo(self) -> None:
        self.mes_cal += 1
        if self.mes_cal > 12:
            self.mes_cal = 1
            self.ano_cal += 1
        self.desenhar_calendario()

    def mostrar_tarefas_do_dia(self, data_str: str) -> None:
        self.data_calendario_selecionada = data_str
        self.list_cal_tarefas.delete(0, tk.END)
        self.lbl_info_data.config(
            text=f"Atividades para o dia: {data_str}",
            font=("Arial", 10, "bold"))

        tarefas = [x for x in self.pendentes if x["deadline"] == data_str]
        if tarefas:
            for t in tarefas:
                coment = f" ({t['comentarios']})" if t.get("comentarios") else ""
                self.list_cal_tarefas.insert(tk.END, f" 📌 {t['atividade']}{coment}")
        else:
            self.list_cal_tarefas.insert(tk.END,
                                         " Nenhuma atividade pendente para este dia.")

        self.text_diario.config(state=tk.NORMAL)
        self.text_diario.delete("1.0", tk.END)
        if data_str in self.diario:
            self.text_diario.insert(tk.END, self.diario[data_str])

    def salvar_diario_auto(self, _event=None) -> None:
        if not self.data_calendario_selecionada:
            return
        if self.timer_salvamento is not None:
            self.root.after_cancel(self.timer_salvamento)
        self.timer_salvamento = self.root.after(
            1000, self._executar_salvamento_diario)

    def _executar_salvamento_diario(self) -> None:
        if not self.data_calendario_selecionada:
            return
        texto = self.text_diario.get("1.0", tk.END).strip()
        if texto:
            self.diario[self.data_calendario_selecionada] = texto
        elif self.data_calendario_selecionada in self.diario:
            del self.diario[self.data_calendario_selecionada]
        salvar_dados_seguros(ARQUIVO_DIARIO, self.diario)
        self.timer_salvamento = None
        self.desenhar_calendario()

    # ── Desconcluir ──────────────────────────
    def desconcluir_atividade(self) -> None:
        selecao = self.tabela_conc.selection()
        if not selecao:
            messagebox.showinfo("Info",
                                "Selecione pelo menos uma atividade para desconcluir.",
                                parent=self.win_conc)
            return

        for sel_item in selecao:
            id_ativ = self.tabela_conc.item(sel_item)["values"][0]
            ativ    = next((x for x in self.concluidas if x.get("id") == id_ativ), None)
            if ativ:
                ativ.pop("data_conclusao", None)
                self.concluidas.remove(ativ)
                self.pendentes.append(ativ)

        self.pendentes.sort(key=lambda x: converter_data(x.get("deadline", "")))
        salvar_dados_seguros(ARQUIVO_PENDENTES,  self.pendentes)
        salvar_dados_seguros(ARQUIVO_CONCLUIDAS, self.concluidas)
        self.atualizar_tabela_concluidas()
        self.atualizar_tabela_principal()
        messagebox.showinfo("Sucesso",
                            f"{len(selecao)} atividade(s) retornada(s) para o To-do!",
                            parent=self.win_conc)

    # ── Estatísticas ─────────────────────────
    def abrir_estatisticas(self) -> None:
        win_est = tk.Toplevel(self.root)
        win_est.title("Dashboard de produtividade")
        win_est.geometry("900x550")
        win_est.transient(self.root)
        win_est.bind("<Escape>", lambda e: win_est.destroy())
        win_est.focus_set()

        frame_filtros = tk.Frame(win_est, bg="#f8fafc", pady=10)
        frame_filtros.pack(fill=tk.X)

        tk.Label(frame_filtros, text="Período de Análise:",
                 bg="#f8fafc", font=("Arial", 9, "bold")
                 ).pack(side=tk.LEFT, padx=(15, 5))
        combo_periodo = ttk.Combobox(
            frame_filtros,
            values=["7 dias", "1 mês", "3 meses", "6 meses", "1 ano", "Personalizado"],
            state="readonly", width=15
        )
        combo_periodo.current(0)
        combo_periodo.pack(side=tk.LEFT, padx=5)

        tk.Label(frame_filtros, text="De:", bg="#f8fafc"
                 ).pack(side=tk.LEFT, padx=(15, 2))
        var_ini = tk.StringVar()
        ent_ini = tk.Entry(frame_filtros, textvariable=var_ini, width=12)
        ent_ini.pack(side=tk.LEFT, padx=5)
        self.setup_mascara_data(ent_ini, var_ini)

        tk.Label(frame_filtros, text="Até:", bg="#f8fafc"
                 ).pack(side=tk.LEFT, padx=(10, 2))
        var_fim = tk.StringVar()
        ent_fim = tk.Entry(frame_filtros, textvariable=var_fim, width=12)
        ent_fim.pack(side=tk.LEFT, padx=5)
        self.setup_mascara_data(ent_fim, var_fim)

        def alternar_campos(_event=None):
            st = tk.NORMAL if combo_periodo.get() == "Personalizado" else tk.DISABLED
            ent_ini.config(state=st)
            ent_fim.config(state=st)

        combo_periodo.bind("<<ComboboxSelected>>", alternar_campos)
        alternar_campos()

        frame_graficos = tk.Frame(win_est, bg="#f1f5f9")
        frame_graficos.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.canvas_pizza  = tk.Canvas(frame_graficos, bg="#ffffff",
                                       bd=1, relief="ridge")
        self.canvas_pizza.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                               padx=5, pady=5)
        self.canvas_barras = tk.Canvas(frame_graficos, bg="#ffffff",
                                       bd=1, relief="ridge")
        self.canvas_barras.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True,
                                padx=5, pady=5)

        def _draw_pizza(no_prazo, atrasadas):
            c = self.canvas_pizza
            c.delete("all")
            c.update_idletasks()
            w, h = max(c.winfo_width(), 400), max(c.winfo_height(), 400)

            c.create_text(w / 2, 30, text="Qualidade de entrega",
                          font=("Arial", 12, "bold"))
            total = no_prazo + atrasadas
            if total == 0:
                c.create_text(w / 2, h / 2,
                              text="Nenhum dado encontrado no período",
                              fill="#64748b")
                return

            cx, cy = w / 2, h / 2 + 20
            r  = min(w, h) / 3
            x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r

            if no_prazo == total:
                c.create_oval(x0, y0, x1, y1, fill="#10b981",
                              outline="white", width=2)
            elif atrasadas == total:
                c.create_oval(x0, y0, x1, y1, fill="#ef4444",
                              outline="white", width=2)
            else:
                ang = (no_prazo / total) * 360
                c.create_arc(x0, y0, x1, y1, start=90, extent=-ang,
                             fill="#10b981", outline="white", width=2)
                c.create_arc(x0, y0, x1, y1, start=90 - ang, extent=-(360 - ang),
                             fill="#ef4444", outline="white", width=2)

            pct_p = (no_prazo / total) * 100
            pct_a = (atrasadas / total) * 100
            c.create_rectangle(w/2-100, h-30, w/2-85, h-15,
                                fill="#10b981", outline="")
            c.create_text(w/2-80, h-22,
                          text=f"No prazo ({pct_p:.1f}%)", anchor="w")
            c.create_rectangle(w/2+20, h-30, w/2+35, h-15,
                                fill="#ef4444", outline="")
            c.create_text(w/2+40, h-22,
                          text=f"Atrasadas ({pct_a:.1f}%)", anchor="w")

        def _draw_barras(freq):
            c = self.canvas_barras
            c.delete("all")
            c.update_idletasks()
            w, h = max(c.winfo_width(), 400), max(c.winfo_height(), 400)

            c.create_text(w / 2, 30, text="Tarefas concluídas por dia",
                          font=("Arial", 12, "bold"))
            if not freq:
                c.create_text(w / 2, h / 2,
                              text="Nenhum dado encontrado no período",
                              fill="#64748b")
                return

            chaves  = sorted(freq, key=lambda d: datetime.strptime(d, DATE_FMT))
            valores = [freq[k] for k in chaves]
            labels  = [k[:5] for k in chaves]
            max_val = max(valores) or 1

            ml, mr, mt, mb = 40, 20, 60, 60
            larg = w - ml - mr
            alt  = h - mt - mb

            c.create_line(ml, h - mb, w - mr, h - mb, fill="#94a3b8")
            c.create_line(ml, mt,     ml,     h - mb, fill="#94a3b8")

            n      = len(valores)
            b_max  = min(larg / n, 50)
            espaço = (larg - b_max * n) / (n + 1)

            for i, val in enumerate(valores):
                bh = (val / max_val) * alt
                x0 = ml + espaço + i * (b_max + espaço)
                y0 = h - mb - bh
                x1 = x0 + b_max
                y1 = h - mb
                c.create_rectangle(x0, y0, x1, y1,
                                   fill="#22c55e", outline="#14532d")
                c.create_text((x0 + x1) / 2, y0 - 10,
                              text=str(val), font=("Arial", 9))
                c.create_text((x0 + x1) / 2, y1 + 15,
                              text=labels[i], font=("Arial", 8),
                              angle=45 if n > 5 else 0)

        def atualizar_graficos(_event=None):
            hoje   = datetime.today()
            per    = combo_periodo.get()
            d_fim  = hoje

            OFFSETS = {"7 dias": 7, "1 mês": 30, "3 meses": 90,
                       "6 meses": 180, "1 ano": 365}
            if per in OFFSETS:
                d_ini = hoje - timedelta(days=OFFSETS[per])
            else:
                try:
                    d_ini = datetime.strptime(var_ini.get(), DATE_FMT)
                    d_fim = datetime.strptime(var_fim.get(), DATE_FMT)
                except ValueError:
                    messagebox.showwarning("Erro",
                                          "Formato de data inválido. Use DD/MM/AAAA.",
                                          parent=win_est)
                    return

            d_ini = d_ini.replace(hour=0,  minute=0,  second=0)
            d_fim = d_fim.replace(hour=23, minute=59, second=59)

            no_prazo = atrasadas = 0
            freq: dict[str, int] = {}

            for a in self.concluidas:
                str_conc = a.get("data_conclusao") or a.get("deadline", "")
                dt_conc  = converter_data(str_conc)
                if dt_conc == datetime.max:
                    continue
                if not (d_ini <= dt_conc <= d_fim):
                    continue

                dt_prazo = converter_data(a.get("deadline", ""))
                if dt_prazo == datetime.max or dt_conc.date() <= dt_prazo.date():
                    no_prazo += 1
                else:
                    atrasadas += 1

                key = dt_conc.strftime(DATE_FMT)
                freq[key] = freq.get(key, 0) + 1

            _draw_pizza(no_prazo, atrasadas)
            _draw_barras(freq)

        tk.Button(frame_filtros, text="↻ Atualizar gráficos",
                  command=atualizar_graficos,
                  bg="#10b981", fg="white", font=("Arial", 9, "bold")
                  ).pack(side=tk.LEFT, padx=20)

        def agendar_atualizacao(e=None):
            if e and e.widget is not win_est:
                return
            if self.timer_graficos:
                win_est.after_cancel(self.timer_graficos)
            self.timer_graficos = win_est.after(200, atualizar_graficos)
            # Limpa a referência após execução para evitar cancel de timer expirado
            def _limpar():
                self.timer_graficos = None
            win_est.after(210, _limpar)

        win_est.bind("<Configure>", agendar_atualizacao)
        agendar_atualizacao()

    # ═══════════════════════════════════════
    #  SISTEMA DE RECORRÊNCIAS
    # ═══════════════════════════════════════
    def calcular_proximo_ciclo(self, data_base: datetime,
                               frequencia: str) -> datetime:
        if frequencia == "Diário":
            return data_base + timedelta(days=1)
        if frequencia == "Semanal":
            return data_base + timedelta(weeks=1)
        if frequencia == "Mensal":
            mes = data_base.month % 12 + 1
            ano = data_base.year + (1 if data_base.month == 12 else 0)
            dia = min(data_base.day, calendar.monthrange(ano, mes)[1])
            return datetime(ano, mes, dia)
        if frequencia == "Anual":
            ano = data_base.year + 1
            dia = min(data_base.day,
                      calendar.monthrange(ano, data_base.month)[1])
            return datetime(ano, data_base.month, dia)
        return data_base

    def processar_recorrencias(self) -> None:
        hoje          = datetime.today()
        limite        = hoje + timedelta(days=JANELA_GERACAO_DIAS)
        mudou_dados   = False
        ids_pendentes = {x.get("id_instancia") for x in self.pendentes
                         if x.get("id_instancia")}
        ids_concluidas = {x.get("id_instancia") for x in self.concluidas
                          if x.get("id_instancia")}

        for rec in self.recorrentes:
            prox = converter_data(rec.get("proxima_data", ""))
            if prox == datetime.max:
                continue

            while prox <= limite:
                id_inst = f"{rec['id']}_{prox.strftime('%Y%m%d')}"

                if id_inst not in ids_pendentes and id_inst not in ids_concluidas:
                    nova = {
                        "id":            str(uuid.uuid4()),
                        "id_instancia":  id_inst,
                        "id_recorrente": rec["id"],
                        "atividade":     f"🔄 {rec['atividade']}",
                        "deadline":      prox.strftime(DATE_FMT),
                        "comentarios":   rec.get("comentarios", ""),
                        "keywords":      [],
                        "data_dia":      None,
                    }
                    self.pendentes.append(nova)
                    ids_pendentes.add(id_inst)
                    mudou_dados = True

                prox = self.calcular_proximo_ciclo(prox, rec["frequencia"])

            # Atualiza proxima_data apenas se avançou
            nova_prox_str = prox.strftime(DATE_FMT)
            if rec.get("proxima_data") != nova_prox_str:
                rec["proxima_data"] = nova_prox_str
                mudou_dados = True

        if mudou_dados:
            self.pendentes.sort(
                key=lambda x: converter_data(x.get("deadline", "")))
            salvar_dados_seguros(ARQUIVO_PENDENTES,   self.pendentes)
            salvar_dados_seguros(ARQUIVO_RECORRENTES, self.recorrentes)

    # ── Nova atividade ───────────────────────
    def nova_atividade_popup(self, _event=None) -> None:
        popup = tk.Toplevel(self.root)
        popup.title("Criar Nova Atividade")
        popup.geometry("380x360")
        popup.transient(self.root)
        popup.grab_set()
        popup.bind("<Escape>", lambda e: popup.destroy())

        tk.Label(popup, text="Atividade:").pack(pady=(10, 0))
        entry_atividade = tk.Entry(popup, width=40)
        entry_atividade.pack(pady=5)
        entry_atividade.focus_set()

        tk.Label(popup, text="Deadline (Inicial se recorrente):").pack()

        frame_dl   = tk.Frame(popup)
        frame_dl.pack(pady=5)

        var_deadline  = tk.StringVar()
        entry_deadline = tk.Entry(frame_dl, width=32, textvariable=var_deadline)
        entry_deadline.pack(side=tk.LEFT, padx=(0, 5))
        self.setup_mascara_data(entry_deadline, var_deadline)

        def abrir_seletor_data():
            top      = tk.Toplevel(popup)
            top.title("📅")
            top.geometry("220x220")
            top.transient(popup)
            top.grab_set()

            hoje_s = datetime.today()
            ano_s  = tk.IntVar(value=hoje_s.year)
            mes_s  = tk.IntVar(value=hoje_s.month)

            frame_nav  = tk.Frame(top)
            frame_nav.pack(pady=10)
            lbl_m_a    = tk.Label(frame_nav, font=("Arial", 10, "bold"), width=12)
            frame_dias = tk.Frame(top)
            frame_dias.pack()

            def desenhar():
                for w in frame_dias.winfo_children():
                    w.destroy()
                MESES_ABR = ["Jan","Fev","Mar","Abr","Mai","Jun",
                             "Jul","Ago","Set","Out","Nov","Dez"]
                lbl_m_a.config(text=f"{MESES_ABR[mes_s.get()-1]} {ano_s.get()}")
                for i, d in enumerate(["D","S","T","Q","Q","S","S"]):
                    tk.Label(frame_dias, text=d, font=("Arial", 8, "bold"),
                             width=3).grid(row=0, column=i)
                cal_o = calendar.Calendar(firstweekday=6)
                for r, sem in enumerate(
                        cal_o.monthdayscalendar(ano_s.get(), mes_s.get())):
                    for c, dia in enumerate(sem):
                        if dia:
                            eh_h = (dia == hoje_s.day and
                                    mes_s.get() == hoje_s.month and
                                    ano_s.get() == hoje_s.year)
                            tk.Button(
                                frame_dias, text=str(dia), width=2,
                                bg="#16a34a" if eh_h else "#f1f5f9",
                                fg="white"  if eh_h else "black",
                                relief="flat",
                                command=lambda d=dia: selecionar(d)
                            ).grid(row=r+1, column=c, padx=1, pady=1)

            def selecionar(dia):
                var_deadline.set(f"{dia:02d}/{mes_s.get():02d}/{ano_s.get()}")
                top.destroy()
                entry_comentarios.focus_set()

            def nav(delta_m):
                m = mes_s.get() + delta_m
                if m < 1:
                    mes_s.set(12); ano_s.set(ano_s.get() - 1)
                elif m > 12:
                    mes_s.set(1);  ano_s.set(ano_s.get() + 1)
                else:
                    mes_s.set(m)
                desenhar()

            tk.Button(frame_nav, text="<", command=lambda: nav(-1),
                      relief="flat", bg="#e2e8f0").pack(side=tk.LEFT)
            lbl_m_a.pack(side=tk.LEFT, padx=5)
            tk.Button(frame_nav, text=">", command=lambda: nav(1),
                      relief="flat", bg="#e2e8f0").pack(side=tk.LEFT)
            desenhar()

        tk.Button(frame_dl, text="📅", command=abrir_seletor_data,
                  bg="#e2e8f0", relief="groove").pack(side=tk.LEFT)

        tk.Label(popup, text="Comentários:").pack()
        entry_comentarios = tk.Entry(popup, width=40)
        entry_comentarios.pack(pady=5)

        # Recorrência
        frame_rec    = tk.Frame(popup)
        frame_rec.pack(pady=10, fill=tk.X, padx=30)
        var_rec      = tk.BooleanVar(value=False)
        frame_freq   = tk.Frame(frame_rec)

        tk.Label(frame_freq, text="Frequência:").pack(side=tk.LEFT)
        combo_freq = ttk.Combobox(
            frame_freq,
            values=["Diário", "Semanal", "Mensal", "Anual"],
            state="readonly", width=15
        )
        combo_freq.current(2)
        combo_freq.pack(side=tk.LEFT, padx=5)

        def toggle_freq():
            if var_rec.get():
                frame_freq.pack(anchor=tk.W, pady=5)
            else:
                frame_freq.pack_forget()

        chk = tk.Checkbutton(frame_rec, text="Essa atividade é recorrente?",
                             variable=var_rec, command=toggle_freq)
        chk.pack(anchor=tk.W)

        def salvar(_event=None):
            nome      = entry_atividade.get().strip()
            deadline  = var_deadline.get().strip()
            coment    = entry_comentarios.get().strip()

            if not nome or not deadline:
                messagebox.showwarning("Aviso",
                                       "Nome e Deadline são obrigatórios!",
                                       parent=popup)
                return
            if not validar_data(deadline):
                messagebox.showwarning("Aviso",
                                       "Formato de data inválido.\nUse DD/MM/AAAA.",
                                       parent=popup)
                return

            if var_rec.get():
                self.recorrentes.append({
                    "id":          str(uuid.uuid4()),
                    "atividade":   nome,
                    "frequencia":  combo_freq.get(),
                    "proxima_data": deadline,
                    "comentarios": coment,
                })
                salvar_dados_seguros(ARQUIVO_RECORRENTES, self.recorrentes)
                self.processar_recorrencias()
            else:
                self.pendentes.append({
                    "id":          str(uuid.uuid4()),
                    "atividade":   nome,
                    "deadline":    deadline,
                    "comentarios": coment,
                    "keywords":    [],
                    "data_dia":    None,
                })
                self.pendentes.sort(
                    key=lambda x: converter_data(x.get("deadline", "")))
                salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)

            self.atualizar_tabela_principal()
            popup.destroy()

        tk.Button(popup, text="Salvar", command=salvar,
                  bg="#16a34a", fg="white").pack(pady=10)
        popup.bind("<Return>", salvar)

    # ── Recorrentes ──────────────────────────
    def abrir_recorrentes(self, _event=None) -> None:
        win_rec = tk.Toplevel(self.root)
        win_rec.title("Gerenciar atividades recorrentes")
        win_rec.geometry("650x400")
        win_rec.bind("<Escape>", lambda e: win_rec.destroy())
        win_rec.focus_set()

        frame_top = tk.Frame(win_rec)
        frame_top.pack(fill=tk.X, padx=10, pady=10)

        colunas   = ("id", "Atividade", "Frequência", "Próximo Gatilho")
        tabela_rec = ttk.Treeview(win_rec, columns=colunas, show="headings")

        for col, w in [("Atividade", 300), ("Frequência", 120),
                       ("Próximo Gatilho", 150)]:
            tabela_rec.heading(col, text=col)
            tabela_rec.column(col, width=w)
        tabela_rec.column("id", width=0, stretch=tk.NO)
        tabela_rec.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def atualizar_lista():
            for item in tabela_rec.get_children():
                tabela_rec.delete(item)
            for rec in self.recorrentes:
                tabela_rec.insert("", tk.END, values=(
                    rec["id"], rec["atividade"],
                    rec["frequencia"], rec.get("proxima_data", "")
                ))

        def excluir_template():
            selecao = tabela_rec.selection()
            if not selecao:
                return
            if messagebox.askyesno(
                "Confirmar",
                "Deseja parar esta recorrência?\n\n"
                "As atividades já geradas continuarão no To-do, "
                "mas novas não serão criadas.",
                parent=win_rec
            ):
                ids = {tabela_rec.item(s)["values"][0] for s in selecao}
                self.recorrentes = [x for x in self.recorrentes
                                    if x["id"] not in ids]
                salvar_dados_seguros(ARQUIVO_RECORRENTES, self.recorrentes)
                atualizar_lista()

        tk.Button(frame_top, text="❌ Parar recorrência selecionada",
                  command=excluir_template, bg="#ef4444", fg="white"
                  ).pack(side=tk.LEFT)

        atualizar_lista()


# ─────────────────────────────────────────────
#  PONTO DE ENTRADA
# ─────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    splash = tk.Toplevel(root)
    splash.overrideredirect(True)

    try:
        img_orig   = tk.PhotoImage(file=caminho_recurso("splash.png"))
        img_splash = img_orig.subsample(2, 2)
        larg, alt  = img_splash.width(), img_splash.height()
        x = (root.winfo_screenwidth()  // 2) - (larg // 2)
        y = (root.winfo_screenheight() // 2) - (alt  // 2)
        splash.geometry(f"{larg}x{alt}+{x}+{y}")
        lbl = tk.Label(splash, image=img_splash, bg="white")
        lbl.image = img_splash
        lbl.pack()
    except tk.TclError:
        print("Aviso: splash.png não encontrada. Abrindo app direto...")

    app = AppOrganizacao(root)

    def iniciar_app():
        splash.destroy()
        root.deiconify()

    root.after(3000, iniciar_app)
    root.mainloop()