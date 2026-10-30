"""
Stub Avançado de Jogo Simulado para Teste de Detecção e Presença.
- Módulos Gráficos: Carrega d3d11.dll, dxgi.dll, d3d12.dll, opengl32.dll, vulkan-1.dll, xinput1_4.dll
- Inicialização Direct3D 11: Cria contexto de dispositivo DirectX real no Windows
- Título da Janela Win32: Registra o título exato do jogo na Windows API (GetWindowTextW)
- Discord RPC: Comunicação nativa via IPC Pipe com Client ID oficial do jogo
- Suporte a Múltiplas Plataformas (Steam, Battle.net, Epic Games, Xbox, etc.)
- Simulação de Memória e Comportamento: Event loop ativo e consumo realista de recursos
"""

import os
import sys
import time
import json
import struct
import argparse
import threading
import tkinter as tk
import ctypes
from ctypes import wintypes

WIN = sys.platform == "win32"

# =========================================================================
# 1. CARREGAMENTO DE MÓDULOS GRÁFICOS E SIMULAÇÃO DIRECTX
# =========================================================================
GRAFICOS = ["d3d11.dll", "dxgi.dll", "d3d12.dll", "opengl32.dll", "vulkan-1.dll", "xinput1_4.dll", "winmm.dll", "ws2_32.dll"]
modulos_carregados = []

def carregar_modulos_graficos():
    global modulos_carregados
    if not WIN:
        return
    for mod in GRAFICOS:
        try:
            h = ctypes.windll.kernel32.LoadLibraryW(mod)
            if h:
                modulos_carregados.append(mod)
        except Exception:
            pass

    # Inicializa contexto Direct3D 11 real no hardware
    try:
        d3d11 = ctypes.windll.d3d11
        pDevice = ctypes.c_void_p()
        pContext = ctypes.c_void_p()
        # D3D_DRIVER_TYPE_HARDWARE = 1, D3D11_SDK_VERSION = 7
        hr = d3d11.D3D11CreateDevice(
            None, 1, None, 0, None, 0, 7,
            ctypes.byref(pDevice), None, ctypes.byref(pContext)
        )
        if hr == 0:
            modulos_carregados.append("D3D11_Device_Active")
    except Exception:
        pass

carregar_modulos_graficos()

# Simula pegada de memória realista (~65 MB)
try:
    _simulated_memory_buffer = bytearray(65 * 1024 * 1024)
except Exception:
    _simulated_memory_buffer = None

# =========================================================================
# 2. IDENTIFICAÇÃO DO JOGO E PLATAFORMA
# =========================================================================
def carregar_dados_jogo():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--name", type=str, default=None)
    parser.add_argument("--id", type=str, default=None)
    parser.add_argument("--platform", type=str, default=None)
    args, _ = parser.parse_known_args()

    game_name = args.name
    app_id = args.id
    platform_name = args.platform
    store_id = None

    meu_exe = os.path.basename(sys.executable).lower()
    if "python" in meu_exe:
        meu_exe = "overwatch.exe"

    # Tenta ler arquivo de metadados companheiro (.json ao lado do executável)
    meta_path = sys.executable + ".json"
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                game_name = game_name or d.get("name")
                app_id = app_id or d.get("id")
                platform_name = platform_name or d.get("platform")
                store_id = d.get("store_id")
        except Exception:
            pass

    if not game_name:
        # Procura no jogos.json nas pastas superiores
        dir_atual = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, 'frozen', False) else __file__))
        for _ in range(6):
            candidato = os.path.join(dir_atual, "jogos.json")
            if os.path.exists(candidato):
                try:
                    with open(candidato, "r", encoding="utf-8") as f:
                        jogos = json.load(f)
                        for j in jogos:
                            for e in j.get("executables", []):
                                alvo = e.get("name", "").replace("\\", "/").lower().split("/")[-1].lstrip(">")
                                if alvo == meu_exe:
                                    game_name = j.get("name", meu_exe)
                                    app_id = j.get("id")
                                    break
                except Exception:
                    pass
            dir_atual = os.path.dirname(dir_atual)

    if not game_name:
        nome_base = os.path.splitext(meu_exe)[0]
        game_name = nome_base.replace("_", " ").replace("-", " ").title()

    if not platform_name:
        platform_name = "Standalone"

    return game_name, app_id, platform_name, store_id

GAME_NAME, DISCORD_APP_ID, PLATFORM_NAME, STORE_ID = carregar_dados_jogo()

if WIN:
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(GAME_NAME)
    except Exception:
        pass

# =========================================================================
# 3. DISCORD RICH PRESENCE (IPC NATIVO)
# =========================================================================
class DiscordRPC:
    def __init__(self, client_id, game_name):
        self.client_id = client_id or "356875221078245376"
        self.game_name = game_name
        self.pipe = None
        self.connected = False
        self.start_time = int(time.time())

    def conectar(self):
        if not WIN:
            return False
        for i in range(10):
            pipe_name = rf"\\.\pipe\discord-ipc-{i}"
            if os.path.exists(pipe_name):
                try:
                    self.pipe = open(pipe_name, "r+b", buffering=0)
                    handshake = json.dumps({"v": 1, "client_id": str(self.client_id)}).encode("utf-8")
                    self.pipe.write(struct.pack("<II", 0, len(handshake)) + handshake)
                    op, length = struct.unpack("<II", self.pipe.read(8))
                    resp = json.loads(self.pipe.read(length).decode("utf-8"))
                    if resp.get("evt") == "READY" or op == 1:
                        self.connected = True
                        self.atualizar_atividade()
                        return True
                except Exception:
                    self.pipe = None
        return False

    def atualizar_atividade(self):
        if not self.connected or not self.pipe:
            return
        try:
            payload = {
                "cmd": "SET_ACTIVITY",
                "args": {
                    "pid": os.getpid(),
                    "activity": {
                        "details": f"Em jogo ({PLATFORM_NAME})",
                        "state": "Simulador Avançado",
                        "timestamps": {"start": self.start_time}
                    }
                },
                "nonce": str(time.time())
            }
            data = json.dumps(payload).encode("utf-8")
            self.pipe.write(struct.pack("<II", 1, len(data)) + data)
            self.pipe.read(8)
        except Exception:
            self.connected = False

    def fechar(self):
        if self.pipe:
            try:
                self.pipe.close()
            except Exception:
                pass
        self.connected = False

# =========================================================================
# 4. JANELA GRÁFICA DO JOGO (COM TITULO E PERSISTÊNCIA WIN32)
# =========================================================================
class StubWindow:
    def __init__(self, root, game_name, app_id, platform_name, store_id):
        self.root = root
        self.game_name = game_name
        self.app_id = app_id
        self.platform_name = platform_name
        self.store_id = store_id
        self.fps_simulado = 60
        self.frames = 0

        self.root.title(self.game_name)
        self.root.geometry("490x270")
        self.root.minsize(430, 230)
        self.root.configure(bg="#121315")

        for p in [os.path.join(os.path.dirname(sys.executable), "app_icon.ico"), "app_icon.ico"]:
            if os.path.exists(p):
                try:
                    self.root.iconbitmap(p)
                    break
                except Exception:
                    pass

        if WIN:
            try:
                self.root.update_idletasks()
                child_hwnd = self.root.winfo_id()
                parent_hwnd = ctypes.windll.user32.GetParent(child_hwnd)
                if parent_hwnd:
                    ctypes.windll.user32.SetWindowTextW(parent_hwnd, self.game_name)
                ctypes.windll.user32.SetWindowTextW(child_hwnd, self.game_name)
            except Exception:
                pass

        frame = tk.Frame(root, bg="#121315", padx=20, pady=16)
        frame.pack(fill="both", expand=True)

        header = tk.Frame(frame, bg="#121315")
        header.pack(fill="x", anchor="w")

        lbl_icone = tk.Label(header, text="🎮", font=("Segoe UI Emoji", 26), bg="#121315", fg="#5865f2")
        lbl_icone.pack(side="left", padx=(0, 10))

        title_box = tk.Frame(header, bg="#121315")
        title_box.pack(side="left", fill="x", expand=True)

        lbl_titulo = tk.Label(
            title_box,
            text=self.game_name,
            font=("Segoe UI", 16, "bold"),
            bg="#121315",
            fg="#ffffff",
            anchor="w"
        )
        lbl_titulo.pack(fill="x")

        exe_nome = os.path.basename(sys.executable)
        info_plat = f"Plataforma: {self.platform_name}"
        if self.store_id:
            info_plat += f" (ID: {self.store_id})"

        lbl_exe = tk.Label(
            title_box,
            text=f"{info_plat}  •  {exe_nome}  •  PID: {os.getpid()}",
            font=("Segoe UI", 9),
            bg="#121315",
            fg="#949ba4",
            anchor="w"
        )
        lbl_exe.pack(fill="x")

        # Card de Status
        card_status = tk.Frame(frame, bg="#1e1f22", padx=12, pady=10, relief="flat")
        card_status.pack(fill="x", pady=(14, 10))

        self.lbl_status = tk.Label(
            card_status,
            text="⏳ Conectando aos serviços do Discord e DirectX...",
            font=("Segoe UI", 10, "bold"),
            bg="#1e1f22",
            fg="#e5a50a",
            anchor="w"
        )
        self.lbl_status.pack(fill="x")

        mods_str = ", ".join([m for m in modulos_carregados if not m.startswith("D3D11_")][:4])
        has_d3d = "Direct3D 11 Ativo" if "D3D11_Device_Active" in modulos_carregados else "GDI+"
        lbl_mods = tk.Label(
            card_status,
            text=f"Módulos 3D: {has_d3d}  |  DLLs: {mods_str}",
            font=("Segoe UI", 9),
            bg="#1e1f22",
            fg="#80848e",
            anchor="w"
        )
        lbl_mods.pack(fill="x", pady=(3, 0))

        btn_frame = tk.Frame(frame, bg="#121315")
        btn_frame.pack(fill="x", side="bottom")

        self.lbl_simulacao = tk.Label(
            btn_frame,
            text=f"Simulação ativa ({self.platform_name})",
            font=("Segoe UI", 9),
            bg="#121315",
            fg="#5865f2"
        )
        self.lbl_simulacao.pack(side="left")

        btn_min = tk.Button(
            btn_frame,
            text="Minimizar",
            font=("Segoe UI", 9),
            bg="#2b2d31",
            fg="#ffffff",
            activebackground="#35373c",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=3,
            command=self.root.iconify
        )
        btn_min.pack(side="left", padx=(14, 0))

        btn_sair = tk.Button(
            btn_frame,
            text="Encerrar Jogo",
            font=("Segoe UI", 9, "bold"),
            bg="#da373c",
            fg="#ffffff",
            activebackground="#b52c30",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=3,
            command=self.encerrar
        )
        btn_sair.pack(side="right")

        self.rpc = DiscordRPC(self.app_id, self.game_name)
        threading.Thread(target=self._conectar_rpc, daemon=True).start()

        self._loop_simulacao()

    def _loop_simulacao(self):
        self.frames += 1
        if self.frames % 3 == 0:
            try:
                self.root.title(self.game_name)
                if WIN:
                    child_hwnd = self.root.winfo_id()
                    parent_hwnd = ctypes.windll.user32.GetParent(child_hwnd)
                    if parent_hwnd:
                        ctypes.windll.user32.SetWindowTextW(parent_hwnd, self.game_name)
            except Exception:
                pass
            if not self.rpc.connected:
                threading.Thread(target=self._conectar_rpc, daemon=True).start()
        self.root.after(1000, self._loop_simulacao)

    def _conectar_rpc(self):
        ok = self.rpc.conectar()
        if ok:
            self.root.after(0, lambda: self.lbl_status.configure(
                text=f"🟢 Ativo no Discord (Identificado como {self.game_name})",
                fg="#23a55a"
            ))
        else:
            self.root.after(0, lambda: self.lbl_status.configure(
                text=f"🟢 Janela Ativa ({self.game_name})",
                fg="#23a55a"
            ))

    def encerrar(self):
        self.rpc.fechar()
        self.root.destroy()
        sys.exit(0)

def main():
    root = tk.Tk()
    app = StubWindow(root, GAME_NAME, DISCORD_APP_ID, PLATFORM_NAME, STORE_ID)
    root.protocol("WM_DELETE_WINDOW", app.encerrar)
    root.mainloop()

if __name__ == "__main__":
    main()
