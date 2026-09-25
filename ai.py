"""Bildanalys av VVS-utrustning.

En bild skickas till en lokal bildmodell i Ollama (inga bilder lämnar datorn).
Modellen får svara med JSON och resultatet blir ett *förslag* — ingenting
sparas förrän användaren trycker Spara.

Modellen är valfri: saknas den fungerar appen ändå, då får man fylla i
fälten själv och bilden sparas som vanligt.
"""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.request

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
STANDARD_MODELL = "qwen2.5vl:3b"

# Modeller som kan se bilder. Används för att varna i förväg i stället för
# att låta användaren vänta på ett anrop som ändå inte kan svara.
BILDMODELLER = ("qwen2.5vl", "qwen2.5-vl", "llava", "llama3.2-vision",
                "moondream", "minicpm-v", "bakllava", "gemma3", "granite3.2-vision")


def ar_bildmodell(namn):
    n = (namn or "").lower()
    return any(m in n for m in BILDMODELLER)


def tillgangliga():
    """Modeller som Ollama har lokalt."""
    try:
        req = urllib.request.Request(OLLAMA + "/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        return []


def valj_modell(cfg=None):
    """Vald modell om den finns lokalt, annars första bildmodellen, annars None."""
    vald = ((cfg or {}).get("ai") or {}).get("modell") or ""
    har = tillgangliga()
    if vald and vald in har:
        return vald
    for m in har:
        if ar_bildmodell(m):
            return m
    return None


def _bild_base64(sokvag, maxsida=1024):
    """Skalar ner och gör om till JPEG-base64. En telefonbild är 3–5 MB;
    modellen behöver inte mer än ~1024 px för att känna igen en koppling."""
    with open(sokvag, "rb") as fh:
        rå = fh.read()
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(rå))
        im = im.convert("RGB")
        if max(im.size) > maxsida:
            skala = maxsida / max(im.size)
            im = im.resize((max(1, int(im.width * skala)),
                            max(1, int(im.height * skala))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
        rå = buf.getvalue()
    except Exception:
        pass                       # PIL saknas/trasig bild: skicka originalet
    return base64.b64encode(rå).decode("ascii")


SYSTEM = """Du inventerar en VVS-verkstad på en skola. Du får en bild och ska
föreslå vad föremålet är. Svara BARA med JSON, ingen förklaring utanför JSON.

Fälten:
  namn        kort svensk benämning på det du faktiskt ser
  kategori    en av: maskin, verktyg, material, inredning, skydd, forbrukning, annat
  antal       hur många du ser (heltal, 1 om du är osäker)
  enhet       st, m, kg, par, rulle, liter
  dimension   dimension eller artikelbeteckning om den syns, annars tom sträng
  tillverkare märke om det syns på bilden, annars tom sträng
  skick       en av: ok, service, trasig, utlånad, borta
  investeringsbehov  en av: behall, investera, avveckla, vetej
              sätt "investera" bara om föremålet ser ut att behöva ersättas
              eller är för slitet för undervisning — annars "vetej"
  anteckning  en kort iakttagelse om just den här bilden
  sakerhet    osäker om du gissar, saker om du är tydligt säker

Svarets form är alltid, med tomma värden där du inte vet:

{"namn":"","kategori":"","antal":0,"enhet":"","dimension":"",
 "tillverkare":"","skick":"","investeringsbehov":"","anteckning":"",
 "sakerhet":""}

Formen är bara ett skal — den är tom med flit. Fyll den med det du ser i
*den här* bilden. Skriv aldrig ett exempelföremål: ser du ingen skruvdragare
ska ordet skruvdragare inte stå i svaret. Skriv inte punkter eller frågetecken
i stället för ett värde; lämna fältet tomt.

Hitta inte på ett märke eller en dimension som inte syns i bilden. Är du
osäker sätter du sakerhet till "osäker" och lämnar fältet tomt i stället.
Kan du inte alls se vad bilden föreställer sätter du namn till "" och
sakerhet till "osäker". Sätt ALDRIG ett pris — priser gissar vi inte, de ska
sättas av en människa."""


def _plocka_json(text):
    """Modeller lägger ofta JSON i ```-block eller blandar in text."""
    if not text:
        return None
    text = text.strip()
    staket = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if staket:
        text = staket.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start, slut = text.find("{"), text.rfind("}")
    if start != -1 and slut > start:
        try:
            return json.loads(text[start:slut + 1])
        except Exception:
            return None
    return None


def _skrap(v):
    """Sant om värdet inte är ett svar utan en platshållare.

    Små modeller fyller ibland i skalet med punkter eller fältnamnet i stället
    för att lämna det tomt. Sådant ska inte hamna i inventeringen."""
    t = (v or "").strip().strip(".·…").strip()
    if not t:
        return True
    if set(t) <= set(".-–—…?!"):          # bara skiljetecken
        return True
    nycklar = {"namn", "kategori", "antal", "enhet", "dimension", "tillverkare",
               "skick", "investeringsbehov", "anteckning", "sakerhet", "vetej",
               "falt", "fält", "varde", "värde", "okand", "okänd", "string",
               "tomt", "inget", "n/a", "na", "none", "null", "unknown"}
    return t.lower() in nycklar


def _stada(forslag):
    """Behåller bara kända fält och rimliga värden."""
    if not isinstance(forslag, dict):
        return {}
    import lager                       # bara för de giltiga listorna
    ut = {}
    for nyckel in ("namn", "kategori", "dimension", "tillverkare",
                   "anteckning", "enhet", "skick", "investeringsbehov"):
        v = forslag.get(nyckel)
        if isinstance(v, str) and v.strip() and not _skrap(v):
            ut[nyckel] = v.strip()[:200]
    # modellen hittar ibland på egna värden — hellre tomt än skräp i arket
    if ut.get("kategori") not in lager.KATEGORI_ID:
        ut.pop("kategori", None)
    if ut.get("skick") not in [k for k, _ in lager.SKICK]:
        ut.pop("skick", None)
    if ut.get("investeringsbehov") not in [k for k, _ in lager.BEHOV]:
        ut.pop("investeringsbehov", None)
    ut.pop("pris", None)            # pris gissar vi aldrig
    antal = forslag.get("antal")
    if isinstance(antal, (int, float)) and antal > 0:
        ut["antal"] = int(antal) if float(antal).is_integer() else float(antal)
    elif isinstance(antal, str):
        m = re.search(r"\d+", antal)
        ut["antal"] = int(m.group()) if m else 1
    ut["sakerhet"] = ("osäker" if str(forslag.get("sakerhet", "")).lower().startswith("osäk")
                      else "saker")
    return ut


def analysera(sokvag, cfg=None, timeout=180):
    """Analyserar en bild och returnerar ett förslag.

    Returnerar alltid ett diktat: antingen {"forslag": {...}, "modell": ...}
    eller {"fel": "..."} med en förklaring som går att visa för användaren.
    """
    modell = valj_modell(cfg)
    if not modell:
        har = tillgangliga()
        if not har:
            return {"fel": "Ollama svarar inte. Starta tjänsten med: "
                           "sudo systemctl start ollama"}
        return {"fel": "Ingen bildmodell finns lokalt. Hämta en med: "
                       "ollama pull " + STANDARD_MODELL,
                "modeller": har}
    try:
        bild = _bild_base64(sokvag)
    except Exception as exc:
        return {"fel": f"Kunde inte läsa bilden: {exc}"}

    kropp = {"model": modell, "stream": False, "format": "json",
             "options": {"temperature": 0.1},
             "messages": [{"role": "user", "content": SYSTEM, "images": [bild]}]}
    req = urllib.request.Request(OLLAMA + "/api/chat",
                                 data=json.dumps(kropp).encode("utf-8"),
                                 method="POST")
    req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            svar = json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        rå = exc.read().decode("utf-8", "replace")[:300]
        return {"fel": f"Modellen svarade fel ({exc.code}): {rå}"}
    except Exception as exc:
        return {"fel": f"Kunde inte nå modellen: {type(exc).__name__}: {exc}"}

    text = ((svar.get("message") or {}).get("content") or "").strip()
    forslag = _stada(_plocka_json(text))
    if not forslag.get("namn"):
        return {"fel": "Modellen kunde inte avgöra vad bilden visar. "
                       "Skriv namnet själv — bilden sparas ändå.",
                "modell": modell, "text": text[:400]}
    forslag.setdefault("antal", 1)
    forslag.setdefault("enhet", "st")
    forslag.setdefault("skick", "ok")
    return {"forslag": forslag, "modell": modell}
