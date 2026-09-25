# SYS.VVS — inventering av VVS-verkstaden

Inventerar utrustningen i VVS-verkstadens lokaler: maskiner, verktyg,
material och inredning. Fotar man ett föremål med telefonen analyserar en
bildmodell vad bilden visar och föreslår vad som finns på den. Allt hamnar i
ett kalkylark som går att exportera och dela med yrkesläraren för programmet.

Inventeringen är **levande** — föremål kan ändras, räknas av och läggas till
när som helst, och telefonen och datorn ser samma sak.

Kräver bara `python3`. Inga paket behöver installeras.

## Två sätt att köra

| Vill du… | Läs |
|---|---|
| Köra på datorn, telefonen på samma nät. Inga foton lämnar datorn. | [`LASMIG.md`](LASMIG.md) |
| Köra utan att datorn är på — en adress du når varifrån som helst | [`DEPLOY.md`](DEPLOY.md) |
| Förstå vad molnet kostar och varför Netlify inte går | [`MOLN.md`](MOLN.md) |

## Snabbstart på en dator

```bash
git clone https://github.com/cribb1979-cyber/inventering.git
cd inventering
./installera.sh --modell     # --modell hämtar bildmodellen (ca 3 GB)
vvsinv
```

## Inför v43

Sista datum räknas fram automatiskt till tisdagen i vecka 43 — VVS-lärarna
träffas torsdag–fredag, så arket behöver vara klart innan. Datumet går att
ändra under Inställningar.

## Säkerheten

Appen **raderar inte och skickar inte** något på egen hand: radering och
utskick kräver att man bekräftar i en ruta.

* **Lokalt** stannar alla foton på datorn — bildanalysen körs av en lokal
  modell.
* **I molnet** skickas fotot till en molntjänst för analys. Appen är byggd
  för att bara fotografera utrustning och VVS-artiklar, aldrig människor.
  Se [`MOLN.md`](MOLN.md).

`config.json` innehåller token och lösenord och är undantagen i
`.gitignore`. Den får aldrig checkas in.
