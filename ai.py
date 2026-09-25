"""Bildanalys av VVS-utrustning.

Två sätt att analysera en bild:

* **Ollama lokalt** (standard på datorn). Ingenting lämnar maskinen.
* **En molntjänst** (Gemini eller ett OpenAI-kompatibelt API). Behövs när
  appen kör på en server, för där finns ingen Ollama. Då skickas bilden till
  tjänsten — det ska man veta om, och därför är det ett aktivt val.

Modellen får svara med JSON och resultatet blir ett *förslag* — ingenting
sparas förrän användaren trycker Spara.

Analysen är valfri: saknas den fungerar appen ändå, då får man fylla i
fälten själv och bilden sparas som vanligt.
"""
import base64
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
STANDARD_MODELL = "qwen2.5vl:3b"

# Molnleverantörer. "openai" betyder vilket API som helst som talar samma
# språk (OpenAI, Mistral, Groq, en lokal server …) — bara adressen ändras.
STANDARD_MODELLER = {"gemini": "gemini-2.0-flash",
                     "openai": "gpt-4o-mini"}
STANDARD_URLAR = {"gemini": "https://generativelanguage.googleapis.com/v1beta",
                  "openai": "https://api.openai.com/v1"}

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
lista ALLT som syns på den. En bild kan visa flera saker — en bänk med tio
kopplingar, en hylla med verktyg, ett svetsaggregat bredvid en slangvinda.
Då blir det flera rader i svaret. Svara BARA med JSON, ingen text utanför.

Fälten per föremål:
  namn        kort svensk benämning på det du faktiskt ser
  kategori    en av: maskin, verktyg, material, inredning, skydd, forbrukning, annat
  antal       hur många du ser av just den saken (heltal, 1 om du är osäker)
  enhet       st, m, kg, par, rulle, liter
  dimension   dimension eller artikelbeteckning om den syns, annars tom sträng
  tillverkare märke om det syns på bilden, annars tom sträng
  skick       en av: ok, service, trasig, utlånad, borta
  investeringsbehov  en av: behall, investera, avveckla, vetej
              sätt "investera" bara om föremålet ser ut att behöva ersättas
              eller är för slitet för undervisning — annars "vetej"
  anteckning  en kort iakttagelse om just den saken
  sakerhet    osäker om du gissar, saker om du är tydligt säker

Svarets form är alltid, med tomma värden där du inte vet:

{"foremal":[
 {"namn":"","kategori":"","antal":0,"enhet":"","dimension":"",
  "tillverkare":"","skick":"","investeringsbehov":"","anteckning":"",
  "sakerhet":""}
]}

Formen är bara ett skal — den är tom med flit. Fyll den med det du ser i
*den här* bilden. Skriv aldrig ett exempelföremål: ser du ingen skruvdragare
ska ordet skruvdragare inte stå i svaret. Anta inte att bilden visar ett
verktyg bara för att du inventerar en verkstad. Skriv inte punkter eller
frågetecken i stället för ett värde; lämna fältet tomt.

En sak per rad. Syns samma sak flera gånger skriver du antalet i "antal" i
stället för att upprepa raden. Ta med allt som går att inventera — även
bänkar, skåp och inredning. Hoppa över bakgrund som väggar och golv.

Hitta inte på ett märke eller en dimension som inte syns i bilden. Är du
osäker sätter du sakerhet till "osäker" och lämnar fältet tomt i stället.
Kan du inte alls se vad bilden föreställer svarar du {"foremal":[]}.
Sätt ALDRIG ett pris — priser gissar vi inte, de ska sättas av en människa."""


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


def _dubbletter(sparade):
    """Slår ihop föremål med samma namn och kategori till en rad.

    En bild på tio likadana kopplingar ska bli *en* rad med antal 10, inte tio
    rader — annars får yrkesläraren ett ark som är omöjligt att läsa."""
    ut = {}
    for f in sparade:
        nyckel = (f.get("namn", "").lower(), f.get("kategori", ""))
        if nyckel in ut:
            ut[nyckel]["antal"] = (float(ut[nyckel].get("antal") or 0)
                                   + float(f.get("antal") or 1))
            if ut[nyckel]["antal"] == int(ut[nyckel]["antal"]):
                ut[nyckel]["antal"] = int(ut[nyckel]["antal"])
            if f.get("sakerhet") == "osäker":
                ut[nyckel]["sakerhet"] = "osäker"
        else:
            ut[nyckel] = dict(f)
    return list(ut.values())


def moln_redo(cfg=None):
    """Är en molntjänst inställd? Returnerar (leverantör, nyckel) eller None."""
    ai_cfg = (cfg or {}).get("ai") or {}
    leverantor = (os.environ.get("VVS_AI_LEVERANTOR")
                  or ai_cfg.get("leverantor") or "").strip().lower()
    nyckel = (os.environ.get("VVS_AI_NYCKEL") or ai_cfg.get("nyckel") or "").strip()
    if leverantor in STANDARD_MODELLER and nyckel:
        return leverantor, nyckel
    return None


def _fraga_ollama(bild, modell, timeout):
    """Frågar den lokala Ollama. Returnerar (text, None) eller (None, fel)."""
    kropp = {"model": modell, "stream": False, "format": "json",
             "options": {"temperature": 0.1, "num_predict": 1500},
             # Håll modellen i minnet. Första anropet tar ~80 s (den laddas då),
             # sedan några sekunder. Utan detta hinner den somna mellan varven
             # och telefonen får vänta varje gång.
             "keep_alive": "30m",
             "messages": [{"role": "user", "content": SYSTEM, "images": [bild]}]}
    text, fel = _post_json(OLLAMA + "/api/chat", kropp, timeout)
    if fel:
        return None, {"fel": f"Kunde inte nå modellen: {fel}"}
    return ((text.get("message") or {}).get("content") or "").strip(), None


def _fraga_gemini(bild, modell, nyckel, bas_url, timeout):
    """Googles generateContent. Bilden skickas som inline_data."""
    # Nyckeln skickas som header, inte i adressen. I adressen hamnar den i
    # loggar och proxyservrar på vägen — det vill man inte med en API-nyckel.
    url = f"{bas_url}/models/{urllib.parse.quote(modell)}:generateContent"
    kropp = {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"role": "user", "parts": [
            {"text": "Inventera det som syns på bilden."},
            {"inline_data": {"mime_type": "image/jpeg", "data": bild}}]}],
        "generationConfig": {"temperature": 0.1,
                             "response_mime_type": "application/json"},
    }
    svar, fel = _post_json(url, kropp, timeout,
                           huvud={"x-goog-api-key": nyckel})
    if fel:
        return None, {"fel": f"Kunde inte nå molntjänsten: {fel}"}
    delar = (((svar.get("candidates") or [{}])[0].get("content") or {})
             .get("parts") or [])
    text = "".join(d.get("text", "") for d in delar).strip()
    if not text:
        blockat = (svar.get("promptFeedback") or {}).get("blockReason")
        return None, {"fel": f"Molntjänsten svarade inget"
                             f"{f' ({blockat})' if blockat else ''}."}
    return text, None


def _fraga_openai(bild, modell, nyckel, bas_url, timeout):
    """OpenAI-formatet. Fungerar även mot Mistral, Groq och lokala servrar —
    det är samma API, bara adressen skiljer."""
    kropp = {
        "model": modell,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": [
                {"type": "text", "text": "Inventera det som syns på bilden."},
                {"type": "image_url",
                 "image_url": {"url": "data:image/jpeg;base64," + bild}}]}],
    }
    svar, fel = _post_json(bas_url + "/chat/completions", kropp, timeout,
                           huvud={"Authorization": f"Bearer {nyckel}"})
    if fel:
        return None, {"fel": f"Kunde inte nå molntjänsten: {fel}"}
    val = (svar.get("choices") or [{}])[0].get("message") or {}
    return (val.get("content") or "").strip(), None


def _post_json(url, kropp, timeout, huvud=None):
    """POST med JSON. Returnerar (svar, None) eller (None, feltext)."""
    req = urllib.request.Request(url, data=json.dumps(kropp).encode("utf-8"),
                                 method="POST")
    req.add_header("content-type", "application/json")
    for nyckel, v in (huvud or {}).items():
        req.add_header(nyckel, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace")), None
    except urllib.error.HTTPError as exc:
        rå = exc.read().decode("utf-8", "replace")[:300]
        return None, f"tjänsten svarade {exc.code}: {rå}"
    except Exception as exc:                                   # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def analysera(sokvag, cfg=None, timeout=180):
    """Analyserar en bild och returnerar ett eller flera förslag.

    Använder molntjänsten om en sådan är inställd, annars Ollama lokalt.
    Returnerar alltid ett diktat: antingen
    {"forslag": [ {...}, ... ], "modell": ...} eller {"fel": "..."} med en
    förklaring som går att visa för användaren.
    """
    ai_cfg = (cfg or {}).get("ai") or {}
    moln = moln_redo(cfg)
    if moln:
        leverantor, nyckel = moln
        modell = (os.environ.get("VVS_AI_MODELL") or ai_cfg.get("modell")
                  or STANDARD_MODELLER[leverantor])
        bas_url = ((os.environ.get("VVS_AI_URL") or ai_cfg.get("url")
                    or STANDARD_URLAR[leverantor]).rstrip("/"))
    else:
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

    if moln:
        if leverantor == "gemini":
            text, fel = _fraga_gemini(bild, modell, nyckel, bas_url, timeout)
        else:
            text, fel = _fraga_openai(bild, modell, nyckel, bas_url, timeout)
    else:
        text, fel = _fraga_ollama(bild, modell, timeout)
    if fel:
        return fel

    data = _plocka_json(text)

    # Modellen kan svara med en lista, med {"foremal": [...]} eller — om den
    # är liten — med ett enda föremål. Alla tre ska bli en lista här.
    if isinstance(data, dict) and isinstance(data.get("foremal"), list):
        rå = data["foremal"]
    elif isinstance(data, dict) and isinstance(data.get("forslag"), list):
        rå = data["forslag"]
    elif isinstance(data, list):
        rå = data
    elif isinstance(data, dict):
        rå = [data]
    else:
        rå = []

    sparade = []
    for ett in rå[:20]:
        f = _stada(ett)
        if not f.get("namn"):
            continue                    # utan namn finns inget att inventera
        f.setdefault("antal", 1)
        f.setdefault("enhet", "st")
        f.setdefault("skick", "ok")
        sparade.append(f)

    if not sparade:
        return {"fel": "Modellen kunde inte avgöra vad bilden visar. "
                       "Skriv namnet själv — bilden sparas ändå.",
                "modell": modell, "text": text[:400]}

    forslag = _dubbletter(sparade)
    return {"forslag": forslag, "modell": modell, "antal_forslag": len(forslag)}


def varm(cfg=None, timeout=240):
    """Laddar in modellen i förväg.

    Första anropet tar omkring 80 sekunder eftersom modellen då läses in i
    minnet. Gör vi det när servern startar slipper den som fotar med telefonen
    sitta och vänta på det. Misslyckas det är det ingen fara — då laddas
    modellen vid första bilden i stället.

    Används en molntjänst behövs ingen förvärmning.
    """
    if moln_redo(cfg):
        return True
    modell = valj_modell(cfg)
    if not modell:
        return False
    kropp = {"model": modell, "stream": False, "keep_alive": "30m",
             "messages": [{"role": "user", "content": "ok"}]}
    req = urllib.request.Request(OLLAMA + "/api/chat",
                                 data=json.dumps(kropp).encode("utf-8"),
                                 method="POST")
    req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
    except Exception:
        return False
