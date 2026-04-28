# weather_pipeline_dag.py
# Author: Zijiang Yang
# Airflow DAG orchestrates the weather data pipeline end to end

import sys
from pathlib import Path

# # src/ is the sibling of dags/ folder. Work both on local docker-compose and on cluster GitSync
# src_dir = Path(__file__).resolve().parent.parent / "src"
# sys.path.insert(0, str(src_dir))

# src/ and config/ are siblings of the dags/ folder.
# Dynamic path resolution works in both environments(new knowledge):
# Local docker-compose: dags/weather_pipeline_dag.py -> parent.parent = /opt/airflow/
# Cluster GitSync: ..../PRJ/dags/weather_pipeline_dag.py -> parent.parent = .../PRJ/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
src_dir = PROJECT_ROOT / "src"
sys.path.insert(0, str(src_dir))
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"

from datetime import datetime, timedelta
import yaml

from airflow.models.dag import DAG
from airflow.providers.standard.operators.python import PythonOperator

from ingest import fetch_all, store_to_mongodb, backup_to_minio
from storage import ObjectStorageClient
from etl import run_etl

dag_default_args = {
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

def say_hello():
    print("Hello from the weather pipeline DAG!")

def run_ingest(ti):
    """Call Sai's fetch_all() and push the documents list to XCom."""
    with open(CONFIG_PATH) as f:
       cfg = yaml.safe_load(f)

    cities = cfg["cities"]
    daily_vars = cfg["variables"]["daily"]
    start_year = int(cfg["time_range"]["start_date"][:4])
    end_year = int(cfg["time_range"]["end_date"][:4])
    tz = cfg.get("timezone", "auto")

    docs = fetch_all(cities, start_year, end_year, daily_vars, tz)
    print(f"Fetched {len(docs)} documents")

    ti.xcom_push(key="docs", value=docs)

def run_store_mongodb(ti):
    """Pull docs from XCom and call Sai's store_to_mongodb()."""
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    mongo = cfg["mongodb"]
    mongo_uri = f"mongodb://{mongo['host']}:{mongo['port']}/"

    # Get the documents that ingest pushed to XCom
    docs = ti.xcom_pull(task_ids="ingest", key="docs")

    inserted = store_to_mongodb(docs, mongo_uri, mongo["database"], mongo["collection"])
    print(f"Inserted {inserted} new documents into MangoDB")

def run_backup_minio(ti):
    """Pull docs from XCom and call Sai's backup_to_minio()."""
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)

    minio_cfg = cfg["minio"]
    storage_client = ObjectStorageClient(
        endpoint=minio_cfg["endpoint"],
        access_key=minio_cfg["access_key"],
        secret_key=minio_cfg["secret_key"],
        secure=minio_cfg["secure"],
    )

    docs = ti.xcom_pull(task_ids="ingest", key="docs")
    uploaded = backup_to_minio(docs, storage_client, minio_cfg["bucket"])
    print(f"Uploaded {uploaded} backup files to MinIO")

def run_etl_task():
    """Call Xitai's run_etl() — reads MongoDB, writes PostgreSQL."""
    run_etl()
    print("ETL complete")

with DAG(
    default_args=dag_default_args,
    dag_id="weather_data_pipeline",
    description="Weather data pipeline: API → MongoDB → ETL → PostgreSQL",
    schedule=None,
    catchup=False,
    start_date=datetime(2026, 4, 1),
    tags=["weather", "etl"],
) as dag:

    hello = PythonOperator(
        task_id="hello",
        python_callable=say_hello,
    )

    ingest_task = PythonOperator(
        task_id="ingest",
        python_callable=run_ingest,
    )

    store_mongodb_task = PythonOperator(
        task_id="store_mongodb",
        python_callable=run_store_mongodb,
    )

    backup_minio_task = PythonOperator(
        task_id="backup_minio",
        python_callable=run_backup_minio,
    )

    etl_task = PythonOperator(
        task_id="etl",
        python_callable=run_etl_task,
    )

    hello >> ingest_task >> store_mongodb_task >> backup_minio_task >> etl_task