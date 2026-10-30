import json, urllib.request
URL = "https://discord.com/api/v9/applications/detectable"
req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
dados = json.load(urllib.request.urlopen(req, timeout=30))
base = [{"name": j["name"], "executables": j.get("executables", [])} for j in dados if j.get("executables")]
json.dump(base, open("jogos.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"{len(base)} jogos salvos em jogos.json")
