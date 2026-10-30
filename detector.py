import json, os, sys, time, psutil

OS_ATUAL = "win32" if sys.platform == "win32" else "linux"
def norm(p): return p.replace("\\", "/").lower().lstrip(">")

def carregar():
    regras = []
    for arq in ("jogos.json", "manual.json"):
        if os.path.exists(arq):
            regras += json.load(open(arq, encoding="utf-8"))
    indice = {}
    for j in regras:
        for e in j["executables"]:
            if e.get("os", OS_ATUAL) != OS_ATUAL:
                continue
            alvo = norm(e["name"])
            indice.setdefault(alvo.split("/")[-1], []).append((alvo, j["name"]))
    return indice

indice = carregar()
print(f"Detector ativo. {len(indice)} executáveis monitorados. Ctrl+C para sair.\n")
abertos = set()
ultima_recarga = time.time()
while True:
    if time.time() - ultima_recarga > 30:
        indice = carregar(); ultima_recarga = time.time()
    agora = set()
    for p in psutil.process_iter(["name", "exe"]):
        try:
            nome = (p.info["name"] or "").lower()
            exe = norm(p.info["exe"] or "")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        for alvo, jogo in indice.get(nome, []):
            if "/" not in alvo or exe.endswith("/" + alvo):
                agora.add(jogo)
    for j in sorted(agora - abertos):
        print(f"[{time.strftime('%H:%M:%S')}] [+] Jogo {j} aberto")
    for j in sorted(abertos - agora):
        print(f"[{time.strftime('%H:%M:%S')}] [-] Jogo {j} fechado")
    abertos = agora
    time.sleep(3)
