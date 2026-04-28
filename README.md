Weather Data Pipeline README 
Author: Zijiang Yang

# Climate Change Data Pipeline

A data pipeline that fetches historical weather observations from the [Open-Meteo Archive API](https://open-meteo.com/en/docs/historical-weather-api). Raw JSON lands in **MongoDB**, with a cold backup copy in **MinIO**. The ETL reads from MongoDB, converts units, and upserts into **PostgreSQL** for downstream climate analytics. The whole flow is orchestrated by **Apache Airflow**. It runs locally with Docker Compose and on a three node Raspberry Pi Kubernetes cluster.

**Course:** Duke ECE 590 — Data Engineering, Spring 2026
**Project #3:** Climate Change
**Team:** Sai Dore · Xitai · Zijiang Yang

---

## Architecture

![Architecture](./flow.png)

## Tech Stack

| Layer | Choice | Rationale (vs. alternatives considered) |
|---|---|---|
| Orchestration | **Apache Airflow 3.x** | DAG as code, UI, retries, GitSync. Alternative: cron has no visibility and no retries. |
| Raw landing | **MongoDB 7.0** | Schema on read matches the nested API JSON. Alternative: PostgreSQL JSONB mixes raw and served data in one system. |
| Backup | **MinIO** | S3 compatible API, a single binary on Pi. Alternative: AWS S3 is not available because the cluster is internal. |
| Serving | **PostgreSQL 16** | Mature SQL JOINs, `UNIQUE` for idempotency. Alternative: MongoDB only has weaker JOIN semantics for geospatial queries. |
| Local dev | **Docker Compose** | Same service layout as the cluster, so developers get the same environment. |
| Cluster | **Kubernetes + Helm** | Course requirement; Docker images are multi arch so they run on ARM64 Pi. |
| DAG delivery | **GitSync (60 s pull)** | `git push` updates the cluster without an image rebuild. |

Full design rationale and decisions: see `docs/design.md`.

## Team & File Ownership

| Person | Role | Owns |
|---|---|---|
| **Sai Dore** | Ingestion + MinIO | `src/api_client.py`, `src/ingest.py`, `src/storage.py`, `config/config.yaml`, `deploy/minio.yaml` |
| **Xitai** | ETL + PostgreSQL | `src/etl.py`, `schema.sql`, `sample_document.json`, `deploy/postgres.yaml`, `deploy/mongodb.yaml` |
| **Zijiang Yang** | Orchestration + Infra | `dags/weather_pipeline_dag.py`, `docker-compose.yaml`, `Dockerfile`, `requirements*.txt`, `deploy/airflow-values.yaml`, `README.md`, `docs/design.md` |

Every source file has an author header, as required by the course for defense accountability.

---

## Repository Structure

```
PRJ/
├── README.md                     ← this file
├── Dockerfile                    ← custom Airflow image
├── docker-compose.yaml           ← local dev stack (10 services)
├── requirements*.txt             ← Python dependencies
├── schema.sql                    ← PostgreSQL DDL
├── sample_document.json          ← MongoDB document contract
├── Setup_Instructions.pdf        ← step by step deployment guide
│
├── config/config.yaml            ← cities, variables, time range, connections
├── dags/weather_pipeline_dag.py  ← linear DAG with 5 tasks
├── src/                          ← api_client · ingest · storage · etl · utils
├── deploy/                       ← K8s manifests + Helm values
└── docs/                         ← requirement_spec.md · design.md
```

---

## Quick Start — Local (Docker Compose)

**Prerequisites:** Docker Desktop, ~4 GB free RAM.

```bash
cd PRJ
docker-compose build            # first time only
docker-compose up -d
docker-compose ps               # wait until services report "healthy"
```

| UI | URL | Login |
|---|---|---|
| Airflow | http://localhost:8080 | `airflow` / `airflow` |
| MinIO | http://localhost:9001 | `minioadmin` / `minioadmin` |
| PostgreSQL (serving) | `postgresql://weather_user:weather_pass@localhost:5433/weather` | — |

Trigger `weather_data_pipeline` in the Airflow UI. With the default config (4 cities × 2 years), you should see:

- **MongoDB:** 8 documents in `weather_raw`
- **MinIO:** 8 JSON files under `weather-raw/raw/`
- **PostgreSQL:** 2,924 rows in `weather_observations` (4 cities × 731 days)

Verify:
```bash
docker-compose exec postgres-data psql -U weather_user -d weather -c \
  "SELECT l.city, COUNT(*) FROM weather_observations w
   JOIN locations l ON w.location_id = l.id GROUP BY l.city;"
```

Running the DAG again will not change the row count. This verifies idempotency.

---

## Deploy — Raspberry Pi Kubernetes Cluster

**Prerequisites:** `kubectl` pointed at the cluster, `helm` v3.x, a `git-credentials` Secret in the target namespace for GitSync.

```bash
# 1. Data stores
kubectl apply -f deploy/mongodb.yaml
kubectl apply -f deploy/postgres.yaml
kubectl apply -f deploy/minio.yaml

# 2. Airflow via Helm
helm repo add apache-airflow https://airflow.apache.org
helm install airflow apache-airflow/airflow -f deploy/airflow-values.yaml

# 3. Open the UI from your laptop
kubectl port-forward svc/airflow-webserver 8080:8080
```

`deploy/airflow-values.yaml` uses `LocalExecutor`, which is suitable for the limited Pi resources (no Celery, no Redis needed). GitSync pulls DAG changes from the GitLab repo every 60 seconds, and Python dependencies are installed via `extraPipPackages`. See `Setup_Instructions.pdf` for the full step by step walkthrough with screenshots.

---

## DAG Overview

| Property | Value |
|---|---|
| **File** | `dags/weather_pipeline_dag.py` |
| **DAG ID** | `weather_data_pipeline` |
| **Topology** | `hello → ingest → store_mongodb → backup_minio → etl` (linear) |
| **Schedule** | `None` (manual trigger during development; `@weekly` for demo) |
| **Retries** | 2 retries, each with a 5 minute delay |
| **Extensibility** | Add a city ⇒ edit `config/config.yaml`; no code change needed |

**Why linear rather than parallel:** `store_mongodb` and `backup_minio` both consume the same XCom payload, so parallelizing them doubles XCom I/O with no meaningful wall clock time saved at the current scale. A linear chain also has simpler failure behavior: if `store_mongodb` fails, backup and ETL never run on inconsistent state.

---

## Data Contract

Contracts are the only interfaces between teammates. Treat them as frozen:

- **MongoDB document** — see `sample_document.json`. One document = one city × one year.
- **PostgreSQL schema** — see `schema.sql`. Normalized `locations` + `weather_observations`, dual unit columns (°C/°F, mm/inch, km/h/mph), `UNIQUE (location_id, time)`, and `TIMESTAMP` instead of `DATE` so hourly resolution needs no schema migration.

**Idempotency enforced at three layers:**

- Mongo: `find_one({city, start_date, end_date})` before each insert.
- MinIO: deterministic object key `raw/<city>_<year>.json` (PUT is idempotent by key).
- PostgreSQL: `INSERT ... ON CONFLICT (location_id, time) DO NOTHING`.

