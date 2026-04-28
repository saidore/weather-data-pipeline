# Weather Data Pipeline — Pipeline Design Document
Author: Zijiang Yang

---

## 1. Architecture

The system has three horizontal layers. Each layer owns one responsibility.

![Architecture](./flow.png)

Business logic in Layer 2 does not need to know who schedules it (Layer 1) or where it runs (Layer 3). So the same Python code can run on a developer's Mac and on the Raspberry Pi cluster without any change.

**Three zone storage.** The data path splits into three stores, each with a different role. **MongoDB** is the raw landing zone; it uses schema on read, so we store whatever JSON the API returns. **MinIO** is a write only cold backup used for disaster recovery. **PostgreSQL** is the serving layer that downstream analysts query with SQL. The ETL only reads from MongoDB. MinIO is never read by the pipeline, so it stays independent from any application bug.

---

## 2. DAG Design

File: `dags/weather_pipeline_dag.py`. The DAG has 5 tasks in linear order:

```
hello → ingest → store_mongodb → backup_minio → etl
```

`hello` is a sanity check task that confirms the DAG framework is alive. The other four tasks form the real data pipeline.

### 2.1 Why linear

`store_mongodb` and `backup_minio` could in principle run in parallel, but we keep them linear:

- **Scale.** At 8 documents per run (~160 KB), each task completes in 1 to 3 seconds. Parallelism does not save meaningful wall clock time.
- **Shared XCom.** Both downstream tasks would pull the same ~160 KB blob, doubling XCom I/O.
- **Failure semantics.** In a linear chain, if `store_mongodb` fails, neither the backup nor the ETL runs. No inconsistent state to worry about.

### 2.2 Trigger properties

| Property | Value | Rationale |
|---|---|---|
| `schedule` | `None` | Historical data is an append only operation against a closed date range; a fixed cron is inappropriate until we add incremental ingest. Planned demo value: `@weekly`. |
| `catchup` | `False` | Without this, Airflow would instantiate a DAG run for every day since `start_date`, producing hundreds of queued instances at first unpause. |
| `start_date` | `datetime(2026, 4, 1)` | Airflow requires a start date even when `schedule=None`. We use a future date to prevent accidental backfill. |
| `retries` | `2` | Covers transient API rate limits and brief DB hiccups without hiding deeper bugs. |
| `retry_delay` | `5 min` | Long enough for Open-Meteo rate limits to clear; short enough that a real failure is noticed quickly. |

### 2.3 XCom usage

`ingest` pushes the document list; `store_mongodb` and `backup_minio` both pull it. **`etl` does not use XCom**; it reads all documents from MongoDB directly (`collection.find({})`). This keeps the XCom payload bounded and lets `run_etl()` be invoked standalone for debugging.

---

## 3. Technology Justification

The project brief calls for "justification for the technologies used (advantages to others visited during the course)." Each selection is listed with its alternatives considered and the deciding factor.

| Layer | Choice | Alternatives considered | Why we picked it |
|---|---|---|---|
| **Orchestration** | Apache Airflow 3.x | Shell + cron | Required by the course. Airflow gives us DAG as code, retries, logs for each tasks, and a UI. Cron has no observability and no failure semantics beyond exit codes. |
| **Raw landing** | MongoDB 7.0 | local filesystem; DynamoDB | Schema on read matches the nested API JSON. Keeping raw and served data in separate engines means a bug in one cannot corrupt the other. Filesystem has no query API; DynamoDB is not self hostable on our cluster. |
| **Cold backup** | MinIO | AWS S3; local PVC without object API | S3 compatible API in a single ARM64 binary. AWS S3 is unavailable on the internal cluster; a raw PVC gives us no object semantics (no versioning, no immutable keys). |
| **Serving layer** | PostgreSQL 16 | MongoDB only | Mature SQL JOINs (important for geospatial queries); `UNIQUE` + `ON CONFLICT` give idempotency at the database layer. Using MongoDB alone would force analysts into MQL and lose relational integrity. |
| **Containerization** | Docker Compose (local) + K8s with Helm (cluster) | K8s only; Compose only | Compose is the easiest developer environment; K8s is the required deployment target. The same service names (`mongodb`, `postgres-data`, `minio`) are used in both, so application code is portable. |
| **DAG delivery** | GitSync sidecar (60 s pull) | Bake DAGs into the image; `kubectl cp` | `git push` to `main` is the deployment mechanism. No image rebuild per DAG change (iteration time drops from 3 minutes to 1 minute). Natively supported by the Airflow Helm chart. |
| **Airflow executor** | CeleryExecutor (local) / LocalExecutor (cluster) | Same executor in both | The local stack inherits Celery from the official Airflow template. On the Pi cluster, Redis and Celery worker pods waste constrained memory for a DAG with only five tasks, so LocalExecutor is lighter. |

---

## 4. Key Design Decisions

### 4.1 Wide table with dual unit columns, not EAV

An earlier ETL draft used an Entity Attribute Value (EAV) schema (one row per `(location, time, variable)`). We migrated to a wide table with **dual unit columns** (`temp_c` and `temp_f`, `precip_mm` and `precip_inch`, etc.) precomputed during ETL. Reason: the project brief requires "support multiple measure units, without requiring computation in the downstream applications." EAV forces analysts to filter by metric name and convert units themselves; the wide table delivers both units directly via `SELECT`. We accept that adding a new variable now requires a schema migration.

### 4.2 MinIO as a write only archive

The ETL reads only MongoDB, never MinIO. If MinIO were on the read path, the two stores would no longer fail independently: a bug that corrupts MongoDB could also corrupt the archive. Keeping MinIO write only preserves its role as the last backup we can recover from if MongoDB data is lost.

### 4.3 Idempotency at three layers

Rerunning the pipeline must not produce duplicate state. Three mechanisms, one per store:

| Layer | Mechanism |
|---|---|
| MongoDB | Application level `find_one({city, start_date, end_date})` before each `insert_one` |
| MinIO | Deterministic object key `raw/<city>_<year>.json`; S3 PUT is idempotent by key |
| PostgreSQL | `locations` uses `ON CONFLICT (city) DO UPDATE` (metadata may drift); `weather_observations` uses `ON CONFLICT (location_id, time) DO NOTHING` (observations are immutable) |

Any DAG retrigger is safe and produces identical final row counts.

### 4.4 `TIMESTAMP`, not `DATE`

The `time` column uses `TIMESTAMP` even though the current data is daily. This lets the pipeline upgrade to hourly or subhourly resolution without a schema migration. It directly satisfies the brief's requirement that the data model "accommodate higher resolution data if needed."

---

## 5. Known Limitations

| Limitation | Mitigation / Future work |
|---|---|
| Secrets are in plaintext YAML | Acceptable for classroom; migrate to Kubernetes Secrets for production |
| ETL hardcodes the variable names it reads from MongoDB | Adding a new variable like humidity requires a code change. A schema with one row per variable would avoid this, at the cost of more complex queries. |
| Single Airflow scheduler replica | No high availability; a scheduler crash pauses the pipeline until restart. |
| No automated tests | Bugs show up during manual full pipeline runs; a pytest suite is planned. |