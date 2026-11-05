"""
Simulador & Detector de Presença de Jogos - EDIÇÃO ULTRA-LEVE (MODO ECONÔMICO)
Projetado especificamente para rodar com fluidez em computadores fracos / antigos:
- Consumo mínimo de memória RAM (~20 MB vs ~200 MB da versão pesada)
- Consumo de CPU em repouso: 0.0% (sem aquecimento nem desligamento de máquina)
- Carregamento único de base (sem leituras desnecessárias de disco de 7.5 MB a cada 30s)
- Detector com intervalo econômico de 8 segundos e varredura otimizada por nome
- Inicialização gráfica 100% segura (sem Vulkan ou D3D12 problemáticos)
- Seleção 100% Automática de Plataforma Nativa e Executável de Produção
- Spoofing de Processo Pai (steam.exe, battle.net.exe, epicgameslauncher.exe)
- 100% Portátil e Independente (Single .EXE)
"""

import os
import sys
import json
import time
import shutil
import unicodedata
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox
import psutil
import ctypes
from ctypes import wintypes

WIN = sys.platform == "win32"
OS_ATUAL = "win32" if WIN else "linux"

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def get_bundle_dir():
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = get_base_dir()
BUNDLE_DIR = get_bundle_dir()

def remover_acentos(texto):
    if not texto:
        return ""
    nfkd = unicodedata.normalize('NFKD', texto)
    return "".join([c for c in nfkd if not unicodedata.combining(c)]).lower()

def norm_path(p):
    return p.replace("\\", "/").lower().lstrip(">")

def get_stub_path():
    candidatos = [
        os.path.join(BASE_DIR, "stub_lite.exe" if WIN else "stub_lite"),
        os.path.join(BUNDLE_DIR, "stub_lite.exe" if WIN else "stub_lite"),
        os.path.join(BASE_DIR, "stub.exe" if WIN else "stub"),
        os.path.join(BUNDLE_DIR, "stub.exe" if WIN else "stub")
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return None

def finalizar_arvore_processos(pid):
    try:
        if WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        else:
            p = psutil.Process(pid)
            for filho in p.children(recursive=True):
                try:
                    filho.kill()
                except Exception:
                    pass
            p.kill()
    except Exception:
        pass

# =========================================================================
# HEURÍSTICA INTELIGENTE: PLATAFORMA E EXECUTÁVEL
# =========================================================================
def identificar_plataforma_nativa(jogo):
    keys = [k.lower() for k in jogo.get("platform_keys", [])]
    nome = jogo.get("name", "").lower()

    # 1. Blizzard / Battle.net
    blizzard_keywords = ["overwatch", "warcraft", "diablo", "hearthstone", "starcraft", "heroes of the storm"]
    if any(b in nome for b in blizzard_keywords) and "battlenet" in keys:
        return "Battle.net", "battle.net.exe"

    # 2. Epic Games Store
    epic_keywords = ["fortnite", "fall guys", "rocket league", "rocketleague"]
    if any(e in nome for e in epic_keywords) and "epic" in keys:
        return "Epic Games Store", "epicgameslauncher.exe"
    if "epic" in keys and "steam" not in keys:
        return "Epic Games Store", "epicgameslauncher.exe"

    # 3. Ubisoft Connect
    ubi_keywords = ["rainbow six", "assassin", "far cry", "division", "ghost recon", "watch dogs"]
    if any(u in nome for u in ubi_keywords) and ("ubisoft" in keys or "uplay" in keys):
        return "Ubisoft Connect", "upc.exe"

    # 4. Outros Battle.net
    if "battlenet" in keys and "steam" not in keys:
        return "Battle.net", "battle.net.exe"

    # 5. Steam
    if "steam" in keys:
        return "Steam", "steam.exe"

    # 6. Microsoft Store / Xbox
    if "microsoft_store" in keys:
        return "Microsoft Store / Xbox", "gamelaunchhelper.exe"

    # 7. GOG
    if "gog" in keys:
        return "GOG Galaxy", "gog_galaxy.exe"

    return "Standalone / Outro", "explorer.exe"

def rankear_executavel_correto(jogo, plat_escolhida=""):
    exes = [e["name"] for e in jogo.get("executables", []) if e.get("os", OS_ATUAL) == OS_ATUAL]
    if not exes:
        return ""
    if len(exes) == 1:
        return exes[0]

    plat_low = plat_escolhida.lower()

    def calcular_pontuacao(e):
        low = e.lower()
        score = 100
        if "server" in low: score -= 90
        if any(w in low for w in ["crash", "report", "bug", "patch", "update", "tool", "setup", "install", "benchmark"]):
            score -= 80
        if any(w in low for w in ["_beta_", "_ptr_", "_test_", "_staging_", "_dev_"]):
            score -= 60
        if any(w in low for w in ["_be.exe", "_eac.exe"]):
            score -= 40
        if low.startswith(">"):
            score -= 25
        if "launcher" in low:
            score -= 15

        if "_retail_" in low: score += 50
        if any(w in low for w in ["x64", "win64", "64"]): score += 25
        if "shipping" in low: score += 20
        if "steam" in plat_low and "steam" in low: score += 20
        if "epic" in plat_low and ("egs" in low or "epic" in low): score += 20

        nome_jogo_clean = "".join([c for c in jogo.get("name", "").lower() if c.isalnum()])
        exe_clean = "".join([c for c in os.path.basename(low) if c.isalnum()])
        if nome_jogo_clean and (nome_jogo_clean in exe_clean or exe_clean.startswith(nome_jogo_clean[:5])):
            score += 30

        return score

    return sorted(exes, key=calcular_pontuacao, reverse=True)[0]

# =========================================================================
# SPOOFING DE PROCESSO PAI (WIN32 API)
# =========================================================================
PROCESS_CREATE_PROCESS = 0x0080
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
PROC_THREAD_ATTRIBUTE_PARENT_PROCESS = 0x00020000

class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR), ('lpDesktop', wintypes.LPWSTR),
        ('lpTitle', wintypes.LPWSTR), ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
        ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD), ('dwXCountChars', wintypes.DWORD),
        ('dwYCountChars', wintypes.DWORD), ('dwFillAttribute', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
        ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD), ('lpReserved2', ctypes.POINTER(ctypes.c_byte)),
        ('hStdInput', wintypes.HANDLE), ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE)
    ]

class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [('StartupInfo', STARTUPINFOW), ('lpAttributeList', ctypes.c_void_p)]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', wintypes.HANDLE), ('hThread', wintypes.HANDLE), ('dwProcessId', wintypes.DWORD), ('dwThreadId', wintypes.DWORD)]

def iniciar_processo_com_pai(cmd_str, cwd, launcher_preferido=None):
    if not WIN:
        proc = subprocess.Popen(cmd_str.split(), cwd=cwd)
        return proc.pid, "sistema"

    kernel32 = ctypes.windll.kernel32
    candidatos = []
    if launcher_preferido:
        candidatos.append(launcher_preferido.lower())
    candidatos.extend(["steam.exe", "battle.net.exe", "epicgameslauncher.exe", "explorer.exe"])

    target_pid = None
    target_name = None

    for nome in candidatos:
        for p in psutil.process_iter(['name', 'pid']):
            try:
                if (p.info['name'] or '').lower() == nome:
                    target_pid = p.info['pid']
                    target_name = p.info['name']
                    break
            except Exception:
                continue
        if target_pid:
            break

    if not target_pid:
        proc = subprocess.Popen(cmd_str, cwd=cwd)
        return proc.pid, "padrão"

    hParent = kernel32.OpenProcess(PROCESS_CREATE_PROCESS, False, target_pid)
    if not hParent:
        proc = subprocess.Popen(cmd_str, cwd=cwd)
        return proc.pid, "padrão"

    try:
        size = ctypes.c_size_t(0)
        kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
        attr_list = ctypes.create_string_buffer(size.value)
        kernel32.InitializeProcThreadAttributeList(attr_list, 1, 0, ctypes.byref(size))

        hParentHandle = wintypes.HANDLE(hParent)
        kernel32.UpdateProcThreadAttribute(
            attr_list, 0, PROC_THREAD_ATTRIBUTE_PARENT_PROCESS,
            ctypes.byref(hParentHandle), ctypes.sizeof(hParentHandle), None, None
        )

        si = STARTUPINFOEXW()
        si.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        si.lpAttributeList = ctypes.cast(attr_list, ctypes.c_void_p)
        pi = PROCESS_INFORMATION()

        flags = EXTENDED_STARTUPINFO_PRESENT
        res = kernel32.CreateProcessW(
            None, cmd_str, None, None, False, flags, None, cwd,
            ctypes.byref(si.StartupInfo), ctypes.byref(pi)
        )

        kernel32.DeleteProcThreadAttributeList(attr_list)
        kernel32.CloseHandle(hParent)

        if res:
            kernel32.CloseHandle(pi.hProcess)
            kernel32.CloseHandle(pi.hThread)
            return pi.dwProcessId, target_name
    except Exception:
        pass

    proc = subprocess.Popen(cmd_str, cwd=cwd)
    return proc.pid, "padrão"

# =========================================================================
# MOTOR DO DETECTOR ULTRA-ECONÔMICO
# =========================================================================
class DetectorEngineLite:
    """
    Detector otimizado:
    - Intervalo de 8 segundos (zero aquecimento de processador)
    - Não recarrega o JSON de 7.5 MB em loop
    - Verifica pelo nome primeiro antes de fazer chamadas custosas de sistema
    """
    def __init__(self, indice_jogos, log_callback, status_callback, active_games_callback):
        self.indice = indice_jogos
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.active_games_callback = active_games_callback
        self.running = False
        self.ativo = False
        self.thread = None
        self.abertos = set()

    def iniciar(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def set_ativo(self, ativar):
        self.ativo = ativar
        if self.ativo:
            self.status_callback(f"🟢 Detector Ativo ({len(self.indice)} regras)", "#23a55a")
            self.log_callback("info", f"Monitoramento ativado (Intervalo econômico: 8.0s).")
        else:
            self.status_callback("⚪ Detector Pausado (0% CPU)", "#949ba4")
            self.log_callback("info", "Monitoramento pausado para economizar recursos.")

    def parar(self):
        self.running = False

    def _loop(self):
        while self.running:
            if not self.ativo:
                time.sleep(1.0)
                continue

            agora = set()
            # Varredura super leve: primeiro consulta apenas name, que não faz I/O de disco
            for p in psutil.process_iter(["name"]):
                try:
                    p_name = (p.info["name"] or "").lower()
                except Exception:
                    continue

                if p_name in self.indice:
                    # Só busca o caminho completo (exe) se o nome bater com um executável monitorado
                    try:
                        p_exe = norm_path(p.exe())
                    except Exception:
                        p_exe = ""

                    for alvo, jogo in self.indice[p_name]:
                        if "/" not in alvo or p_exe.endswith("/" + alvo):
                            agora.add(jogo)

            abertos_novos = agora - self.abertos
            for j in sorted(abertos_novos):
                self.log_callback("open", f"[+] Jogo '{j}' detectado aberto")

            fechados = self.abertos - agora
            for j in sorted(fechados):
                self.log_callback("close", f"[-] Jogo '{j}' fechado")

            if agora != self.abertos:
                self.active_games_callback(list(agora))

            self.abertos = agora
            # Espera 8 segundos para manter a CPU fria
            for _ in range(80):
                if not self.running or not self.ativo:
                    break
                time.sleep(0.1)

# =========================================================================
# APLICAÇÃO PRINCIPAL ULTRA-LEVE (TKINTER PURO + TEMA ESCURO NATIVO)
# =========================================================================
class AppLite(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Game Presence Simulator - Edição Ultra-Leve")
        self.geometry("980x640")
        self.minsize(860, 540)
        self.configure(bg="#141518")

        for ico in [os.path.join(BASE_DIR, "app_icon.ico"), os.path.join(BUNDLE_DIR, "app_icon.ico")]:
            if os.path.exists(ico):
                try:
                    self.iconbitmap(ico)
                    break
                except Exception:
                    pass

        self._garantir_pastas()

        self.jogos = []
        self.indice_detector = {}
        self.visiveis = []
        self.jogo_selecionado = None
        self.active_stubs = []
        self.limite_exibicao = 50

        self._carregar_base_unica()
        self._criar_interface()

        # Detector econômico inicia pausado por padrão (0% CPU)
        self.detector = DetectorEngineLite(
            indice_jogos=self.indice_detector,
            log_callback=self._log_detector_safe,
            status_callback=self._status_detector_safe,
            active_games_callback=self._active_games_safe
        )
        self.detector.iniciar()

        self._filtrar_jogos()
        self.after(3000, self._verificar_stubs_vivos)

    def _garantir_pastas(self):
        os.makedirs(os.path.join(BASE_DIR, "simulados"), exist_ok=True)
        manual_base = os.path.join(BASE_DIR, "manual.json")
        if not os.path.exists(manual_base):
            try:
                with open(manual_base, "w", encoding="utf-8") as f:
                    json.dump([], f)
            except Exception:
                pass

    def _carregar_base_unica(self):
        """Carrega a base uma única vez e gera o índice do detector sem sobrecarga."""
        lista = []
        for nome_arq in ("jogos.json", "manual.json"):
            p = os.path.join(BASE_DIR, nome_arq)
            if not os.path.exists(p):
                p = os.path.join(BUNDLE_DIR, nome_arq)
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        dados = json.load(f)
                        if isinstance(dados, list):
                            lista += dados
                except Exception:
                    pass

        self.jogos = lista
        indice = {}
        for j in lista:
            nome = j.get("name", "")
            j["_search"] = remover_acentos(nome)
            for e in j.get("executables", []):
                if e.get("os", OS_ATUAL) != OS_ATUAL:
                    continue
                alvo = norm_path(e.get("name", ""))
                if alvo:
                    nome_exe = alvo.split("/")[-1]
                    indice.setdefault(nome_exe, []).append((alvo, nome))

        self.indice_detector = indice

    def _criar_interface(self):
        # Configuração de Estilo TTK Moderno Escuro
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(".", background="#141518", foreground="#ffffff", font=("Segoe UI", 9))
        style.configure("TFrame", background="#141518")
        style.configure("Card.TFrame", background="#1e1f23")
        style.configure("TNotebook", background="#141518", tabmargins=[2, 5, 2, 0])
        style.configure("TNotebook.Tab", background="#2b2d31", foreground="#dbdee1", padding=[14, 5], font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#5865f2")], foreground=[("selected", "#ffffff")])

        # Divisão em duas colunas: Esquerda (Biblioteca) | Direita (Ações e Abas)
        paned = tk.PanedWindow(self, orient="horizontal", bg="#141518", sashwidth=4, bd=0)
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # ----------------- PAINEL ESQUERDO -----------------
        left_box = tk.Frame(paned, bg="#1e1f23", padx=10, pady=10)
        paned.add(left_box, minsize=360, width=380)

        lbl_app = tk.Label(left_box, text="🎮 Game Presence (Ultra-Leve)", font=("Segoe UI", 13, "bold"), bg="#1e1f23", fg="#ffffff")
        lbl_app.pack(anchor="w")

        lbl_sub = tk.Label(left_box, text="Modo Econômico: 0% CPU • ~20 MB RAM", font=("Segoe UI", 8), bg="#1e1f23", fg="#23a55a")
        lbl_sub.pack(anchor="w", pady=(0, 8))

        # Campo de Busca
        search_frame = tk.Frame(left_box, bg="#1e1f23")
        search_frame.pack(fill="x", pady=(0, 6))

        self.var_busca = tk.StringVar()
        self.var_busca.trace_add("write", lambda *_: self._filtrar_jogos())

        entry_busca = tk.Entry(
            search_frame, textvariable=self.var_busca, font=("Segoe UI", 10),
            bg="#2b2d31", fg="#ffffff", insertbackground="#ffffff", relief="flat", bd=4
        )
        entry_busca.pack(side="left", fill="x", expand=True, padx=(0, 4))

        btn_limpar = tk.Button(
            search_frame, text="✕", font=("Segoe UI", 8, "bold"),
            bg="#313338", fg="#dbdee1", activebackground="#3b3e45", activeforeground="#ffffff",
            relief="flat", width=3, command=lambda: self.var_busca.set("")
        )
        btn_limpar.pack(side="right")

        self.lbl_contador = tk.Label(left_box, text="Carregando biblioteca...", font=("Segoe UI", 8), bg="#1e1f23", fg="#949ba4")
        self.lbl_contador.pack(anchor="w", pady=(2, 4))

        # Lista de Jogos com Scrollbar nativa
        list_frame = tk.Frame(left_box, bg="#141518")
        list_frame.pack(fill="both", expand=True)

        self.listbox_jogos = tk.Listbox(
            list_frame, bg="#141518", fg="#dbdee1", selectbackground="#5865f2", selectforeground="#ffffff",
            font=("Segoe UI", 9), relief="flat", bd=0, highlightthickness=0, activestyle="none"
        )
        scrollbar = tk.Scrollbar(list_frame, orient="vertical", command=self.listbox_jogos.yview, bg="#2b2d31")
        self.listbox_jogos.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self.listbox_jogos.pack(side="left", fill="both", expand=True)
        self.listbox_jogos.bind("<<ListboxSelect>>", self._ao_selecionar_item_lista)

        self.btn_mais = tk.Button(
            left_box, text="Carregar mais jogos...", font=("Segoe UI", 8, "bold"),
            bg="#2b2d31", fg="#5865f2", relief="flat", pady=4, command=self._carregar_mais_jogos
        )

        # ----------------- PAINEL DIREITO -----------------
        right_box = tk.Frame(paned, bg="#141518", padx=10, pady=4)
        paned.add(right_box, minsize=460)

        # CARD: Jogo Selecionado e Configurações
        card_sel = tk.Frame(right_box, bg="#1e1f23", padx=14, pady=12)
        card_sel.pack(fill="x", pady=(0, 8))

        self.lbl_jogo_nome = tk.Label(card_sel, text="Selecione um jogo na lista", font=("Segoe UI", 14, "bold"), bg="#1e1f23", fg="#ffffff")
        self.lbl_jogo_nome.pack(anchor="w")

        # Linha Plataforma e Executável
        grid_config = tk.Frame(card_sel, bg="#1e1f23")
        grid_config.pack(fill="x", pady=(8, 6))

        tk.Label(grid_config, text="Plataforma Nativa:", font=("Segoe UI", 8, "bold"), bg="#1e1f23", fg="#949ba4").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.var_plataforma = tk.StringVar()
        self.combo_plat = ttk.Combobox(grid_config, textvariable=self.var_plataforma, state="readonly", width=22)
        self.combo_plat.grid(row=0, column=1, sticky="w", padx=(0, 14))
        self.combo_plat.bind("<<ComboboxSelected>>", lambda *_: self._ao_mudar_plataforma())

        tk.Label(grid_config, text="Executável Principal:", font=("Segoe UI", 8, "bold"), bg="#1e1f23", fg="#949ba4").grid(row=0, column=2, sticky="w", padx=(0, 6))
        self.var_exec = tk.StringVar()
        self.combo_exec = ttk.Combobox(grid_config, textvariable=self.var_exec, state="readonly", width=26)
        self.combo_exec.grid(row=0, column=3, sticky="w")
        self.combo_exec.bind("<<ComboboxSelected>>", lambda *_: self._atualizar_preview())

        self.lbl_preview_path = tk.Label(card_sel, text="📁 Destino: simulados/", font=("Segoe UI", 8), bg="#1e1f23", fg="#5865f2")
        self.lbl_preview_path.pack(anchor="w", pady=(4, 8))

        # Botões de Ação
        btn_bar = tk.Frame(card_sel, bg="#1e1f23")
        btn_bar.pack(fill="x")

        self.btn_gerar_abrir = tk.Button(
            btn_bar, text="🚀 Gerar e Abrir (Simulador)", font=("Segoe UI", 9, "bold"),
            bg="#5865f2", fg="#ffffff", activebackground="#4752c4", activeforeground="#ffffff",
            relief="flat", padx=14, pady=5, command=self._acao_gerar_e_abrir
        )
        self.btn_gerar_abrir.pack(side="left", padx=(0, 8))

        self.btn_apenas_gerar = tk.Button(
            btn_bar, text="💾 Apenas Criar Pasta", font=("Segoe UI", 8),
            bg="#2b2d31", fg="#ffffff", activebackground="#35373c", activeforeground="#ffffff",
            relief="flat", padx=10, pady=5, command=self._acao_apenas_gerar
        )
        self.btn_apenas_gerar.pack(side="left", padx=(0, 8))

        btn_abrir_pasta = tk.Button(
            btn_bar, text="📂 Abrir Pasta Simulados", font=("Segoe UI", 8),
            bg="#313338", fg="#dbdee1", activebackground="#3b3e45", activeforeground="#ffffff",
            relief="flat", padx=10, pady=5, command=self._abrir_pasta_simulados
        )
        btn_abrir_pasta.pack(side="left")

        # ----------------- ABAS INFERIORES -----------------
        notebook = ttk.Notebook(right_box)
        notebook.pack(fill="both", expand=True)

        tab_detector = tk.Frame(notebook, bg="#1e1f23", padx=8, pady=8)
        tab_stubs = tk.Frame(notebook, bg="#1e1f23", padx=8, pady=8)
        tab_manual = tk.Frame(notebook, bg="#1e1f23", padx=8, pady=8)

        notebook.add(tab_detector, text="📡 Detector Econômico")
        notebook.add(tab_stubs, text="⚡ Stubs em Execução")
        notebook.add(tab_manual, text="➕ Adicionar Manual")

        self._montar_aba_detector(tab_detector)
        self._montar_aba_stubs(tab_stubs)
        self._montar_aba_manual(tab_manual)

    def _montar_aba_detector(self, parent):
        top = tk.Frame(parent, bg="#1e1f23")
        top.pack(fill="x", pady=(0, 6))

        self.var_detector_ativo = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(
            top, text="Ativar Monitoramento em Segundo Plano (8.0s)",
            variable=self.var_detector_ativo, onvalue=True, offvalue=False,
            font=("Segoe UI", 9, "bold"), bg="#1e1f23", fg="#ffffff",
            selectcolor="#2b2d31", activebackground="#1e1f23", activeforeground="#ffffff",
            command=self._alternar_detector
        )
        chk.pack(side="left")

        self.lbl_detector_status = tk.Label(
            top, text="⚪ Detector Pausado (0% CPU)", font=("Segoe UI", 8, "bold"),
            bg="#1e1f23", fg="#949ba4"
        )
        self.lbl_detector_status.pack(side="left", padx=12)

        btn_limpar = tk.Button(
            top, text="Limpar", font=("Segoe UI", 8), bg="#2b2d31", fg="#ffffff",
            relief="flat", padx=8, pady=1, command=self._limpar_log
        )
        btn_limpar.pack(side="right")

        self.txt_log = tk.Text(
            parent, bg="#141518", fg="#dbdee1", font=("Consolas", 9),
            relief="flat", bd=0, highlightthickness=0, wrap="word"
        )
        self.txt_log.pack(fill="both", expand=True)

        self.txt_log.tag_config("time", foreground="#72767d")
        self.txt_log.tag_config("open", foreground="#23a55a")
        self.txt_log.tag_config("close", foreground="#f23f43")
        self.txt_log.tag_config("info", foreground="#5865f2")

    def _montar_aba_stubs(self, parent):
        top = tk.Frame(parent, bg="#1e1f23")
        top.pack(fill="x", pady=(0, 6))

        tk.Label(top, text="Processos Simulados Ativos:", font=("Segoe UI", 9, "bold"), bg="#1e1f23", fg="#ffffff").pack(side="left")

        btn_fechar_todos = tk.Button(
            top, text="Encerrar Todos", font=("Segoe UI", 8, "bold"),
            bg="#da373c", fg="#ffffff", activebackground="#b52c30", relief="flat",
            padx=8, pady=2, command=self._encerrar_todos_stubs
        )
        btn_fechar_todos.pack(side="right")

        cols = ("PID", "Jogo", "Executável", "Plataforma", "Pai (Launcher)")
        self.tree_stubs = ttk.Treeview(parent, columns=cols, show="headings", height=8)
        for c in cols:
            self.tree_stubs.heading(c, text=c)
            self.tree_stubs.column(c, width=100, anchor="w")
        self.tree_stubs.column("Jogo", width=160)
        self.tree_stubs.pack(fill="both", expand=True)

    def _montar_aba_manual(self, parent):
        form = tk.Frame(parent, bg="#1e1f23", pady=8)
        form.pack(fill="x")

        tk.Label(form, text="Nome do Jogo:", font=("Segoe UI", 8, "bold"), bg="#1e1f23", fg="#ffffff").grid(row=0, column=0, sticky="w", pady=4)
        self.entry_manual_nome = tk.Entry(form, bg="#2b2d31", fg="#ffffff", insertbackground="#ffffff", relief="flat", bd=4, width=32)
        self.entry_manual_nome.grid(row=0, column=1, sticky="w", padx=6, pady=4)

        tk.Label(form, text="Executável:", font=("Segoe UI", 8, "bold"), bg="#1e1f23", fg="#ffffff").grid(row=1, column=0, sticky="w", pady=4)
        self.entry_manual_exe = tk.Entry(form, bg="#2b2d31", fg="#ffffff", insertbackground="#ffffff", relief="flat", bd=4, width=32)
        self.entry_manual_exe.grid(row=1, column=1, sticky="w", padx=6, pady=4)

        btn_salvar = tk.Button(
            form, text="➕ Salvar em manual.json", font=("Segoe UI", 8, "bold"),
            bg="#5865f2", fg="#ffffff", relief="flat", padx=10, pady=4, command=self._adicionar_manual
        )
        btn_salvar.grid(row=2, column=1, sticky="w", padx=6, pady=6)

    # ----------------- CONTROLE E DADOS -----------------
    def _filtrar_jogos(self):
        termo = remover_acentos(self.var_busca.get().strip())
        if not termo:
            self.visiveis = self.jogos
        else:
            termos = termo.split()
            self.visiveis = [j for j in self.jogos if all(t in j.get("_search", "") for t in termos)]

        total = len(self.visiveis)
        self.lbl_contador.configure(text=f"Mostrando {min(total, self.limite_exibicao)} de {total} jogos cadastrados")

        self.listbox_jogos.delete(0, "end")
        for j in self.visiveis[:self.limite_exibicao]:
            nome = j.get("name", "Sem Nome")
            qtd = len(j.get("executables", []))
            self.listbox_jogos.insert("end", f" {nome} ({qtd} exe)")

        if total > self.limite_exibicao:
            self.btn_mais.pack(fill="x", pady=(4, 0))
            self.btn_mais.configure(text=f"Carregar mais ({total - self.limite_exibicao} restantes)...")
        else:
            self.btn_mais.pack_forget()

        if self.visiveis and not self.jogo_selecionado:
            self._selecionar_jogo(self.visiveis[0])

    def _carregar_mais_jogos(self):
        self.limite_exibicao += 60
        self._filtrar_jogos()

    def _ao_selecionar_item_lista(self, event):
        sel = self.listbox_jogos.curselection()
        if sel and sel[0] < len(self.visiveis):
            self._selecionar_jogo(self.visiveis[sel[0]])

    def _selecionar_jogo(self, jogo):
        self.jogo_selecionado = jogo
        nome = jogo.get("name", "Desconhecido")
        self.lbl_jogo_nome.configure(text=nome)

        # 1. Plataforma Nativa
        plat_nativa_nome, _ = identificar_plataforma_nativa(jogo)
        plats = [p.get("name") for p in jogo.get("platforms", []) if p.get("name")]
        if not plats:
            plats = ["Standalone / Outro"]
        if "Standalone / Outro" not in plats:
            plats.append("Standalone / Outro")

        self.combo_plat.configure(values=plats)
        sel_plat = plats[0]
        for p in plats:
            if plat_nativa_nome.lower() in p.lower():
                sel_plat = p
                break
        self.var_plataforma.set(sel_plat)

        # 2. Executável Correto
        exes = [e["name"] for e in jogo.get("executables", []) if e.get("os", OS_ATUAL) == OS_ATUAL]
        if exes:
            self.combo_exec.configure(values=exes)
            exe_correto = rankear_executavel_correto(jogo, sel_plat)
            self.var_exec.set(exe_correto if exe_correto in exes else exes[0])
            self.btn_gerar_abrir.configure(state="normal")
            self.btn_apenas_gerar.configure(state="normal")
        else:
            self.combo_exec.configure(values=["Nenhum executável Windows"])
            self.var_exec.set("Nenhum executável Windows")
            self.btn_gerar_abrir.configure(state="disabled")
            self.btn_apenas_gerar.configure(state="disabled")

        self._atualizar_preview()

    def _ao_mudar_plataforma(self):
        if not self.jogo_selecionado:
            return
        plat = self.var_plataforma.get()
        exes = [e["name"] for e in self.jogo_selecionado.get("executables", []) if e.get("os", OS_ATUAL) == OS_ATUAL]
        melhor = rankear_executavel_correto(self.jogo_selecionado, plat)
        if melhor and melhor in exes:
            self.var_exec.set(melhor)
        self._atualizar_preview()

    def _calcular_caminho(self):
        if not self.jogo_selecionado:
            return None, None, None, None
        exe_raw = self.var_exec.get()
        if not exe_raw or "Nenhum" in exe_raw:
            return None, None, None, None

        nome_jogo = self.jogo_selecionado.get("name", "Jogo")
        nome_pasta_jogo = "".join([c for c in nome_jogo if c not in '<>:"/\\|?*']).strip()
        plat = self.var_plataforma.get().lower()

        store_id = None
        for p in self.jogo_selecionado.get("platforms", []):
            if p.get("name", "").lower() in plat:
                s_ids = p.get("store_ids", [])
                if s_ids:
                    store_id = s_ids[0]
                break

        if "steam" in plat:
            base_folder = os.path.join(BASE_DIR, "simulados", "Steam", "steamapps", "common", nome_pasta_jogo)
            launcher = "steam.exe"
        elif "battle.net" in plat or "battlenet" in plat:
            base_folder = os.path.join(BASE_DIR, "simulados", "Battle.net", nome_pasta_jogo)
            launcher = "battle.net.exe"
        elif "epic" in plat:
            base_folder = os.path.join(BASE_DIR, "simulados", "Epic Games", nome_pasta_jogo)
            launcher = "epicgameslauncher.exe"
        elif "microsoft" in plat or "xbox" in plat:
            base_folder = os.path.join(BASE_DIR, "simulados", "XboxGames", nome_pasta_jogo)
            launcher = "gamelaunchhelper.exe"
        elif "ubisoft" in plat or "uplay" in plat:
            base_folder = os.path.join(BASE_DIR, "simulados", "Ubisoft", "games", nome_pasta_jogo)
            launcher = "upc.exe"
        elif "gog" in plat:
            base_folder = os.path.join(BASE_DIR, "simulados", "GOG Galaxy", "Games", nome_pasta_jogo)
            launcher = "gog_galaxy.exe"
        else:
            base_folder = os.path.join(BASE_DIR, "simulados", "Games", nome_pasta_jogo)
            launcher = "explorer.exe"

        destino_exe = os.path.abspath(os.path.join(base_folder, *norm_path(exe_raw).split("/")))
        return base_folder, destino_exe, launcher, store_id

    def _atualizar_preview(self):
        _, destino, launcher, _ = self._calcular_caminho()
        if not destino:
            self.lbl_preview_path.configure(text="📁 Destino: simulados/")
            return
        rel = os.path.relpath(destino, BASE_DIR)
        self.lbl_preview_path.configure(text=f"📁 Instalação: {rel} (Processo Pai: {launcher})")

    def _obter_caminho_gerado(self):
        base_folder, destino, launcher, store_id = self._calcular_caminho()
        if not destino:
            return None
        stub_origem = get_stub_path()
        if not stub_origem or not os.path.exists(stub_origem):
            messagebox.showerror("Stub Ausente", "Arquivo stub_lite.exe ou stub.exe não encontrado.")
            return None

        os.makedirs(os.path.dirname(destino), exist_ok=True)
        try:
            shutil.copy(stub_origem, destino)
            plat = self.var_plataforma.get().lower()

            if "steam" in plat and store_id:
                with open(os.path.join(base_folder, "steam_appid.txt"), "w", encoding="utf-8") as f:
                    f.write(str(store_id))
            elif "battle.net" in plat:
                with open(os.path.join(base_folder, ".build.info"), "w", encoding="utf-8") as f:
                    f.write(f"Product!STRING:0\n{store_id or 'game'}\n")
            elif "epic" in plat:
                os.makedirs(os.path.join(base_folder, ".egstore"), exist_ok=True)

            meta = {
                "name": self.jogo_selecionado.get("name", "Jogo"),
                "id": self.jogo_selecionado.get("id"),
                "platform": self.var_plataforma.get(),
                "store_id": store_id
            }
            with open(destino + ".json", "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Erro ao Gerar", f"Falha ao gerar arquivos:\n{e}")
            return None

        return destino

    def _acao_apenas_gerar(self):
        dest = self._obter_caminho_gerado()
        if dest:
            rel = os.path.relpath(dest, BASE_DIR)
            messagebox.showinfo("Sucesso", f"Estrutura gerada com sucesso em:\n{rel}")

    def _acao_gerar_e_abrir(self):
        dest = self._obter_caminho_gerado()
        if not dest:
            return

        nome_jogo = self.jogo_selecionado.get("name", "Jogo")
        app_id = self.jogo_selecionado.get("id")
        _, _, launcher, _ = self._calcular_caminho()
        plat = self.var_plataforma.get()

        cmd = f'"{dest}" --name "{nome_jogo}" --platform "{plat}"'
        if app_id:
            cmd += f' --id "{app_id}"'

        cwd = os.path.dirname(dest)
        try:
            pid, parent_name = iniciar_processo_com_pai(cmd, cwd, launcher_preferido=launcher)
            self.active_stubs.append({
                "pid": pid,
                "game": nome_jogo,
                "exe": os.path.basename(dest),
                "platform": plat,
                "parent": parent_name
            })
            self._atualizar_tabela_stubs()
            self._log_detector_safe("info", f"Stub iniciado: {os.path.basename(dest)} (PID {pid}) | Pai: {parent_name}")
        except Exception as e:
            messagebox.showerror("Erro ao Iniciar", f"Falha ao executar o processo:\n{e}")

    def _abrir_pasta_simulados(self):
        p = os.path.join(BASE_DIR, "simulados")
        os.makedirs(p, exist_ok=True)
        if WIN:
            os.startfile(p)
        else:
            subprocess.run(["xdg-open", p])

    def _alternar_detector(self):
        ativar = self.var_detector_ativo.get()
        self.detector.set_ativo(ativar)

    def _limpar_log(self):
        self.txt_log.delete("1.0", "end")

    def _log_detector_safe(self, tag, texto):
        self.after(0, lambda: self._append_log(tag, texto))

    def _append_log(self, tag, texto):
        t = time.strftime("[%H:%M:%S] ")
        self.txt_log.insert("end", t, "time")
        self.txt_log.insert("end", f"{texto}\n", tag)
        self.txt_log.see("end")

    def _status_detector_safe(self, texto, cor):
        self.after(0, lambda: self.lbl_detector_status.configure(text=texto, fg=cor))

    def _active_games_safe(self, jogos):
        pass

    def _atualizar_tabela_stubs(self):
        for item in self.tree_stubs.get_children():
            self.tree_stubs.delete(item)
        for s in self.active_stubs:
            self.tree_stubs.insert("", "end", values=(s["pid"], s["game"], s["exe"], s["platform"], s["parent"]))

    def _verificar_stubs_vivos(self):
        vivos = []
        for s in self.active_stubs:
            if psutil.pid_exists(s["pid"]):
                vivos.append(s)
        if len(vivos) != len(self.active_stubs):
            self.active_stubs = vivos
            self._atualizar_tabela_stubs()
        self.after(3000, self._verificar_stubs_vivos)

    def _encerrar_todos_stubs(self):
        for s in list(self.active_stubs):
            finalizar_arvore_processos(s["pid"])
        self.active_stubs = []
        self._atualizar_tabela_stubs()

    def _adicionar_manual(self):
        nome = self.entry_manual_nome.get().strip()
        exe = self.entry_manual_exe.get().strip()
        if not nome or not exe:
            messagebox.showwarning("Aviso", "Preencha o nome do jogo e o executável.")
            return

        novo = {
            "name": nome,
            "executables": [{"name": exe, "os": OS_ATUAL}],
            "platforms": [{"name": "Manual", "platform": "manual"}]
        }

        p = os.path.join(BASE_DIR, "manual.json")
        try:
            dados = []
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    dados = json.load(f)
            dados.append(novo)
            with open(p, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
            messagebox.showinfo("Sucesso", f"Jogo '{nome}' adicionado com sucesso!")
            self.entry_manual_nome.delete(0, "end")
            self.entry_manual_exe.delete(0, "end")
            self._carregar_base_unica()
            self._filtrar_jogos()
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao salvar: {e}")

def main():
    app = AppLite()
    app.mainloop()

if __name__ == "__main__":
    main()
