from datetime import timedelta
import logging

from google.auth import default as google_auth_default
from google.auth import iam
from google.auth.transport import requests
from google.cloud import storage
from google.oauth2 import service_account

from app.core.settings import settings

logger = logging.getLogger(__name__)

def _get_storage_client():
    # Prefer explicit service account JSON; fallback to default credentials (Cloud Run).
    credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if credentials_path:
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path
        )
        return storage.Client(
            credentials=credentials,
            project=settings.GOOGLE_CLOUD_PROJECT
        )
    return storage.Client(project=settings.GOOGLE_CLOUD_PROJECT)


def _get_signing_credentials():
    credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if credentials_path:
        return service_account.Credentials.from_service_account_file(
            credentials_path
        )

    # Use IAM signBlob for environments without private keys (e.g., Cloud Run).
    credentials, _project_id = google_auth_default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    request = requests.Request()
    credentials.refresh(request)

    service_account_email = getattr(credentials, "service_account_email", None)
    if not service_account_email:
        raise RuntimeError(
            "Default credentials have no service_account_email. "
            "Set GOOGLE_APPLICATION_CREDENTIALS to a service account key JSON, "
            "or run on a service account that can sign URLs."
        )

    signer = iam.Signer(request, credentials, service_account_email)
    return service_account.Credentials(
        signer=signer,
        service_account_email=service_account_email,
        token_uri="https://oauth2.googleapis.com/token",
    )
def generate_signed_upload_url(object_name: str, content_type: str) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)

    # Generate a v4 signed URL for uploading a blob as a PUT request.
    # A content type header is required to upload through the signed URL.
    signing_credentials = _get_signing_credentials()
    url = blob.generate_signed_url(
        version="v4",
        method="PUT",
        expiration=timedelta(seconds=settings.SIGNED_URL_EXPIRATION_SECONDS),
        content_type=content_type,
        credentials=signing_credentials,
        service_account_email=getattr(signing_credentials, "signer_email", None),
    )
    return url

def generate_signed_download_url(object_name: str) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)

    # Generate a v4 signed URL for downloading a blob as a GET request.
    signing_credentials = _get_signing_credentials()
    url = blob.generate_signed_url(
        version="v4",
        method="GET",
        expiration=timedelta(seconds=settings.SIGNED_URL_EXPIRATION_SECONDS),
        credentials=signing_credentials,
        service_account_email=getattr(signing_credentials, "signer_email", None),
    )
    return url


def generate_download_url(object_name: str) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)
    try:
        signing_credentials = _get_signing_credentials()
        return blob.generate_signed_url(
            version="v4",
            method="GET",
            expiration=timedelta(seconds=settings.SIGNED_URL_EXPIRATION_SECONDS),
            credentials=signing_credentials,
            service_account_email=getattr(signing_credentials, "signer_email", None),
        )
    except AttributeError:
        logger.warning("Signed URL unavailable; falling back to public URL.")
        return blob.public_url

def generate_public_url(object_name: str) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)
    return blob.public_url


def upload_bytes(
    object_name: str,
    data: bytes,
    content_type: str = "application/pdf",
    make_public: bool = False,
) -> str:
    client = _get_storage_client()
    bucket = client.bucket(settings.GCS_BUCKET_NAME)
    blob = bucket.blob(object_name)
    blob.upload_from_string(data, content_type=content_type)
    if make_public:
        try:
            blob.make_public()
        except Exception as exc:
            logger.warning("Failed to make object public: %s", exc)
    return f"gs://{settings.GCS_BUCKET_NAME}/{object_name}"
