# Molnet — vad som gäller och varför

**Guiden du följer ligger i `DEPLOY.md`.** Den här filen förklarar bara
bakgrunden, så att du kan bedöma om molnet är rätt val för dig.

## Varför Netlify inte går

Netlify publicerar **färdiga filer**. Det kör inget program. Den här appen är
ett Python-program som sparar filer, skickar e-post och analyserar bilder.
Netlify kan visa en sida — inte vara servern. Därför finns inget att bygga
och byggsteget kommer att misslyckas hur repot än ser ut.

## Vad som byggdes för att Render skulle gå

| Del | Lösning |
|---|---|
| Lagringen | `stigar.py` + `VVS_DATA` låter data och `config.json` ligga på en monterad disk i stället för i kodmappen |
| Bildanalysen | `ai.py` kan skicka fotot till Google Gemini eller OpenAI när ingen lokal modell finns |
| Hemligheter | Alla nycklar och lösenord kan komma från miljövariabler och skrivs då aldrig till disk |
| Inloggningen | `VVS_KRAV_TOKEN=1` kräver token även från 127.0.0.1 — nödvändigt bakom en proxy |
| Deployment | `render.yaml`, `Procfile`, `requirements.txt`, `.env.example` |

## Det du bör veta innan du sätter igång

**Bilderna lämnar skolan.** Lokalt analyseras fotona av Ollama och stannar på
datorn. I molnet måste de skickas till Google eller OpenAI. Det är en
verklig skillnad. Appen är byggd för att bara fotografera utrustning och
VVS-artiklar, aldrig människor eller lokaler i allmänhet — men det är ditt
ansvar att se till att det blir så i praktiken.

**Det kostar pengar.** En Render-instans som kan ha en monterad disk är
en betald instans (några tiotals kronor i månaden). Gratisnivån kan inte
behålla data mellan omstarter, och då spelar det ingen roll hur bra koden är.

**Token i adressen.** Skyddet är en hemlig token i länken. Den som har
länken kommer in. Det är tillräckligt för en inventering inom skolan, men
det är inte ett riktigt konto med lösenord och utloggning. Vill du ha det
behövs mer arbete.

## Två lager av filer — välj ett

Datorn och molnet är samma program men **två skilda lager av filer**. De synkas
inte av sig själva. Bestäm därför vilken som är den riktiga:

* **Molnet som sanning** — både telefon och dator öppnar Render-adressen. En
  lista, alltid, och datorn behöver inte vara på. Så pekar du om datorn: fyll i
  nyckeln `moln` i `config.json` (se `DEPLOY.md`).
* **Datorn som sanning** — kör lokalt (`LASMIG.md`) och låt telefonen vara på
  samma nät. Då lämnar inga foton datorn, men datorn måste vara påslagen.

Att köra båda samtidigt är möjligt men förvirrande: du får två listor som
aldrig möts.

## Alternativet: tunneln

Datorn är servern, och telefonen når den utifrån via Tailscale. Ingen kod
ändras, ingenting kostar, och **inga bilder lämnar datorn**. Enda villkoret
är att datorn är påslagen — alltså exakt samma sak som i dag, men telefonen
fungerar även utanför skolans nätverk.

Är datorn oftast på är det här enklare och bättre än molnet. Är den oftast av
är molnet rätt väg.
