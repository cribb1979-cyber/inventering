"""SYS.VVS — inventering av VVS-verkstaden.

Två saker skiljer den här servern från de andra apparna i ~/:
  1) Den lyssnar på nätet (0.0.0.0) så att telefonen kommer åt den, inte bara
     på 127.0.0.1. Därför krävs en token för allt som kommer utifrån —
     skolnätet är delat och appen får inte vara öppen för vem som helst.
  2) Bilder sparas och analyseras lokalt. Ingenting lämnar datorn.
"""
import base64
import io
import json
import os
import re
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ai
import epost
import kalkyl
import lager
import stigar

# QR-koden ritas med qrcode-paketet. Det är ren Python utan beroenden, men
# ligger ändå inte i standardbiblioteket — och på en server är det bygget, inte
# koden, som avgör om det finns. Vi prövar en gång vid start i stället för att
# hoppas: går det inte, säger appen det rakt ut i stället för att visa en tom
# ruta. Se också kontrollen i render.yaml, som stoppar bygget i stället.
try:
    import qrcode
    import qrcode.image.svg
    QR_OK = True
except Exception as _qr_fel:                                     # noqa: BLE001
    QR_OK = False
    _QR_FEL = f"{type(_qr_fel).__name__}: {_qr_fel}"

# Sökvägarna kommer från stigar.py, så att de går att flytta till en monterad
# disk med VVS_DATA när appen kör i molnet.
HERE = stigar.HERE
DATA = stigar.DATA
BILDER = stigar.BILDER
EXPORT = stigar.EXPORT
CONFIG = stigar.CONFIG
PORT = int(os.environ.get("VVS_PORT") or os.environ.get("PORT") or "8792")
MAX_KROPP = 30 * 1024 * 1024          # telefonbilder är stora men inte så stora
LOKALA = {"127.0.0.1", "::1"}

# I molnet kommer varje besök via plattformens proxyserver. Om den ansluter
# från 127.0.0.1 ser appen alla besök som "lokala" och släpper in dem utan
# token — autentiseringen skulle vara avstängd utan att någon märkte det.
# Sätt VVS_KRAV_TOKEN=1 på en server så krävs token även från 127.0.0.1.
KRAV_TOKEN_ALLA = os.environ.get("VVS_KRAV_TOKEN", "") not in ("", "0", "nej")


def _qr_utan_kod():
    """En liten bild som förklarar varför QR-koden inte syns.

    Skickas i samma ruta där koden skulle ha varit, så att rutan aldrig blir
    tyst tom — den säger vad man gör i stället.
    """
    from xml.sax.saxutils import escape as _esc
    rader = ["QR-koden kan inte ritas här.",
             "Skriv in adressen nedan i telefonen."]
    text = "".join(
        f'<text x="95" y="{88 + i * 19}" text-anchor="middle" '
        f'font-family="-apple-system,system-ui,sans-serif" font-size="11.5" '
        f'fill="#5b6672">{_esc(r)}</text>' for i, r in enumerate(rader))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="190" height="190" '
            f'viewBox="0 0 190 190"><rect width="190" height="190" fill="#fff"/>'
            f'{text}</svg>').encode("utf-8")


def lan_ip():
    """Datorns adress på nätet, den telefonen ska använda."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))      # kräver ingen trafik, ger bara rätt interface
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


# Nycklar som satts via miljövariabler, t.ex. på en server. Läses om vid varje
# las_config(). Det är ingen kapplöpning mellan trådarna: värdet byggs bara av
# miljövariablerna, och de ändras inte medan programmet kör. Alla trådar
# räknar alltså fram exakt samma sak.
FRAN_MILJO = {}

# Bara de här fälten är hemliga och får aldrig skrivas till disk *när de
# kommer från miljön*. Övriga värden från miljön (skola, program, mottagare)
# sparas som vanligt — annars försvinner användarens ändring tyst när hen
# trycker Spara i appen, och det är ett värre fel än det skyddet skulle lösa.
HEMLIGA = (("token",), ("ai", "nyckel"), ("mejl", "losenord"))


def _utan_hemliga(cfg):
    """Kopia av cfg där hemligheter *som satts via miljön* är borttagna.

    En token som appen själv har skapat måste däremot sparas — annars blir den
    en ny varje gång servern startar och telefonens bokmärke slutar fungera.
    """
    rent = {k: (dict(v) if isinstance(v, dict) else v) for k, v in cfg.items()}
    for vag in HEMLIGA:
        topp = vag[0]
        if topp not in FRAN_MILJO:
            continue
        if len(vag) == 1:
            rent.pop(topp, None)
            continue
        # Bara den del som verkligen kom från miljön, inte hela gruppen.
        if vag[1] not in (FRAN_MILJO.get(topp) or {}):
            continue
        under = rent.get(topp)
        if isinstance(under, dict):
            under.pop(vag[1], None)
            if not under:
                rent.pop(topp, None)
    return rent


def miljo_overstyrning():
    """Inställningar från miljövariabler.

    På en server (Render, en VPS) får hemligheterna inte ligga i en fil i
    kodträdet. Miljövariabler vinner därför över config.json. Lokalt är de
    tomma och då gäller filen precis som förut.

    VVS_TOKEN, VVS_SKOLA, VVS_PROGRAM, VVS_ANSVARIG, VVS_DEADLINE,
    VVS_MEJL_<ADRESS|NAMN|SMTP_SERVER|SMTP_PORT|LOSENORD>, VVS_AI_<NYCKEL|MODELL|URL|LEVERANTOR>
    """
    ut = {}
    for nyckel, namn in (("token", "VVS_TOKEN"), ("skola", "VVS_SKOLA"),
                         ("program", "VVS_PROGRAM"), ("ansvarig", "VVS_ANSVARIG"),
                         ("deadline", "VVS_DEADLINE")):
        v = os.environ.get(namn)
        if v:
            ut[nyckel] = v
    ai = {}
    for nyckel, namn in (("nyckel", "VVS_AI_NYCKEL"), ("modell", "VVS_AI_MODELL"),
                         ("url", "VVS_AI_URL"), ("leverantor", "VVS_AI_LEVERANTOR")):
        v = os.environ.get(namn)
        if v:
            ai[nyckel] = v
    if ai:
        ut["ai"] = ai
    mejl = {}
    for nyckel, namn in (("adress", "VVS_MEJL_ADRESS"), ("namn", "VVS_MEJL_NAMN"),
                         ("smtp_server", "VVS_MEJL_SMTP_SERVER"),
                         ("smtp_port", "VVS_MEJL_SMTP_PORT"),
                         ("losenord", "VVS_MEJL_LOSENORD")):
        v = os.environ.get(namn)
        if v:
            mejl[nyckel] = v
    if mejl:
        ut["mejl"] = mejl
    return ut


def las_config():
    # Miljövariablerna läses först, så att skriv_config längre ner vet vad som
    # kom från miljön och alltså inte får sparas på disk.
    global FRAN_MILJO
    FRAN_MILJO = miljo_overstyrning()
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    ändrad = False
    if not cfg.get("token") and not os.environ.get("VVS_TOKEN"):
        cfg["token"] = secrets.token_urlsafe(16)
        ändrad = True
    cfg.setdefault("port", PORT)
    cfg.setdefault("ai", {"modell": ""})
    for nyckel, tomt in (("skola", ""), ("program", ""), ("ansvarig", ""),
                         ("deadline", standard_deadline())):
        if nyckel not in cfg:
            cfg[nyckel] = tomt
            ändrad = True
    if ändrad:
        skriv_config(cfg)
    # Miljövariablerna sist, så att de alltid gäller.
    for nyckel, v in FRAN_MILJO.items():
        if nyckel in ("mejl", "ai"):
            cfg[nyckel] = {**(cfg.get(nyckel) or {}), **v}
        else:
            cfg[nyckel] = v
    return cfg


def standard_deadline():
    """Tisdagen i vecka 43 — då VVS-lärarna träffas. Går att ändra i appen."""
    import datetime
    i_dag = datetime.date.today()
    return datetime.date.fromisocalendar(i_dag.isocalendar()[0], 43, 2).isoformat()


def deadline_text(varde):
    """'2026-10-20' -> 'tisdag 20 okt (v43)'"""
    import datetime
    if not varde:
        return ""
    try:
        d = datetime.date.fromisoformat(str(varde)[:10])
    except ValueError:
        return str(varde)
    dagar = ("måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag")
    månad = ("jan", "feb", "mars", "apr", "maj", "juni", "juli", "aug", "sep",
             "okt", "nov", "dec")
    return (f"{dagar[d.weekday()]} {d.day} {månad[d.month-1]} "
            f"(v{d.isocalendar()[1]})")


def dagar_kvar(varde):
    import datetime
    try:
        d = datetime.date.fromisoformat(str(varde)[:10])
    except (ValueError, TypeError):
        return None
    return (d - datetime.date.today()).days


def ark_meta(cfg):
    """Rubrikblocket som följer med i kalkylarket."""
    return {"skola": cfg.get("skola") or "", "program": cfg.get("program") or "",
            "ansvarig": cfg.get("ansvarig") or "",
            "deadline": deadline_text(cfg.get("deadline"))}


def skriv_config(cfg):
    """Skriver config.json — men aldrig token eller lösenord.

    Allt annat sparas, även om det också finns i miljön. Miljövariabeln gäller
    ändå när appen läser (se las_config), men filen får innehålla det
    användaren själv skrev in.
    """
    rent = _utan_hemliga(cfg)
    mapp = os.path.dirname(CONFIG)
    if mapp:
        os.makedirs(mapp, exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(rent, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, CONFIG)
    try:
        os.chmod(CONFIG, 0o600)
    except OSError:
        pass


def _utan_fragedel(a):
    """Tar bort ?… ur en rad som ska loggas, så att nyckeln inte skrivs ut."""
    if not isinstance(a, str) or "?" not in a:
        return a
    i = a.find("?")
    j = a.find(" ", i)
    return a[:i] + (a[j:] if j > -1 else "")


class Svar(BaseHTTPRequestHandler):
    server_version = "SYS.VVS/1.0"
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- hjälpare
    def log_message(self, fmt, *args):
        """Bara avvikelser loggas — annars dränks allt av /api/status.

        Frågedelen klipps bort med flit. QR-koden hämtas med nyckeln i
        adressen (?t=…), och den har inte i en loggfil att göra — varken på
        datorn eller i molnet."""
        if self.path.startswith("/api/status") or self.path.startswith("/bilder/"):
            return
        sys.stderr.write("%s - %s\n" % (
            self.address_string(),
            fmt % tuple(_utan_fragedel(a) for a in args)))

    def _send(self, kod, kropp, typ="application/json; charset=utf-8", extra=None):
        if isinstance(kropp, str):
            kropp = kropp.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(kropp)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for n, v in (extra or {}).items():
            self.send_header(n, v)
        self.end_headers()
        try:
            self.wfile.write(kropp)
        except (BrokenPipeError, ConnectionResetError):
            pass                       # klienten hann stänga, inte vårt problem

    def _json(self, kod, obj):
        self._send(kod, json.dumps(obj, ensure_ascii=False))

    def _fel(self, kod, text):
        self._json(kod, {"fel": text})

    def _kropp(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        if n > MAX_KROPP:
            raise ValueError(f"för stor förfrågan ({n // 1024 // 1024} MB)")
        rå = self.rfile.read(n)
        try:
            return json.loads(rå.decode("utf-8"))
        except Exception:
            raise ValueError("ogiltig JSON")

    def _lokal(self):
        """Är anropet från själva datorn? Alltid nej om VVS_KRAV_TOKEN är satt."""
        if KRAV_TOKEN_ALLA:
            return False
        return self.client_address[0] in LOKALA

    def _bas_url(self):
        """Adressen telefonen ska öppna — rätt adress, på rätt plats.

        Bakom en proxy (Render m.fl.) kommer den riktiga adressen och
        protokollet i X-Forwarded-*. Att i stället gissa på datorns
        nätverksadress vore fel: i molnet finns ingen sådan adress, och den
        QR-kod man då fick pekade på en intern maskin som telefonen inte når.

        Lokalt finns inga X-Forwarded-huvuden alls, och då gäller datorns
        adress på nätet precis som förut.
        """
        proxad = (self.headers.get("X-Forwarded-Host")
                  or self.headers.get("X-Forwarded-Proto"))
        if proxad:
            # Proxyn kan skicka en kommaseparerad lista; den första gäller.
            namn = (self.headers.get("X-Forwarded-Host")
                    or self.headers.get("Host") or "").split(",")[0].strip()
            schema = (self.headers.get("X-Forwarded-Proto")
                      or "https").split(",")[0].strip()
            if namn:
                return f"{schema}://{namn}"
        return f"http://{lan_ip()}:{PORT}"

    def _autentiserad(self):
        """Lokala anrop släpps igenom utan token, allt annat kräver rätt token."""
        if self._lokal():
            return True
        cfg = las_config()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        given = (q.get("t") or [None])[0] or self.headers.get("X-Token") or ""
        return secrets.compare_digest(str(given), str(cfg.get("token") or "-"))

    def _logg(self, handling, text=""):
        try:
            with open(os.path.join(DATA, "logg.jsonl"), "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"tid": time.strftime("%Y-%m-%d %H:%M:%S"),
                                     "handling": handling, "text": text[:200]},
                                    ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ---------------------------------------------------------------- GET
    def do_HEAD(self):
        """Svar på HEAD. Render kollar att tjänsten lever med HEAD /, och utan
        den här metoden svarade servern 501 — vilket i driftsloggen ser ut som
        ett fel, fast allt var bra."""
        v = urllib.parse.urlparse(self.path).path
        self.send_response(200 if v in ("/", "/index.html") else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        v = u.path
        if v in ("/", "/index.html"):
            # Rubriken talar om ifall QR-koden kan ritas på den här servern.
            # Den är publik med flit: det är den enda upplysning som går att få
            # utan token, och den avslöjar ingenting om inventeringen.
            self._send(200, self._fil("index.html"), "text/html; charset=utf-8",
                       {"X-SYSVVS-QR": "ja" if QR_OK else "nej"})
            return
        if v.startswith("/bilder/"):
            self._bildfil(v)
            return
        if not self._autentiserad():
            self._fel(401, "ogiltig eller saknad token")
            return
        try:
            if v == "/api/status":
                cfg = las_config()
                self._json(200, {"version": lager.las()["version"],
                                 "mobil": self._bas_url(),
                                 "lokal": f"http://127.0.0.1:{PORT}",
                                 "token": cfg["token"],
                                 "bildmodell": ai.valj_modell(cfg) or ai.molnmodell(cfg),
                                 "standard_modell": ai.STANDARD_MODELL,
                                 "modeller": ai.tillgangliga(),
                                 "molntjanst": (ai.moln_inst(cfg) or {}).get("leverantor") or "",
                                 "skola": cfg.get("skola") or "",
                                 "program": cfg.get("program") or "",
                                 "ansvarig": cfg.get("ansvarig") or "",
                                 "deadline": deadline_text(cfg.get("deadline")),
                                 "dagar_kvar": dagar_kvar(cfg.get("deadline")),
                                 "epost": epost.ar_redo(),
                                 "tid": time.strftime("%H:%M:%S")})
                return
            if v == "/api/lista":
                cfg = las_config()
                d = lager.lista()
                d["bildmodell"] = ai.valj_modell(cfg) or ai.molnmodell(cfg)
                self._json(200, d)
                return
            if v == "/api/ai-koll":
                self._ai_koll()
                return
            if v == "/api/logg":
                self._json(200, {"logg": lager.logg(80)})
                return
            if v == "/api/qr":
                self._qr()
                return
            if v == "/api/installningar":
                cfg = las_config()
                self._json(200, {"skola": cfg.get("skola") or "",
                                 "program": cfg.get("program") or "",
                                 "ansvarig": cfg.get("ansvarig") or "",
                                 "deadline": (cfg.get("deadline") or "")[:10],
                                 "deadline_text": deadline_text(cfg.get("deadline")),
                                 "dagar_kvar": dagar_kvar(cfg.get("deadline")),
                                 "standard_deadline": standard_deadline(),
                                 "epost_redo": epost.ar_redo(),
                                 "min_adress": epost.las_konto().get("adress", ""),
                                 # färdigt brev, en källa: samma text som servern
                                 # använder om klienten inte skickar med någon
                                 "standardbrev": epost.standardbrev(
                                     ark_meta(cfg), len(lager.las()["poster"]),
                                     deadline_text(cfg.get("deadline")))})
                return
            if v == "/api/kalkyl":
                self._kalkyl(u)
                return
        except Exception as exc:                                # noqa: BLE001
            self._fel(500, f"{type(exc).__name__}: {exc}")
            return
        self._fel(404, "finns inte")

    def _ai_koll(self):
        """Svarar på vad bildanalysen använder — och vad som är fel om något är det.

        Frågar molntjänsten vilka modeller nyckeln får använda. Nyckeln själv
        lämnar aldrig servern; svaret säger bara om den finns."""
        cfg = las_config()
        inst = ai.moln_inst(cfg)
        if not inst:
            self._json(200, {"leverantor": "ollama (lokalt)",
                             "modell": ai.valj_modell(cfg),
                             "modeller": ai.tillgangliga(),
                             "fel": "" if ai.valj_modell(cfg) else
                                    "ingen lokal bildmodell hittad",
                             "nyckel": "nej"})
            return
        lista, fel = ai.lista_modeller(inst)
        svar = {"leverantor": inst["leverantor"],
                "modell": inst["modell"],
                "anvand_modell": ai.molnmodell(cfg),
                "nyckel": "ja",
                "antal_modeller": len(lista),
                "modeller": lista[:40],
                "vald_av_listan": ai.valj_bildmodell(lista, inst["leverantor"]),
                "fel": fel or ""}
        self._json(200, svar)

    def _fil(self, namn):
        with open(os.path.join(HERE, namn), "rb") as fh:
            return fh.read()

    def _bildfil(self, v):
        """Bilder kräver token även lokalt — de kan visa skolans lokaler."""
        namn = os.path.basename(v)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", namn or ""):
            self._fel(400, "ogiltigt filnamn")
            return
        cfg = las_config()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        given = (q.get("t") or [None])[0] or self.headers.get("X-Token") or ""
        if not (self._lokal()
                or secrets.compare_digest(str(given), str(cfg.get("token")))):
            self._fel(401, "ogiltig token")
            return
        stig = os.path.join(BILDER, namn)
        if not os.path.isfile(stig):
            self._fel(404, "bilden finns inte")
            return
        typ = "image/png" if namn.endswith(".png") else "image/jpeg"
        with open(stig, "rb") as fh:
            self._send(200, fh.read(), typ, {"Cache-Control": "max-age=3600"})

    def _qr(self):
        """QR-kod till telefonens adress, så man slipper skriva in den.

        Skrivs som SVG i stället för PNG. Då räcker qrcode-paketet, som är ren
        Python utan beroenden — Pillow behövs inte, och det är just Pillow som
        saknas på en server. Bilden blir dessutom skarp i alla storlekar.

        Går det inte att rita koden svarar vi ändå med en bild — en som säger
        vad som är fel. En tom ruta går inte att skilja från "inget hände",
        och då får man leta i blindo.
        """
        if not QR_OK:
            print(f"QR: qrcode-modulen saknas ({_QR_FEL})", file=sys.stderr, flush=True)
            self._send(200, _qr_utan_kod(), "image/svg+xml")
            return
        try:
            cfg = las_config()
            url = f"{self._bas_url()}/?t={urllib.parse.quote(cfg['token'])}"
            img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage,
                              box_size=12, border=3)
            buf = io.BytesIO()
            img.save(buf)
        except Exception as exc:                                  # noqa: BLE001
            print(f"QR: kunde inte rita koden ({type(exc).__name__}: {exc})",
                  file=sys.stderr, flush=True)
            self._send(200, _qr_utan_kod(), "image/svg+xml")
            return
        self._send(200, buf.getvalue(), "image/svg+xml")

    def _kalkyl(self, u):
        q = urllib.parse.parse_qs(u.query)
        fmt = ((q.get("format") or ["xlsx"])[0] or "xlsx").lower()
        poster = lager.las()["poster"]
        if not poster:
            self._fel(400, "inventeringen är tom")
            return
        namn = time.strftime("inventering-%Y-%m-%d")
        meta = ark_meta(las_config())
        if fmt == "csv":
            try:
                data = kalkyl.csv_bytes(poster, meta)
            except Exception as exc:                            # noqa: BLE001
                self._fel(500, f"kunde inte bygga kalkylarket: {exc}")
                return
            self._logg("export", "csv")
            self._send(200, data, "text/csv; charset=utf-8",
                       {"Content-Disposition": f'attachment; filename="{namn}.csv"'})
            return
        try:
            xs, _ = kalkyl.skriv(poster, EXPORT, meta, namn)
        except Exception as exc:                                # noqa: BLE001
            self._fel(500, f"kunde inte skriva kalkylarket: {exc}")
            return
        self._logg("export", f"xlsx {xs}")
        with open(xs, "rb") as fh:
            self._send(200, fh.read(),
                       "application/vnd.openxmlformats-officedocument."
                       "spreadsheetml.sheet",
                       {"Content-Disposition": f'attachment; filename="{namn}.xlsx"'})

    # ---------------------------------------------------------------- POST
    def do_POST(self):
        v = urllib.parse.urlparse(self.path).path
        if not self._autentiserad():
            self._fel(401, "ogiltig eller saknad token")
            return
        try:
            kropp = self._kropp()
        except ValueError as exc:
            self._fel(400, str(exc))
            return
        try:
            self._rutter(v, kropp)
        except KeyError as exc:
            self._fel(404, f"posten finns inte: {exc}")
        except ValueError as exc:
            self._fel(400, str(exc))
        except Exception as exc:                                # noqa: BLE001
            self._fel(500, f"{type(exc).__name__}: {exc}")

    def _rutter(self, v, kropp):
        if v == "/api/ny":
            if not kropp.get("program"):        # ärvs från inställningarna
                program = (las_config().get("program") or "").strip()
                if program:
                    kropp = dict(kropp, program=program)
            post = lager.ny(kropp)
            self._logg("ny", post.get("namn", ""))
            self._json(200, {"post": post, "version": lager.las()["version"]})
            return
        if v == "/api/andra":
            pid = kropp.get("id") or ""
            post = lager.andra(pid, kropp)
            self._logg("andra", post.get("namn", ""))
            self._json(200, {"post": post, "version": lager.las()["version"]})
            return
        if v == "/api/rakna":
            pid = kropp.get("id") or ""
            post = lager.rakna(pid, float(kropp.get("delta") or 0))
            self._json(200, {"post": post, "version": lager.las()["version"]})
            return
        if v == "/api/radera":
            if not kropp.get("bekrafta"):
                self._fel(400, "radering kräver bekrafta: true")
                return
            bort = lager.radera(kropp.get("id") or "")
            self._logg("radera", bort.get("namn", ""))
            self._json(200, {"bort": bort, "version": lager.las()["version"]})
            return
        if v == "/api/bild":
            self._bild(kropp)
            return
        if v == "/api/installningar":
            self._spara_installningar(kropp)
            return
        if v == "/api/skicka":
            self._skicka(kropp)
            return
        self._fel(404, "finns inte")

    def _spara_installningar(self, kropp):
        cfg = las_config()
        for nyckel in ("skola", "program", "ansvarig", "deadline"):
            if nyckel in kropp:
                cfg[nyckel] = str(kropp[nyckel] or "").strip()[:200]
        if kropp.get("ai_modell") is not None:
            cfg.setdefault("ai", {})["modell"] = str(kropp["ai_modell"] or "").strip()
        skriv_config(cfg)
        self._logg("installningar", f"{cfg.get('skola')} / {cfg.get('program')}")
        self._json(200, {"ok": True, "deadline_text": deadline_text(cfg.get("deadline")),
                         "dagar_kvar": dagar_kvar(cfg.get("deadline"))})

    def _skicka(self, kropp):
        """Skickar kalkylarket som bilaga. Kräver ett uttryckligt bekrafta."""
        if not kropp.get("bekrafta"):
            self._fel(400, "utskick kräver bekrafta: true")
            return
        till = str(kropp.get("till") or "").strip()
        poster = lager.las()["poster"]
        if not poster:
            self._fel(400, "inventeringen är tom — ingenting att skicka")
            return
        cfg = las_config()
        meta = ark_meta(cfg)
        bas = time.strftime("inventering-%Y-%m-%d")
        try:
            xs, _ = kalkyl.skriv(poster, EXPORT, meta, bas)
        except Exception as exc:                                # noqa: BLE001
            self._fel(500, f"kunde inte skriva kalkylarket: {exc}")
            return
        amne = kropp.get("amne") or (
            f"Inventering {meta.get('program') or 'VVS'} — "
            f"{time.strftime('%Y-%m-%d')}")
        text = kropp.get("text") or epost.standardbrev(meta, len(poster),
                                                      meta.get("deadline"))
        svar = epost.skicka(till, amne, text, [(xs, os.path.basename(xs))])
        if svar.get("fel"):
            self._logg("skicka_fel", svar["fel"][:150])
            self._json(200, svar)
            return
        self._logg("skicka", f"{till} ({len(poster)} poster)")
        svar["fil"] = os.path.basename(xs)
        svar["poster"] = len(poster)
        svar["till"] = till
        self._json(200, svar)

    def _bild(self, kropp):
        """Tar emot en bild från telefonen, sparar den och föreslår ett föremål."""
        data = kropp.get("bild") or ""
        m = re.match(r"data:image/(jpeg|jpg|png|webp);base64,(.*)$", data, re.S)
        if not m:
            self._fel(400, "bilden saknas eller har okänt format")
            return
        ändelse, b64 = ("jpg" if m.group(1) in ("jpeg", "jpg") else m.group(1)), m.group(2)
        try:
            rå = base64.b64decode(b64)
        except Exception:
            self._fel(400, "kunde inte avkoda bilden")
            return
        if not rå:
            self._fel(400, "bilden är tom")
            return
        os.makedirs(BILDER, exist_ok=True)
        namn = "%s-%s.%s" % (time.strftime("%Y%m%d-%H%M%S"),
                             secrets.token_hex(3), ändelse)
        stig = os.path.join(BILDER, namn)
        with open(stig, "wb") as fh:
            fh.write(rå)
        self._logg("bild", f"{namn} ({len(rå)//1024} kB)")

        svar = ai.analysera(stig, las_config())
        svar["fil"] = namn
        svar["kb"] = len(rå) // 1024
        forslag = svar.get("forslag") or []
        if forslag:
            namnlista = ", ".join(f.get("namn", "?") for f in forslag[:6])
            self._logg("analys", f"{namn}: {len(forslag)} st — {namnlista}")
        elif svar.get("fel"):
            self._logg("analys_fel", svar["fel"][:150])
        self._json(200, svar)


def main():
    stigar.se_till_att_mappar_finns()
    cfg = las_config()
    modell = ai.valj_modell(cfg)
    moln = bool(os.environ.get("RENDER") or os.environ.get("VVS_KRAV_TOKEN"))
    print("SYS.VVS — inventering av VVS-verkstaden")
    print(f"  här    : {HERE}")
    print(f"  data   : {DATA}")
    print(f"  lyssnar: 0.0.0.0:{PORT}")
    if moln:
        # Inte token i klartext i serverloggen — loggen kan läsas av fler.
        print(f"  läge   : moln (token krävs, längd {len(cfg.get('token') or '')})")
    else:
        print(f"  datorn : http://127.0.0.1:{PORT}")
        print(f"  mobil  : http://{lan_ip()}:{PORT}/?t={cfg['token']}")
    if modell:
        print(f"  bild-AI: {modell}")
    elif ai.moln_inst(cfg):
        # I molnet finns ingen Ollama. Namnet valideras inte här — det görs
        # vid första bilden, och då byts ett dött namn ut automatiskt.
        print(f"  bild-AI: {ai.molnmodell(cfg)} hos {ai.moln_inst(cfg)['leverantor']} (moln)")
    else:
        print(f"  bild-AI: ingen bildmodell — hämta med: ollama pull {ai.STANDARD_MODELL}")
    print(f"  poster : {len(lager.las()['poster'])} i inventeringen")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Svar)
    srv.daemon_threads = True

    # Värm bildmodellen i bakgrunden. Den som fotar med telefonen ska inte
    # behöva vänta på att modellen laddas in första gången.
    if modell and not ai.moln_inst(cfg):
        def _varm():
            t0 = time.time()
            if ai.varm(cfg):
                print(f"  modellen är inläst ({time.time() - t0:.0f} s)")
            else:
                print("  kunde inte läsa in modellen i förväg")
        threading.Thread(target=_varm, daemon=True).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstänger")


if __name__ == "__main__":
    main()
