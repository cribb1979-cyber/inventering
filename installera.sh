#!/bin/bash
# Sätter upp SYS.VVS på en ny Linux-maskin.
#
#   ./installera.sh            installera för den här användaren
#   ./installera.sh --modell   hämta också bildmodellen (ca 3 GB)
#
# Ingenting installeras systemtungt: allt hamnar i din hemkatalog och går att
# ta bort igen genom att radera ~/.local/bin/vvsinv och .desktop-filen.

set -u
MAPP="$(cd "$(dirname "$0")" && pwd)"
MODELL=0
[ "${1:-}" = "--modell" ] && MODELL=1

fel() { echo "fel: $*" >&2; exit 1; }

# ---- 1. python3 ------------------------------------------------------------
command -v python3 >/dev/null 2>&1 || fel "python3 saknas. Installera med:  sudo apt install python3"
echo "python3: $(python3 -V 2>&1)"

# ---- 2. startfilen ---------------------------------------------------------
mkdir -p "$HOME/.local/bin"
ln -sf "$MAPP/bin/vvsinv" "$HOME/.local/bin/vvsinv"
chmod +x "$MAPP/bin/vvsinv"
echo "startfil: ~/.local/bin/vvsinv"

case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) echo "obs: ~/.local/bin ligger inte i PATH. Lägg till raden"
       echo '     export PATH="$HOME/.local/bin:$PATH"'
       echo "     i ~/.bashrc om du vill kunna skriva 'vvsinv' i terminalen." ;;
esac

# ---- 3. skrivbordsikonen ---------------------------------------------------
mkdir -p "$HOME/.local/share/applications"
sed "s|^Exec=vvsinv|Exec=$HOME/.local/bin/vvsinv|" \
    "$MAPP/sysvvs.desktop" > "$HOME/.local/share/applications/sysvvs.desktop"
echo "startmeny: SYS.VVS"

if [ -d "$HOME/Skrivbord" ]; then SKRIVBORD="$HOME/Skrivbord"
elif [ -d "$HOME/Desktop" ]; then SKRIVBORD="$HOME/Desktop"
else SKRIVBORD=""; fi
if [ -n "$SKRIVBORD" ]; then
    cp "$HOME/.local/share/applications/sysvvs.desktop" "$SKRIVBORD/sysvvs.desktop"
    chmod +x "$SKRIVBORD/sysvvs.desktop"
    # GNOME kräver att genvägar markeras som betrodda
    command -v gio >/dev/null 2>&1 && \
        gio set "$SKRIVBORD/sysvvs.desktop" metadata::trusted true 2>/dev/null
    echo "skrivbord: $SKRIVBORD/sysvvs.desktop"
fi

# ---- 4. ikonen -------------------------------------------------------------
if python3 -c "import PIL" 2>/dev/null; then
    (cd "$MAPP" && python3 ikon.py >/dev/null 2>&1) && echo "ikon: ritad" \
        || echo "ikon: kunde inte ritas (fortsätter ändå)"
    command -v gtk-update-icon-cache >/dev/null 2>&1 && \
        gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1
else
    echo "ikon: python3-pil saknas, hoppar över (sudo apt install python3-pil)"
fi

# ---- 5. bildmodellen (frivilligt) ------------------------------------------
if [ "$MODELL" = 1 ]; then
    if ! command -v ollama >/dev/null 2>&1; then
        echo "bildmodell: ollama saknas. Se https://ollama.com/download"
    else
        echo "hämtar bildmodellen qwen2.5vl:3b (ca 3 GB)…"
        ollama pull qwen2.5vl:3b || echo "  hämtningen misslyckades — appen går ändå att använda"
    fi
fi

# ---- 6. starta -------------------------------------------------------------
mkdir -p "$MAPP/data/bilder" "$MAPP/data/export"
echo
echo "Klart. Starta med:  vvsinv     (eller ikonen SYS.VVS)"
echo "Telefonadressen visas i terminalen och under Inställningar → Koppla telefonen."
