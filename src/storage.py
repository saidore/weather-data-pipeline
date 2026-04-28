# storage.py
# Author information: Sai Dore
# Handles pipeline's connection to MinIO object storage, makes sure buckets exist and uploads files into MinIO. 

from pathlib import Path
import logging
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger("weather_pipeline")

class ObjectStorageClient:
    """Wrapper around MinIO/S3-compatible client for file uploads."""
    
    def __init__(self, endpoint: str, access_key: str, secret_key: str, secure: bool = False):
        """ Create and store a MinIO client connection. """
        
        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        
    def ensure_bucket(self, bucket_name: str):
        """Create bucket if missing; do nothing if it already exists."""
        
        try:
            found = self.client.bucket_exists(bucket_name)  # Check whether bucket already exists

            if found:
                logger.info("Bucket already exists: %s", bucket_name)
                return

            self.client.make_bucket(bucket_name)  # Create bucket only when missing
            logger.info("Created bucket: %s", bucket_name)

        except S3Error as e:   # Storage-related error
            # MinIO may still raise these on repeated/racing create requests
            if e.code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                logger.info("Bucket already available: %s", bucket_name)
                return

            raise RuntimeError(f"Failed to ensure bucket '{bucket_name}': {e}") from e

    def upload_file(self, bucket_name: str, object_name: str, file_path: str|Path, content_type: str = "application/octet-stream"):
        """Upload one local file into the specified bucket."""
        
        try:
            file_path = Path(file_path)
            # Upload file into object storage
            self.client.fput_object(bucket_name=bucket_name, object_name=object_name, file_path=str(file_path), content_type=content_type)
            logger.info("Uploaded file to object storage via bucket=%s, object=%s", bucket_name, object_name)

        except S3Error as e:   # Storage-related error
            raise RuntimeError(f"Failed to upload '{file_path}' to bucket '{bucket_name}': {e}") from e

def build_object_name(prefix: str, file_path: str|Path) -> str:
    """Build object-storage key."""
    file_name = Path(file_path).name  # Name of csv/JSON file
    return f"{prefix.strip('/')}/{file_name}"  # Key such as raw/rawfile.json or curated/curatedfile.csv