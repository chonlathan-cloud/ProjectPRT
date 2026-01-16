from datetime import timedelta
import logging
from google.cloud import storage
from app.core.settings import settings

logger = logging.getLogger(__name__)

def _get_storage_client():
    # Prefer explicit service account JSON; fallback to default credentials (Cloud Run).
    credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if credentials_path:
        return storage.Client.from_service_account_json(
            json_credentials_path=credentials_path,
            project=settings.GOOGLE_CLOUD_PROJECT
        )
    return storage.Client(project=settings.GOOGLE_CLOUD_PROJECT)
def generate_signed_upload_url(object_name: str, content_type: str) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)

    # Generate a v4 signed URL for uploading a blob as a PUT request.
    # A content type header is required to upload through the signed URL.
    url = blob.generate_signed_url(
        version="v4",
        method="PUT",
        expiration=timedelta(seconds=settings.SIGNED_URL_EXPIRATION_SECONDS),
        content_type=content_type,
    )
    return url

def generate_signed_download_url(object_name: str) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)

    # Generate a v4 signed URL for downloading a blob as a GET request.
    url = blob.generate_signed_url(
        version="v4",
        method="GET",
        expiration=timedelta(seconds=settings.SIGNED_URL_EXPIRATION_SECONDS)
    )
    return url


def generate_download_url(object_name: str) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)
    try:
        return blob.generate_signed_url(
            version="v4",
            method="GET",
            expiration=timedelta(seconds=settings.SIGNED_URL_EXPIRATION_SECONDS)
        )
    except AttributeError:
        logger.warning("Signed URL unavailable; falling back to public URL.")
        return blob.public_url

def upload_bytes(object_name: str, data: bytes, content_type: str = "application/pdf") -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)
    blob.upload_from_string(data, content_type=content_type)
    return f"gs://{settings.GCS_BUCKET_NAME}/{object_name}"
