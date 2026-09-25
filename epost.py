"""Skicka kalkylarket till ansvarig yrkeslärare.

E-postkontot läses ur appens egen config.json (nyckeln "mejl"). Finns inget
där tittar vi i SYS.ASSISTs konfiguration, så att den som redan har satt upp
ett konto där slipper fylla i det igen. Ingenting skickas förrän någon
trycker Skicka — samma regel som i resten av huset.
"""
import email.utils
import json
import os
import smtplib
import ssl
import time
from email.message import EmailMessage

HERE = os.path.dirname(os.path.abspath(__file__))
EGEN_CFG = os.path.join(HERE, "config.json")
ASSISTENT_CFG = os.path.expanduser("~/assistent/config.json")


def _konto_fran(sokvag):
    try:
        with open(sokvag, encoding="utf-8") as fh:
            m = (json.load(fh) or {}).get("mejl") or {}
    except Exception:
        return {}
    if not (m.get("adress") and m.get("smtp_server") and m.get("losenord")):
        return {}
    return m


def las_konto():
    """E-postkontot från appens config, annars från SYS.ASSIST. {} om inget."""
    return _konto_fran(EGEN_CFG) or _konto_fran(ASSISTENT_CFG)


def ar_redo():
    return bool(las_konto())


def _smtp(port):
    """465 är SMTPS (SSL direkt), 587/25 börjar klart och växlar upp."""
    return smtplib.SMTP_SSL if int(port) == 465 else smtplib.SMTP


def skicka(till, amne, text, bilagor=()):
    """Skickar ett brev, eventuellt med bilagor.

    bilagor = [(sokvag, filnamn)] . Returnerar {"ok":...} eller {"fel":...}.
    """
    konto = las_konto()
    if not konto:
        return {"fel": "Inget e-postkonto är ifyllt. Lägg in det under "
                       '"mejl" i config.json (adress, smtp_server, '
                       "smtp_port och ett applösenord)."}
    till = (till or "").strip()
    if not till:
        return {"fel": "ingen mottagare"}
    if "@" not in till:
        return {"fel": f"'{till}' ser inte ut som en e-postadress"}
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr((konto.get("namn") or "", konto["adress"]))
    msg["To"] = till
    msg["Subject"] = amne or "(inget ämne)"
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg.set_content(text or "", cte="quoted-printable")

    for sokvag, namn in bilagor:
        typ = ("application/vnd.openxmlformats-officedocument."
               "spreadsheetml.sheet" if namn.endswith(".xlsx") else "application/octet-stream")
        with open(sokvag, "rb") as fh:
            msg.add_attachment(fh.read(), maintype=typ.split("/")[0],
                               subtype=typ.split("/")[1], filename=namn)

    port = int(konto.get("smtp_port") or 465)
    svar = {"ok": True, "text": f"skickat till {till}", "tid": time.strftime("%H:%M")}
    try:
        if port == 465:
            with smtplib.SMTP_SSL(konto["smtp_server"], port,
                                  context=ssl.create_default_context(), timeout=45) as s:
                s.login(konto["adress"], konto["losenord"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(konto["smtp_server"], port, timeout=45) as s:
                s.ehlo()
                s.starttls(context=ssl.create_default_context())
                s.login(konto["adress"], konto["losenord"])
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return {"fel": "Inloggningen nekades. Använd ett applösenord, inte ditt "
                       "vanliga lösenord."}
    except Exception as exc:                                   # noqa: BLE001
        return {"fel": f"kunde inte skicka: {type(exc).__name__}: {exc}"}
    return svar


def standardbrev(meta, antal, deadline=None):
    """Färdigt brev man kan skicka med arket — skrivet för att gå att skicka
    vidare till en kollega utan att man behöver formulera sig."""
    namn = meta.get("ansvarig") or "kollega"
    skola = meta.get("skola") or "skolan"
    program = meta.get("program") or "programmet"
    rader = [
        "Hej!",
        "",
        "Här kommer kalkylbladet för inventeringen av utrustning på "
        f"{skola}, {program}.",
        f"Det innehåller {antal} poster med benämning, antal, inköpsår, skick "
        "och bedömt investeringsbehov.",
        "",
        "Fyll gärna i det som saknas och rätta det som blivit fel — särskilt "
        "kolumnerna Investeringsbehov och Pris/enhet, eftersom de ligger till "
        "grund för var vi behöver investera.",
    ]
    if deadline:
        rader += ["", f"Jag är tacksam om du har fyllt i dokumentet senast {deadline}."]
    rader += ["", "Hör av dig om något är oklart.", "", "Mvh", namn]
    return "\n".join(rader)
