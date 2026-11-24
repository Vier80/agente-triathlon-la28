"""Simulazione dei qualificati di triathlon a LA28 (World Triathlon)

Legge i ranking ufficiali di World Triathlon (triathlon.org) e applica il sistema di qualificazione
del CIO per il triathlon a LA28 (versione del 12 maggio 2026) per simulare chi si qualificherebbe oggi.
Le regole sono applicate come le applica World Triathlon nella sua "Olympic qualification simulation"
(PDF uomini e donne del 17/11/2026, usati per il collaudo).

Tre ranking letti da https://triathlon.org/api/rankings/<numero> (la stessa fonte delle pagine del sito):
  11 / 12  Individual Olympic Qualification Ranking (IOQR), uomini / donne
  64       Mixed Relay Olympic Qualification Ranking (MROQR)
  13 / 14  World Triathlon Ranking, uomini / donne (soglia dei primi 160 e "New Flag" dal ranking)
Più il file a mano continentali.txt con i risultati dei Giochi continentali già disputati.

ATTENZIONE: nel triathlon i posti vanno al NOC (Comitato Olimpico Nazionale), non all'atleta.
L'atleta indicato in ogni riga è quello che ha "conquistato" il posto per il suo NOC.

Scrive le righe in un database Notion e produce il file triathlon.json per la pagina grafica.

Variabili d'ambiente:
  NOTION_TOKEN, NOTION_DATABASE_ID   credenziali e database Notion
  DRY_RUN=true                       solo prova: non scrive su Notion (triathlon.json viene creato lo stesso)
  MODALITA                           "sostituzione" (le righe vecchie vengono archiviate) oppure "archivio"
  CAMPIONI_2027                      vuoto = proiezione (decisione 3b); altrimenti i NOC in ordine di arrivo
                                     del Mondiale di staffetta 2027, separati da virgola (es. "AUS,GBR")
Solo per le prove:
  RANKING_DIR                        cartella con i file 11.json, 12.json, 13.json, 14.json, 64.json
  OGGI                               data finta AAAA-MM-GG
  CONTINENTALI                       percorso di un altro file di Giochi continentali
"""
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date, datetime

import requests

# ------------------------------------------------------------------ impostazioni
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
_raw_id = os.getenv("NOTION_DATABASE_ID", "").strip().replace("-", "")
_found = re.search(r"[0-9a-fA-F]{32}", _raw_id)
DATABASE_ID = _found.group(0) if _found else _raw_id
DRY_RUN = os.getenv("DRY_RUN", "").strip().lower() == "true"
MODALITA = (os.getenv("MODALITA", "") or "sostituzione").strip().lower()
JSON_OUT = os.getenv("JSON_OUT", "triathlon.json")
RANKING_DIR = os.getenv("RANKING_DIR", "")
OGGI = os.getenv("OGGI", "")
CONTINENTALI = os.getenv("CONTINENTALI", "") or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                             "continentali.txt")

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

API = "https://triathlon.org/api/rankings/{}"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/json",
                        "Referer": "https://triathlon.org/world-rankings/olympic"})

# numeri dei ranking nel sito di World Triathlon
RANK_IOQR = {"M": 11, "F": 12}       # ranking olimpico individuale
RANK_WR = {"M": 13, "F": 14}         # World Triathlon Ranking
RANK_MROQR = 64                      # ranking olimpico della staffetta mista

# ------------------------------------------------------------------ regolamento (versione 12/5/2026)
HOST = "USA"                              # paese ospitante: 2 posti per genere (D.1)
CUTOFF = date(2028, 5, 18)                # data dei ranking finali; dopo è "Qualificato"
NATI_ENTRO = 2010                         # C.1: nati entro il 31/12/2010 (il ranking dà solo l'anno)
TOP_WR = 160                              # C.2: bisogna essere tra i primi 160 del World Triathlon Ranking
POSTI_GENERE = 55                         # B.1: 51 + 2 ospitante + 2 Universality
POSTI_IOQR = 21                           # D.1: ranking olimpico individuale
POSTI_UNIV = 2                            # D.2: Universality (Commissione Tripartita)
NOC_MROQR = 8                             # D.1: 16 posti per genere = 8 NOC da 2
TOP_MROQR_CONT = 15                       # D.1: garanzia continentale solo se tra i primi 15
MAX_BASE, MAX_TOP30 = 2, 3                # B.2: 3 per genere se il NOC ha 3 atleti tra i primi 30 dell'IOQR
RISERVE = 6                               # quanti "prossimi in lista" mostrare (riassegnazione F.1)
# Mondiale di staffetta mista 2026 (Amburgo, 12/7/2026): ordine d'arrivo dei primi
CAMPIONI_2026 = ["FRA", "HUN", "GBR", "USA"]
_c27 = os.getenv("CAMPIONI_2027", "").replace(" ", "").upper()
CAMPIONI_2027 = [c for c in _c27.split(",") if c]
# ordine di priorità dei "New Flag" (D.1)
ORDINE_GIOCHI = ["Africa", "Americhe", "Asia", "Europa", "Oceania"]   # Giochi africani, panamericani, ...
NOMI_GIOCHI = {"Africa": "Giochi africani 2027", "Americhe": "Giochi panamericani 2027",
               "Asia": "Giochi asiatici 2026", "Europa": "Giochi europei 2027",
               "Oceania": "Giochi del Pacifico 2027"}
ORDINE_WR = ["Africa", "Americhe", "Asia", "Europa", "Oceania"]
CONT_ORDER = ["Africa", "Americhe", "Asia", "Europa", "Oceania"]

GENERI = {"M": "Uomini", "F": "Donne"}
EVENTO = {"M": "Individuale maschile", "F": "Individuale femminile", "X": "Staffetta mista"}

# nomi delle vie (sono anche le opzioni della colonna Notion "Via di qualificazione")
VIA = {
    "H": "Paese ospitante (USA)",
    "M26": "Mondiale staffetta mista 2026",
    "M27": "Mondiale staffetta mista 2027",
    "M27P": "Mondiale staffetta mista 2027 (proiezione)",
    "SC": "Ranking olimpico staffetta (posto continentale)",
    "S": "Ranking olimpico staffetta",
    "I": "Ranking olimpico individuale",
    "IR": "Ranking olimpico individuale (posto riassegnato)",
    "U": "Universality",
    "G": "Giochi continentali (New Flag)",
    "W": "World Triathlon Ranking (New Flag)",
    "R": "Riserva",
    "T": "Squadra staffetta mista",
}
# lettera usata dalla pagina per il colore
TIPO = {"H": "H", "M26": "M", "M27": "M", "M27P": "M", "SC": "S", "S": "S", "I": "I", "IR": "I",
        "U": "U", "G": "G", "W": "W", "R": "R", "T": "T"}

# codici di World Triathlon diversi da quelli del CIO
WT_TO_NOC = {"SGP": "SIN"}
NON_NOC = {"MAC", "AIN", "NEU", "EOR", "IRT", "ROT", "WT"}   # senza Comitato Olimpico riconosciuto

# continenti delle confederazioni di World Triathlon (Israele in Europa, Kazakistan in Asia)
CONTINENTI = {
    "Africa": "ALG ANG BEN BOT BUR BDI CMR CPV CAF CHA COM CGO COD CIV DJI EGY GEQ ERI SWZ ETH GAB GAM GHA "
              "GUI GBS KEN LES LBR LBA MAD MAW MLI MTN MRI MAR MOZ NAM NIG NGR RWA STP SEN SEY SLE SOM RSA "
              "SSD SUD TAN TOG TUN UGA ZAM ZIM",
    "Americhe": "ANT ARG ARU BAH BAR BIZ BER BOL BRA IVB CAN CAY CHI COL CRC CUB DMA DOM ECU ESA GRN GUA "
                "GUY HAI HON JAM MEX NCA PAN PAR PER PUR SKN LCA VIN SUR TTO USA URU VEN ISV",
    "Asia": "AFG BRN BAN BHU BRU CAM CHN TPE HKG IND INA IRI IRQ JPN JOR KAZ PRK KOR KUW KGZ LAO LBN MAS "
            "MDV MGL MYA NEP OMA PAK PLE PHI QAT KSA SIN SRI SYR TJK THA TLS TKM UAE UZB VIE YEM",
    "Europa": "ALB AND ARM AUT AZE BLR BEL BIH BUL CRO CYP CZE DEN EST FIN FRA GEO GER GBR GRE HUN ISL IRL "
              "ISR ITA KOS LAT LIE LTU LUX MLT MDA MON MNE NED MKD NOR POL POR ROU RUS SMR SRB SVK SLO ESP "
              "SWE SUI TUR UKR",
    "Oceania": "ASA AUS COK FIJ FSM GUM KIR MHL NRU NZL PLW PNG SAM SOL TGA TUV VAN",
}
NOC_CONT = {c: k for k, v in CONTINENTI.items() for c in v.split()}


def die(msg):
    print(f"ERRORE: {msg}")
    sys.exit(1)


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def today():
    return date.fromisoformat(OGGI) if OGGI else date.today()


def chiave_nome(s):
    """Nome semplificato per confrontare grafie diverse (accenti, maiuscole, spazi)."""
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(sorted(re.findall(r"[a-z]+", s)))


# ------------------------------------------------------------------ lettura dati
def fetch_ranking(rid):
    """Un ranking intero: il sito restituisce tutte le righe in una sola risposta."""
    if RANKING_DIR:
        with open(os.path.join(RANKING_DIR, f"{rid}.json"), encoding="utf-8") as f:
            return json.load(f)
    last = None
    for attempt in range(4):
        try:
            r = SESSION.get(API.format(rid), timeout=60)
            if r.status_code >= 500 or r.status_code == 429:
                raise RuntimeError(f"stato {r.status_code}")
            r.raise_for_status()
            data = r.json()
            if not isinstance(data.get("rows"), list):
                raise RuntimeError("risposta senza 'rows'")
            return data
        except Exception as e:
            last = e
            time.sleep(3 + 3 * attempt)
    raise RuntimeError(f"ranking {rid} di triathlon.org non raggiungibile ({last})")


def atleta(r, i):
    """Trasforma una riga del sito in un dizionario con nomi italiani."""
    code = str(r.get("noc") or "").upper().strip()
    noc = WT_TO_NOC.get(code, code)
    return {"id": str(r.get("athleteId") or f"x{i}"), "nome": str(r.get("name") or "").strip(),
            "code": code, "noc": noc, "rank": int(num(r.get("rank"), i + 1)), "punti": num(r.get("points")),
            "nato": int(num(r.get("yob"), 0)) or None, "naz_rank": int(num(r.get("nationRank"), 0)),
            "paese": str(r.get("countryName") or noc), "cont": NOC_CONT.get(noc, ""), "ordine": i}


def leggi_continentali(path, notes):
    """Risultati dei Giochi continentali dal file continentali.txt: {(continente, genere): {...}}."""
    giochi = {}
    if not os.path.exists(path):
        notes.append(f"File {os.path.basename(path)} non trovato: tutti i posti dei Giochi continentali sono 'In attesa'.")
        return giochi
    with open(path, encoding="utf-8") as f:
        for n, riga in enumerate(f, 1):
            riga = riga.strip()
            if not riga or riga.startswith("#"):
                continue
            parti = [p.strip() for p in riga.split("|")]
            if len(parti) < 6:
                notes.append(f"continentali.txt, riga {n} ignorata (servono almeno 6 campi): {riga[:60]}")
                continue
            cont, gen, nome_giochi, pos, nome, code = parti[:6]
            nato = int(num(parti[6], 0)) if len(parti) > 6 else None
            if cont not in CONT_ORDER or gen not in ("M", "F"):
                notes.append(f"continentali.txt, riga {n} ignorata (continente o genere non validi): {riga[:60]}")
                continue
            code = code.upper()
            g = giochi.setdefault((cont, gen), {"giochi": nome_giochi, "arrivi": []})
            g["arrivi"].append({"pos": int(num(pos, 999)), "nome": nome, "code": code,
                                "noc": WT_TO_NOC.get(code, code), "nato": nato})
    for g in giochi.values():
        g["arrivi"].sort(key=lambda a: a["pos"])
    return giochi


def load_data(notes):
    data = {"ioqr": {}, "wr": {}, "pubblicato": {}}
    sconosciuti = set()
    for g in ("M", "F"):
        for chiave, rid in (("ioqr", RANK_IOQR[g]), ("wr", RANK_WR[g])):
            raw = fetch_ranking(rid)
            lista = [atleta(r, i) for i, r in enumerate(raw.get("rows") or [])]
            lista = [a for a in lista if a["nome"] and a["noc"]]
            lista.sort(key=lambda a: (a["rank"], -a["punti"], a["ordine"]))
            data[chiave][g] = lista
            data["pubblicato"][f"{chiave}_{g}"] = str(raw.get("published") or "")
            sconosciuti |= {a["noc"] for a in lista if not a["cont"] and a["noc"] not in NON_NOC}
            print(f"  {raw.get('categoryName', '')} {raw.get('name', '')}: {len(lista)} atleti "
                  f"(pubblicato {raw.get('published', '?')})")
    raw = fetch_ranking(RANK_MROQR)
    squadre = []
    for i, r in enumerate(raw.get("rows") or []):
        if int(num(r.get("nationRank"), 1)) != 1:      # solo la prima squadra di ogni nazione
            continue
        code = str(r.get("noc") or "").upper()
        noc = WT_TO_NOC.get(code, code)
        squadre.append({"rank": int(num(r.get("rank"), i + 1)), "noc": noc, "code": code,
                        "paese": str(r.get("countryName") or noc), "punti": num(r.get("points")),
                        "cont": NOC_CONT.get(noc, "")})
    squadre.sort(key=lambda s: s["rank"])
    data["mroqr"] = squadre
    data["pubblicato"]["mroqr"] = str(raw.get("published") or "")
    print(f"  {raw.get('categoryName', '')}: {len(squadre)} squadre (pubblicato {raw.get('published', '?')})")
    if sconosciuti:
        notes.append("ATTENZIONE: continente non riconosciuto per " + ", ".join(sorted(sconosciuti))
                     + " (aggiungere il codice in CONTINENTI)")
    data["giochi"] = leggi_continentali(CONTINENTALI, notes)
    return data


# ------------------------------------------------------------------ simulazione
class Stato:
    """Tutto quello che serve durante la simulazione (posti assegnati, conteggi per NOC...)."""

    def __init__(self, data, oggi):
        self.data = data
        self.ok = "Qualificato" if oggi >= CUTOFF else "Provvisorio"
        self.posti = {"M": [], "F": []}           # elenco dei posti assegnati (anche annullati)
        self.notes = []
        # eleggibilità (C.1 e C.2): nati entro il 2010 e tra i primi 160 del World Triathlon Ranking
        self.wr_rank = {}
        self.wr_nome = {}
        for g in ("M", "F"):
            for a in data["wr"][g]:
                self.wr_rank[(g, a["id"])] = a["rank"]
                self.wr_nome.setdefault((g, a["noc"], chiave_nome(a["nome"])), a)
        # massimo per NOC (B.2): 3 se il NOC ha almeno 3 atleti tra i primi 30 dell'IOQR, altrimenti 2
        self.max_noc = {}
        for g in ("M", "F"):
            conta = {}
            for a in data["ioqr"][g]:
                if a["rank"] <= 30:
                    conta[a["noc"]] = conta.get(a["noc"], 0) + 1
            self.max_noc[g] = {n: MAX_TOP30 for n, k in conta.items() if k >= 3}
        # atleti eleggibili per genere e NOC (per sapere chi può schierare 2 uomini + 2 donne)
        self.eleggibili = {g: {} for g in ("M", "F")}
        for g in ("M", "F"):
            for a in data["wr"][g]:
                if self.eleggibile(g, a):
                    self.eleggibili[g].setdefault(a["noc"], []).append(a)
        self.pointer = {"M": 0, "F": 0}           # punto dell'IOQR a cui si è arrivati
        self.saltati = {"M": set(), "F": set()}   # "i due migliori" dei NOC già qualificati (D.1)

    # --- regole di base
    def eleggibile(self, g, a):
        if a["noc"] in NON_NOC:
            return False
        if a.get("nato") and a["nato"] > NATI_ENTRO:
            return False
        rk = self.wr_rank.get((g, a["id"]))
        return rk is not None and rk <= TOP_WR

    def limite(self, g, noc):
        return self.max_noc[g].get(noc, MAX_BASE)

    def attivi(self, g):
        return [p for p in self.posti[g] if not p.get("annullato")]

    def conta(self, g, noc):
        return sum(1 for p in self.attivi(g) if p["noc"] == noc)

    def noc_qualificati(self):
        return {p["noc"] for g in ("M", "F") for p in self.attivi(g) if p["noc"]}

    def puo_staffetta(self, noc):
        """Ha almeno 2 uomini e 2 donne eleggibili?"""
        return len(self.eleggibili["M"].get(noc, [])) >= 2 and len(self.eleggibili["F"].get(noc, [])) >= 2

    def migliori_ioqr(self, g, noc, k=2):
        """I k atleti eleggibili meglio classificati del NOC nel ranking olimpico."""
        return [a for a in self.data["ioqr"][g] if a["noc"] == noc and self.eleggibile(g, a)][:k]

    # --- assegnazione di un posto
    def dai(self, g, via, noc, a=None, dettaglio="", status=None, extra=None):
        p = {"g": g, "via": via, "noc": noc, "a": a, "dettaglio": dettaglio, "stato": status or self.ok}
        p.update(extra or {})
        self.posti[g].append(p)
        return p

    def dai_staffetta(self, via, noc, dettaglio):
        """Le vie della staffetta danno 2 posti per genere al NOC."""
        for g in ("M", "F"):
            for i, a in enumerate(self.migliori_ioqr(g, noc)):
                self.dai(g, via, noc, a, f"{dettaglio}; {'miglior' if i == 0 else 'secondo'} atleta "
                                          f"{noc} nel ranking olimpico (n.{a['rank']})")
            mancano = 2 - len(self.migliori_ioqr(g, noc))
            for _ in range(max(0, mancano)):      # NOC senza abbastanza atleti nell'IOQR
                self.dai(g, via, noc, None, dettaglio + "; atleta da scegliere dal NOC")

    # --- prossimo atleta dell'IOQR (usato anche per i posti che "tornano" all'IOQR)
    def prossimo_ioqr(self, g, salta_migliori=True, salta_gia_dentro=False):
        """Scorre il ranking olimpico individuale da dove si era arrivati.
        salta_migliori: salta "i due migliori" dei NOC già qualificati con le vie precedenti (D.1)
        salta_gia_dentro: salta gli atleti che hanno già generato un posto (serve per le riserve)"""
        lista = self.data["ioqr"][g]
        dentro = {p["a"]["id"] for p in self.attivi(g) if p["a"]} if salta_gia_dentro else set()
        while self.pointer[g] < len(lista):
            a = lista[self.pointer[g]]
            self.pointer[g] += 1
            if not self.eleggibile(g, a):
                continue
            if salta_migliori and a["id"] in self.saltati[g]:
                continue
            if a["id"] in dentro:
                continue
            if self.conta(g, a["noc"]) >= self.limite(g, a["noc"]):
                continue
            return a
        return None


def simula(data, oggi=None):
    oggi = oggi or today()
    s = Stato(data, oggi)
    notes = s.notes

    # 1) Paese ospitante: 2 posti per genere agli USA (se hanno atleti eleggibili)
    s.dai_staffetta("H", HOST, "posto garantito al paese ospitante")
    for g in ("M", "F"):
        if len(s.eleggibili[g].get(HOST, [])) < 2:
            notes.append(f"{GENERI[g]}: gli USA hanno meno di 2 atleti eleggibili; se non li avranno, i posti "
                         f"dell'ospitante torneranno all'IOQR (F.2)")

    # 2) Mondiale di staffetta mista 2026: 2+2 al primo NOC non ancora qualificato e con 2+2 eleggibili
    def campione(lista, via, nome):
        for noc in lista:
            if noc in s.noc_qualificati():
                continue
            if not s.puo_staffetta(noc):
                notes.append(f"{nome}: {noc} non ha 2 uomini e 2 donne eleggibili, il posto passa al successivo")
                continue
            s.dai_staffetta(via, noc, f"{nome}: primo NOC dell'ordine d'arrivo non ancora qualificato")
            return noc
        return None

    campione(CAMPIONI_2026, "M26", "Mondiale staffetta mista 2026 (Amburgo)")

    # 3) Mondiale di staffetta mista 2027: se non c'è ancora, proiezione = primo NOC dell'MROQR non qualificato
    if CAMPIONI_2027:
        campione(CAMPIONI_2027, "M27", "Mondiale staffetta mista 2027")
    else:
        for sq in data["mroqr"]:
            if sq["noc"] not in s.noc_qualificati() and s.puo_staffetta(sq["noc"]):
                s.dai_staffetta("M27P", sq["noc"],
                                f"PROIEZIONE: il Mondiale 2027 non si è ancora disputato; il posto va al primo NOC "
                                f"del ranking olimpico di staffetta non ancora qualificato (n.{sq['rank']})")
                break

    # 4) Ranking olimpico della staffetta mista: 8 NOC da 2+2
    #    a) garanzia continentale: miglior NOC di ogni continente senza NOC già qualificati, se tra i primi 15
    qualificati_prima = s.noc_qualificati()
    cont_coperti = {NOC_CONT.get(n, "") for n in qualificati_prima}
    presi = []
    for cont in CONT_ORDER:
        if cont in cont_coperti:
            continue
        sq = next((x for x in data["mroqr"] if x["cont"] == cont and x["rank"] <= TOP_MROQR_CONT
                   and x["noc"] not in s.noc_qualificati() and s.puo_staffetta(x["noc"])), None)
        if sq:
            s.dai_staffetta("SC", sq["noc"], f"miglior NOC {cont_nome(cont)} nel ranking olimpico di staffetta "
                                             f"(n.{sq['rank']}, entro i primi {TOP_MROQR_CONT})")
            presi.append(sq["noc"])
    #    b) i posti rimanenti, fino a 8 NOC in tutto, in ordine di ranking
    for sq in data["mroqr"]:
        if len(presi) >= NOC_MROQR:
            break
        if sq["noc"] in s.noc_qualificati() or not s.puo_staffetta(sq["noc"]):
            continue
        s.dai_staffetta("S", sq["noc"], f"n.{sq['rank']} del ranking olimpico di staffetta")
        presi.append(sq["noc"])
    extra_ioqr = 2 * (NOC_MROQR - len(presi))
    if extra_ioqr:
        notes.append(f"Ranking di staffetta: solo {len(presi)} NOC con 2+2 eleggibili; {extra_ioqr // 2} posti "
                     f"per genere tornano all'IOQR")

    # 5) Ranking olimpico individuale: 21 posti per genere (più quelli tornati dalla staffetta)
    #    I due migliori atleti dei NOC che hanno già posti non possono prendere posti dal ranking individuale.
    per_genere = {}
    for g in ("M", "F"):
        for noc in qualificati_prima | set(presi):
            for a in s.migliori_ioqr(g, noc):
                s.saltati[g].add(a["id"])
        dati_g = 0
        while dati_g < POSTI_IOQR + extra_ioqr // 2:
            a = s.prossimo_ioqr(g)
            if not a:
                notes.append(f"{GENERI[g]}: atleti eleggibili finiti nel ranking olimpico individuale")
                break
            k = s.conta(g, a["noc"]) + 1
            s.dai(g, "I", a["noc"], a, f"n.{a['rank']} del ranking olimpico individuale; {k}º posto {a['noc']} "
                                        f"(massimo {s.limite(g, a['noc'])})")
            dati_g += 1
        per_genere[g] = dati_g

    for g in ("M", "F"):
        # 6) Universality: 2 posti per genere, decide la Commissione Tripartita
        for i in range(POSTI_UNIV):
            s.dai(g, "U", "", None, "decide la Commissione Tripartita dopo il periodo di qualificazione "
                                    "(richieste dei NOC dal 1/10/2027 al 15/1/2028)", status="In attesa",
                  extra={"n_univ": i + 1})

        # 7) Giochi continentali "New Flag": 1 posto per continente al primo NOC non ancora qualificato
        for cont in ORDINE_GIOCHI:
            assegna_giochi(s, g, cont)

        # 8) World Triathlon Ranking "New Flag": 1 posto per continente al primo NOC non ancora qualificato
        for cont in ORDINE_WR:
            assegna_wr(s, g, cont)

        # 9) Annullamenti: se un NOC con un posto New Flag ottiene un posto dall'IOQR (o, per il WR, dai Giochi),
        #    il posto New Flag viene annullato e riassegnato nello stesso continente (vedi D.1 e la simulazione WT)
        for giro in range(50):
            cambiato = False
            for p in list(s.attivi(g)):
                if p["via"] == "G" and p["noc"] and any(
                        q is not p and q["noc"] == p["noc"] and q["via"] in ("I", "IR") for q in s.attivi(g)):
                    p["annullato"] = True
                    notes.append(f"{GENERI[g]}: annullato il posto dei Giochi continentali di {p['noc']} "
                                 f"({p['a']['nome'] if p['a'] else ''}) perché {p['noc']} ha anche un posto "
                                 f"dal ranking individuale; si riassegna")
                    assegna_giochi(s, g, p["cont"], riassegnazione=True)
                    cambiato = True
                elif p["via"] == "W" and p["noc"] and any(
                        q is not p and q["noc"] == p["noc"] and q["via"] in ("I", "IR", "G") for q in s.attivi(g)):
                    p["annullato"] = True
                    notes.append(f"{GENERI[g]}: annullato il posto New Flag del World Triathlon Ranking di "
                                 f"{p['noc']} ({p['a']['nome']}) perché {p['noc']} ha anche un altro posto; si riassegna")
                    assegna_wr(s, g, p["cont"], riassegnazione=True)
                    cambiato = True
            if not cambiato:
                break

    # riserve: i prossimi atleti dell'IOQR che prenderebbero un posto non confermato (F.1)
    riserve = {}
    for g in ("M", "F"):
        riserve[g] = []
        salva = s.pointer[g]
        while len(riserve[g]) < RISERVE:
            a = s.prossimo_ioqr(g, salta_gia_dentro=True)
            if not a:
                break
            riserve[g].append(a)
        s.pointer[g] = salva
    return s, riserve


def cont_nome(c):
    return {"Africa": "dell'Africa", "Americhe": "delle Americhe", "Asia": "dell'Asia",
            "Europa": "d'Europa", "Oceania": "dell'Oceania"}[c]


def dati_atleta(s, g, a):
    """Dati dell'atleta dal ranking olimpico individuale; se non c'è, rank e punti restano vuoti."""
    x = next((r for r in s.data["ioqr"][g] if r["id"] == a["id"]), None)
    if x:
        return dict(x)
    aa = dict(a)
    aa["rank"], aa["punti"] = None, None
    return aa


def al_ioqr(s, g, motivo, extra):
    """Un posto New Flag senza NOC idonei torna al prossimo atleta del ranking olimpico individuale."""
    a = s.prossimo_ioqr(g, salta_migliori=False)
    if not a:
        s.dai(g, "IR", "", None, motivo + "; nessun atleta disponibile nell'IOQR", status="In attesa", extra=extra)
        return
    k = s.conta(g, a["noc"]) + 1
    s.dai(g, "IR", a["noc"], a, f"{motivo}: va al prossimo atleta del ranking olimpico individuale "
                                f"(n.{a['rank']}); {k}º posto {a['noc']}", extra=extra)


def assegna_giochi(s, g, cont, riassegnazione=False):
    info = s.data["giochi"].get((cont, g))
    extra = {"cont": cont}
    if not info:
        s.dai(g, "G", "", None, f"{NOMI_GIOCHI[cont]} non ancora disputati: il posto andrà al primo NOC "
                                f"{cont_nome(cont)} non ancora qualificato", status="In attesa", extra=extra)
        return
    for arr in info["arrivi"]:
        noc = arr["noc"]
        if noc in NON_NOC or NOC_CONT.get(noc) != cont or s.conta(g, noc) > 0:
            continue
        # l'atleta deve essere eleggibile: lo cerco nel World Triathlon Ranking per nome e NOC
        a = s.wr_nome.get((g, noc, chiave_nome(arr["nome"])))
        if not a or not s.eleggibile(g, a):
            continue
        aa = dati_atleta(s, g, a)
        s.dai(g, "G", noc, aa, f"{info['giochi']}: {arr['pos']}º all'arrivo, primo atleta di un NOC "
                               f"{cont_nome(cont)} non ancora qualificato"
                               + (" (riassegnazione)" if riassegnazione else ""), extra=extra)
        return
    al_ioqr(s, g, f"{info['giochi']}: nessun NOC idoneo non ancora qualificato", extra)


def assegna_wr(s, g, cont, riassegnazione=False):
    extra = {"cont": cont}
    for a in s.data["wr"][g]:
        if a["rank"] > TOP_WR:
            break
        if a["cont"] != cont or s.conta(g, a["noc"]) > 0 or not s.eleggibile(g, a):
            continue
        aa = dati_atleta(s, g, a)
        s.dai(g, "W", a["noc"], aa, f"n.{a['rank']} del World Triathlon Ranking, primo atleta di un NOC "
                                    f"{cont_nome(cont)} non ancora qualificato"
                                    + (" (riassegnazione)" if riassegnazione else ""), extra=extra)
        return
    al_ioqr(s, g, f"World Triathlon Ranking: nessun NOC {cont_nome(cont)} idoneo non ancora qualificato", extra)


# ------------------------------------------------------------------ righe, staffette e file
ORDINE_VIA = ["H", "M26", "M27", "M27P", "SC", "S", "I", "IR", "U", "G", "W", "R", "T"]


def to_rows(s, riserve, rankdate):
    rows = []
    for g in ("M", "F"):
        n = 0
        for p in s.attivi(g):
            n += 1
            a = p["a"]
            base = {"g": g, "gender": GENERI[g], "cat": EVENTO[g], "disc": "Individuale",
                    "via_k": p["via"], "via": VIA[p["via"]], "tipo": TIPO[p["via"]], "status": p["stato"],
                    "detail": p["dettaglio"], "rankdate": rankdate, "posto": n}
            if a is None:
                base.update({"name": f"(da assegnare) {VIA[p['via']]}" + (f" n.{p['n_univ']}" if p.get("n_univ") else "")
                             + (f" · {p['cont']}" if p.get("cont") and p["via"] == "G" else ""),
                             "noc": p["noc"], "code": "", "country": "", "cont": p.get("cont", "") if p["via"] == "G" else "",
                             "rank": None, "points": None, "born": None, "wr": None})
            else:
                base.update({"name": a["nome"], "noc": a["noc"], "code": a.get("code", a["noc"]),
                             "country": a.get("paese", ""), "cont": NOC_CONT.get(a["noc"], ""),
                             "rank": a.get("rank"),
                             "points": a.get("punti"), "born": a.get("nato"),
                             "wr": s.wr_rank.get((g, a["id"]))})
            rows.append(base)
        for k, a in enumerate(riserve[g], 1):
            rows.append({"g": g, "gender": GENERI[g], "cat": EVENTO[g], "disc": "Individuale", "via_k": "R",
                         "via": VIA["R"], "tipo": "R", "status": "Candidato", "rankdate": rankdate, "posto": None,
                         "detail": f"{k}ª riserva: prossimo atleta del ranking olimpico se un posto non viene "
                                   f"confermato (F.1), rispettando il massimo per NOC",
                         "name": a["nome"], "noc": a["noc"], "code": a["code"], "country": a["paese"],
                         "cont": a["cont"], "rank": a["rank"], "points": a["punti"], "born": a["nato"],
                         "wr": s.wr_rank.get((g, a["id"]))})
    # staffetta mista: ogni NOC con almeno 2 uomini e 2 donne qualificati può schierare una squadra (B.2)
    for noc, info in staffette(s).items():
        rows.append({"g": "X", "gender": "Misto", "cat": EVENTO["X"], "disc": "Staffetta mista", "via_k": "T",
                     "via": VIA["T"], "tipo": "T", "status": s.ok, "rankdate": rankdate, "posto": None,
                     "detail": f"{info['M']} uomini e {info['F']} donne qualificati; "
                               + (f"n.{info['mroqr']} del ranking olimpico di staffetta" if info["mroqr"]
                                  else "non classificato nel ranking olimpico di staffetta"),
                     "name": f"Squadra {info['paese']}", "noc": noc, "code": noc, "country": info["paese"],
                     "cont": NOC_CONT.get(noc, ""), "rank": info["mroqr"], "points": info["punti"], "born": None,
                     "wr": None})
    return rows


def staffette(s):
    mr = {sq["noc"]: sq for sq in s.data["mroqr"]}
    paesi = {}
    for g in ("M", "F"):
        for p in s.attivi(g):
            if p["a"]:
                paesi.setdefault(p["noc"], p["a"].get("paese", p["noc"]))
    out = {}
    for noc in sorted({p["noc"] for g in ("M", "F") for p in s.attivi(g) if p["noc"]}):
        m, f = s.conta("M", noc), s.conta("F", noc)
        if m >= 2 and f >= 2:
            sq = mr.get(noc)
            out[noc] = {"M": m, "F": f, "mroqr": sq["rank"] if sq else None, "punti": sq["punti"] if sq else None,
                        "paese": sq["paese"] if sq else paesi.get(noc, noc)}
    return dict(sorted(out.items(), key=lambda kv: (kv[1]["mroqr"] or 999, kv[0])))


def print_rows(rows):
    cur = None
    for r in rows:
        if r["cat"] != cur:
            cur = r["cat"]
            print(f"\n=== {cur} ===")
        rk = r["rank"] if r["rank"] is not None else "-"
        pos = r["posto"] if r["posto"] else " "
        print(f"{pos!s:>3} {r['tipo']} | {rk!s:>4} | {r['name'][:32]:<32} | {r['noc']:<3} | {r['status']:<11} | {r['via']}")


def build_json(s, rows, rankdate):
    cats = {}
    for g in ("M", "F"):
        cats[g] = {"genere": g, "nome": EVENTO[g], "classificati_ioqr": len(s.data["ioqr"][g]),
                   "posti": [], "riserve": []}
        for r in rows:
            if r["g"] != g:
                continue
            item = {"posto": r["posto"], "nome": r["name"], "noc": r["noc"], "codice": r["code"],
                    "paese": r["country"], "continente": r["cont"], "rank": r["rank"], "punti": r["points"],
                    "wr": r["wr"], "nato": r["born"], "tipo": r["tipo"], "via": r["via"], "stato": r["status"],
                    "nota": r["detail"], "attesa": r["rank"] is None and r["tipo"] != "R" and not r["noc"]}
            (cats[g]["riserve"] if r["tipo"] == "R" else cats[g]["posti"]).append(item)
    annullati = [{"genere": g, "nome": p["a"]["nome"] if p["a"] else "", "noc": p["noc"], "via": VIA[p["via"]]}
                 for g in ("M", "F") for p in s.posti[g] if p.get("annullato")]
    st = [{"noc": noc, "paese": v["paese"], "uomini": v["M"], "donne": v["F"], "rank_mroqr": v["mroqr"],
           "punti": v["punti"]} for noc, v in staffette(s).items()]
    return {"aggiornato": rankdate, "pubblicazione_ranking": s.data["pubblicato"], "cutoff": CUTOFF.isoformat(),
            "posti_per_genere": POSTI_GENERE, "campioni_2027": CAMPIONI_2027,
            "categorie": cats, "staffette": st, "annullati": annullati, "note": s.notes}


# --------------------------------------------------------------------- Notion
COLUMNS = {
    "gender": ["Genere"], "disc": ["Disciplina"], "cat": ["Evento", "Categoria"],
    "via": ["Via di qualificazione", "Via"], "status": ["Stato"], "noc": ["NOC"],
    "code": ["Codice WT"], "country": ["Nazione", "Paese"], "cont": ["Continente"],
    "rank": ["Ranking"], "points": ["Punti"], "born": ["Anno di nascita"], "detail": ["Dettagli"],
    "rankdate": ["Data classifica"], "sim": ["Simulazione"],
}
OPTIONAL = {"disc", "cat", "code", "country", "cont", "points", "born", "detail", "rankdate", "sim"}


def notion(method, path, **kwargs):
    r = None
    for attempt in range(4):
        r = requests.request(method, "https://api.notion.com/v1" + path, headers=NOTION_HEADERS,
                             timeout=30, **kwargs)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(float(r.headers.get("Retry-After", 2)) + attempt)
            continue
        break
    if not r.ok:
        raise RuntimeError(f"Notion ha risposto {r.status_code}: {r.text[:400]}")
    return r.json()


def read_schema():
    props = notion("GET", f"/databases/{DATABASE_ID}")["properties"]
    by_name = {n.strip().lower(): (n, p["type"]) for n, p in props.items()}
    mapping, missing = {}, []
    for key, options in COLUMNS.items():
        hit = next((by_name[o.lower()] for o in options if o.lower() in by_name), None)
        if hit:
            mapping[key] = hit
        elif key in OPTIONAL:
            print(f"Nota: nel database non c'e' la colonna '{options[0]}': quel dato non verra' scritto.")
        else:
            missing.append(options[0])
    titles = [(n, p["type"]) for n, p in props.items() if p["type"] == "title"]
    mapping["name"] = titles[0]
    if missing:
        die("nel database non trovo queste colonne: " + ", ".join(missing)
            + ". Colonne presenti: " + ", ".join(props.keys()))
    return mapping


def notion_value(ptype, value):
    if ptype == "number":
        return {"number": None if value in (None, "") else float(value)}
    value = "" if value is None else str(value)
    if ptype == "title":
        return {"title": [{"text": {"content": value[:2000]}}]}
    if ptype == "rich_text":
        return {"rich_text": [{"text": {"content": value[:2000]}}]}
    if ptype == "select":
        return {"select": {"name": value.replace(",", " ")[:100]} if value else None}
    if ptype == "date":
        return {"date": {"start": value} if value else None}
    raise RuntimeError(f"Tipo di colonna non gestito: {ptype}. Usa testo, numero, selezione o data.")


def archive_all_rows():
    cursor, n = None, 0
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = notion("POST", f"/databases/{DATABASE_ID}/query", json=body)
        for page in data["results"]:
            notion("PATCH", f"/pages/{page['id']}", json={"archived": True})
            n += 1
            time.sleep(0.3)
        if not data.get("has_more"):
            return n
        cursor = data["next_cursor"]


def write_rows(mapping, rows, sim_label):
    done = errors = 0
    for r in rows:
        values = dict(r)
        values["sim"] = sim_label
        props = {name: notion_value(ptype, values.get(key, "")) for key, (name, ptype) in mapping.items()}
        try:
            notion("POST", "/pages", json={"parent": {"database_id": DATABASE_ID}, "properties": props})
            done += 1
            if done % 50 == 0:
                print(f"  ... scritte {done} righe", flush=True)
            time.sleep(0.35)
        except RuntimeError as e:
            errors += 1
            print(f"  Errore su {r['name']}: {e}")
    return done, errors


# ----------------------------------------------------------------------- main
def main():
    if not DRY_RUN and (not NOTION_TOKEN or not DATABASE_ID):
        die("mancano NOTION_TOKEN o NOTION_DATABASE_ID (controlla i Secrets su GitHub).")
    print("Leggo i ranking di World Triathlon (triathlon.org/world-rankings) ...")
    notes = []
    data = load_data(notes)
    if not all(data["ioqr"].values()) or not data["mroqr"]:
        die("non sono riuscito a leggere i ranking olimpici.")
    s, riserve = simula(data)
    s.notes[:0] = notes
    s.notes.append("Russia e Bielorussia sono contate come gli altri NOC (scelta del progetto).")
    s.notes.append("Singapore compare come SGP nei ranking di World Triathlon: qui è contata con il codice olimpico SIN.")
    if not CAMPIONI_2027:
        s.notes.append("Mondiale di staffetta 2027 non ancora disputato: il posto è una PROIEZIONE (primo NOC del "
                       "ranking olimpico di staffetta non ancora qualificato). World Triathlon, nella sua simulazione, "
                       "usa invece il campione 2025 (Australia).")
    rankdate = today().isoformat()
    rows = to_rows(s, riserve, rankdate)
    print_rows(rows)
    print()
    for g in ("M", "F"):
        att = s.attivi(g)
        print(f"{GENERI[g]}: {len(att)} posti su {POSTI_GENERE} "
              f"({sum(1 for p in att if p['noc'])} con NOC, {sum(1 for p in att if not p['noc'])} in attesa); "
              f"{len({p['noc'] for p in att if p['noc']})} NOC")
    print(f"Squadre di staffetta mista possibili: {len(staffette(s))}")
    print()
    for n in s.notes:
        print("NOTA:", n)
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(build_json(s, rows, rankdate), f, ensure_ascii=False, indent=1)
    print(f"\nFile per la pagina grafica scritto: {JSON_OUT}")
    if DRY_RUN:
        print(f"\nProva terminata: {len(rows)} righe preparate, non e' stato scritto nulla su Notion.")
        return
    mapping = read_schema()
    if MODALITA.startswith("sostit"):
        print(f"Modalita' sostituzione: archiviate {archive_all_rows()} righe della simulazione precedente.")
    sim_label = datetime.now().strftime("%Y-%m-%d %H:%M")
    done, errors = write_rows(mapping, rows, sim_label)
    print(f"\nFatto. Righe scritte: {done}. Errori: {errors}. Simulazione: {sim_label}.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    code = 0
    try:
        main()
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
