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

def caminho_recurso(caminho_relativo):
    """ Garante que o programa encontra os ficheiros tanto em modo de teste (.py) 
        como depois de compactado pelo PyInstaller (.exe) """
    try:
        # O PyInstaller cria uma pasta temporária em _MEIPASS quando o .exe abre
        caminho_base = sys._MEIPASS
    except Exception:
        caminho_base = os.path.abspath(".")
    return os.path.join(caminho_base, caminho_relativo)

# --- SISTEMA DE PASTAS NA APPDATA ---
appdata_path = os.getenv('APPDATA')
PASTA_APP = os.path.join(appdata_path, 'Leaf')

if not os.path.exists(PASTA_APP):
    os.makedirs(PASTA_APP)

ARQUIVO_PENDENTES = os.path.join(PASTA_APP, 'pendentes.json')
ARQUIVO_CONCLUIDAS = os.path.join(PASTA_APP, 'concluidas.json')
ARQUIVO_DIARIO = os.path.join(PASTA_APP, 'diario.json')
ARQUIVO_RECORRENTES = os.path.join(PASTA_APP, 'recorrentes.json')
# -----------------------------------------

def carregar_dados_seguros(arquivo, tipo_padrao):
    if not os.path.exists(arquivo):
        return tipo_padrao
    
    with open(arquivo, 'r', encoding='utf-8') as f:
        conteudo = f.read()
        if not conteudo:
            return tipo_padrao
            
        try:
            texto_decodificado = base64.b64decode(conteudo).decode('utf-8')
            return json.loads(texto_decodificado)
        except Exception:
            try:
                return json.loads(conteudo)
            except:
                return tipo_padrao

# --- CORREÇÃO DO ERRO DE PERMISSÃO ---
def salvar_dados_seguros(arquivo, dados):
    texto_json = json.dumps(dados, ensure_ascii=False)
    texto_codificado = base64.b64encode(texto_json.encode('utf-8')).decode('utf-8')
    
    caminho_absoluto = os.path.abspath(arquivo)
    
    try:
        if os.name == 'nt' and os.path.exists(caminho_absoluto):
            ctypes.windll.kernel32.SetFileAttributesW(caminho_absoluto, 128)
    except Exception:
        pass

    with open(arquivo, 'w', encoding='utf-8') as f:
        f.write(texto_codificado)
        
    try:
        if os.name == 'nt': 
            ctypes.windll.kernel32.SetFileAttributesW(caminho_absoluto, 2)
    except Exception:
        pass
# -------------------------------------

def converter_data(data_str):
    try:
        return datetime.strptime(data_str, "%d/%m/%Y")
    except ValueError:
        return datetime.max

class AppOrganizacao:
    def __init__(self, root):
        self.root = root
        self.root.title("Leaf v.1.0")
        self.root.iconbitmap('icone.ico')
        self.root.geometry("900x550")
        
        try:
            self.root.iconbitmap('icone.ico')
        except:
            pass
        
        self.pendentes = carregar_dados_seguros(ARQUIVO_PENDENTES, [])
        self.concluidas = carregar_dados_seguros(ARQUIVO_CONCLUIDAS, [])
        self.diario = carregar_dados_seguros(ARQUIVO_DIARIO, {})
        self.recorrentes = carregar_dados_seguros(ARQUIVO_RECORRENTES, [])
        self.processar_recorrencias() # Acorda o robô de repetição ao abrir o app
        
        for ativ in self.pendentes + self.concluidas:
            if 'id' not in ativ:
                ativ['id'] = str(uuid.uuid4())
        
        # Otimização: Ordena apenas no carregamento inicial
        self.pendentes.sort(key=lambda x: converter_data(x.get('deadline', '')))
        
        self.ano_cal = datetime.today().year
        self.mes_cal = datetime.today().month
        self.data_calendario_selecionada = None
        self.timer_salvamento = None 
        self.timer_graficos = None # Variável para o debounce dos gráficos
        
        self.configurar_interface_principal()
        self.atualizar_relogio()
        self.atualizar_tabela_principal()

    def configurar_interface_principal(self):
        self.lbl_relogio = tk.Label(self.root, text="", font=("Arial", 11, "bold"), bg="#bbbbbb", fg="#14532d", pady=6)
        self.lbl_relogio.pack(fill=tk.X, side=tk.TOP)

        frame_botoes = tk.Frame(self.root)
        frame_botoes.pack(fill=tk.X, padx=10, pady=10)
        
        btn_nova = tk.Button(frame_botoes, text="+ Nova atividade", command=self.nova_atividade_popup, bg="#16a34a", fg="white", font=("Arial", 10, "bold"))
        btn_nova.pack(side=tk.LEFT, padx=5)
        
        btn_concluir = tk.Button(frame_botoes, text="✓ Concluir selecionada(s)", command=lambda: self.concluir_atividade(self.tabela))
        btn_concluir.pack(side=tk.LEFT, padx=5)

        btn_add_dia = tk.Button(frame_botoes, text="➔ Agendar para hoje", command=self.adicionar_ao_dia)
        btn_add_dia.pack(side=tk.LEFT, padx=5)

        btn_menu_dia = tk.Button(frame_botoes, text="📋 Atividades do dia", command=self.abrir_menu_dia)
        btn_menu_dia.pack(side=tk.LEFT, padx=5)
        
        btn_calendario = tk.Button(frame_botoes, text="📅 Calendário", command=self.abrir_calendario_popup, bg="#15803d", fg="white")
        btn_calendario.pack(side=tk.RIGHT, padx=5)
        
        # Botão recorrentes verde e logo após o calendário
        btn_recorrentes = tk.Button(frame_botoes, text="🔄 Recorrentes", command=self.abrir_recorrentes, bg="#15803d", fg="white")
        btn_recorrentes.pack(side=tk.RIGHT, padx=5)
        
        btn_concluidas = tk.Button(frame_botoes, text="📁 Atividades concluídas", command=self.abrir_concluidas)
        btn_concluidas.pack(side=tk.RIGHT, padx=5)

        lbl_titulo_tabela = tk.Label(self.root, text="📌 To-do", font=("Arial", 11, "bold"), fg="#166534")
        lbl_titulo_tabela.pack(anchor=tk.W, padx=15, pady=(5, 0))

        frame_rodape = tk.Frame(self.root)
        frame_rodape.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        
        frame_legenda = tk.Frame(frame_rodape)
        frame_legenda.pack(side=tk.LEFT)
        
        tk.Label(frame_legenda, text="Legenda de prazos:", font=("Arial", 9, "bold"), fg="#14532d").pack(side=tk.LEFT, padx=(0, 5))
        tk.Label(frame_legenda, text=" Atrasada ", bg="#14532d", fg="#ffffff", font=("Arial", 8)).pack(side=tk.LEFT, padx=2)
        tk.Label(frame_legenda, text=" Hoje ", bg="#16a34a", fg="#ffffff", font=("Arial", 8)).pack(side=tk.LEFT, padx=2)
        tk.Label(frame_legenda, text=" Esta semana ", bg="#86efac", fg="#064e3b", font=("Arial", 8)).pack(side=tk.LEFT, padx=2)
        tk.Label(frame_legenda, text=" > 1 Semana ", bg="#dcfce7", fg="#064e3b", font=("Arial", 8)).pack(side=tk.LEFT, padx=2)
        tk.Label(frame_legenda, text=" Sem data ", bg="#ffffff", fg="#000000", borderwidth=1, relief="solid", font=("Arial", 8)).pack(side=tk.LEFT, padx=2)

        lbl_copyright = tk.Label(frame_rodape, text="© 2026 João Victor Aires. All rights reserved.", font=("Arial", 8), fg="#64748b")
        lbl_copyright.pack(side=tk.RIGHT)

        colunas = ("id", "Atividade", "Deadline", "Comentários")
        self.tabela = ttk.Treeview(self.root, columns=colunas, show="headings")
        
        self.tabela.heading("Atividade", text="Atividade")
        self.tabela.heading("Deadline", text="Deadline")
        self.tabela.heading("Comentários", text="Comentários")
        
        self.tabela.column("id", width=0, stretch=tk.NO)
        self.tabela.column("Atividade", width=280)
        self.tabela.column("Deadline", width=130, anchor=tk.CENTER)
        self.tabela.column("Comentários", width=400)
        
        self.tabela.tag_configure('atrasada', background='#14532d', foreground='#ffffff')
        self.tabela.tag_configure('hoje', background='#16a34a', foreground='#ffffff')
        self.tabela.tag_configure('esta_semana', background='#86efac', foreground='#064e3b')
        self.tabela.tag_configure('mais_uma_semana', background='#dcfce7', foreground='#064e3b')
        self.tabela.tag_configure('normal', background='#ffffff', foreground='#000000')

        self.tabela.pack(fill=tk.BOTH, expand=True, padx=10, pady=(2, 10))

        self.menu_contexto = tk.Menu(self.root, tearoff=0)
        self.menu_contexto.add_command(label="Editar Atividade", command=self.editar_atividade_popup)
        self.menu_contexto.add_command(label="Marcar como Concluída(s)", command=lambda: self.concluir_atividade(self.tabela))
        self.menu_contexto.add_separator()
        self.menu_contexto.add_command(label="❌ Excluir Atividade(s)", command=self.excluir_atividade)
        
        self.tabela.bind("<Button-3>", self.mostrar_menu_contexto)
        self.tabela.bind("<Button-1>", self.desmarcar_clique_vazio)

# --- ATALHOS DE TECLADO ---
        self.root.bind('<Control-n>', self.nova_atividade_popup)
        self.root.bind('<Control-N>', self.nova_atividade_popup) # Para funcionar mesmo se o Caps Lock estiver ligado

        self.root.bind('<Control-n>', self.nova_atividade_popup)
        self.root.bind('<Control-N>', self.nova_atividade_popup)
        
        self.root.bind('<Control-k>', self.abrir_calendario_popup)
        self.root.bind('<Control-K>', self.abrir_calendario_popup)
        
        self.root.bind('<Control-r>', self.abrir_recorrentes)
        self.root.bind('<Control-R>', self.abrir_recorrentes)

    def desmarcar_clique_vazio(self, event):
        tabela = event.widget
        if tabela.identify_region(event.x, event.y) == "nothing":
            tabela.selection_remove(tabela.selection())

    def atualizar_relogio(self):
        dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
        meses = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
        
        agora = datetime.now()
        txt_dia_semana = dias_semana[agora.weekday()]
        txt_mes = meses[agora.month - 1]
        
        texto_barra = f"📅 {txt_dia_semana}, {agora.day} de {txt_mes} de {agora.year}   |   🕓 {agora.strftime('%H:%M:%S')}"
        self.lbl_relogio.config(text=texto_barra)
        self.root.after(1000, self.atualizar_relogio)

    def atualizar_tabela_principal(self):
        for item in self.tabela.get_children():
            self.tabela.delete(item)
            
        hoje = datetime.today().date()
        ano_atual, semana_atual, _ = hoje.isocalendar()
        
        for ativ in self.pendentes:
            prazo = converter_data(ativ['deadline'])
            tag_linha = 'normal'
            
            if prazo != datetime.max:
                prazo_date = prazo.date()
                diferenca_dias = (prazo_date - hoje).days

                if prazo_date < hoje:
                    tag_linha = 'atrasada'
                elif prazo_date == hoje:
                    tag_linha = 'hoje'
                elif diferenca_dias > 7:
                    tag_linha = 'mais_uma_semana'
                else:
                    ano_praz, sem_praz, _ = prazo_date.isocalendar()
                    if ano_praz == ano_atual and sem_praz == semana_atual:
                        tag_linha = 'esta_semana'
            
            self.tabela.insert("", tk.END, values=(ativ['id'], ativ['atividade'], ativ['deadline'], ativ.get('comentarios', '')), tags=(tag_linha,))

    def setup_mascara_data(self, entry_widget, string_var):
        def formatar_data(*args):
            texto = string_var.get()
            digitos = "".join([c for c in texto if c.isdigit()])
            formatado = ""
            if len(digitos) > 0: formatado += digitos[:2]
            if len(digitos) > 2: formatado += "/" + digitos[2:4]
            if len(digitos) > 4: formatado += "/" + digitos[4:8]
            
            if texto != formatado:
                string_var.set(formatado)
            
            entry_widget.after(2, lambda: entry_widget.icursor(tk.END))
                
        string_var.trace_add("write", formatar_data)

    def mostrar_menu_contexto(self, event):
        item_sob_mouse = self.tabela.identify_row(event.y)
        if item_sob_mouse:
            if item_sob_mouse not in self.tabela.selection():
                self.tabela.selection_set(item_sob_mouse)
            self.menu_contexto.post(event.x_root, event.y_root)

    def editar_atividade_popup(self):
        selecao = self.tabela.selection()
        if not selecao:
            return
        
        if len(selecao) > 1:
            messagebox.showinfo("Info", "Selecione apenas UMA atividade para editar.")
            return
            
        item = self.tabela.item(selecao[0])
        id_ativ = item['values'][0]
        ativ_idx = next((i for i, x in enumerate(self.pendentes) if x['id'] == id_ativ), None)
        
        if ativ_idx is None:
            return
            
        ativ = self.pendentes[ativ_idx]

        popup = tk.Toplevel(self.root)
        popup.title("Editar Atividade")
        popup.geometry("350x250")
        popup.transient(self.root)
        popup.grab_set()
        popup.bind('<Escape>', lambda event: popup.destroy())

        tk.Label(popup, text="Atividade:").pack(pady=(10, 0))
        entry_atividade = tk.Entry(popup, width=40)
        entry_atividade.insert(0, ativ['atividade'])
        entry_atividade.pack(pady=5)
        entry_atividade.focus_set()

        tk.Label(popup, text="Deadline (DD/MM/AAAA):").pack()
        var_deadline = tk.StringVar(value=ativ['deadline'])
        entry_deadline = tk.Entry(popup, width=40, textvariable=var_deadline)
        entry_deadline.pack(pady=5)
        self.setup_mascara_data(entry_deadline, var_deadline)

        tk.Label(popup, text="Comentários:").pack()
        entry_comentarios = tk.Entry(popup, width=40)
        entry_comentarios.insert(0, ativ['comentarios'])
        entry_comentarios.pack(pady=5)

        def salvar_edicao(event=None):
            ativ['atividade'] = entry_atividade.get().strip()
            ativ['deadline'] = var_deadline.get().strip()
            ativ['comentarios'] = entry_comentarios.get().strip()
            
            # Otimização: Reordena e salva apenas no momento da edição
            self.pendentes.sort(key=lambda x: converter_data(x.get('deadline', '')))
            salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
            
            self.atualizar_tabela_principal()
            popup.destroy()

        tk.Button(popup, text="Salvar Alterações", command=salvar_edicao, bg="#15803d", fg="white").pack(pady=15)
        popup.bind('<Return>', salvar_edicao)

    def excluir_atividade(self):
        selecao = self.tabela.selection()
        if not selecao:
            return
            
        resposta = messagebox.askyesno("Confirmar Exclusão", f"Tem certeza que deseja excluir em definitivo as {len(selecao)} atividade(s) selecionada(s)?")
        if resposta:
            for sel_item in selecao:
                item = self.tabela.item(sel_item)
                id_ativ = item['values'][0]
                
                ativ_encontrada = next((x for x in self.pendentes if x['id'] == id_ativ), None)
                if ativ_encontrada:
                    self.pendentes.remove(ativ_encontrada)
                    
            salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
            self.atualizar_tabela_principal()

    def concluir_atividade(self, tabela_origem):
        selecao = tabela_origem.selection()
        if not selecao:
            messagebox.showinfo("Info", "Selecione pelo menos uma atividade para concluir.")
            return
            
        for sel_item in selecao:
            item = tabela_origem.item(sel_item)
            id_ativ = item['values'][0]
            
            ativ_encontrada = next((x for x in self.pendentes if x['id'] == id_ativ), None)
            if ativ_encontrada:
                ativ_encontrada['data_conclusao'] = datetime.today().strftime("%d/%m/%Y")
                
                self.pendentes.remove(ativ_encontrada)
                self.concluidas.append(ativ_encontrada)
                
        salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
        salvar_dados_seguros(ARQUIVO_CONCLUIDAS, self.concluidas)
        
        self.atualizar_tabela_principal()
        
        if hasattr(self, 'win_conc') and self.win_conc.winfo_exists():
            self.atualizar_tabela_concluidas()
            
        messagebox.showinfo("Sucesso", f"{len(selecao)} atividade(s) enviada(s) para concluídas!")
        
        if tabela_origem != self.tabela:
            for sel_item in selecao:
                if tabela_origem.exists(sel_item):
                    tabela_origem.delete(sel_item)

    def adicionar_ao_dia(self):
        selecao = self.tabela.selection()
        if not selecao:
            messagebox.showinfo("Info", "Selecione pelo menos uma atividade na planilha principal.")
            return
            
        hoje_str = datetime.today().strftime("%d/%m/%Y")
        contador = 0
        
        for sel_item in selecao:
            item = self.tabela.item(sel_item)
            id_ativ = item['values'][0]
            
            for ativ in self.pendentes:
                if ativ['id'] == id_ativ:
                    ativ['data_dia'] = hoje_str
                    contador += 1
                    break
                    
        salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
        messagebox.showinfo("Sucesso", f"{contador} atividade(s) copiada(s) para as tarefas do dia!")

    def remover_do_dia(self, tabela_origem):
        selecao = tabela_origem.selection()
        if not selecao:
            messagebox.showinfo("Info", "Selecione pelo menos uma atividade para remover do dia.")
            return
            
        contador = 0
        for sel_item in selecao:
            item = tabela_origem.item(sel_item)
            id_ativ = item['values'][0]
            
            for ativ in self.pendentes:
                if ativ['id'] == id_ativ:
                    ativ['data_dia'] = None
                    contador += 1
                    break
                    
        salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
        
        for sel_item in selecao:
            if tabela_origem.exists(sel_item):
                tabela_origem.delete(sel_item)
                
        messagebox.showinfo("Sucesso", f"{contador} atividade(s) removida(s) das tarefas do dia!")

    def abrir_concluidas(self):
        self.win_conc = tk.Toplevel(self.root)
        self.win_conc.title("Atividades concluídas")
        self.win_conc.geometry("850x450")
        self.win_conc.bind('<Escape>', lambda event: self.win_conc.destroy())
        self.win_conc.focus_set()
        
        frame_top = tk.Frame(self.win_conc)
        frame_top.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Label(frame_top, text="🔍 Buscar:").pack(side=tk.LEFT)
        self.entry_busca = tk.Entry(frame_top, width=25)
        self.entry_busca.pack(side=tk.LEFT, padx=5)
        self.entry_busca.bind("<KeyRelease>", lambda e: self.atualizar_tabela_concluidas())
        
        tk.Label(frame_top, text="  |  Ordenar por:").pack(side=tk.LEFT)
        self.combo_ordem = ttk.Combobox(frame_top, values=["Padrão", "Atividade (A-Z)", "Atividade (Z-A)", "Deadline (Mais novas)", "Deadline (Mais antigas)"], state="readonly", width=22)
        self.combo_ordem.current(0)
        self.combo_ordem.pack(side=tk.LEFT, padx=5)
        self.combo_ordem.bind("<<ComboboxSelected>>", lambda e: self.atualizar_tabela_concluidas())
        
        btn_exportar = tk.Button(frame_top, text="📥 Exportar para .txt", command=self.exportar_concluidas, bg="#10b981", fg="white", font=("Arial", 9, "bold"))
        btn_exportar.pack(side=tk.RIGHT, padx=(5, 0))

        btn_estatisticas = tk.Button(frame_top, text="📊 Estatísticas", command=self.abrir_estatisticas, bg="#047857", fg="white", font=("Arial", 9, "bold"))
        btn_estatisticas.pack(side=tk.RIGHT, padx=5)

        colunas = ("id", "Atividade", "Deadline", "Comentários", "Palavras-chave")
        self.tabela_conc = ttk.Treeview(self.win_conc, columns=colunas, show="headings")
        
        self.tabela_conc.heading("Atividade", text="Atividade")
        self.tabela_conc.heading("Deadline", text="Deadline")
        self.tabela_conc.heading("Comentários", text="Comentários")
        self.tabela_conc.heading("Palavras-chave", text="Palavras-chave")
        
        self.tabela_conc.column("id", width=0, stretch=tk.NO)
        self.tabela_conc.column("Atividade", width=230)
        self.tabela_conc.column("Deadline", width=100, anchor=tk.CENTER)
        self.tabela_conc.column("Comentários", width=300)
        self.tabela_conc.column("Palavras-chave", width=150)
        
        self.tabela_conc.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        self.menu_contexto_conc = tk.Menu(self.win_conc, tearoff=0)

        self.menu_contexto_conc.add_command(label="↩️ Voltar para To-do", command=self.desconcluir_atividade)
        self.menu_contexto_conc.add_separator()

        self.menu_contexto_conc.add_command(label="🏷️ Gerenciar Palavras-chave", command=self.gerenciar_palavras_chave_popup)
        
        self.tabela_conc.bind("<Button-3>", self.mostrar_menu_contexto_conc)
        self.tabela_conc.bind("<Button-1>", self.desmarcar_clique_vazio)
        
        self.atualizar_tabela_concluidas()

    def mostrar_menu_contexto_conc(self, event):
        item_sob_mouse = self.tabela_conc.identify_row(event.y)
        if item_sob_mouse:
            if item_sob_mouse not in self.tabela_conc.selection():
                self.tabela_conc.selection_set(item_sob_mouse)
            self.menu_contexto_conc.post(event.x_root, event.y_root)

    def atualizar_tabela_concluidas(self):
        for item in self.tabela_conc.get_children():
            self.tabela_conc.delete(item)
            
        busca = self.entry_busca.get().lower()
        ordem = self.combo_ordem.get()
        
        lista_exibicao = []
        for ativ in self.concluidas:
            texto_atividade = ativ.get('atividade', '').lower()
            tags = " ".join(ativ.get('keywords', [])).lower()
            if busca in texto_atividade or busca in tags:
                lista_exibicao.append(ativ)
                
        if ordem == "Atividade (A-Z)":
            lista_exibicao.sort(key=lambda x: x.get('atividade', '').lower())
        elif ordem == "Atividade (Z-A)":
            lista_exibicao.sort(key=lambda x: x.get('atividade', '').lower(), reverse=True)
        elif ordem == "Deadline (Mais Novas)":
            lista_exibicao.sort(key=lambda x: converter_data(x.get('deadline', '')), reverse=True)
        elif ordem == "Deadline (Mais Antigas)":
            lista_exibicao.sort(key=lambda x: converter_data(x.get('deadline', '')))

        for ativ in lista_exibicao:
            str_tags = ", ".join(ativ.get('keywords', []))
            self.tabela_conc.insert("", tk.END, values=(
                ativ.get('id', ''), 
                ativ.get('atividade',''), 
                ativ.get('deadline',''), 
                ativ.get('comentarios',''),
                str_tags
            ))

    def gerenciar_palavras_chave_popup(self):
        selecao = self.tabela_conc.selection()
        if not selecao:
            return
            
        if len(selecao) > 1:
            messagebox.showinfo("Info", "Selecione apenas UMA atividade para gerenciar tags.")
            return

        item = self.tabela_conc.item(selecao[0])
        id_ativ = item['values'][0]
        
        ativ_idx = next((i for i, x in enumerate(self.concluidas) if x.get('id') == id_ativ), None)
        if ativ_idx is None: return
        
        ativ = self.concluidas[ativ_idx]
        if 'keywords' not in ativ:
            ativ['keywords'] = []

        popup = tk.Toplevel(self.root)
        popup.title("Gerenciar Palavras-chave")
        popup.geometry("300x320")
        popup.transient(self.root)
        popup.grab_set()
        popup.bind('<Escape>', lambda event: popup.destroy())

        tk.Label(popup, text=f"Tags para:\n{ativ.get('atividade','')}", font=("Arial", 9, "bold"), wraplength=280).pack(pady=10)

        frame_list = tk.Frame(popup)
        frame_list.pack(fill=tk.BOTH, expand=True, padx=10)

        listbox_tags = tk.Listbox(frame_list)
        listbox_tags.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(frame_list, orient="vertical")
        scrollbar.config(command=listbox_tags.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        listbox_tags.config(yscrollcommand=scrollbar.set)

        def atualizar_listbox():
            listbox_tags.delete(0, tk.END)
            for tag in ativ['keywords']:
                listbox_tags.insert(tk.END, f" #{tag}")

        atualizar_listbox()

        frame_controles = tk.Frame(popup)
        frame_controles.pack(fill=tk.X, padx=10, pady=10)

        entry_nova_tag = tk.Entry(frame_controles)
        entry_nova_tag.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        entry_nova_tag.focus_set()

        def add_tag(event=None):
            nova_tag = entry_nova_tag.get().strip().replace("#", "")
            if nova_tag and nova_tag not in ativ['keywords']:
                ativ['keywords'].append(nova_tag)
                atualizar_listbox()
                entry_nova_tag.delete(0, tk.END)
                salvar_dados_seguros(ARQUIVO_CONCLUIDAS, self.concluidas)
                self.atualizar_tabela_concluidas()

        btn_add = tk.Button(frame_controles, text=" + ", command=add_tag, bg="#16a34a", fg="white", font=("Arial", 10, "bold"))
        btn_add.pack(side=tk.LEFT)
        popup.bind('<Return>', add_tag)

        def remove_tag():
            selecao_tag = listbox_tags.curselection()
            if selecao_tag:
                tag_real = listbox_tags.get(selecao_tag[0]).replace(" #", "")
                ativ['keywords'].remove(tag_real)
                atualizar_listbox()
                salvar_dados_seguros(ARQUIVO_CONCLUIDAS, self.concluidas)
                self.atualizar_tabela_concluidas()

        btn_remover = tk.Button(popup, text="Remover Tag Selecionada", command=remove_tag, bg="#ef4444", fg="white")
        btn_remover.pack(pady=(0, 10))

    def exportar_concluidas(self):
        if not self.concluidas:
            messagebox.showinfo("Info", "Não há atividades concluídas para exportar.")
            return

        caminho_arquivo = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Arquivo de Texto", "*.txt")],
            initialfile="atividades_concluidas.txt",
            title="Salvar Histórico"
        )
        
        if caminho_arquivo:
            try:
                with open(caminho_arquivo, 'w', encoding='utf-8') as f:
                    f.write("=== HISTÓRICO DE ATIVIDADES CONCLUÍDAS ===\n")
                    f.write(f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}\n")
                    f.write("="*42 + "\n\n")
                    
                    for ativ in self.concluidas:
                        f.write(f"ATIVIDADE: {ativ.get('atividade', 'Sem título')}\n")
                        f.write(f"PRAZO: {ativ.get('deadline', 'Sem data')}\n")
                        coment = ativ.get('comentarios', '')
                        if coment:
                            f.write(f"COMENTARIOS: {coment}\n")
                        tags = ", ".join(ativ.get('keywords', []))
                        if tags:
                            f.write(f"TAGS: {tags}\n")
                        f.write("-" * 42 + "\n")
                
                messagebox.showinfo("Sucesso", f"Atividades exportadas com sucesso para:\n{caminho_arquivo}")
            except Exception as e:
                messagebox.showerror("Erro", f"Ocorreu um erro ao salvar o arquivo:\n{e}")

    def abrir_menu_dia(self):
        janela = tk.Toplevel(self.root)
        janela.title("Atividades do dia")
        janela.geometry("750x450") 
        janela.bind('<Escape>', lambda event: janela.destroy())
        janela.focus_set()
        
        # --- LEGENDA DE PRIORIDADES (Com as cores exatas das linhas) ---
        frame_leg_dia = tk.Frame(janela)
        frame_leg_dia.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=5)
        
        tk.Label(frame_leg_dia, text="Prioridades:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        tk.Label(frame_leg_dia, text=" Alta ", bg="#fca5a5", fg="black", font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        tk.Label(frame_leg_dia, text=" Média ", bg="#fde047", fg="black", font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        tk.Label(frame_leg_dia, text=" Baixa ", bg="#86efac", fg="black", font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        tk.Label(frame_leg_dia, text=" Nenhuma ", bg="#dcfce7", fg="#14532d", font=("Arial", 9)).pack(side=tk.LEFT, padx=5)
        
        notebook = ttk.Notebook(janela)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))
        
        aba_hoje = tk.Frame(notebook)
        aba_nao_concluidas = tk.Frame(notebook)
        
        notebook.add(aba_hoje, text="Para hoje")
        notebook.add(aba_nao_concluidas, text="Atividades não concluídas (Antigas)")
        
        # --- COLUNAS DA TABELA (Voltamos ao padrão, sem a coluna P) ---
        colunas = ("id", "Atividade", "Deadline", "Comentários")
        
        tb_hoje = ttk.Treeview(aba_hoje, columns=colunas, show="headings")
        tb_hoje.heading("Atividade", text="Atividade")
        tb_hoje.heading("Deadline", text="Deadline")
        tb_hoje.heading("Comentários", text="Comentários")
        tb_hoje.column("id", width=0, stretch=tk.NO)
        tb_hoje.column("Atividade", width=250)
        tb_hoje.column("Deadline", width=100, anchor=tk.CENTER)
        tb_hoje.column("Comentários", width=250)
        tb_hoje.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        frame_btn_hoje = tk.Frame(aba_hoje)
        frame_btn_hoje.pack(pady=5)
        tk.Button(frame_btn_hoje, text="✓ Concluir selecionada(s)", command=lambda: self.concluir_atividade(tb_hoje)).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_btn_hoje, text="❌ Remover do dia", command=lambda: self.remover_do_dia(tb_hoje)).pack(side=tk.LEFT, padx=5)

        tb_antigas = ttk.Treeview(aba_nao_concluidas, columns=colunas, show="headings")
        tb_antigas.heading("Atividade", text="Atividade")
        tb_antigas.heading("Deadline", text="Deadline")
        tb_antigas.heading("Comentários", text="Comentários")
        tb_antigas.column("id", width=0, stretch=tk.NO)
        tb_antigas.column("Atividade", width=250)
        tb_antigas.column("Deadline", width=100, anchor=tk.CENTER)
        tb_antigas.column("Comentários", width=250)
        tb_antigas.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        frame_btn_antigas = tk.Frame(aba_nao_concluidas)
        frame_btn_antigas.pack(pady=5)
        tk.Button(frame_btn_antigas, text="✓ Concluir selecionada(s)", command=lambda: self.concluir_atividade(tb_antigas)).pack(side=tk.LEFT, padx=5)
        tk.Button(frame_btn_antigas, text="❌ Remover do dia", command=lambda: self.remover_do_dia(tb_antigas)).pack(side=tk.LEFT, padx=5)
        
        # --- CONFIGURANDO AS CORES DAS LINHAS ---
        for tb in (tb_hoje, tb_antigas):
            tb.tag_configure('alta', background='#fca5a5', foreground='black')      # Vermelho claro
            tb.tag_configure('media', background='#fde047', foreground='black')     # Amarelo claro
            tb.tag_configure('baixa', background='#86efac', foreground='black')     # Verde claro (diferente)
            tb.tag_configure('normal', background='#dcfce7', foreground='#14532d')  # O padrão que você já usava
            tb.bind("<Button-1>", self.desmarcar_clique_vazio)
        
        def carregar_listas():
            for item in tb_hoje.get_children(): tb_hoje.delete(item)
            for item in tb_antigas.get_children(): tb_antigas.delete(item)
            
            hoje_str = datetime.today().strftime("%d/%m/%Y")
            for ativ in self.pendentes:
                if ativ.get('data_dia'):
                    # Define a tag correta baseada na prioridade salva
                    pri = ativ.get('prioridade', '')
                    tag_linha = 'alta' if pri == "Alta" else 'media' if pri == "Média" else 'baixa' if pri == "Baixa" else 'normal'
                    
                    valores = (ativ['id'], ativ['atividade'], ativ['deadline'], ativ.get('comentarios', ''))
                    
                    if ativ['data_dia'] == hoje_str:
                        tb_hoje.insert("", tk.END, values=valores, tags=(tag_linha,))
                    else:
                        tb_antigas.insert("", tk.END, values=valores, tags=(tag_linha,))
                        
        carregar_listas()
        
        menu_ctx = tk.Menu(janela, tearoff=0)
        tabela_alvo = [None]
        
        def abrir_popup_prioridade():
            if not tabela_alvo[0]: return
            selecao = tabela_alvo[0].selection()
            if not selecao: return
            
            pop = tk.Toplevel(janela)
            pop.title("Prioridade")
            pop.geometry("260x140")
            pop.transient(janela)
            pop.grab_set()
            pop.bind('<Escape>', lambda event: pop.destroy())
            pop.focus_set()
            
            tk.Label(pop, text="Defina a prioridade:", font=("Arial", 10, "bold")).pack(pady=10)
            
            def salvar_pri(nivel):
                for sel in selecao:
                    id_ativ = tabela_alvo[0].item(sel)['values'][0]
                    for ativ in self.pendentes:
                        if ativ['id'] == id_ativ:
                            ativ['prioridade'] = nivel
                            break
                salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
                carregar_listas() 
                pop.destroy()
                
            frame_b = tk.Frame(pop)
            frame_b.pack()
            
            # Botões já com as cores de fundo correspondentes
            tk.Button(frame_b, text="Alta", bg="#fca5a5", fg="black", command=lambda: salvar_pri("Alta"), width=8).grid(row=0, column=0, padx=2)
            tk.Button(frame_b, text="Média", bg="#fde047", fg="black", command=lambda: salvar_pri("Média"), width=8).grid(row=0, column=1, padx=2)
            tk.Button(frame_b, text="Baixa", bg="#86efac", fg="black", command=lambda: salvar_pri("Baixa"), width=8).grid(row=0, column=2, padx=2)
            tk.Button(frame_b, text="Nenhuma", bg="#dcfce7", fg="#14532d", command=lambda: salvar_pri("")).grid(row=1, column=0, columnspan=3, pady=10, sticky="ew")

        menu_ctx.add_command(label="🎯 Adicionar/Editar Prioridade", command=abrir_popup_prioridade)
        
        def capturar_clique_direito(event):
            tabela = event.widget
            item_sob_mouse = tabela.identify_row(event.y)
            if item_sob_mouse:
                if item_sob_mouse not in tabela.selection():
                    tabela.selection_set(item_sob_mouse)
                tabela_alvo[0] = tabela
                menu_ctx.post(event.x_root, event.y_root)
                
        tb_hoje.bind("<Button-3>", capturar_clique_direito)
        tb_antigas.bind("<Button-3>", capturar_clique_direito)

    def abrir_calendario_popup(self, event=None):
        self.win_cal = tk.Toplevel(self.root)
        self.win_cal.title("Calendário")
        self.win_cal.geometry("500x680")
        self.win_cal.transient(self.root)

        self.win_cal.bind('<Escape>', lambda event: self.win_cal.destroy())
        self.win_cal.focus_set()
        
        self.frame_ctrl_cal = tk.Frame(self.win_cal)
        self.frame_ctrl_cal.pack(fill=tk.X, pady=10)
        tk.Button(self.frame_ctrl_cal, text="◀", command=self.mes_anterior).pack(side=tk.LEFT, padx=20)
        self.lbl_mes_ano = tk.Label(self.frame_ctrl_cal, text="", font=("Arial", 12, "bold"))
        self.lbl_mes_ano.pack(side=tk.LEFT, expand=True)
        tk.Button(self.frame_ctrl_cal, text="▶", command=self.mes_proximo).pack(side=tk.RIGHT, padx=20)
        
        self.frame_dias_cal = tk.Frame(self.win_cal)
        self.frame_dias_cal.pack(pady=5)
        
        frame_resultados = tk.Frame(self.win_cal)
        frame_resultados.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.lbl_info_data = tk.Label(frame_resultados, text="Clique em um dia para ver as entregas", font=("Arial", 10, "italic"))
        self.lbl_info_data.pack(anchor=tk.W, pady=2)
        
        self.list_cal_tarefas = tk.Listbox(frame_resultados, height=4, font=("Arial", 10))
        self.list_cal_tarefas.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(frame_resultados, text="Diário de bordo:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(5, 2))
        
        self.text_diario = tk.Text(frame_resultados, height=10, font=("Arial", 10), wrap=tk.WORD, bg="#f8fafc")
        self.text_diario.pack(fill=tk.BOTH, expand=True)
        self.text_diario.bind("<KeyRelease>", self.salvar_diario_auto)
        
        self.text_diario.config(state=tk.DISABLED)
        
        self.desenhar_calendario()

    def desenhar_calendario(self):
        for widget in self.frame_dias_cal.winfo_children():
            widget.destroy()
            
        meses_nomes = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        self.lbl_mes_ano.config(text=f"{meses_nomes[self.mes_cal - 1]} / {self.ano_cal}")
        
        dias_semana = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
        for col, dia in enumerate(dias_semana):
            tk.Label(self.frame_dias_cal, text=dia, font=("Arial", 9, "bold"), width=6).grid(row=0, column=col, pady=2)
            
        cal = calendar.Calendar(firstweekday=6)
        cal_matriz = cal.monthdayscalendar(self.ano_cal, self.mes_cal)
        
        for r_idx, semana in enumerate(cal_matriz):
            for c_idx, dia in enumerate(semana):
                if dia == 0:
                    tk.Label(self.frame_dias_cal, text="", width=6).grid(row=r_idx+1, column=c_idx)
                else:
                    data_str = f"{dia:02d}/{self.mes_cal:02d}/{self.ano_cal}"
                    tem_tarefa = any(x['deadline'] == data_str for x in self.pendentes)
                    tem_diario = data_str in self.diario and self.diario[data_str].strip() != ""
                    
                    cor_bg = "#bbf7d0" if tem_tarefa else "#f1f5f9"
                    txt_botao = f"{dia}*" if tem_diario else str(dia)
                    font_estilo = ("Arial", 9, "bold") if tem_tarefa or tem_diario else ("Arial", 9)
                    
                    btn_dia = tk.Button(self.frame_dias_cal, text=txt_botao, width=5, bg=cor_bg, font=font_estilo,
                                        command=lambda d=data_str: self.mostrar_tarefas_do_dia(d))
                    btn_dia.grid(row=r_idx+1, column=c_idx, padx=2, pady=2)

    def mes_anterior(self):
        self.mes_cal -= 1
        if self.mes_cal < 1:
            self.mes_cal = 12
            self.ano_cal -= 1
        self.desenhar_calendario()

    def mes_proximo(self):
        self.mes_cal += 1
        if self.mes_cal > 12:
            self.mes_cal = 1
            self.ano_cal += 1
        self.desenhar_calendario()

    def mostrar_tarefas_do_dia(self, data_str):
        self.data_calendario_selecionada = data_str
        
        self.list_cal_tarefas.delete(0, tk.END)
        self.lbl_info_data.config(text=f"Atividades para o dia: {data_str}", font=("Arial", 10, "bold"))
        
        tarefas = [x for x in self.pendentes if x['deadline'] == data_str]
        if not tarefas:
            self.list_cal_tarefas.insert(tk.END, " Nenhuma atividade pendente para este dia.")
        else:
            for t in tarefas:
                coment = f" ({t['comentarios']})" if t['comentarios'] else ""
                self.list_cal_tarefas.insert(tk.END, f" 📌 {t['atividade']}{coment}")

        self.text_diario.config(state=tk.NORMAL)
        self.text_diario.delete("1.0", tk.END)
        if data_str in self.diario:
            self.text_diario.insert(tk.END, self.diario[data_str])

    def salvar_diario_auto(self, event):
        if not self.data_calendario_selecionada:
            return
            
        if self.timer_salvamento is not None:
            self.root.after_cancel(self.timer_salvamento)
            
        self.timer_salvamento = self.root.after(1000, self._executar_salvamento_diario)

    def _executar_salvamento_diario(self):
        if not self.data_calendario_selecionada:
            return
            
        texto_atual = self.text_diario.get("1.0", tk.END).strip()
        
        if texto_atual:
            self.diario[self.data_calendario_selecionada] = texto_atual
        else:
            if self.data_calendario_selecionada in self.diario:
                del self.diario[self.data_calendario_selecionada]
                
        salvar_dados_seguros(ARQUIVO_DIARIO, self.diario)
        self.desenhar_calendario()

    def desconcluir_atividade(self):
        selecao = self.tabela_conc.selection()
        if not selecao:
            messagebox.showinfo("Info", "Selecione pelo menos uma atividade para desconcluir.", parent=self.win_conc)
            return
            
        for sel_item in selecao:
            item = self.tabela_conc.item(sel_item)
            id_ativ = item['values'][0] # Pega o ID invisível da atividade
            
            # Procura a atividade na lista de concluídas
            ativ_encontrada = next((x for x in self.concluidas if x.get('id') == id_ativ), None)
            
            if ativ_encontrada:
                # Remove o carimbo de conclusão
                ativ_encontrada.pop('data_conclusao', None)
                
                # Move da lista de concluídas de volta para as pendentes
                self.concluidas.remove(ativ_encontrada)
                self.pendentes.append(ativ_encontrada)
                
        # Reordena a lista principal (To-do) pela data de entrega
        self.pendentes.sort(key=lambda x: converter_data(x.get('deadline', '')))
                
        # Salva as duas listas nos seus respectivos arquivos .json
        salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
        salvar_dados_seguros(ARQUIVO_CONCLUIDAS, self.concluidas)
        
        # Atualiza as duas tabelas visualmente
        self.atualizar_tabela_concluidas()
        self.atualizar_tabela_principal()
        
        messagebox.showinfo("Sucesso", f"{len(selecao)} atividade(s) retornada(s) para o To-do!", parent=self.win_conc)

    def abrir_estatisticas(self):
        win_est = tk.Toplevel(self.root)
        win_est.title("Dashboard de produtividade")
        win_est.geometry("900x550")
        win_est.transient(self.root)

        win_est.bind('<Escape>', lambda event: win_est.destroy())
        win_est.focus_set()
        
        frame_filtros = tk.Frame(win_est, bg="#f8fafc", pady=10)
        frame_filtros.pack(fill=tk.X)
        
        tk.Label(frame_filtros, text="Período de Análise:", bg="#f8fafc", font=("Arial", 9, "bold")).pack(side=tk.LEFT, padx=(15, 5))
        combo_periodo = ttk.Combobox(frame_filtros, values=["7 dias", "1 mês", "3 meses", "6 meses", "1 ano", "Personalizado"], state="readonly", width=15)
        combo_periodo.current(0)
        combo_periodo.pack(side=tk.LEFT, padx=5)
        
        tk.Label(frame_filtros, text="De:", bg="#f8fafc").pack(side=tk.LEFT, padx=(15,2))
        var_data_ini = tk.StringVar()
        ent_data_ini = tk.Entry(frame_filtros, textvariable=var_data_ini, width=12)
        ent_data_ini.pack(side=tk.LEFT, padx=5)
        self.setup_mascara_data(ent_data_ini, var_data_ini)
        
        tk.Label(frame_filtros, text="Até:", bg="#f8fafc").pack(side=tk.LEFT, padx=(10,2))
        var_data_fim = tk.StringVar()
        ent_data_fim = tk.Entry(frame_filtros, textvariable=var_data_fim, width=12)
        ent_data_fim.pack(side=tk.LEFT, padx=5)
        self.setup_mascara_data(ent_data_fim, var_data_fim)
        
        def alternar_campos_data(event=None):
            if combo_periodo.get() == "Personalizado":
                ent_data_ini.config(state=tk.NORMAL)
                ent_data_fim.config(state=tk.NORMAL)
            else:
                ent_data_ini.config(state=tk.DISABLED)
                ent_data_fim.config(state=tk.DISABLED)
                
        combo_periodo.bind("<<ComboboxSelected>>", alternar_campos_data)
        alternar_campos_data()
        
        frame_graficos = tk.Frame(win_est, bg="#f1f5f9")
        frame_graficos.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.canvas_pizza = tk.Canvas(frame_graficos, bg="#ffffff", bd=1, relief="ridge")
        self.canvas_pizza.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas_barras = tk.Canvas(frame_graficos, bg="#ffffff", bd=1, relief="ridge")
        self.canvas_barras.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        def desenhar_grafico_pizza(no_prazo, atrasadas):
            self.canvas_pizza.delete("all")
            w = self.canvas_pizza.winfo_width()
            h = self.canvas_pizza.winfo_height()
            
            if w <= 1 or h <= 1: 
                w, h = 400, 400
                
            self.canvas_pizza.create_text(w/2, 30, text="Qualidade de entrega", font=("Arial", 12, "bold"))
            
            total = no_prazo + atrasadas
            if total == 0:
                self.canvas_pizza.create_text(w/2, h/2, text="Nenhum dado encontrado no período", fill="#64748b")
                return
                
            cx, cy, r = w/2, h/2 + 20, min(w, h)/3
            x0, y0, x1, y1 = cx - r, cy - r, cx + r, cy + r
            
            ang_prazo = (no_prazo / total) * 360
            ang_atraso = (atrasadas / total) * 360
            
# Se 100% for no prazo, desenha um círculo verde completo
            if no_prazo == total:
                self.canvas_pizza.create_oval(x0, y0, x1, y1, fill="#10b981", outline="white", width=2)
                
            # Se 100% for atrasado, desenha um círculo vermelho completo
            elif atrasadas == total:
                self.canvas_pizza.create_oval(x0, y0, x1, y1, fill="#ef4444", outline="white", width=2)
                
            # Se for misto, desenha as fatias da pizza normalmente
            else:
                self.canvas_pizza.create_arc(x0, y0, x1, y1, start=90, extent=-ang_prazo, fill="#10b981", outline="white", width=2)
                self.canvas_pizza.create_arc(x0, y0, x1, y1, start=90-ang_prazo, extent=-ang_atraso, fill="#ef4444", outline="white", width=2)
            
            pct_prazo = (no_prazo/total)*100
            pct_atraso = (atrasadas/total)*100
            
            self.canvas_pizza.create_rectangle(w/2 - 100, h - 30, w/2 - 85, h - 15, fill="#10b981", outline="")
            self.canvas_pizza.create_text(w/2 - 80, h - 22, text=f"No Prazo ({pct_prazo:.1f}%)", anchor="w")
            
            self.canvas_pizza.create_rectangle(w/2 + 20, h - 30, w/2 + 35, h - 15, fill="#ef4444", outline="")
            self.canvas_pizza.create_text(w/2 + 40, h - 22, text=f"Atrasadas ({pct_atraso:.1f}%)", anchor="w")

        def desenhar_grafico_barras(freq_conclusao):
            self.canvas_barras.delete("all")
            w = self.canvas_barras.winfo_width()
            h = self.canvas_barras.winfo_height()
            
            if w <= 1 or h <= 1: 
                w, h = 400, 400
                
            self.canvas_barras.create_text(w/2, 30, text="Tarefas concluídas por dia", font=("Arial", 12, "bold"))
            
            if not freq_conclusao:
                self.canvas_barras.create_text(w/2, h/2, text="Nenhum dado encontrado no período", fill="#64748b")
                return

            chaves_ordenadas = sorted(freq_conclusao.keys(), key=lambda d: datetime.strptime(d, "%d/%m/%Y"))
            valores = [freq_conclusao[k] for k in chaves_ordenadas]
            labels = [k[:5] for k in chaves_ordenadas] 
            
            max_val = max(valores)
            if max_val == 0: max_val = 1
            
            margem_esq, margem_dir, margem_top, margem_bot = 40, 20, 60, 60
            largura_util = w - margem_esq - margem_dir
            altura_util = h - margem_top - margem_bot
            
            self.canvas_barras.create_line(margem_esq, h - margem_bot, w - margem_dir, h - margem_bot, fill="#94a3b8")
            self.canvas_barras.create_line(margem_esq, margem_top, margem_esq, h - margem_bot, fill="#94a3b8")
            
            qtd_barras = len(valores)
            largura_barra_max = min(largura_util / qtd_barras, 50) 
            espacamento = (largura_util - (largura_barra_max * qtd_barras)) / (qtd_barras + 1)
            
            for i in range(qtd_barras):
                val = valores[i]
                altura_barra = (val / max_val) * altura_util
                
                x0 = margem_esq + espacamento + i * (largura_barra_max + espacamento)
                y0 = h - margem_bot - altura_barra
                x1 = x0 + largura_barra_max
                y1 = h - margem_bot
                
                self.canvas_barras.create_rectangle(x0, y0, x1, y1, fill="#22c55e", outline="#14532d")
                self.canvas_barras.create_text((x0+x1)/2, y0 - 10, text=str(val), font=("Arial", 9))
                self.canvas_barras.create_text((x0+x1)/2, y1 + 15, text=labels[i], font=("Arial", 8), angle=45 if qtd_barras > 5 else 0)

        def atualizar_graficos(event=None):
            self.canvas_pizza.update_idletasks()
            self.canvas_barras.update_idletasks()
            
            hoje = datetime.today()
            periodo = combo_periodo.get()
            data_fim_calc = hoje
            
            if periodo == "7 dias": data_ini_calc = hoje - timedelta(days=7)
            elif periodo == "1 mês": data_ini_calc = hoje - timedelta(days=30)
            elif periodo == "3 meses": data_ini_calc = hoje - timedelta(days=90)
            elif periodo == "6 meses": data_ini_calc = hoje - timedelta(days=180)
            elif periodo == "1 ano": data_ini_calc = hoje - timedelta(days=365)
            else: 
                try:
                    data_ini_calc = datetime.strptime(var_data_ini.get(), "%d/%m/%Y")
                    data_fim_calc = datetime.strptime(var_data_fim.get(), "%d/%m/%Y")
                except ValueError:
                    messagebox.showwarning("Erro", "Formato de data inválido. Use DD/MM/AAAA.", parent=win_est)
                    return
            
            data_ini_calc = data_ini_calc.replace(hour=0, minute=0, second=0)
            data_fim_calc = data_fim_calc.replace(hour=23, minute=59, second=59)
            
            no_prazo, atrasadas = 0, 0
            freq_conclusao = {}
            
            for ativ in self.concluidas:
                str_conc = ativ.get('data_conclusao', ativ.get('deadline', ''))
                dt_conc = converter_data(str_conc)
                
                if dt_conc == datetime.max: continue
                    
                if data_ini_calc <= dt_conc <= data_fim_calc:
                    dt_prazo = converter_data(ativ.get('deadline', ''))
                    
                    if dt_prazo == datetime.max or dt_conc.date() <= dt_prazo.date():
                        no_prazo += 1
                    else:
                        atrasadas += 1
                        
                    str_data_formatada = dt_conc.strftime("%d/%m/%Y")
                    freq_conclusao[str_data_formatada] = freq_conclusao.get(str_data_formatada, 0) + 1

            desenhar_grafico_pizza(no_prazo, atrasadas)
            desenhar_grafico_barras(freq_conclusao)
            
        btn_atualizar = tk.Button(frame_filtros, text="↻ Atualizar Gráficos", command=atualizar_graficos, bg="#10b981", fg="white", font=("Arial", 9, "bold"))
        btn_atualizar.pack(side=tk.LEFT, padx=20)
        
        # Otimização: Implementação do Debounce no resize para evitar travamento da CPU
        def agendar_atualizacao(e=None):
            if e and e.widget != win_est: return
            if self.timer_graficos:
                win_est.after_cancel(self.timer_graficos)
            self.timer_graficos = win_est.after(200, atualizar_graficos)

        win_est.bind("<Configure>", agendar_atualizacao)
        agendar_atualizacao()

# =================================================================
    # SISTEMA DE RECORRÊNCIAS
    # =================================================================
    def calcular_proximo_ciclo(self, data_base, frequencia):
        if frequencia == "Diário":
            return data_base + timedelta(days=1)
        elif frequencia == "Semanal":
            return data_base + timedelta(days=7)
        elif frequencia == "Mensal":
            mes = data_base.month + 1
            ano = data_base.year
            if mes > 12:
                mes = 1
                ano += 1
            _, max_dias = calendar.monthrange(ano, mes)
            dia = min(data_base.day, max_dias) # Mantém o dia (ex: 31) ou desce pro máx do mês (ex: 28 fev)
            return datetime(ano, mes, dia)
        elif frequencia == "Anual":
            ano = data_base.year + 1
            mes = data_base.month
            _, max_dias = calendar.monthrange(ano, mes)
            dia = min(data_base.day, max_dias)
            return datetime(ano, mes, dia)
        return data_base

    def processar_recorrencias(self):
        hoje = datetime.today()
        limite_geracao = hoje + timedelta(days=15) # Gera com 15 dias de antecedência pra não poluir
        mudou_dados = False

        for rec in self.recorrentes:
            prox_data = converter_data(rec['proxima_data'])
            if prox_data == datetime.max: continue
            
            # Enquanto a próxima data estiver na janela de tempo de 15 dias
            while prox_data <= limite_geracao:
                # Cria uma "impressão digital" para garantir que a tarefa deste ciclo exato não seja duplicada
                id_instancia = f"{rec['id']}_{prox_data.strftime('%Y%m%d')}"
                
                existe_pendente = any(x.get('id_instancia') == id_instancia for x in self.pendentes)
                existe_concluida = any(x.get('id_instancia') == id_instancia for x in self.concluidas)
                
                if not existe_pendente and not existe_concluida:
                    self.pendentes.append({
                        "id": str(uuid.uuid4()),
                        "id_instancia": id_instancia,
                        "id_recorrente": rec['id'],
                        "atividade": f"🔄 {rec['atividade']}", # Põe um emoji pra identificar
                        "deadline": prox_data.strftime("%d/%m/%Y"),
                        "comentarios": rec['comentarios'],
                        "data_dia": None
                    })
                    mudou_dados = True
                
                # Avança a matemática pro próximo ciclo
                prox_data = self.calcular_proximo_ciclo(prox_data, rec['frequencia'])
                rec['proxima_data'] = prox_data.strftime("%d/%m/%Y")
                mudou_dados = True

        if mudou_dados:
            self.pendentes.sort(key=lambda x: converter_data(x.get('deadline', '')))
            salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
            salvar_dados_seguros(ARQUIVO_RECORRENTES, self.recorrentes)

    def nova_atividade_popup(self, event=None):
        popup = tk.Toplevel(self.root)
        popup.title("Criar Nova Atividade")
        popup.geometry("380x360")
        popup.transient(self.root)
        popup.grab_set()
        popup.bind('<Escape>', lambda event: popup.destroy())

        tk.Label(popup, text="Atividade:").pack(pady=(10, 0))
        entry_atividade = tk.Entry(popup, width=40)
        entry_atividade.pack(pady=5)
        entry_atividade.focus_set()

        tk.Label(popup, text="Deadline (Inicial se recorrente):").pack()
        var_deadline = tk.StringVar()
        entry_deadline = tk.Entry(popup, width=40, textvariable=var_deadline)
        entry_deadline.pack(pady=5)
        self.setup_mascara_data(entry_deadline, var_deadline)

        tk.Label(popup, text="Comentários:").pack()
        entry_comentarios = tk.Entry(popup, width=40)
        entry_comentarios.pack(pady=5)

        # --- MENU DE RECORRÊNCIA ---
        frame_rec = tk.Frame(popup)
        frame_rec.pack(pady=10, fill=tk.X, padx=30)
        
        var_recorrente = tk.BooleanVar(value=False)
        chk_rec = tk.Checkbutton(frame_rec, text="Essa atividade é recorrente?", variable=var_recorrente)
        chk_rec.pack(anchor=tk.W)
        
        frame_freq = tk.Frame(frame_rec)
        tk.Label(frame_freq, text="Frequência:").pack(side=tk.LEFT)
        combo_freq = ttk.Combobox(frame_freq, values=["Diário", "Semanal", "Mensal", "Anual"], state="readonly", width=15)
        combo_freq.current(2)
        combo_freq.pack(side=tk.LEFT, padx=5)

        def toggle_freq():
            if var_recorrente.get():
                frame_freq.pack(anchor=tk.W, pady=5)
            else:
                frame_freq.pack_forget()
                
        chk_rec.config(command=toggle_freq)

        def salvar(event=None):
            atividade = entry_atividade.get().strip()
            deadline = var_deadline.get().strip()
            comentarios = entry_comentarios.get().strip()
            
            if not atividade or not deadline:
                messagebox.showwarning("Aviso", "Nome e Deadline são obrigatórios!", parent=popup)
                return
                
            if var_recorrente.get():
                # Salva a matriz no arquivo de recorrentes
                novo_template = {
                    "id": str(uuid.uuid4()),
                    "atividade": atividade,
                    "frequencia": combo_freq.get(),
                    "proxima_data": deadline,
                    "comentarios": comentarios
                }
                self.recorrentes.append(novo_template)
                salvar_dados_seguros(ARQUIVO_RECORRENTES, self.recorrentes)
                self.processar_recorrencias() # Chama o motor para gerar a tarefa na tabela
            else:
                self.pendentes.append({
                    "id": str(uuid.uuid4()),
                    "atividade": atividade,
                    "deadline": deadline,
                    "comentarios": comentarios,
                    "data_dia": None
                })
                self.pendentes.sort(key=lambda x: converter_data(x.get('deadline', '')))
                salvar_dados_seguros(ARQUIVO_PENDENTES, self.pendentes)
            
            self.atualizar_tabela_principal()
            popup.destroy()

        tk.Button(popup, text="Salvar", command=salvar, bg="#16a34a", fg="white").pack(pady=10)
        popup.bind('<Return>', salvar)

    def abrir_recorrentes(self, event=None):
        win_rec = tk.Toplevel(self.root)
        win_rec.title("Gerenciar Atividades Recorrentes")
        win_rec.geometry("650x400")
        win_rec.bind('<Escape>', lambda event: win_rec.destroy())
        win_rec.focus_set()

        frame_top = tk.Frame(win_rec)
        frame_top.pack(fill=tk.X, padx=10, pady=10)

        def excluir_template():
            selecao = tabela_rec.selection()
            if not selecao: return
            if messagebox.askyesno("Confirmar", "Deseja parar esta recorrência?\n\nAs atividades já geradas na tabela continuarão lá, mas o programa vai parar de criar novas automaticamente.", parent=win_rec):
                for sel in selecao:
                    item = tabela_rec.item(sel)
                    id_rec = item['values'][0]
                    rec_encontrada = next((x for x in self.recorrentes if x['id'] == id_rec), None)
                    if rec_encontrada: self.recorrentes.remove(rec_encontrada)
                salvar_dados_seguros(ARQUIVO_RECORRENTES, self.recorrentes)
                atualizar_lista()

        tk.Button(frame_top, text="❌ Parar Recorrência Selecionada", command=excluir_template, bg="#ef4444", fg="white").pack(side=tk.LEFT)

        colunas = ("id", "Atividade", "Frequência", "Próximo Gatilho")
        tabela_rec = ttk.Treeview(win_rec, columns=colunas, show="headings")
        tabela_rec.heading("Atividade", text="Atividade")
        tabela_rec.heading("Frequência", text="Frequência")
        tabela_rec.heading("Próximo Gatilho", text="Próximo gatilho")
        
        tabela_rec.column("id", width=0, stretch=tk.NO)
        tabela_rec.column("Atividade", width=300)
        tabela_rec.column("Frequência", width=120)
        tabela_rec.column("Próximo Gatilho", width=150)
        tabela_rec.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        def atualizar_lista():
            for item in tabela_rec.get_children(): tabela_rec.delete(item)
            for rec in self.recorrentes:
                tabela_rec.insert("", tk.END, values=(rec['id'], rec['atividade'], rec['frequencia'], rec.get('proxima_data', '')))

        atualizar_lista()
    # =================================================================

if __name__ == "__main__":
    root = tk.Tk()
    
    # 1. Oculta a janela principal imediatamente
    root.withdraw()

    # 2. Cria a janela do Splash Screen
    splash = tk.Toplevel(root)
    splash.overrideredirect(True) # Remove a barra superior e os botões do Windows

    # 3. Carrega e redimensiona a imagem dividindo cada lado por 2
    try:
        # Carrega a imagem original usando a função de caminho seguro
        img_original = tk.PhotoImage(file=caminho_recurso("splash.png"))
        
        # O método subsample(2, 2) divide a largura por 2 e a altura por 2 nativamente
        img_splash = img_original.subsample(2, 2)
        
        # Pega nas dimensões da nova imagem já reduzida
        largura = img_splash.width()
        altura = img_splash.height()
        
        # Pega nas dimensões do ecrã do utilizador para centralizar a imagem
        tela_w = root.winfo_screenwidth()
        tela_h = root.winfo_screenheight()
        
        x = (tela_w // 2) - (largura // 2)
        y = (tela_h // 2) - (altura // 2)
        
        splash.geometry(f"{largura}x{altura}+{x}+{y}")
        
        # Coloca a imagem reduzida no ecrã
        lbl_splash = tk.Label(splash, image=img_splash, bg="white")
        lbl_splash.image = img_splash # Mantém a referência na memória
        lbl_splash.pack()
        
    except tk.TclError:
        # Caso a imagem não seja encontrada, o app avisa e abre direto
        print("Aviso: Imagem splash.png não encontrada. Abrindo app direto...")

    # 4. Inicializa o seu aplicativo Leaf por trás dos panos
    app = AppOrganizacao(root)

    # 5. Cria a função que destrói o splash e revela a janela principal do Leaf
    def iniciar_app():
        splash.destroy()
        root.deiconify() # Revela a janela principal

    # 6. Conta 3 segundos (3000 milissegundos) antes de alternar os ecrãs
    root.after(3000, iniciar_app)

    root.mainloop()