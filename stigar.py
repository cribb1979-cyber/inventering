"""Var appen har sina filer.

Ett enda ställe för sökvägarna, så att server, lager och kalkylark aldrig kan
hamna i otakt.

På en molnserver (Render, Railway, en VPS) försvinner allt som skrivs i
kodmappen när tjänsten startas om. Inventeringen och fotona måste därför
ligga på en monterad disk, och en sådan monteras någon annanstans än i
kodmappen. Sätt då VVS_DATA till diskens sökväg:

    VVS_DATA=/var/data        # Render: monteringspunkten för disken

Lokalt är variabeln tom och allt hamnar i data/ precis som förut.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# Inventeringen, fotona och de exporterade arken.
DATA = os.path.abspath(os.environ.get("VVS_DATA") or os.path.join(HERE, "data"))
BILDER = os.path.join(DATA, "bilder")
EXPORT = os.path.join(DATA, "export")
INVENTERING = os.path.join(DATA, "inventering.json")

# config.json innehåller token och — om man lagt dem där — lösenord. Lägg den
# på samma disk som datan på en server, annars skapas en ny token vid varje
# omstart och telefonens bokmärke slutar fungera.
CONFIG = os.path.abspath(os.environ.get("VVS_CONFIG") or os.path.join(HERE, "config.json"))


def se_till_att_mappar_finns():
    """Skapar mapparna om de inte finns. Körs vid start."""
    for mapp in (DATA, BILDER, EXPORT, os.path.dirname(CONFIG)):
        if mapp:
            os.makedirs(mapp, exist_ok=True)
