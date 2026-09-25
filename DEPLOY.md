# Lägga appen på nätet (Render)

Här är hela vägen från noll till en adress du kan öppna i telefonen, **utan
att din dator behöver vara på**. Räkna med 20–30 minuter första gången.

Det du behöver skaffa under vägen:

| Vad | Var | Kostar |
|---|---|---|
| GitHub-konto | github.com | 0 kr |
| Render-konto | render.com | 0 kr att skapa |
| En API-nyckel för bildanalys | aistudio.google.com | 0 kr |
| Render Web Service + disk | render.com | ca 7 $/mån |

> **Varför inte Netlify?** Netlify kan bara visa sidor som redan ligger färdiga
> på disk. Den här appen behöver ett program som kör hela tiden, sparar filer
> och tar emot foton. Det kan inte Netlify. Render kan.

---

## Steg 1 — Få upp koden på GitHub

Allt är förberett: koden är committad, repoadressen är inlagd, och repots
egen "Initial commit" är redan ihopslagen med din historik. Kvar är bara att
logga in och skjuta upp.

**Kör det här själv i en terminal** — inloggningen kräver att du svarar i en
webbläsare, så den kan inte göras automatiskt:

```bash
gh auth login
```

Välj: **GitHub.com** → **HTTPS** → **Login with a web browser**. Kopiera
engångskoden du får och klistra in den på sidan som öppnas.

Skjut sedan upp koden — det är ett enda kommando, eftersom allt annat redan
är gjort:

```bash
cd ~/vvs-inventering
git push -u origin main
```

Kontrollera att ingenting känsligt följde med:

```bash
git ls-files | grep -E "config\.json|\.env$"     # ska svara inget
```

> **Repot är publikt.** Vem som helst kan läsa koden. Det som ligger där är
> bara programmet — ingen inventering, inga foton och inga lösenord. Ändå
> värt att veta. Vill du ha det privat i stället: gå till repot på GitHub →
> **Settings** → längst ner → **Change visibility** → *Make private*. Render
> kan publicera från ett privat repo också, men då måste du ge Render
> åtkomst till det (Render frågar om det när du väljer repot).

> **Netlify bygger på samma repo.** Netlify försöker bygga varje gång du
> pushar, och det kommer att misslyckas — det är väntat, för Netlify kan inte
> köra den här sortens program (se `MOLN.md`). Det skadar ingenting, men vill
> du slippa de röda kryssen: gå in på Netlify → ditt projekt → **Site
> configuration** → **Build & deploy** → *Stop builds*. Render bryr sig inte
> om Netlify.

---

## Steg 2 — Skaffa en nyckel för bildanalys

Render kan inte köra bildmodellen (Ollama) — den kräver mer minne än tjänsten
får. I stället skickas fotot till en molntjänst, och **bara fotot**. Det är
därför appen bara fotar utrustning och VVS-artiklar, aldrig människor.

1. Gå till **aistudio.google.com** och logga in med ditt Google-konto.
2. Välj **Get API key** → **Create API key**.
3. Kopiera nyckeln (en lång sträng). Klistra in den någonstans tillfälligt —
   du behöver den i steg 3. **Mejla den inte till dig själv.**

Gratisnivån räcker gott: några hundra foton per dag utan kostnad.

Vill du hellre använda OpenAI i stället: skaffa en nyckel på
platform.openai.com och sätt `VVS_AI_LEVERANTOR=openai`.

---

## Steg 3 — Skapa tjänsten på Render

1. Gå till **render.com** och logga in med GitHub-kontot.
2. **New +** → **Blueprint**.
3. Välj repot `cribb1979-cyber/inventering`. Render hittar `render.yaml` och
   föreslår allt själv.
4. Render frågar efter de hemliga värdena (de står med `sync: false` i filen).
   Fyll i:

   **VVS_TOKEN** — telefonens lösenord. Hitta på en lång sträng själv, till
   exempel fyra ord i följd. Den ska vara svår att gissa.

   **VVS_AI_NYCKEL** — nyckeln du kopierade i steg 2.

5. Tryck **Apply** / **Create**. Render bygger och startar. Det tar några
   minuter; första bygget är långsammast.

När det är klart får du en adress som ser ut så:

```
https://sysvvs-inventering.onrender.com
```

---

## Steg 4 — Öppna på telefonen

Adressen behöver token på slutet. Skriv i telefonens webbläsare:

```
https://sysvvs-inventering.onrender.com/?t=DIN-TOKEN
```

1. Sidan öppnas. Kontrollera att inventeringen syns.
2. Lägg sidan på hemskärmen:
   * **iPhone:** dela-ikonen → *Lägg till på hemskärmen*
   * **Android:** de tre prickarna → *Lägg till på startskärmen*
3. Klart. Därifrån öppnas den som en app, med token redan ifylld.

Öppna samma adress på datorn. Nu ser telefonen och datorn **samma
inventering** — det du fotar i verkstaden kan du städa upp i efterhand vid
skrivbordet.

> **Viktigt:** eftersom `VVS_KRAV_TOKEN=1` krävs token även från datorn i
> molnet. Det är med flit — annars skulle appen se alla besök som "lokala"
> och släppa in vem som helst. Bokmärk adressen *med* `?t=...` på båda
> enheterna.

---

## Steg 5 — Provkör

Gå igenom de här punkterna en gång direkt, så vet du att allt hänger ihop:

- [ ] Startsidan laddas i telefonen.
- [ ] **Lägg till** → skriv ett föremål → det syns under **Inventering**.
- [ ] **Ta en bild** på något i verkstaden → ett förslag kommer tillbaka.
      (Första analysen kan ta upp till en halv minut.)
- [ ] Öppna samma sida på datorn → föremålet finns där också.
- [ ] **Kalkylark** → **Excel** → filen laddas ner.
- [ ] Starta om tjänsten i Render (**Manual Deploy** → *Restart*) → föremålet
      finns **kvar**. Detta prövar att disken fungerar.

Den sista punkten är den viktiga. Försvinner allt vid omstart är disken inte
monterad — då är `VVS_DATA` fel inställd.

---

## Om något går fel

| Symptom | Orsak | Åtgärd |
|---|---|---|
| "ogiltig eller saknad token" | token fattas eller är fel i adressen | lägg till `?t=DIN-TOKEN` på slutet, exakt som du skrev den i Render |
| Allt försvinner vid omstart | disken är inte monterad | kontrollera att `VVS_DATA=/var/data` och att disken står under **Disks** med samma sökväg |
| Bildanalysen svarar "ingen bildmodell" | nyckeln saknas eller är fel | kontrollera `VVS_AI_NYCKEL` under Environment |
| Analysen svarar 400/403 | nyckeln avvisas | skapa en ny nyckel på aistudio.google.com |
| Sidan är långsam första gången | gratistjänsten "somnar" | normal första gångs last. Uppgradera planen om det stör |
| Bygget misslyckas | fel i koden | läs loggen i Render → **Logs** |

---

## Vill du köra lokalt i stället?

Det går alldeles utmärkt, och då behövs varken Render eller någon nyckel:

```bash
cd ~/vvs-inventering
./installera.sh --modell
vvsinv
```

Då analyseras bilderna av en lokal modell och **ingenting lämnar datorn**.
Baksidan är att datorn måste vara på, och telefonen måste vara på samma
nätverk. Se `LASMIG.md`.
