# Agente Triathlon LA28: guida passo passo

L'agente legge i ranking ufficiali di World Triathlon, applica il sistema di qualificazione LA28
(versione del 12 maggio 2026) come fa World Triathlon nella sua simulazione, scrive il risultato nel
database Notion **LA28 Triathlon** e aggiorna la pagina `triathlon.html` della mappa.

## Cosa c'è nella cartella

- `scrape_triathlon_la28.py`: l'agente vero e proprio
- `continentali.txt`: i risultati dei Giochi continentali già disputati (da aggiornare a mano)
- `.github/workflows/agente.yml`: il pulsante "Run workflow" su GitHub
- `GUIDA.md`: questa guida

Per il sito (repository `map-q-la28`): `triathlon.html`, `triathlon.json` (i dati di oggi, per vederla
subito) e `home.html` 1.6 (homepage con la riga del triathlon).

## Da dove prende i dati

Le pagine di triathlon.org leggono i ranking da `https://triathlon.org/api/rankings/<numero>`, che dà
tutto il ranking in una sola risposta. L'agente legge da lì:

| Numero | Ranking | A cosa serve |
|---|---|---|
| 11 / 12 | Individual Olympic Qualification Ranking, uomini / donne | posti individuali, limite di 3 per NOC |
| 64 | Mixed Relay Olympic Qualification Ranking | 8 NOC della staffetta, proiezione 2027 |
| 13 / 14 | World Triathlon Ranking, uomini / donne | soglia dei primi 160, "New Flag" dal ranking |

## Prima configurazione (una volta sola)

1. **Notion: collega la connessione.** Nella pagina ⚙️ Agenti 🕵🏻‍♂️ trovi il nuovo database
   **LA28 Triathlon** (in fondo). Aprilo a tutta pagina, `•••` in alto a destra > Connessioni >
   aggiungi "Agente Squash". Se vuoi, trascinalo nel riquadro con gli altri database LA28.
2. **GitHub: crea il repository.** New repository, nome `agente-triathlon-la28`, **Private**, Create.
3. **GitHub: carica i file.** Add file > Upload files: `scrape_triathlon_la28.py`, `continentali.txt`,
   `GUIDA.md` > Commit changes. Poi Add file > Create new file, nome `.github/workflows/agente.yml`,
   incolla il contenuto di `agente.yml` > Commit changes (la cartella `.github` non si carica trascinandola).
4. **GitHub: i segreti.** Settings > Secrets and variables > Actions > New repository secret, tre volte:
   - `NOTION_TOKEN`: il token della connessione "Agente Squash" (lo stesso degli altri agenti)
   - `NOTION_DATABASE_ID`: `422f48c9aad98159adaff446eb4cc6ab`
   - `MAPPA_TOKEN`: un token GitHub fine-grained solo sul repository `map-q-la28`, con
     **Contents: Read and write** e **Actions: Read and write** (puoi riusare quello dello skate)
5. **Sito.** Nel repository `map-q-la28`: Add file > Upload files > `triathlon.html`, `triathlon.json`,
   `home.html` > Commit changes. Poi apri `sport.html` > matita e aggiungi la riga del triathlon
   (vedi la scheda 59, sezione "sport.html"). Infine Actions > Aggiorna mappa LA28 > Run workflow.

## Come si lancia

Repository `agente-triathlon-la28` > Actions > Agente Triathlon LA28 > Run workflow:

- **prova** (spuntata): legge i ranking e stampa la simulazione nel registro, senza scrivere niente.
  Fai così la prima volta. Togli la spunta per il lancio vero.
- **modalita**: `sostituzione` (consigliato) archivia le righe vecchie in Notion; `archivio` le lascia.
- **campioni_2027**: lascia vuoto finché il Mondiale di staffetta 2027 non si è disputato (il posto è
  una proiezione). Dopo il Mondiale scrivi i NOC in ordine d'arrivo, per esempio `AUS,GBR,FRA`.

Il lancio vero scrive circa 130 righe (55 posti + 6 riserve per genere, più le squadre di staffetta).
I ranking cambiano dopo ogni gara: basta lanciarlo una volta alla settimana o dopo una gara importante.

## Quando aggiornare continentali.txt

Dopo ogni Giochi continentali (africani gennaio 2027, europei giugno 2027, panamericani e del Pacifico
luglio-agosto 2027) aggiungi le righe dei primi 20-30 arrivati, uomini e donne, nel formato indicato in
cima al file. Finché un Giochi non c'è nel file, il suo posto resta "In attesa".

## Se qualcosa non va

- `ranking ... di triathlon.org non raggiungibile`: il sito non risponde ai server di GitHub. Riprova;
  se continua, scrivimelo (si può passare ai file Excel di esportazione).
- `nel database non trovo queste colonne`: una colonna Notion è stata rinominata; rimettile il nome.
- `Notion ha risposto 404`: la connessione "Agente Squash" non è collegata al database (punto 1).
- `ATTENZIONE: continente non riconosciuto`: è comparso un paese nuovo; va aggiunto in `CONTINENTI`.
