# etl.py
# Author: Xitai 

from datetime import datetime
# import pytz coz we use datetime.fromisoformat instead
from psycopg2.extras import execute_values
import os
import yaml
import psycopg2
from pymongo import MongoClient
from pathlib import Path

# location cache to avoid repeat queries
LOCATION_CACHE = {}


INSERT_LOCATION_SQL = '''
    INSERT INTO locations (city, latitude, longitude, elevation, timezone)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (city) DO UPDATE SET
        latitude = EXCLUDED.latitude,
        longitude = EXCLUDED.longitude,
        elevation = EXCLUDED.elevation,
        timezone = EXCLUDED.timezone
    RETURNING id;
    '''

INSERT_WEATHER_SQL = '''
    INSERT INTO weather_observations
    (location_id, time, temp_c, temp_f, precip_mm, precip_inch, wind_speed_kmh, wind_speed_mph)
    VALUES %s
    ON CONFLICT (location_id, time) DO NOTHING
    '''


def load_config():
    '''
    Read config/config.yaml, returns mongodb + postgres config
    '''
    base_dir = Path(__file__).resolve().parents[1]
    config_path = base_dir / "config" / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def get_connection(pg_conf):
    '''
    Connect to PostgreSQL
    '''
    conn = psycopg2.connect(
        host=pg_conf["host"],
        dbname=pg_conf["database"],
        user=pg_conf["user"],
        password=pg_conf["password"],
        port=pg_conf["port"]
    )
    return conn

def ensure_schema(conn): #added by Zijiang
    '''
    Run schema.sql to create tables if they don't exist.
    '''
    base_dir = Path(__file__).resolve().parents[1]
    schema_path = base_dir / "schema.sql"
    with open(schema_path, "r") as f:
        sql = f.read()

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        conn.commit()
    except psycopg2.errors.DuplicateTable:
        # Tables already exist, fine
        conn.rollback()
    cursor.close()

def get_mongo_collection(mongo_conf):
    '''
    Connect to MongoDB
    '''
    uri = f"mongodb://{mongo_conf['host']}:{mongo_conf['port']}/"
    client = MongoClient(uri)
    db = client[mongo_conf["database"]]
    collection = db[mongo_conf["collection"]]
    return client, collection


def get_mongo_docs(collection):
    '''
    Get all documents from MongoDB
    '''
    return collection.find({})


# Unit conversion
def c_to_f(c):
    if c is None:
        return None
    return round(c * 9 / 5 + 32, 2)

def mm_to_inch(mm):
    if mm is None:
        return None
    return round(mm / 25.4, 4)

def kmh_to_mph(kmh):
    if kmh is None:
        return None
    return round(kmh / 1.609, 2)

def get_or_create_location(cursor, city, lat, lon, elevation, timezone, location_cache):
    '''
    Find or create city, return id
    Use city as cache key + unique constraint
    '''
    if city in location_cache:
        return location_cache[city]

    cursor.execute(INSERT_LOCATION_SQL, (city, lat, lon, elevation, timezone))
    location_id = cursor.fetchone()[0]

    location_cache[city] = location_id
    return location_id

def transform_document(cursor, doc):
    '''
    return [(location_id, time, temp_c, temp_f, precip_mm, precip_inch, wind_speed_kmh, wind_speed_mph)]
    '''
    # ------------ location ------------
    city = doc["city"]
    lat = doc["latitude"]
    lon = doc["longitude"]
    api = doc["api_response"]
    elevation = api.get("elevation")
    timezone = api.get("timezone")
    location_id = get_or_create_location(cursor, city, lat, lon, elevation, timezone, LOCATION_CACHE)

    # ------------ data ------------
    daily = api.get("daily", {})
    data_time = daily.get("time", [])
    temps = daily.get("temperature_2m_mean", [])
    precips = daily.get("precipitation_sum", [])
    winds = daily.get("wind_speed_10m_max", [])

    rows = []
    for i, t_str in enumerate(data_time):
        t_c = temps[i] if i < len(temps) else None
        p_mm = precips[i] if i < len(precips) else None
        w_kmh = winds[i] if i < len(winds) else None

        rows.append((
            location_id,
            datetime.fromisoformat(t_str),
            t_c, c_to_f(t_c),
            p_mm, mm_to_inch(p_mm),
            w_kmh, kmh_to_mph(w_kmh),
        ))

    return rows

def batch_insert(cursor, rows):
    '''
    Batch insert
    '''
    if not rows:
        return 0
    execute_values(
        cursor,
        INSERT_WEATHER_SQL,
        rows,
        page_size=1000
    )
    return len(rows)

def run_etl():
    config = load_config()

    conn = get_connection(config["postgres"])
    ensure_schema(conn)  # added by ZIjiang
    mongo_client, mongo_collection = get_mongo_collection(config["mongodb"])
    cursor = conn.cursor()

    mongo_docs = get_mongo_docs(mongo_collection)

    for doc in mongo_docs:
        rows = transform_document(cursor, doc)
        batch_insert(cursor, rows)

    conn.commit()
    mongo_client.close()
    cursor.close()
    conn.close()