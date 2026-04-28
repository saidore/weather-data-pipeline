# ingest.py
# Author information: Sai Dore
# Calls Open Meteo API for each city and year combination, stores raw JSON docs in MongoDB and backs up these files in MinIO.

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from pymongo import MongoClient
from api_client import OpenMeteoClient
from storage import ObjectStorageClient

logger = logging.getLogger("weather_pipeline")

# API fetching: calls API and builds raw docs from response
def fetch_city_year(client: OpenMeteoClient, city: dict, year: int, daily_vars: list[str], tz: str= 'auto')-> dict:
    """Fetches weather data for one city and one calendar year combination. Returns a MongoDB document with
        metadata wrapping the raw API response."""
    
    start_date = f"{year}-01-01"
    end_date = f"{year}-12-31"
    api_response = client.get_weather_data(latitude=city["latitude"], longitude=city["longitude"], start_date=start_date,
        end_date=end_date, daily_vars=daily_vars, timezone=tz)  # Wraps API response in a larger document with metadata
    # Adds metadata to the API response making it easier to trace 
    document = {"city": city["name"], "latitude": city["latitude"], "longitude": city["longitude"], "start_date": start_date,        #This is the real format，Open-Meteo API initially returns this
        "end_date": end_date, "ingested_at": datetime.now(timezone.utc).isoformat(), "api_response": api_response}
    
    logger.info("Fetched data for %s (%s)", city["name"], year)
    return document

def fetch_all(cities: list[dict], start_year: int, end_year: int, daily_vars: list[str], tz: str = "auto") -> list[dict]:
    """Fetch data for every city and year combination."""

    client = OpenMeteoClient()
    documents = []
    for city in cities:  # Iterate through each city year combo
        for year in range(start_year, end_year+1):
            try:
                doc = fetch_city_year(client, city, year, daily_vars, tz)
                documents.append(doc)  # Collect documents into list
            except Exception as e:
                logger.exception("Failed to fetch %s/%s: %s", city["name"], year, e)
    return documents

# MongoDB storage: stores raw API documents
def store_to_mongodb(documents: list[dict], mongo_uri: str, db_name, collection_name: str) -> int:
    """Insert the raw documents into MongoDB. Returns number of the documents inserted."""
    
    # Get requested database and collection
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
    
    inserted = 0
    for doc in documents:
        # Iterate through each doc and use city and start date as key to avoid duplicates
        existing = collection.find_one({"city": doc["city"],"start_date": doc["start_date"],"end_date": doc["end_date"]})
        
        if existing:  # Document exist already so skip it
            logger.info("Document already exists for %s (%s – %s), skipping.", doc["city"], doc["start_date"], doc["end_date"])
            continue
        collection.insert_one(doc)   # Insert only new docs to collection to avoid re-inserting same raw data
        inserted+=1
        logger.info("Inserted MongoDB document for %s (%s – %s).", doc["city"], doc["start_date"], doc["end_date"])
    
    # Close MongoDB connection
    client.close()
    logger.info("MongoDB storage complete — %d new documents.", inserted)
    return inserted  # Return number of new inserted docs

# MinIO backup (write-only): saves backup copies of raw docs to MinIO
def backup_to_minio(documents: list[dict], storage_client: ObjectStorageClient, bucket: str) -> int: 
    """ Save each raw document as a JSON file in MinIO. This is just used as a backup used for manual recovery."""

    storage_client.ensure_bucket(bucket)  # Make sure bucket exists
    uploaded = 0
    # Build safe file name for each doc, write to JSON and upload
    for doc in documents:
        # Each city/year combination unique for each file so use for name
        city = doc["city"].lower().replace(" ", "_")
        year = doc["start_date"][:4]
        object_name = f"raw/{city}_{year}.json"
        # Write data to a temporary JSON file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
            json.dump(doc, tmp, indent=2, default=str)
            tmp_path = tmp.name
        # Upload file to MinIO
        storage_client.upload_file(bucket_name=bucket, object_name=object_name, file_path=tmp_path, content_type="application/json")
        Path(tmp_path).unlink(missing_ok=True)  # Deletes temp file, prevents error if file non-existent
        uploaded += 1
    
    logger.info("MinIO backup complete — %d files uploaded.", uploaded)
    return uploaded