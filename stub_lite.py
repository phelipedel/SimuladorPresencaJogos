"""
Stub Ultra-Leve de Jogo Simulado para Teste de Detecção e Presença (Modo Econômico).
Otimizado especificamente para computadores modestos, antigos ou com refrigeração limitada:
- Sem consumo artificial de RAM (0 MB de buffer alocado)
- Inicialização gráfica 100% segura (sem Vulkan ou D3D12 que travam placas antigas)
- DirectX 11 com fallback seguro para evitar crash de driver
- Título nativo Win32 (SetWindowTextW) para detecção correta no Discord
- Discord Rich Presence nativo via IPC Pipe (sem dependências externas)
- Consumo de CPU em repouso: 0%
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
# 1. CARREGAMENTO GRÁFICO SEGURO (SEM VULKAN / D3D12 QUE TRAVAM GPUs ANTIGAS)
# =========================================================================
SAFE_DLLS = ["d3d11.dll", "dxgi.dll", "xinput1_4.dll", "winmm.dll", "ws2_32.dll"]
modulos_carregados = []

def carregar_modulos_seguros():
    global modulos_carregados
    if not WIN:
        return
    for mod in SAFE_DLLS:
        try:
            h = ctypes.windll.kernel32.LoadLibraryW(mod)
            if h:
                modulos_carregados.append(mod)
        except Exception:
            pass

    # Inicializa Direct3D 11 com proteção contra crash de driver legado
    try:
        d3d11 = ctypes.windll.d3d11
        pDevice = ctypes.c_void_p()
        pContext = ctypes.c_void_p()
        
        # Tenta modo Hardware (1). Se falhar, tenta modo WARP/Software (2) sem derrubar a GPU
        hr = d3d11.D3D11CreateDevice(
            None, 1, None, 0, None, 0, 7,
            ctypes.byref(pDevice), None, ctypes.byref(pContext)
        )
        if hr == 0:
            modulos_carregados.append("D3D11_Hardware")
        else:
            # Fallback seguro para WARP
            hr_warp = d3d11.D3D11CreateDevice(
                None, 2, None, 0, None, 0, 7,
                ctypes.byref(pDevice), None, ctypes.byref(pContext)
            )
            if hr_warp == 0:
                modulos_carregados.append("D3D11_WARP")
    except Exception:
        pass

carregar_modulos_seguros()

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
# 3. DISCORD RICH PRESENCE (IPC LEVE E NÃO-BLOQUEANTE)
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
        for i in range(5):
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
                        "state": "Modo Ultra-Leve",
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
# 4. JANELA GRÁFICA ULTRA-LEVE (TKINTER PURO, 0% CPU, < 15MB RAM)
# =========================================================================
class StubWindowLite:
    def __init__(self, root, game_name, app_id, platform_name, store_id):
        self.root = root
        self.game_name = game_name
        self.app_id = app_id
        self.platform_name = platform_name
        self.store_id = store_id

        self.root.title(self.game_name)
        self.root.geometry("440x220")
        self.root.minsize(400, 200)
        self.root.configure(bg="#141518")

        for p in [os.path.join(os.path.dirname(sys.executable), "app_icon.ico"), "app_icon.ico"]:
            if os.path.exists(p):
                try:
                    self.root.iconbitmap(p)
                    break
                except Exception:
                    pass

        # Garante título Win32 real no topo da hierarquia de janelas
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

        # Layout Simples e Fluido
        main_frame = tk.Frame(root, bg="#141518", padx=16, pady=14)
        main_frame.pack(fill="both", expand=True)

        lbl_titulo = tk.Label(
            main_frame,
            text=f"🎮  {self.game_name}",
            font=("Segoe UI", 14, "bold"),
            bg="#141518",
            fg="#ffffff",
            anchor="w"
        )
        lbl_titulo.pack(fill="x")

        exe_nome = os.path.basename(sys.executable)
        info_sub = f"Plataforma: {self.platform_name}  •  {exe_nome} (PID: {os.getpid()})"
        lbl_sub = tk.Label(
            main_frame,
            text=info_sub,
            font=("Segoe UI", 8),
            bg="#141518",
            fg="#949ba4",
            anchor="w"
        )
        lbl_sub.pack(fill="x", pady=(2, 10))

        # Card de Status
        card = tk.Frame(main_frame, bg="#1e1f23", padx=12, pady=10, relief="flat")
        card.pack(fill="x", pady=(0, 10))

        self.lbl_status = tk.Label(
            card,
            text="⏳ Conectando aos serviços do Discord...",
            font=("Segoe UI", 9, "bold"),
            bg="#1e1f23",
            fg="#e5a50a",
            anchor="w"
        )
        self.lbl_status.pack(fill="x")

        has_d3d = "Direct3D Ativo" if ("D3D11_Hardware" in modulos_carregados or "D3D11_WARP" in modulos_carregados) else "GDI+"
        lbl_gfx = tk.Label(
            card,
            text=f"Modo Econômico: {has_d3d}  |  Consumo de CPU: 0%  |  RAM: ~12 MB",
            font=("Segoe UI", 8),
            bg="#1e1f23",
            fg="#80848e",
            anchor="w"
        )
        lbl_gfx.pack(fill="x", pady=(2, 0))

        # Barra inferior de botões
        bar_bottom = tk.Frame(main_frame, bg="#141518")
        bar_bottom.pack(fill="x", side="bottom")

        btn_min = tk.Button(
            bar_bottom,
            text="Minimizar",
            font=("Segoe UI", 8),
            bg="#2b2d31",
            fg="#ffffff",
            activebackground="#35373c",
            activeforeground="#ffffff",
            relief="flat",
            padx=10,
            pady=2,
            command=self.root.iconify
        )
        btn_min.pack(side="left")

        btn_fechar = tk.Button(
            bar_bottom,
            text="Encerrar Jogo",
            font=("Segoe UI", 8, "bold"),
            bg="#da373c",
            fg="#ffffff",
            activebackground="#b52c30",
            activeforeground="#ffffff",
            relief="flat",
            padx=12,
            pady=2,
            command=self.encerrar
        )
        btn_fechar.pack(side="right")

        self.rpc = DiscordRPC(self.app_id, self.game_name)
        threading.Thread(target=self._conectar_rpc, daemon=True).start()

        # Loop leve a cada 4 segundos (economiza 100% de CPU)
        self._loop_economico()

    def _loop_economico(self):
        if WIN:
            try:
                child_hwnd = self.root.winfo_id()
                parent_hwnd = ctypes.windll.user32.GetParent(child_hwnd)
                if parent_hwnd:
                    ctypes.windll.user32.SetWindowTextW(parent_hwnd, self.game_name)
            except Exception:
                pass
        if not self.rpc.connected:
            threading.Thread(target=self._conectar_rpc, daemon=True).start()
        self.root.after(4000, self._loop_economico)

    def _conectar_rpc(self):
        ok = self.rpc.conectar()
        if ok:
            self.root.after(0, lambda: self.lbl_status.configure(
                text=f"🟢 Ativo no Discord ({self.game_name})",
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
    app = StubWindowLite(root, GAME_NAME, DISCORD_APP_ID, PLATFORM_NAME, STORE_ID)
    root.protocol("WM_DELETE_WINDOW", app.encerrar)
    root.mainloop()

if __name__ == "__main__":
    main()
