# Att köra SYS.VVS på en server (Render m.fl.)

Det här är en **plan**, inte något som är byggt. Appen som finns i dag är
gjord för att köra på din dator. Den här filen beskriver vad som måste
ändras om den ska kunna köra utan att datorn är påslagen.

## Varför Netlify inte går

Netlify publicerar **färdiga filer**. Den kör inget program. Den här appen är
ett Python-program som sparar filer, skickar e-post och analyserar bilder.
Netlify kan visa en sida — inte vara servern. Det finns inget att bygga, och
därför kommer dess byggsteg att misslyckas hur repot än ser ut.

## Vad Render klarar

Render kan köra Python-program, och ger HTTPS automatiskt. Men fyra saker
måste lösas, och ingen av dem är gratis på riktigt.

### 1. Lagringen

Render har ingen egen hårddisk som överlever en omstart på gratisen.
Inventeringen ligger i en fil — startar tjänsten om, är allt borta.

* **Beständig disk** hos Render: kräver en betald instans.
* **Databas** i stället: Render har en som är gratis en begränsad tid,
  Supabase och Neon har gratisnivåer som varar. Då måste `lager.py` skrivas
  om från fil till databas — det är det största jobbet.
* Fotona behöver samma sak. Bilder i en databas är dumt; de hör i
  objektlagring (Cloudflare R2, Supabase Storage).

### 2. Bildanalysen

Ollama kan inte köras på Render. Modellen är 3 GB, Render har ingen GPU, och
en sådan instans kostar mer än hela projektet är värt.

Alltså måste analysen gå till ett **molntjänst-API** i stället:

* Bilden lämnar skolan och skickas till Google, Anthropic eller OpenAI.
  Det är en annan sak än i dag, då ingenting lämnar datorn — värt att tänka
  igenom innan man fotar lokaler och utrustning.
* Det behövs en API-nyckel, och oftast ett betalkort.

### 3. E-posten

Många webbhotell stänger utgående e-postportar för att stoppa spam. Att
skicka via Gmail från Render fungerar därför inte säkert. Då får utskicket gå
via en e-posttjänst (Resend, Brevo) — eller så hoppar man över mejlknappen
och laddar ner arket i stället.

### 4. Inloggningen

Adressen blir publik. I dag skyddas allt av en token i länken — den som har
länken kommer in. På internet räcker inte det. Det behövs ett riktigt
lösenord, och token får bli en sessionsnyckel.

## Vad som redan är klart

`server.py` läser nu inställningar och hemligheter ur miljövariabler om de
finns, så att inget lösenord behöver ligga i en fil på en främmande server:

    VVS_TOKEN, VVS_SKOLA, VVS_PROGRAM, VVS_ANSVARIG, VVS_DEADLINE
    VVS_MEJL_ADRESS, VVS_MEJL_NAMN, VVS_MEJL_SMTP_SERVER,
    VVS_MEJL_SMTP_PORT, VVS_MEJL_LOSENORD

## Vad jobbet består av

| Del | Omfattning |
|---|---|
| Lagring till databas i stället för fil | `lager.py` skrivs om, `server.py` följer med |
| Bilder till objektlagring | ny fil, `server.py` och `index.html` anropar den |
| Bildanalys mot moln-API | `ai.py` skrivs om; samma gränssnitt mot resten |
| Riktig inloggning | nytt i `server.py` och `index.html` |
| Deployment-filer | `requirements.txt`, `render.yaml`, startkommando |
| Provkörning | samma tester som i dag, mot molnet |

Det är ungefär en lika stor insats som appen var att bygga. Gör det bara om
datorn verkligen inte kan vara på — tunnel-alternativet kostar ingenting och
behåller både Ollama och hemligheterna hemma.

## Alternativet: tunneln

Datorn är servern, och telefonen når den utifrån via Tailscale. Ingen kod
ändras, ingen kostnad, inga bilder lämnar datorn. Enda villkoret: datorn
måste vara på.
