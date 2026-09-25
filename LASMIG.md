# SYS.VVS — inventering av VVS-verkstaden

Inventerar utrustningen i VVS-verkstadens lokaler: maskiner, verktyg,
material och inredning. Fotar man ett föremål med telefonen analyserar en
lokal AI vad bilden visar och föreslår allt som finns på den. Allt hamnar i
ett kalkylark som går att exportera och dela med yrkesläraren för programmet.

Inventeringen är **levande** — föremål kan ändras, räknas av och läggas till
när som helst. Telefonen och datorn ser samma sak.

> Ska appen fungera **utan att datorn är påslagen**, eller från telefonen
> utanför skolans nät? Följ då **`DEPLOY.md`** i stället. Den här filen
> beskriver den lokala varianten, där ingenting lämnar datorn.

## Öppna

* Skrivbordsikonen **SYS.VVS**, eller
* startmenyn → SYS.VVS, eller
* `vvsinv` i en terminal

## Snabb översikt

| Vill du… | Läs |
|---|---|
| Köra på datorn, telefonen på samma nät | den här filen |
| Köra utan att datorn är på (Render) | `DEPLOY.md` |
| Förstå varför Netlify inte går | `MOLN.md` |

## Kom igång på en ny dator

```bash
git clone <adressen-till-repot> vvs-inventering
cd vvs-inventering
./installera.sh --modell
vvsinv
```

`installera.sh` lägger startfilen i `~/.local/bin`, skrivbordsikonen på plats
och ritar ikonen. `--modell` hämtar också bildmodellen (ca 3 GB) — hoppa över
flaggan om du inte vill ha AI-analysen, appen fungerar ändå.

**Det enda som krävs i förväg är `python3`.** Inga paket behöver installeras
för att appen ska starta. Vill du ha ikonen ritad behövs `python3-pil`, och
för QR-koden i terminalen `qrencode` — annars visas adressen som text.

Bildanalysen kräver [Ollama](https://ollama.com/download) med modellen
`qwen2.5vl:3b`. Utan den fungerar allt utom AI-förslagen.

## På telefonen

1. Starta appen på datorn (`vvsinv --qr` skriver ut adressen och en QR-kod).
2. Telefonen måste vara på **samma nät** som datorn.
3. Skanna QR-koden, eller skriv in adressen i mobilens webbläsare.
4. Lägg sidan på hemskärmen — då öppnas den som en app.

Adressen innehåller en token. Utan token nekar servern allt utifrån; från
datorn (127.0.0.1) behövs ingen. Token ligger i `config.json` (rättighet 600)
och skickas aldrig vidare någon annanstans.

Kör appen i molnet (se `DEPLOY.md`) räknas inte datorn som lokal: där klistrar
du in nyckeln en gång i rutan **Koppla ihop appen** i stället. QR-koden ritas
sedan på **Kalkyl**-sidan, och telefonens kamera gör resten.

> Behöver telefonen fungera även när datorn är avstängd, eller utanför
> skolans nätverk? Då ska appen ligga på en server i stället. Se
> **`DEPLOY.md`** — där står hela vägen steg för steg. Det som ändras då är
> att bildanalysen skickas till en molntjänst i stället för att köras lokalt,
> och att fotona därför lämnar datorn.

## Vad den gör

| Flik | Vad som händer |
|---|---|
| **Inventering** | Allt som finns, sorterat per kategori. Här räknar du av (−/+) och ändrar uppgifter. |
| **Lägg till** | Skriv in ett föremål, eller **ta ett foto** — AI:n listar allt den ser i bilden. |
| **Kalkylark** | Sammanställning per investeringsbehov, export till Excel/CSV och knappen som mejlar arket till yrkesläraren. |
| **Historik** | Varje ändring, vem som gjorde den och när. |

## Foto och AI

Tryck **Ta en bild**. Kameran öppnas, bilden skalas ner i telefonen och
skickas till datorn. AI:n tittar på *hela* bilden och listar allt som går att
inventera — en bänk med tio kopplingar blir en rad med antal 10, inte tio
rader. Hittar den flera saker får varje sak ett eget kort:

* bocka av det du inte vill ha,
* **Ändra** öppnar kortet i formuläret om något är fel,
* **Lägg till valda** lägger in dem i inventeringen.

Hittar den bara en sak fylls formuläret i direkt i stället. **Ingenting sparas
förrän du trycker.** Hittar den ingenting säger den det — den hittar inte på
ett föremål som inte finns i bilden.

Modellen laddas in när servern startar, så första fotot är snabbt. Sedan
några sekunder per bild.

## Investeringsbehov

Varje föremål får en bedömning: **Behåll**, **Investera**, **Avveckla**
eller **Vet ej**. Det är den kolumnen inventeringen ska leda fram till — var
behöver skolan satsa, och var behövs det inte lika mycket.

**Pris sätter en människa.** AI:n gissar aldrig ett pris. Saknas priser blir
summan för låg, och arket varnar om det.

## Kalkylarket

Rubriken visar skola, program, ansvarig lärare, datum och när det ska vara
ifyllt. Kolumnerna: namn, kategori, antal, enhet, placering, inköpsår, skick,
dimension, tillverkningsmärke, investeringsbehov, prioritet, pris/enhet,
summa och anteckning.

* **Excel** (.xlsx) — talen ligger som tal, kolumnrubriken är fryst och det
  går att filtrera.
* **CSV** — semikolon och UTF-8, för den som hellre jobbar i ett annat program.

Filen hamnar i `data/export/`.

## Dela med yrkesläraren

Fliken **Kalkylark** har ett färdigskrivet brev: skola, program, antal
föremål och sista datum fylls i automatiskt. Ändra mottagare och text om du
vill, tryck sedan **Skicka**. Ingenting skickas förrän du bekräftar i rutan
som kommer.

## Inför v43

Sista datum räknas fram automatiskt till **tisdagen i vecka 43** (VVS träffas
tors–fre v43, så arket behöver vara klart innan). Datumet går att ändra under
Inställningar, och nedräkningen visas i appen.

## Säkerheten

Appen **raderar inte och skickar inte** något på egen hand. Radering och
utskick kräver att du bekräftar i en ruta. Alla bilder stannar på datorn —
bildanalysen körs lokalt i Ollama, inga foton lämnar maskinen.

> Det gäller den **lokala** varianten. Körs appen i molnet skickas fotot till
> en molntjänst för analys — se `MOLN.md`.

## Om AI:n

Bildanalysen använder en lokal bildmodell (`qwen2.5vl:3b` som standard).
Saknas modellen fungerar appen ändå: bilden sparas och du fyller i fälten
själv. Modellen hittar inte på märken eller dimensioner den inte ser, och
sätter aldrig ett pris.

Hämta modellen med:

    ollama pull qwen2.5vl:3b

Kör appen i molnet finns ingen lokal modell. Då används en molntjänst i
stället och fotona skickas dit — se `DEPLOY.md` och `MOLN.md`.

## Inställningar

Skola, program, ansvarig lärare och sista datum. Sparas i `config.json`.
Programmet ärvs automatiskt av nya föremål.

## Filer

| Fil | Innehåll |
|---|---|
| `server.py` | Servern, alla sidor och anrop |
| `lager.py` | Själva inventeringen — läsa, ändra, räkna av, historik |
| `stigar.py` | Var filerna ligger (går att flytta med `VVS_DATA`) |
| `kalkyl.py` | Bygger kalkylarket (Excel och CSV) |
| `ai.py` | Bildanalys — lokalt via Ollama, eller mot en molntjänst |
| `epost.py` | Skickar kalkylarket som brev |
| `index.html` | Hela gränssnittet (telefon och dator) |
| `bin/vvsinv` | Startfilen |
| `installera.sh` | Sätter upp appen på en ny dator |
| `sysvvs.desktop` | Skrivbordsikonen och startmenyn |
| `DEPLOY.md` | Guiden för att lägga appen på nätet |
| `MOLN.md` | Bakgrunden: varför Netlify inte går, vad molnet kostar |
| `data/inventering.json` | Inventeringen och historiken |
| `data/bilder/` | Fotona |
| `data/export/` | Exporterade kalkylark |
| `config.json` | Token, port och uppgifterna om skolan (rättighet 600) |

Saknas `config.json` skapas den första gången appen startar, med en egen
slumpad token. `config.example.json` visar vilka fält som finns.

## E-post

Fliken **Kalkylark** kan mejla arket direkt till yrkesläraren. För det
behövs ett konto i `config.json`:

```json
"mejl": {
  "adress": "du@skola.se",
  "namn": "Ditt Namn",
  "smtp_server": "smtp.gmail.com",
  "smtp_port": 465,
  "losenord": "applösenord-här"
}
```

Använd ett **applösenord**, inte ditt vanliga lösenord. Saknas kontot visas
ett besked i appen och du kan ladda ner arket och bifoga det själv i stället.
Finns ett konto uppsatt för SYS.ASSIST lånas det automatiskt.

## Starta om

Har koden ändrats måste servern startas om — den behåller den kod som fanns
i minnet när den startade:

    vvsinv --omstart
