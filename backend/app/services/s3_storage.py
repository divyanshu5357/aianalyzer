import boto3
from botocore.exceptions import ClientError

BUCKET_NAME = "cu-custom-ai-agent-files"
AWS_REGION = "eu-north-1"

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
)


import logging

logger = logging.getLogger(__name__)

def generate_upload_url(
    object_key: str,
    content_type: str,
    expires_in: int = 3600,
) -> str:
    try:
        return s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
    except ClientError as e:
        logger.error(f"Error generating presigned URL: {e}")
        raise


def download_file(object_key: str, local_path: str) -> None:
    try:
        s3_client.download_file(
            BUCKET_NAME,
            object_key,
            local_path,
        )
    except ClientError as e:
        logger.error(f"Error downloading file from S3: {e}")
        raise


def delete_file(object_key: str) -> None:
    try:
        s3_client.delete_object(
            Bucket=BUCKET_NAME,
            Key=object_key,
        )
    except ClientError as e:
        logger.error(f"Error deleting file from S3: {e}")
        # Not raising, since this is usually cleanup
        pass


def check_object_exists(object_key: str) -> bool:
    try:
        s3_client.head_object(Bucket=BUCKET_NAME, Key=object_key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        logger.error(f"Error checking object existence: {e}")
        raise