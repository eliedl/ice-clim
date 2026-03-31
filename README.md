# ice-clim — Climatologie des glaces de mer

Projet R&D de climatologie des glaces de mer du golfe du Saint-Laurent, à partir des données journalières du Service canadien des glaces (SCG) au format SIGRID-3.

---

## Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- Python 3.13+ avec `venv`
- Archive SCG : `D:/professionnel/ice-raw-data-MPO`

---

## Démarrage rapide

### 1. Cloner le dépôt et créer l'environnement Python

```bash
git clone <repo-url>
cd ice-clim
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
```

### 2. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Éditer `.env` et renseigner les valeurs :

```
POSTGRES_DB=ice_clim
POSTGRES_USER=postgres
POSTGRES_PASSWORD=ice_clim_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5434
```

### 3. Démarrer le conteneur PostGIS

```bash
docker compose up -d
```

Vérifier que le serveur est prêt :

```bash
docker exec ice-clim-db pg_isready -U postgres
# /var/run/postgresql:5432 - accepting connections
```

### 4. Option A — Restaurer depuis une sauvegarde

Si vous disposez d'un fichier `ice_clim_YYYYMMDD.dump` (pg_dump format custom) :

```bash
# Copier le dump dans le conteneur
docker cp ice_clim_YYYYMMDD.dump ice-clim-db:/var/tmp/ice_clim.dump

# Restaurer (requiert PostgreSQL 16+)
MSYS_NO_PATHCONV=1 docker exec -e PGPASSWORD=<mot_de_passe> ice-clim-db \
    pg_restore -U postgres -d ice_clim /var/tmp/ice_clim.dump
```

### 4. Option B — Ingérer depuis l'archive brute

Ingérer les shapefiles GEC_D_* (hivers 2011–2020) depuis l'archive SCG :

```bash
.venv/Scripts/python.exe scripts/ingest_gec_d.py
```

Le script est reprise possible (*resumable*) : il ignore les dates déjà ingérées si interrompu.

---

## Structure du projet

```
ice-clim/
├── scripts/
│   ├── ingest_gec_d.py            # Ingestion des shapefiles journaliers
│   └── first_ice_climatology.py   # Climatologie de la date d'englacement
├── docs/
│   ├── DECISIONS.md               # Journal des décisions scientifiques
│   ├── first_ice_sept-iles.png    # Carte produite
│   └── ...
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Base de données

| Paramètre | Valeur |
|-----------|--------|
| Image | `postgis/postgis:16-3.4` |
| Conteneur | `ice-clim-db` |
| Port | `5434` (hôte) → `5432` (conteneur) |
| Base | `ice_clim` |
| Table principale | `public.sgrda` |
| Volume | `ice-clim_pgdata` (persistant) |

### Schéma de la table `sgrda`

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | BIGSERIAL | Clé primaire |
| `region` | TEXT | Région SCG (ex. `AWIS28`) |
| `t1` | TIMESTAMPTZ | Date d'observation (18:00 UTC) |
| `ct` | TEXT | Concentration totale (code SIGRID-3, ex. `50` = 5/10) |
| `ca/cb/cc` | TEXT | Concentrations partielles |
| `sa/sb/sc` | TEXT | Stade de développement |
| `fa/fb/fc` | TEXT | Forme de glace |
| `geometry` | MULTIPOLYGON 4326 | Géométrie du polygone |

> **Note encodage CT :** les valeurs CT sont des codes à deux chiffres (`00`–`92`), pas des entiers 0–10. Utiliser `ct::int >= 50` pour filtrer CT > 4/10.

---

## Sauvegarde et restauration

```bash
# Créer une sauvegarde
MSYS_NO_PATHCONV=1 docker exec -e PGPASSWORD=<mot_de_passe> ice-clim-db \
    pg_dump -U postgres -d ice_clim -F c -f /var/tmp/ice_clim.dump

# Copier vers le disque
docker cp ice-clim-db:/var/tmp/ice_clim.dump D:/professionnel/iceDB/ice_clim_$(date +%Y%m%d).dump
```
