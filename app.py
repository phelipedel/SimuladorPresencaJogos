"""
Simulador & Detector de Presença de Jogos - Versão Inteligente Multiplataforma
- Seleção 100% Automática do Executável Correto e do Processo/Launcher Nativo
- Reconhecimento de versões retail, x64, shipping, descartando servers, crash-reporters e betas
- Simulação de Estrutura de Instalação Real por Plataforma (Steam, Battle.net, Epic Games, Xbox, etc.)
- Spoofing de Processo Pai (steam.exe, battle.net.exe, epicgameslauncher.exe, explorer.exe)
- Módulos Gráficos e Direct3D 11 via stub compilado
- Executável 100% Autônomo e Portátil com Ícone Embutido
"""

import os
import sys
import json
import time
import shutil
import unicodedata
import threading
import subprocess
import urllib.request
import tkinter as tk
from tkinter import messagebox
import psutil
import customtkinter as ctk
import ctypes
from ctypes import wintypes

# Configurações do tema CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

WIN = sys.platform == "win32"
OS_ATUAL = "win32" if WIN else "linux"

def get_base_dir():
    """Retorna o diretório onde o executável (.exe) ou script está localizado."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def get_bundle_dir():
    """Retorna o diretório temporário interno do PyInstaller (_MEIPASS)."""
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
        os.path.join(BASE_DIR, "stub.exe" if WIN else "stub"),
        os.path.join(BASE_DIR, "dist", "stub.exe" if WIN else "stub"),
        os.path.join(BUNDLE_DIR, "stub.exe" if WIN else "stub"),
        os.path.join(BUNDLE_DIR, "dist", "stub.exe" if WIN else "stub")
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
# HEURÍSTICA INTELIGENTE: PLATAFORMA E EXECUTÁVEL CORRETOS
# =========================================================================
def identificar_plataforma_nativa(jogo):
    """
    Identifica automaticamente a plataforma nativa correta e seu executável launcher.
    """
    keys = [k.lower() for k in jogo.get("platform_keys", [])]
    nome = jogo.get("name", "").lower()

    # 1. Jogos Blizzard / Battle.net
    blizzard_keywords = ["overwatch", "warcraft", "diablo", "hearthstone", "starcraft", "heroes of the storm", "starcraft ii"]
    if any(b in nome for b in blizzard_keywords) and "battlenet" in keys:
        return "Battle.net", "battle.net.exe"

    # 2. Jogos Epic Games Primários / Exclusivos
    epic_keywords = ["fortnite", "fall guys", "unreal tournament", "rocket league", "rocketleague"]
    if any(e in nome for e in epic_keywords) and "epic" in keys:
        return "Epic Games Store", "epicgameslauncher.exe"
    if "epic" in keys and "steam" not in keys:
        return "Epic Games Store", "epicgameslauncher.exe"

    # 3. Jogos Ubisoft Primários
    ubi_keywords = ["rainbow six", "assassin", "far cry", "division", "ghost recon", "watch dogs", "crew"]
    if any(u in nome for u in ubi_keywords) and ("ubisoft" in keys or "uplay" in keys):
        return "Ubisoft Connect", "upc.exe"

    # 4. Outros Battle.net
    if "battlenet" in keys and "steam" not in keys:
        return "Battle.net", "battle.net.exe"

    # 5. Jogos Steam (padrão para maioria dos jogos de PC)
    if "steam" in keys:
        return "Steam", "steam.exe"

    # 6. Microsoft Store / Xbox
    if "microsoft_store" in keys:
        return "Microsoft Store / Xbox", "gamelaunchhelper.exe"

    # 7. GOG Galaxy
    if "gog" in keys:
        return "GOG Galaxy", "gog_galaxy.exe"

    return "Standalone / Outro", "explorer.exe"

def rankear_executavel_correto(jogo, plat_escolhida=""):
    """
    Analisa todos os executáveis do jogo e seleciona automaticamente o executável principal,
    descartando servidores dedicados, crash-reporters, updaters, betas e ferramentas.
    """
    exes = [e["name"] for e in jogo.get("executables", []) if e.get("os", OS_ATUAL) == OS_ATUAL]
    if not exes:
        return ""
    if len(exes) == 1:
        return exes[0]

    plat_low = plat_escolhida.lower()

    def calcular_pontuacao(e):
        low = e.lower()
        score = 100

        # Penalidades graves (não são o jogo jogável)
        if "server" in low: score -= 90
        if any(w in low for w in ["crash", "report", "bug", "patch", "update", "tool", "gmad", "setup", "install", "benchmark", "editor"]):
            score -= 80
        if any(w in low for w in ["_beta_", "_ptr_", "_test_", "_staging_", "_dev_", "_alpha_"]):
            score -= 60
        if any(w in low for w in ["_be.exe", "_eac.exe"]):
            score -= 40
        if low.startswith(">"):
            score -= 25
        if "launcher" in low:
            score -= 15

        # Bônus fortes para versões principais
        if "_retail_" in low: score += 50
        if any(w in low for w in ["x64", "win64", "64"]): score += 25
        if "shipping" in low: score += 20

        # Compatibilidade com a plataforma selecionada
        if "steam" in plat_low and "steam" in low: score += 20
        if "epic" in plat_low and ("egs" in low or "epic" in low): score += 20

        # Bônus se o nome do executável coincidir com o nome do jogo
        nome_jogo_clean = "".join([c for c in jogo.get("name", "").lower() if c.isalnum()])
        exe_clean = "".join([c for c in os.path.basename(low) if c.isalnum()])
        if nome_jogo_clean and (nome_jogo_clean in exe_clean or exe_clean.startswith(nome_jogo_clean[:5])):
            score += 30

        return score

    exes_ordenados = sorted(exes, key=calcular_pontuacao, reverse=True)
    return exes_ordenados[0]

# =========================================================================
# SPOOFING DE PROCESSO PAI (Win32 API)
# =========================================================================
PROC_THREAD_ATTRIBUTE_PARENT_PROCESS = 0x00020000
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
PROCESS_CREATE_PROCESS = 0x0080

class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD), ('lpReserved', wintypes.LPWSTR), ('lpDesktop', wintypes.LPWSTR),
        ('lpTitle', wintypes.LPWSTR), ('dwX', wintypes.DWORD), ('dwY', wintypes.DWORD),
        ('dwXSize', wintypes.DWORD), ('dwYSize', wintypes.DWORD), ('dwXCountChars', wintypes.DWORD),
        ('dwYCountChars', wintypes.DWORD), ('dwFillAttribute', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
        ('wShowWindow', wintypes.WORD), ('cbReserved2', wintypes.WORD), ('lpReserved2', ctypes.c_char_p),
        ('hStdInput', wintypes.HANDLE), ('hStdOutput', wintypes.HANDLE), ('hStdError', wintypes.HANDLE),
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
# MOTOR DO DETECTOR
# =========================================================================
class DetectorEngine:
    def __init__(self, log_callback, status_callback, active_games_callback):
        self.log_callback = log_callback
        self.status_callback = status_callback
        self.active_games_callback = active_games_callback
        self.running = False
        self.paused = False
        self.thread = None
        self.indice = {}
        self.abertos = set()
        self.ultima_recarga = 0

    def carregar_indice(self):
        regras = []
        for nome_arq in ("jogos.json", "manual.json"):
            p_base = os.path.join(BASE_DIR, nome_arq)
            p_bundle = os.path.join(BUNDLE_DIR, nome_arq)
            caminho = p_base if os.path.exists(p_base) else (p_bundle if os.path.exists(p_bundle) else None)
            if caminho:
                try:
                    with open(caminho, "r", encoding="utf-8") as f:
                        dados = json.load(f)
                        if isinstance(dados, list):
                            regras += dados
                except Exception:
                    pass

        indice = {}
        total_regras = 0
        for j in regras:
            nome_jogo = j.get("name", "Desconhecido")
            for e in j.get("executables", []):
                if e.get("os", OS_ATUAL) != OS_ATUAL:
                    continue
                alvo = norm_path(e.get("name", ""))
                if not alvo:
                    continue
                nome_exe = alvo.split("/")[-1]
                indice.setdefault(nome_exe, []).append((alvo, nome_jogo))
                total_regras += 1

        self.indice = indice
        self.ultima_recarga = time.time()
        return len(indice), total_regras

    def iniciar(self):
        if self.running:
            return
        self.running = True
        self.paused = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def pausar(self, pausar=True):
        self.paused = pausar
        if self.paused:
            self.status_callback("⏸️ Detector Pausado", "#e5a50a")
        else:
            self.status_callback(f"🟢 Detector Ativo ({len(self.indice)} regras)", "#23a55a")

    def parar(self):
        self.running = False

    def _loop(self):
        qtd_chaves, total_regras = self.carregar_indice()
        self.log_callback("info", f"Detector iniciado. {qtd_chaves} executáveis monitorados ({total_regras} regras).")
        self.status_callback(f"🟢 Detector Ativo ({qtd_chaves} regras)", "#23a55a")

        while self.running:
            if self.paused:
                time.sleep(1)
                continue

            if time.time() - self.ultima_recarga > 30:
                qtd_chaves, total_regras = self.carregar_indice()
                if not self.paused:
                    self.status_callback(f"🟢 Detector Ativo ({qtd_chaves} regras)", "#23a55a")

            agora = set()
            for p in psutil.process_iter(["name", "exe"]):
                try:
                    p_name = (p.info["name"] or "").lower()
                    p_exe = norm_path(p.info["exe"] or "")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

                for alvo, jogo in self.indice.get(p_name, []):
                    if "/" not in alvo or p_exe.endswith("/" + alvo):
                        agora.add(jogo)

            abertos_novos = agora - self.abertos
            for j in sorted(abertos_novos):
                self.log_callback("open", f"[+] Jogo '{j}' aberto")

            fechados = self.abertos - agora
            for j in sorted(fechados):
                self.log_callback("close", f"[-] Jogo '{j}' fechado")

            if agora != self.abertos:
                self.active_games_callback(list(agora))

            self.abertos = agora
            time.sleep(2.5)

# =========================================================================
# APLICAÇÃO PRINCIPAL
# =========================================================================
class GamePresenceApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Game Presence Simulator & Detector")
        self.geometry("1140x750")
        self.minsize(990, 650)

        # Cores elegantes
        self.color_bg = "#18191c"
        self.color_card = "#232428"
        self.color_card_inner = "#1e1f22"
        self.color_accent = "#5865f2"
        self.color_accent_hover = "#4752c4"
        self.color_success = "#23a55a"
        self.color_danger = "#da373c"

        self.configure(fg_color=self.color_bg)

        # Define ícone da janela
        for ico in [os.path.join(BASE_DIR, "app_icon.ico"), os.path.join(BUNDLE_DIR, "app_icon.ico")]:
            if os.path.exists(ico):
                try:
                    self.iconbitmap(ico)
                    break
                except Exception:
                    pass

        self.jogos = []
        self.visiveis = []
        self.jogo_selecionado = None
        self.active_stubs = []
        self.limite_exibicao = 60

        self._garantir_arquivos_iniciais()
        self.jogos = self._carregar_jogos()

        self._criar_layout()

        self.detector = DetectorEngine(
            log_callback=self._log_detector_threadsafe,
            status_callback=self._status_detector_threadsafe,
            active_games_callback=self._active_games_threadsafe
        )
        self.detector.iniciar()

        self.after(2000, self._verificar_stubs_vivos)
        self._filtrar_jogos()

    def _garantir_arquivos_iniciais(self):
        os.makedirs(os.path.join(BASE_DIR, "simulados"), exist_ok=True)

        jogos_base = os.path.join(BASE_DIR, "jogos.json")
        jogos_bundle = os.path.join(BUNDLE_DIR, "jogos.json")
        if not os.path.exists(jogos_base) and os.path.exists(jogos_bundle):
            try:
                shutil.copy(jogos_bundle, jogos_base)
            except Exception:
                pass

        manual_base = os.path.join(BASE_DIR, "manual.json")
        if not os.path.exists(manual_base):
            try:
                with open(manual_base, "w", encoding="utf-8") as f:
                    json.dump([], f)
            except Exception:
                pass

    def _carregar_jogos(self):
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

        for j in lista:
            nome = j.get("name", "")
            j["_search"] = remover_acentos(nome)
        return lista

    def _salvar_manual(self, dados):
        p = os.path.join(BASE_DIR, "manual.json")
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showerror("Erro ao salvar", f"Falha ao salvar manual.json: {e}")

    def _criar_layout(self):
        self.grid_columnconfigure(0, weight=0, minsize=420)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # =========================================================================
        # PAINEL ESQUERDO: BIBLIOTECA DE JOGOS & BUSCA
        # =========================================================================
        left_frame = ctk.CTkFrame(self, fg_color=self.color_card, corner_radius=12)
        left_frame.grid(row=0, column=0, padx=(14, 7), pady=14, sticky="nsew")
        left_frame.grid_columnconfigure(0, weight=1)
        left_frame.grid_rowconfigure(3, weight=1)

        lbl_app = ctk.CTkLabel(
            left_frame,
            text="🎮 Game Presence",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff"
        )
        lbl_app.grid(row=0, column=0, padx=16, pady=(16, 2), sticky="w")

        lbl_sub = ctk.CTkLabel(
            left_frame,
            text="Simulador Multiplataforma Inteligente",
            font=ctk.CTkFont(size=12),
            text_color="#949ba4"
        )
        lbl_sub.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="w")

        # Busca
        search_box = ctk.CTkFrame(left_frame, fg_color="transparent")
        search_box.grid(row=2, column=0, padx=14, pady=(0, 4), sticky="ew")
        search_box.grid_columnconfigure(0, weight=1)

        self.var_busca = ctk.StringVar()
        self.var_busca.trace_add("write", lambda *_: self._filtrar_jogos())

        self.entry_busca = ctk.CTkEntry(
            search_box,
            textvariable=self.var_busca,
            placeholder_text="🔍 Buscar jogo (ex: GTA, CS, Overwatch, Valorant)...",
            fg_color="#2b2d31",
            border_color="#35373c",
            border_width=1,
            corner_radius=8,
            height=38,
            font=ctk.CTkFont(size=13)
        )
        self.entry_busca.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        btn_limpar = ctk.CTkButton(
            search_box,
            text="✕",
            width=36,
            height=38,
            fg_color="#313338",
            hover_color="#3b3e45",
            corner_radius=8,
            command=lambda: self.var_busca.set("")
        )
        btn_limpar.grid(row=0, column=1)

        self.lbl_contador = ctk.CTkLabel(
            left_frame,
            text="Carregando biblioteca...",
            font=ctk.CTkFont(size=11),
            text_color="#949ba4"
        )
        self.lbl_contador.grid(row=2, column=0, padx=16, pady=(46, 4), sticky="w")

        self.scroll_jogos = ctk.CTkScrollableFrame(
            left_frame,
            fg_color=self.color_card_inner,
            corner_radius=8
        )
        self.scroll_jogos.grid(row=3, column=0, padx=14, pady=(22, 10), sticky="nsew")
        self.scroll_jogos.grid_columnconfigure(0, weight=1)

        bottom_left = ctk.CTkFrame(left_frame, fg_color="transparent")
        bottom_left.grid(row=4, column=0, padx=14, pady=(4, 14), sticky="ew")
        bottom_left.grid_columnconfigure(0, weight=1)

        self.btn_atualizar = ctk.CTkButton(
            bottom_left,
            text="🔄 Atualizar Base (Discord API)",
            height=36,
            fg_color="#35373c",
            hover_color="#404249",
            corner_radius=8,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._baixar_base_discord
        )
        self.btn_atualizar.grid(row=0, column=0, sticky="ew")

        # =========================================================================
        # PAINEL DIREITO: DETALHES DO JOGO, CONTROLE & ABAS DE FERRAMENTAS
        # =========================================================================
        right_frame = ctk.CTkFrame(self, fg_color=self.color_card, corner_radius=12)
        right_frame.grid(row=0, column=1, padx=(7, 14), pady=14, sticky="nsew")
        right_frame.grid_columnconfigure(0, weight=1)
        right_frame.grid_rowconfigure(1, weight=1)

        action_card = ctk.CTkFrame(right_frame, fg_color=self.color_card_inner, corner_radius=10)
        action_card.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="ew")
        action_card.grid_columnconfigure(0, weight=1)

        top_info = ctk.CTkFrame(action_card, fg_color="transparent")
        top_info.grid(row=0, column=0, padx=16, pady=(14, 2), sticky="ew")
        top_info.grid_columnconfigure(0, weight=1)

        self.lbl_jogo_nome = ctk.CTkLabel(
            top_info,
            text="Selecione um jogo na lista à esquerda",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color="#ffffff",
            anchor="w"
        )
        self.lbl_jogo_nome.grid(row=0, column=0, sticky="w")

        self.lbl_auto_badge = ctk.CTkLabel(
            top_info,
            text="⚡ Configuração Automática",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#23a55a",
            fg_color="#18271e",
            corner_radius=6,
            padx=8,
            pady=3
        )
        self.lbl_auto_badge.grid(row=0, column=1, sticky="e")

        # Linha 1: Executável Automático (com seletor)
        exec_frame = ctk.CTkFrame(action_card, fg_color="transparent")
        exec_frame.grid(row=1, column=0, padx=16, pady=(6, 2), sticky="ew")
        exec_frame.grid_columnconfigure(1, weight=1)

        lbl_exec = ctk.CTkLabel(
            exec_frame,
            text="Processo / Exe:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#dbdee1",
            width=120,
            anchor="w"
        )
        lbl_exec.grid(row=0, column=0, sticky="w")

        self.var_exec_selecionado = ctk.StringVar(value="")
        self.var_exec_selecionado.trace_add("write", lambda *_: self._atualizar_caminho_preview())

        self.menu_executaveis = ctk.CTkOptionMenu(
            exec_frame,
            variable=self.var_exec_selecionado,
            values=["Nenhum jogo selecionado"],
            fg_color="#2b2d31",
            button_color="#35373c",
            button_hover_color="#404249",
            corner_radius=8,
            height=34,
            dynamic_resizing=True
        )
        self.menu_executaveis.grid(row=0, column=1, sticky="ew")

        # Linha 2: Plataforma Nativa / Launcher (com seletor)
        plat_frame = ctk.CTkFrame(action_card, fg_color="transparent")
        plat_frame.grid(row=2, column=0, padx=16, pady=(4, 6), sticky="ew")
        plat_frame.grid_columnconfigure(1, weight=1)

        lbl_plat = ctk.CTkLabel(
            plat_frame,
            text="Plataforma:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#dbdee1",
            width=120,
            anchor="w"
        )
        lbl_plat.grid(row=0, column=0, sticky="w")

        self.var_plataforma_selecionada = ctk.StringVar(value="Steam")
        self.var_plataforma_selecionada.trace_add("write", lambda *_: self._ao_mudar_plataforma())

        self.menu_plataformas = ctk.CTkOptionMenu(
            plat_frame,
            variable=self.var_plataforma_selecionada,
            values=["Steam", "Battle.net", "Epic Games Store", "Microsoft Store / Xbox", "Standalone / Outro"],
            fg_color="#2b2d31",
            button_color="#35373c",
            button_hover_color="#404249",
            corner_radius=8,
            height=34,
            dynamic_resizing=True
        )
        self.menu_plataformas.grid(row=0, column=1, sticky="ew")

        # Linha 3: Preview do caminho de instalação real
        self.lbl_destino_preview = ctk.CTkLabel(
            action_card,
            text="📁 Instalação Simula: simulados/",
            font=ctk.CTkFont(size=11, family="Consolas"),
            text_color="#949ba4",
            anchor="w"
        )
        self.lbl_destino_preview.grid(row=3, column=0, padx=16, pady=(2, 4), sticky="w")

        # Linha 4: Informações de simulação de processo pai e gráficos
        self.lbl_simulacao_info = ctk.CTkLabel(
            action_card,
            text="⚙️ Simulação: Direct3D 11 / Vulkan | Processo Pai: steam.exe / explorer.exe",
            font=ctk.CTkFont(size=11),
            text_color="#23a55a",
            anchor="w"
        )
        self.lbl_simulacao_info.grid(row=4, column=0, padx=16, pady=(0, 12), sticky="w")

        # Linha 5: Botões de Ação
        btn_bar = ctk.CTkFrame(action_card, fg_color="transparent")
        btn_bar.grid(row=5, column=0, padx=16, pady=(0, 14), sticky="ew")

        self.btn_gerar_abrir = ctk.CTkButton(
            btn_bar,
            text="🚀 Gerar e Iniciar",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.color_accent,
            hover_color=self.color_accent_hover,
            height=38,
            corner_radius=8,
            command=self._acao_gerar_e_abrir
        )
        self.btn_gerar_abrir.pack(side="left", padx=(0, 8))

        self.btn_gerar = ctk.CTkButton(
            btn_bar,
            text="📦 Apenas Gerar",
            font=ctk.CTkFont(size=13),
            fg_color="#313338",
            hover_color="#3b3e45",
            height=38,
            corner_radius=8,
            command=self._acao_apenas_gerar
        )
        self.btn_gerar.pack(side="left", padx=(0, 8))

        self.btn_abrir_pasta = ctk.CTkButton(
            btn_bar,
            text="📂 Abrir Pasta Simulados",
            font=ctk.CTkFont(size=13),
            fg_color="#313338",
            hover_color="#3b3e45",
            height=38,
            corner_radius=8,
            command=self._abrir_pasta_simulados
        )
        self.btn_abrir_pasta.pack(side="left")

        # =========================================================================
        # ABAS: DETECTOR EM TEMPO REAL | STUBS ATIVOS | ADICIONAR MANUAL
        # =========================================================================
        self.tabview = ctk.CTkTabview(
            right_frame,
            fg_color=self.color_card_inner,
            segmented_button_fg_color="#2b2d31",
            segmented_button_selected_color=self.color_accent,
            segmented_button_selected_hover_color=self.color_accent_hover,
            corner_radius=10
        )
        self.tabview.grid(row=1, column=0, padx=16, pady=(4, 16), sticky="nsew")

        tab_detector = self.tabview.add("📡 Detector em Tempo Real")
        tab_stubs = self.tabview.add("⚡ Processos Ativos (Stubs)")
        tab_manual = self.tabview.add("➕ Adicionar Manual")

        self._construir_aba_detector(tab_detector)
        self._construir_aba_stubs(tab_stubs)
        self._construir_aba_manual(tab_manual)

    def _construir_aba_detector(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        ctrl_bar = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl_bar.grid(row=0, column=0, padx=10, pady=(6, 6), sticky="ew")
        ctrl_bar.grid_columnconfigure(1, weight=1)

        self.switch_detector = ctk.CTkSwitch(
            ctrl_bar,
            text="Monitoramento Automático",
            font=ctk.CTkFont(size=13, weight="bold"),
            progress_color=self.color_success,
            command=self._alternar_detector
        )
        self.switch_detector.select()
        self.switch_detector.grid(row=0, column=0, sticky="w")

        self.lbl_detector_status = ctk.CTkLabel(
            ctrl_bar,
            text="🟢 Detector Ativo (carregando...)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.color_success
        )
        self.lbl_detector_status.grid(row=0, column=1, padx=12, sticky="w")

        btn_limpar_log = ctk.CTkButton(
            ctrl_bar,
            text="🧹 Limpar Log",
            width=90,
            height=28,
            fg_color="#313338",
            hover_color="#3b3e45",
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            command=self._limpar_log_detector
        )
        btn_limpar_log.grid(row=0, column=2, padx=4)

        btn_copiar_log = ctk.CTkButton(
            ctrl_bar,
            text="📋 Copiar",
            width=70,
            height=28,
            fg_color="#313338",
            hover_color="#3b3e45",
            corner_radius=6,
            font=ctk.CTkFont(size=11),
            command=self._copiar_log_detector
        )
        btn_copiar_log.grid(row=0, column=3)

        self.frame_jogos_ativos = ctk.CTkFrame(parent, fg_color="#18191c", corner_radius=6)
        self.frame_jogos_ativos.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="ew")

        self.lbl_jogos_ativos_info = ctk.CTkLabel(
            self.frame_jogos_ativos,
            text="🎯 Jogos detectados abertos agora: Nenhum",
            font=ctk.CTkFont(size=12),
            text_color="#949ba4",
            anchor="w"
        )
        self.lbl_jogos_ativos_info.pack(padx=10, pady=6, fill="x")

        self.txt_detector_log = ctk.CTkTextbox(
            parent,
            fg_color="#111214",
            text_color="#dbdee1",
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=8,
            border_width=1,
            border_color="#2b2d31",
            wrap="word"
        )
        self.txt_detector_log.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")

        tk_text = self.txt_detector_log._textbox
        tk_text.tag_config("time", foreground="#72767d")
        tk_text.tag_config("open", foreground="#23a55a", font=("Consolas", 10, "bold"))
        tk_text.tag_config("close", foreground="#f23f43", font=("Consolas", 10, "bold"))
        tk_text.tag_config("info", foreground="#5865f2")

    def _construir_aba_stubs(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        top_stubs = ctk.CTkFrame(parent, fg_color="transparent")
        top_stubs.grid(row=0, column=0, padx=10, pady=(6, 6), sticky="ew")
        top_stubs.grid_columnconfigure(0, weight=1)

        lbl_desc = ctk.CTkLabel(
            top_stubs,
            text="Processos simulados com Processo Pai (Launcher / Explorer):",
            font=ctk.CTkFont(size=13),
            text_color="#949ba4"
        )
        lbl_desc.grid(row=0, column=0, sticky="w")

        btn_kill_all = ctk.CTkButton(
            top_stubs,
            text="🛑 Encerrar Todos os Stubs",
            fg_color=self.color_danger,
            hover_color="#b52c30",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
            corner_radius=6,
            command=self._encerrar_todos_os_stubs
        )
        btn_kill_all.grid(row=0, column=1)

        self.scroll_stubs = ctk.CTkScrollableFrame(
            parent,
            fg_color="#18191c",
            corner_radius=8
        )
        self.scroll_stubs.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.scroll_stubs.grid_columnconfigure(0, weight=1)

        self._atualizar_lista_stubs_ui()

    def _construir_aba_manual(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(2, weight=1)

        card_form = ctk.CTkFrame(parent, fg_color="#18191c", corner_radius=8)
        card_form.grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")
        card_form.grid_columnconfigure(1, weight=1)

        lbl_title = ctk.CTkLabel(
            card_form,
            text="Adicionar Novo Jogo Manualmente",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#ffffff"
        )
        lbl_title.grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 8), sticky="w")

        lbl_n = ctk.CTkLabel(card_form, text="Nome do Jogo:", font=ctk.CTkFont(size=12))
        lbl_n.grid(row=1, column=0, padx=12, pady=4, sticky="w")
        self.entry_manual_nome = ctk.CTkEntry(
            card_form,
            placeholder_text="ex: Grand Theft Auto V",
            fg_color="#2b2d31",
            border_color="#35373c",
            height=34
        )
        self.entry_manual_nome.grid(row=1, column=1, padx=(0, 12), pady=4, sticky="ew")

        lbl_e = ctk.CTkLabel(card_form, text="Executável:", font=ctk.CTkFont(size=12))
        lbl_e.grid(row=2, column=0, padx=12, pady=4, sticky="w")
        self.entry_manual_exe = ctk.CTkEntry(
            card_form,
            placeholder_text="ex: gta5.exe ou bin/client.exe",
            fg_color="#2b2d31",
            border_color="#35373c",
            height=34
        )
        self.entry_manual_exe.grid(row=2, column=1, padx=(0, 12), pady=4, sticky="ew")

        btn_salvar_manual = ctk.CTkButton(
            card_form,
            text="➕ Salvar em manual.json",
            fg_color=self.color_accent,
            hover_color=self.color_accent_hover,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=34,
            corner_radius=6,
            command=self._adicionar_jogo_manual
        )
        btn_salvar_manual.grid(row=3, column=1, padx=(0, 12), pady=(8, 12), sticky="e")

        lbl_lista_manual = ctk.CTkLabel(
            parent,
            text="Jogos Manuais Cadastrados:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#ffffff"
        )
        lbl_lista_manual.grid(row=1, column=0, padx=12, pady=(4, 4), sticky="w")

        self.scroll_manuais = ctk.CTkScrollableFrame(
            parent,
            fg_color="#18191c",
            corner_radius=8
        )
        self.scroll_manuais.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.scroll_manuais.grid_columnconfigure(0, weight=1)

        self._atualizar_lista_manuais_ui()

    # =========================================================================
    # LÓGICA DE FILTRO E EXIBIÇÃO DE JOGOS
    # =========================================================================
    def _filtrar_jogos(self):
        termo = remover_acentos(self.var_busca.get().strip())
        if termo:
            self.visiveis = [j for j in self.jogos if termo in j.get("_search", "")]
        else:
            self.visiveis = self.jogos

        total = len(self.jogos)
        encontrados = len(self.visiveis)
        self.lbl_contador.configure(text=f"Exibindo {min(encontrados, self.limite_exibicao)} de {encontrados} jogos (Total na base: {total})")

        for widget in self.scroll_jogos.winfo_children():
            widget.destroy()

        if not self.visiveis:
            lbl_vazio = ctk.CTkLabel(
                self.scroll_jogos,
                text="Nenhum jogo encontrado com esse termo.",
                text_color="#949ba4"
            )
            lbl_vazio.pack(padx=10, pady=20)
            return

        for idx, jogo in enumerate(self.visiveis[:self.limite_exibicao]):
            nome = jogo.get("name", "Sem nome")
            exes = [e["name"] for e in jogo.get("executables", []) if e.get("os", OS_ATUAL) == OS_ATUAL]
            qtd_exes = len(exes)

            is_sel = (self.jogo_selecionado and self.jogo_selecionado.get("name") == nome)
            fg = "#383a40" if is_sel else "#2b2d31"
            txt_color = "#ffffff" if is_sel else "#dbdee1"

            # Identifica a plataforma nativa
            plat_nativa, _ = identificar_plataforma_nativa(jogo)
            plat_badge = f" • {plat_nativa}" if plat_nativa else ""

            btn_item = ctk.CTkButton(
                self.scroll_jogos,
                text=f"{nome}  ({qtd_exes} exe{'s' if qtd_exes != 1 else ''}{plat_badge})",
                anchor="w",
                fg_color=fg,
                hover_color="#3b3e45",
                text_color=txt_color,
                corner_radius=6,
                height=34,
                font=ctk.CTkFont(size=12, weight="bold" if is_sel else "normal"),
                command=lambda j=jogo: self._selecionar_jogo(j)
            )
            btn_item.pack(fill="x", padx=4, pady=2)

        if encontrados > self.limite_exibicao:
            btn_mais = ctk.CTkButton(
                self.scroll_jogos,
                text=f"Carregar mais ({encontrados - self.limite_exibicao} restantes)...",
                fg_color="#18191c",
                hover_color="#2b2d31",
                text_color="#5865f2",
                font=ctk.CTkFont(size=12, weight="bold"),
                height=32,
                command=self._carregar_mais_jogos
            )
            btn_mais.pack(fill="x", padx=4, pady=6)

        if not self.jogo_selecionado and self.visiveis:
            self._selecionar_jogo(self.visiveis[0])

    def _carregar_mais_jogos(self):
        self.limite_exibicao += 60
        self._filtrar_jogos()

    def _obter_plataformas_jogo(self, jogo):
        """Retorna a lista de nomes de plataformas disponíveis e o mapeamento de store_ids."""
        plats = jogo.get("platforms", [])
        if not plats:
            return ["Standalone / Outro"], {}

        nomes = []
        mapa = {}
        for p in plats:
            nome = p.get("name")
            key = p.get("platform", "").lower()
            store_ids = p.get("store_ids", [])
            if nome:
                nomes.append(nome)
                mapa[nome] = {
                    "key": key,
                    "store_id": store_ids[0] if store_ids else None
                }

        nomes.append("Standalone / Outro")
        return nomes, mapa

    def _selecionar_jogo(self, jogo):
        """
        SELEÇÃO 100% AUTOMÁTICA:
        Escolhe de imediato o executável correto e a plataforma/launcher nativo!
        """
        self.jogo_selecionado = jogo
        nome = jogo.get("name", "Desconhecido")
        self.lbl_jogo_nome.configure(text=nome)

        # 1. Identifica a Plataforma Nativa Automática
        plat_nativa_nome, _ = identificar_plataforma_nativa(jogo)

        nomes_plats, self.mapa_plataformas = self._obter_plataformas_jogo(jogo)
        self.menu_plataformas.configure(values=nomes_plats)

        # Seleciona automaticamente a plataforma nativa correspondente
        plat_selecionada = nomes_plats[0]
        for p_name in nomes_plats:
            if plat_nativa_nome.lower() in p_name.lower() or p_name.lower() in plat_nativa_nome.lower():
                plat_selecionada = p_name
                break
        self.var_plataforma_selecionada.set(plat_selecionada)

        # 2. Identifica e seleciona AUTOMATICAMENTE o Executável Correto
        exes = [e["name"] for e in jogo.get("executables", []) if e.get("os", OS_ATUAL) == OS_ATUAL]

        if exes:
            self.menu_executaveis.configure(values=exes)
            exe_correto = rankear_executavel_correto(jogo, plat_selecionada)
            self.var_exec_selecionado.set(exe_correto if exe_correto in exes else exes[0])
            self.btn_gerar_abrir.configure(state="normal")
            self.btn_gerar.configure(state="normal")
        else:
            self.menu_executaveis.configure(values=["Nenhum executável compatível (Windows)"])
            self.var_exec_selecionado.set("Nenhum executável compatível (Windows)")
            self.btn_gerar_abrir.configure(state="disabled")
            self.btn_gerar.configure(state="disabled")

        self._atualizar_caminho_preview()

    def _ao_mudar_plataforma(self):
        """Se o usuário mudar manualmente a plataforma, reavalia se há executável específico dela."""
        if not self.jogo_selecionado:
            return
        plat_escolhida = self.var_plataforma_selecionada.get()
        exe_atual = self.var_exec_selecionado.get()
        exes = [e["name"] for e in self.jogo_selecionado.get("executables", []) if e.get("os", OS_ATUAL) == OS_ATUAL]

        # Se houver executável que bate com a plataforma nova (ex: steam/egs), sugere ele
        melhor = rankear_executavel_correto(self.jogo_selecionado, plat_escolhida)
        if melhor and melhor in exes and melhor != exe_atual:
            self.var_exec_selecionado.set(melhor)
        else:
            self._atualizar_caminho_preview()

    def _calcular_caminho_instalacao(self):
        if not self.jogo_selecionado:
            return None, None, None, None
        exe_raw = self.var_exec_selecionado.get()
        if not exe_raw or "Nenhum" in exe_raw:
            return None, None, None, None

        nome_jogo = self.jogo_selecionado.get("name", "Jogo")
        nome_pasta_jogo = "".join([c for c in nome_jogo if c not in '<>:"/\\|?*']).strip()

        plat_escolhida = self.var_plataforma_selecionada.get()
        info_plat = getattr(self, "mapa_plataformas", {}).get(plat_escolhida, {})
        plat_key = info_plat.get("key", "").lower()
        store_id = info_plat.get("store_id")

        launcher_exe = "explorer.exe"

        if "steam" in plat_key or "steam" in plat_escolhida.lower():
            base_folder = os.path.join(BASE_DIR, "simulados", "Steam", "steamapps", "common", nome_pasta_jogo)
            launcher_exe = "steam.exe"
        elif "battle.net" in plat_key or "battle.net" in plat_escolhida.lower() or "battlenet" in plat_key:
            base_folder = os.path.join(BASE_DIR, "simulados", "Battle.net", nome_pasta_jogo)
            launcher_exe = "battle.net.exe"
        elif "epic" in plat_key or "epic" in plat_escolhida.lower():
            base_folder = os.path.join(BASE_DIR, "simulados", "Epic Games", nome_pasta_jogo)
            launcher_exe = "epicgameslauncher.exe"
        elif "microsoft" in plat_key or "xbox" in plat_escolhida.lower():
            base_folder = os.path.join(BASE_DIR, "simulados", "XboxGames", nome_pasta_jogo)
            launcher_exe = "gamelaunchhelper.exe"
        elif "ubisoft" in plat_key or "uplay" in plat_escolhida.lower():
            base_folder = os.path.join(BASE_DIR, "simulados", "Ubisoft", "games", nome_pasta_jogo)
            launcher_exe = "upc.exe"
        elif "gog" in plat_key or "gog" in plat_escolhida.lower():
            base_folder = os.path.join(BASE_DIR, "simulados", "GOG Galaxy", "Games", nome_pasta_jogo)
            launcher_exe = "gog_galaxy.exe"
        else:
            base_folder = os.path.join(BASE_DIR, "simulados", "Games", nome_pasta_jogo)
            launcher_exe = "explorer.exe"

        caminho_rel = norm_path(exe_raw)
        destino_exe = os.path.abspath(os.path.join(base_folder, *caminho_rel.split("/")))
        return base_folder, destino_exe, launcher_exe, store_id

    def _atualizar_caminho_preview(self):
        base_folder, destino, launcher_exe, store_id = self._calcular_caminho_instalacao()
        if not destino:
            self.lbl_destino_preview.configure(text="📁 Instalação Simula: simulados/")
            return

        rel = os.path.relpath(destino, BASE_DIR)
        self.lbl_destino_preview.configure(text=f"📁 Instalação: {rel}")

        store_str = f" (ID: {store_id})" if store_id else ""
        plat_str = self.var_plataforma_selecionada.get()
        exe_nome = os.path.basename(destino)
        self.lbl_simulacao_info.configure(
            text=f"⚙️ Processo: {exe_nome}  |  Pai: {launcher_exe}  |  {plat_str}{store_str}"
        )

    # =========================================================================
    # AÇÕES: GERAR / INICIAR STUBS COM SIMULAÇÃO COMPLETA
    # =========================================================================
    def _obter_caminho_destino(self):
        base_folder, destino, launcher_exe, store_id = self._calcular_caminho_instalacao()
        if not destino:
            messagebox.showwarning("Aviso", "Selecione um jogo e executável válidos.")
            return None

        stub_origem = get_stub_path()
        if not stub_origem or not os.path.exists(stub_origem):
            messagebox.showerror(
                "Stub não encontrado",
                "O arquivo stub.exe não foi encontrado.\nCertifique-se de que ele esteja compilado."
            )
            return None

        os.makedirs(os.path.dirname(destino), exist_ok=True)
        try:
            shutil.copy(stub_origem, destino)

            plat_escolhida = self.var_plataforma_selecionada.get().lower()

            # Cria arquivos de metadados reais da plataforma selecionada
            if "steam" in plat_escolhida:
                if store_id:
                    with open(os.path.join(base_folder, "steam_appid.txt"), "w", encoding="utf-8") as f:
                        f.write(str(store_id))
            elif "battle.net" in plat_escolhida:
                build_info = os.path.join(base_folder, ".build.info")
                with open(build_info, "w", encoding="utf-8") as f:
                    f.write(f"Product!STRING:0\n{store_id or 'game'}\n")
            elif "epic" in plat_escolhida:
                os.makedirs(os.path.join(base_folder, ".egstore"), exist_ok=True)

            # Pastas complementares de jogo
            os.makedirs(os.path.join(base_folder, "Data"), exist_ok=True)
            cfg_path = os.path.join(base_folder, "game_settings.ini")
            if not os.path.exists(cfg_path):
                with open(cfg_path, "w", encoding="utf-8") as f:
                    f.write("[Graphics]\nRenderer=Direct3D11\nResolution=1920x1080\nFullscreen=1\n")

            # Metadados do stub
            meta_path = destino + ".json"
            meta_dados = {
                "name": self.jogo_selecionado.get("name", "Jogo"),
                "id": self.jogo_selecionado.get("id"),
                "platform": self.var_plataforma_selecionada.get(),
                "store_id": store_id
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta_dados, f, indent=2, ensure_ascii=False)

        except Exception as e:
            messagebox.showerror("Erro ao copiar", f"Não foi possível gerar a estrutura:\n{e}")
            return None

        return destino

    def _acao_apenas_gerar(self):
        dest = self._obter_caminho_destino()
        if dest:
            rel = os.path.relpath(dest, BASE_DIR)
            messagebox.showinfo("Sucesso", f"Estrutura e executável gerados com sucesso em:\n{rel}")

    def _acao_gerar_e_abrir(self):
        dest = self._obter_caminho_destino()
        if not dest:
            return

        nome_jogo = self.jogo_selecionado.get("name", "Jogo")
        app_id = self.jogo_selecionado.get("id")
        _, _, launcher_exe, store_id = self._calcular_caminho_instalacao()
        plat_str = self.var_plataforma_selecionada.get()

        # Monta linha de comando
        cmd = f'"{dest}" --name "{nome_jogo}" --platform "{plat_str}"'
        if app_id:
            cmd += f' --id "{app_id}"'

        cwd = os.path.dirname(dest)

        try:
            pid, parent_name = iniciar_processo_com_pai(cmd, cwd, launcher_preferido=launcher_exe)
            self.active_stubs.append({
                "pid": pid,
                "game": nome_jogo,
                "exe": os.path.basename(dest),
                "path": dest,
                "platform": plat_str,
                "parent": parent_name,
                "start_time": time.strftime("%H:%M:%S")
            })
            self._atualizar_lista_stubs_ui()
            self._log_detector_threadsafe(
                "info",
                f"Stub iniciado: {os.path.basename(dest)} (PID {pid}) | Plataforma: {plat_str} | Pai: {parent_name}"
            )
        except Exception as e:
            messagebox.showerror("Erro ao executar", f"Falha ao iniciar o processo:\n{e}")

    def _abrir_pasta_simulados(self):
        pasta = os.path.join(BASE_DIR, "simulados")
        os.makedirs(pasta, exist_ok=True)
        if WIN:
            os.startfile(pasta)
        else:
            subprocess.Popen(["xdg-open", pasta])

    # =========================================================================
    # GERENCIAMENTO DE STUBS ATIVOS
    # =========================================================================
    def _verificar_stubs_vivos(self):
        vivos = []
        houve_mudanca = False
        for item in self.active_stubs:
            pid = item["pid"]
            if psutil.pid_exists(pid):
                try:
                    p = psutil.Process(pid)
                    if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                        vivos.append(item)
                    else:
                        houve_mudanca = True
                except Exception:
                    houve_mudanca = True
            else:
                houve_mudanca = True

        if houve_mudanca:
            self.active_stubs = vivos
            self._atualizar_lista_stubs_ui()

        self.after(2000, self._verificar_stubs_vivos)

    def _atualizar_lista_stubs_ui(self):
        for widget in self.scroll_stubs.winfo_children():
            widget.destroy()

        if not self.active_stubs:
            lbl_vazio = ctk.CTkLabel(
                self.scroll_stubs,
                text="Nenhum processo simulado em execução no momento.",
                text_color="#949ba4",
                font=ctk.CTkFont(size=12)
            )
            lbl_vazio.pack(padx=10, pady=24)
            return

        for item in self.active_stubs:
            card = ctk.CTkFrame(self.scroll_stubs, fg_color="#232428", corner_radius=6)
            card.pack(fill="x", padx=6, pady=4)
            card.grid_columnconfigure(0, weight=1)

            parent_info = f"Pai: {item.get('parent', 'explorer.exe')}"
            plat_info = f"Plat: {item.get('platform', 'Gamer')}"
            lbl_info = ctk.CTkLabel(
                card,
                text=f"🟢 {item['game']}  •  {item['exe']}  (PID: {item['pid']} | {plat_info} | {parent_info})",
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#ffffff",
                anchor="w"
            )
            lbl_info.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")

            rel = os.path.relpath(item['path'], BASE_DIR)
            lbl_sub = ctk.CTkLabel(
                card,
                text=f"Iniciado às {item['start_time']}  •  {rel}",
                font=ctk.CTkFont(size=10),
                text_color="#949ba4",
                anchor="w"
            )
            lbl_sub.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="w")

            btn_kill = ctk.CTkButton(
                card,
                text="Finalizar",
                width=80,
                height=28,
                fg_color="#da373c",
                hover_color="#b52c30",
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda pid=item["pid"]: self._encerrar_stub_por_pid(pid)
            )
            btn_kill.grid(row=0, column=1, rowspan=2, padx=10, pady=6)

    def _encerrar_stub_por_pid(self, pid):
        finalizar_arvore_processos(pid)
        self._verificar_stubs_vivos()

    def _encerrar_todos_os_stubs(self):
        for item in self.active_stubs:
            finalizar_arvore_processos(item["pid"])
        self.active_stubs = []
        self._atualizar_lista_stubs_ui()
        self._log_detector_threadsafe("info", "Todos os stubs simulados foram encerrados.")

    # =========================================================================
    # JOGOS MANUAIS
    # =========================================================================
    def _adicionar_jogo_manual(self):
        nome = self.entry_manual_nome.get().strip()
        exe = self.entry_manual_exe.get().strip()
        if not nome or not exe:
            messagebox.showwarning("Atenção", "Preencha o nome do jogo e o executável.")
            return

        novo = {
            "name": nome,
            "executables": [{"os": OS_ATUAL, "name": exe}],
            "platforms": [{"platform": "standalone", "name": "Standalone / Outro", "store_ids": []}]
        }

        manual_path = os.path.join(BASE_DIR, "manual.json")
        manuais = []
        if os.path.exists(manual_path):
            try:
                with open(manual_path, "r", encoding="utf-8") as f:
                    manuais = json.load(f)
            except Exception:
                manuais = []

        manuais.append(novo)
        self._salvar_manual(manuais)

        self.jogos = self._carregar_jogos()
        self._filtrar_jogos()
        self._atualizar_lista_manuais_ui()
        self.detector.carregar_indice()

        self.entry_manual_nome.delete(0, "end")
        self.entry_manual_exe.delete(0, "end")

        messagebox.showinfo("Sucesso", f"Jogo '{nome}' adicionado com sucesso em manual.json!")

    def _atualizar_lista_manuais_ui(self):
        for widget in self.scroll_manuais.winfo_children():
            widget.destroy()

        manual_path = os.path.join(BASE_DIR, "manual.json")
        manuais = []
        if os.path.exists(manual_path):
            try:
                with open(manual_path, "r", encoding="utf-8") as f:
                    manuais = json.load(f)
            except Exception:
                pass

        if not manuais:
            lbl_vazio = ctk.CTkLabel(
                self.scroll_manuais,
                text="Nenhum jogo manual adicionado ainda.",
                text_color="#949ba4",
                font=ctk.CTkFont(size=12)
            )
            lbl_vazio.pack(padx=10, pady=20)
            return

        for idx, item in enumerate(manuais):
            card = ctk.CTkFrame(self.scroll_manuais, fg_color="#232428", corner_radius=6)
            card.pack(fill="x", padx=6, pady=3)
            card.grid_columnconfigure(0, weight=1)

            nome = item.get("name", "Jogo")
            exes = ", ".join([e.get("name", "") for e in item.get("executables", [])])

            lbl_info = ctk.CTkLabel(
                card,
                text=f"{nome}  ({exes})",
                font=ctk.CTkFont(size=12),
                text_color="#ffffff",
                anchor="w"
            )
            lbl_info.grid(row=0, column=0, padx=10, pady=6, sticky="w")

            btn_del = ctk.CTkButton(
                card,
                text="Excluir",
                width=65,
                height=26,
                fg_color="#313338",
                hover_color=self.color_danger,
                font=ctk.CTkFont(size=11),
                command=lambda i=idx: self._remover_jogo_manual(i)
            )
            btn_del.grid(row=0, column=1, padx=10, pady=6)

    def _remover_jogo_manual(self, index):
        manual_path = os.path.join(BASE_DIR, "manual.json")
        if not os.path.exists(manual_path):
            return
        try:
            with open(manual_path, "r", encoding="utf-8") as f:
                manuais = json.load(f)
            if 0 <= index < len(manuais):
                removido = manuais.pop(index)
                self._salvar_manual(manuais)
                self.jogos = self._carregar_jogos()
                self._filtrar_jogos()
                self._atualizar_lista_manuais_ui()
                self.detector.carregar_indice()
                self._log_detector_threadsafe("info", f"Jogo manual removido: {removido.get('name')}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha ao remover item: {e}")

    # =========================================================================
    # DETECTOR CALLBACKS
    # =========================================================================
    def _alternar_detector(self):
        ligado = bool(self.switch_detector.get())
        self.detector.pausar(not ligado)

    def _log_detector_threadsafe(self, tag, texto):
        self.after(0, lambda: self._append_detector_log(tag, texto))

    def _append_detector_log(self, tag, texto):
        agora = time.strftime("[%H:%M:%S] ")
        tk_text = self.txt_detector_log._textbox
        tk_text.insert("end", agora, "time")
        tk_text.insert("end", texto + "\n", tag)
        tk_text.see("end")

    def _status_detector_threadsafe(self, texto, cor):
        self.after(0, lambda: self.lbl_detector_status.configure(text=texto, text_color=cor))

    def _active_games_threadsafe(self, lista_jogos):
        self.after(0, lambda: self._atualizar_jogos_ativos_ui(lista_jogos))

    def _atualizar_jogos_ativos_ui(self, lista_jogos):
        if not lista_jogos:
            self.lbl_jogos_ativos_info.configure(
                text="🎯 Jogos detectados abertos agora: Nenhum",
                text_color="#949ba4"
            )
        else:
            jogos_str = " | ".join(lista_jogos)
            self.lbl_jogos_ativos_info.configure(
                text=f"🎯 Jogos detectados abertos agora ({len(lista_jogos)}): {jogos_str}",
                text_color="#23a55a"
            )

    def _limpar_log_detector(self):
        self.txt_detector_log._textbox.delete("1.0", "end")

    def _copiar_log_detector(self):
        conteudo = self.txt_detector_log._textbox.get("1.0", "end").strip()
        if conteudo:
            self.clipboard_clear()
            self.clipboard_append(conteudo)
            messagebox.showinfo("Copiado", "Log do detector copiado para a área de transferência!")

    # =========================================================================
    # ATUALIZAR BASE DO DISCORD
    # =========================================================================
    def _baixar_base_discord(self):
        self.btn_atualizar.configure(state="disabled", text="⏳ Baixando base...")

        def _tarefa():
            url = "https://discord.com/api/v9/applications/detectable"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=40) as response:
                    dados = json.load(response)

                base = []
                for j in dados:
                    if not j.get("executables"):
                        continue
                    platforms = []
                    platform_keys = []
                    skus = j.get("third_party_skus", [])
                    dist_map = {
                        "steam": ("Steam", "https://store.steampowered.com/app/"),
                        "battlenet": ("Battle.net", ""),
                        "epic": ("Epic Games Store", ""),
                        "xbox": ("Microsoft Store / Xbox", "https://www.xbox.com/games/store/-/"),
                        "uplay": ("Ubisoft Connect", ""),
                        "gog": ("GOG Galaxy", "")
                    }
                    grouped = {}
                    for s in skus:
                        d = s.get("distributor", "").lower()
                        grouped.setdefault(d, []).append(s.get("id"))

                    for d, ids in grouped.items():
                        if d in dist_map:
                            p_name, url_base = dist_map[d]
                            platform_keys.append(d)
                            urls = [f"{url_base}{i}" for i in ids if url_base]
                            platforms.append({
                                "platform": d,
                                "name": p_name,
                                "store_ids": ids,
                                "urls": urls
                            })

                    base.append({
                        "id": j.get("id"),
                        "name": j["name"],
                        "platform_keys": platform_keys,
                        "platforms": platforms,
                        "executables": j.get("executables", [])
                    })

                caminho_salvar = os.path.join(BASE_DIR, "jogos.json")
                with open(caminho_salvar, "w", encoding="utf-8") as f:
                    json.dump(base, f, indent=2, ensure_ascii=False)

                self.after(0, lambda: self._pos_download_sucesso(len(base)))
            except Exception as e:
                self.after(0, lambda: self._pos_download_erro(str(e)))

        threading.Thread(target=_tarefa, daemon=True).start()

    def _pos_download_sucesso(self, total):
        self.btn_atualizar.configure(state="normal", text="🔄 Atualizar Base (Discord API)")
        self.jogos = self._carregar_jogos()
        self._filtrar_jogos()
        self.detector.carregar_indice()
        self._log_detector_threadsafe("info", f"Base atualizada com sucesso! {total} jogos carregados.")
        messagebox.showinfo("Base Atualizada", f"Base de jogos atualizada com sucesso!\n{total} jogos disponíveis.")

    def _pos_download_erro(self, err_msg):
        self.btn_atualizar.configure(state="normal", text="🔄 Atualizar Base (Discord API)")
        self._log_detector_threadsafe("close", f"Falha ao atualizar base: {err_msg}")
        messagebox.showerror("Erro ao Baixar", f"Não foi possível baixar a base do Discord:\n{err_msg}")

if __name__ == "__main__":
    app = GamePresenceApp()
    app.mainloop()
