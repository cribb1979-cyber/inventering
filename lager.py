"""Inventeringen — levande lager.

En post är ett föremål i VVS-verkstaden. Allt ligger i data/inventering.json
och varje ändring höjer en version, så att telefon och skrivbord kan se att
den andra ändrat något. Varje ändring skrivs också till en historik.
"""
import json
import math
import os
import threading
import time
import uuid

import stigar

# Inventeringsfilen. Ligger på den disk stigar pekar ut, så att den överlever
# en omstart när appen kör i molnet.
FIL = stigar.INVENTERING
# Låset skyddar en *hel* läs-ändra-skriv-sekvens, inte bara filen. Telefonen
# och datorn kan skriva samtidigt, och utan detta försvinner ändringar tyst:
# två trådar läser samma läge, båda ändrar, och den sista skriver över den
# första. Se _med_las nedan.
LÅS = threading.RLock()

KATEGORIER = [
    ("maskin", "Maskin"),
    ("verktyg", "Verktyg"),
    ("material", "Material"),
    ("inredning", "Inredning / bänk"),
    ("skydd", "Skyddsutrustning"),
    ("forbrukning", "Förbrukning"),
    ("annat", "Annat"),
]
KATEGORI_ID = [k for k, _ in KATEGORIER]

SKICK = [
    ("ok", "Fungerar"),
    ("service", "Behöver service"),
    ("trasig", "Trasig"),
    ("utlånad", "Utlånad"),
    ("borta", "Saknas"),
]

# Bedömningen som inventeringen ska leda fram till: var behöver vi investera?
# Samma värden som kalkylarket skriver i kolumnen Investeringsbehov.
BEHOV = [
    ("behall", "Behåll"),
    ("investera", "Investera"),
    ("avveckla", "Avveckla"),
    ("vetej", "Vet ej"),
]

PRIORITET = [
    ("hog", "Hög"),
    ("medel", "Medel"),
    ("lag", "Låg"),
]

# fält som får sättas av klienten, med sin typ
FALT = {
    "namn": str, "kategori": str, "antal": float, "enhet": str,
    "placering": str, "inkopsar": str, "skick": str, "dimension": str,
    "tillverkare": str, "anteckning": str, "bild": str, "serienummer": str,
    "program": str, "investeringsbehov": str, "prioritet": str, "pris": float,
}

# fält som bara får ha vissa värden
ETT_AV = {"kategori": KATEGORI_ID, "skick": [k for k, _ in SKICK],
          "investeringsbehov": [k for k, _ in BEHOV],
          "prioritet": [k for k, _ in PRIORITET]}


def _tomt_lager():
    return {"version": 1, "poster": [], "logg": []}


def las():
    with LÅS:
        try:
            with open(FIL, encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict) or "poster" not in data:
                return _tomt_lager()
            data.setdefault("version", 1)
            data.setdefault("logg", [])
            return data
        except FileNotFoundError:
            return _tomt_lager()
        except Exception:
            # trasig fil: lägg undan den i stället för att skriva över beviset
            try:
                os.replace(FIL, FIL + ".trasig-" + time.strftime("%Y%m%d-%H%M%S"))
            except Exception:
                pass
            return _tomt_lager()


def spara(data, handling, text=""):
    """Skriver lagret, höjer versionen och lägger en rad i historiken."""
    with LÅS:
        data["version"] = int(data.get("version", 1)) + 1
        data.setdefault("logg", [])
        data["logg"].append({"tid": time.strftime("%Y-%m-%d %H:%M:%S"),
                             "handling": handling, "text": text[:300]})
        data["logg"] = data["logg"][-500:]
        os.makedirs(os.path.dirname(FIL), exist_ok=True)
        tmp = FIL + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, FIL)
        return data


def _tal(v):
    """Gör om ett värde till ett ändligt tal. Kastar ValueError annars.

    "nan" och "oändligt" måste stoppas här. Annars blir antalet NaN, och då
    nollas posten och märks "Saknas" — utan att någon förstår varför.
    """
    if isinstance(v, bool):
        raise ValueError("värdet måste vara ett tal")
    if isinstance(v, (int, float)):
        t = float(v)
    else:
        # "18 500", "1 250,50" och "1,250.50" ska alla bli tal. Vanligt
        # mellanslag och hårt mellanslag är tusentalsavgränsare.
        text = (str(v).replace("\u00a0", "").replace("\u202f", "")
                .replace(" ", "").replace("kr", "").replace(":-", "").strip())
        # Den avgränsare som står sist är decimaltecknet — de andra tusental.
        if "." in text and "," in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(",", ".")
        t = float(text)                   # ValueError om det inte är ett tal
    if not math.isfinite(t):
        raise ValueError("talet är inte ett vanligt tal")
    return t


def _stada_falt(kropp, ny=False):
    """Plockar ut kända fält och gör om antal till ett vettigt tal."""
    ut = {}
    for nyckel, typ in FALT.items():
        if nyckel not in kropp:
            continue
        v = kropp[nyckel]
        if typ is float:
            try:
                v = _tal(v)
            except (TypeError, ValueError):
                v = 0
            if v < 0:
                v = 0
            if v == int(v):
                v = int(v)
        else:
            v = "" if v is None else str(v).strip()[:300]
        ut[nyckel] = v
    if ny and "namn" not in ut:
        raise ValueError("namn saknas")
    for nyckel, giltiga in ETT_AV.items():
        if nyckel in ut and ut[nyckel] and ut[nyckel] not in giltiga:
            ut.pop(nyckel)              # hellre tomt än ett påhittat värde
    return ut


def ny(kropp):
    """Lägger till ett föremål. Antal 1 om inget anges."""
    # Hela läs-ändra-skriv-sekvensen under låset. Annars kan två
    # samtidiga ändringar läsa samma läge och den ena försvinna.
    with LÅS:
        data = las()
        falt = _stada_falt(kropp, ny=True)
        falt.setdefault("kategori", "annat")
        falt.setdefault("skick", "ok")
        falt.setdefault("antal", 1)
        falt.setdefault("enhet", "st")
        nu = time.strftime("%Y-%m-%d %H:%M")
        post = {"id": uuid.uuid4().hex[:8], "skapad": nu, "andrad": nu, **falt}
        data["poster"].append(post)
        spara(data, "ny", f"{post['namn']} ({post.get('kategori')})")
        return post


def andra(pid, kropp):
    """Ändrar angivna fält på ett föremål. Övriga rörs inte."""
    # Hela läs-ändra-skriv-sekvensen under låset. Annars kan två
    # samtidiga ändringar läsa samma läge och den ena försvinna.
    with LÅS:
        data = las()
        for post in data["poster"]:
            if post["id"] == pid:
                falt = _stada_falt(kropp)
                ändrade = {k: (post.get(k, ""), v) for k, v in falt.items()
                           if post.get(k) != v}
                if not ändrade:
                    return post
                post.update({k: nytt for k, (_, nytt) in ändrade.items()})
                post["andrad"] = time.strftime("%Y-%m-%d %H:%M")
                beskriv = ", ".join(f"{k}: {gammalt or '–'}→{nytt or '–'}"
                                    for k, (gammalt, nytt) in ändrade.items())
                spara(data, "andra", f"{post['namn']}: {beskriv}")
                return post
        raise KeyError(pid)


def rakna(pid, delta):
    """Räknar av eller lägger till. Används när något förbrukas eller köps in.

    Går aldrig under noll, och en förbrukad post blir 'borta' automatiskt så
    att den syns i stället för att tyst försvinna."""
    # Hela läs-ändra-skriv-sekvensen under låset. Annars kan två
    # samtidiga ändringar läsa samma läge och den ena försvinna.
    with LÅS:
        data = las()
        tal = _tal(delta)               # stoppar nan och oändligt
        for post in data["poster"]:
            if post["id"] == pid:
                före = float(post.get("antal") or 0)
                efter = max(0.0, före + tal)
                if efter == int(efter):
                    efter = int(efter)
                post["antal"] = efter
                post["andrad"] = time.strftime("%Y-%m-%d %H:%M")
                if efter == 0 and post.get("skick") == "ok":
                    post["skick"] = "borta"
                elif efter > 0 and post.get("skick") == "borta":
                    post["skick"] = "ok"
                spara(data, "rakna", f"{post['namn']}: {före:g} → {efter:g} "
                                     f"({'+' if tal > 0 else ''}{tal:g})")
                return post
        raise KeyError(pid)


def radera(pid):
    # Hela läs-ändra-skriv-sekvensen under låset. Annars kan två
    # samtidiga ändringar läsa samma läge och den ena försvinna.
    with LÅS:
        data = las()
        för = len(data["poster"])
        bort = [p for p in data["poster"] if p["id"] == pid]
        data["poster"] = [p for p in data["poster"] if p["id"] != pid]
        if len(data["poster"]) == för:
            raise KeyError(pid)
        spara(data, "radera", bort[0]["namn"] if bort else pid)
        return bort[0] if bort else {}


def lista():
    data = las()
    poster = sorted(data["poster"],
                    key=lambda p: (p.get("kategori") or "", (p.get("namn") or "").lower()))
    return {"version": data["version"], "poster": poster,
            "kategorier": KATEGORIER, "skick": SKICK,
            "behov": BEHOV, "prioritet": PRIORITET,
            "antal_poster": len(poster),
            "summa_antal": sum(float(p.get("antal") or 0) for p in poster)}


def logg(antal=60):
    return las()["logg"][-antal:][::-1]
