import os
from typing import BinaryIO, Dict, Optional
from urllib.parse import urlparse

import boto3
import botocore
from django.core.files.uploadedfile import UploadedFile
from s3.const import AccountType
from s3.entities import AccountConfig, AccountConfigsRegistry

SERVER_SIDE_ENCRYPTION = 'AES256'
DEFAULT_UPLOAD_FILE_MAX_FILE_SIZE = 1024 * 1024 * 5  # 5MB
DEFAULT_PRESIGNED_DATA_EXPIRATION = 60 * 10  # 10 min


def upload_file(
    *,
    account_type: AccountType,
    file: BinaryIO,
    filename: str,
    content_type: str,
    subfolder: Optional[str] = None,
    # NOTE: if there is only one bucket in account_type then there is no reason
    # to specify bucket name. Otherwise error will be rised.
    bucket: Optional[str] = None,
    client_config: Optional[botocore.config.Config] = None,
    s3_config: AccountConfigsRegistry,
) -> str:
    """Uploads file to specified S3 account and returns object url.
    If bucket uses CDN then resulting url will be CDN-based instead of direct
    S3 url.
    """

    account_config = s3_config.get_account_config(account_type)
    bucket_config = account_config.get_bucket_config(bucket=bucket)
    bucket = bucket_config.name

    if bucket_config.content_types is not None:
        if content_type not in bucket_config.content_types:
            raise ValueError(
                f'content type {content_type} is not allowed '
                f'for bucket {bucket} in account {account_type}'
            )

    if subfolder is not None:
        object_key = os.path.join(subfolder, filename)
    else:
        object_key = filename

    client = _client_factory(
        account_type=account_type,
        config=client_config,
        bucket=bucket,
        s3_config=s3_config,
    )
    # See docs for more details: https://botocore.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html?highlight=put_object#S3.Client.put_object
    kwargs = dict(
        Body=file,
        Key=object_key,
        Bucket=bucket,
        ContentType=content_type,
        ACL=bucket_config.acl,
    )
    if bucket_config.use_server_side_encryption:
        kwargs['ServerSideEncryption'] = SERVER_SIDE_ENCRYPTION
    client.put_object(**kwargs)

    if bucket_config.cdn_config is not None:
        # e.g. 'https://bmstatic.cloud' instead of 'https://s3.eu-central-1.amazonaws.com'
        object_base_url = bucket_config.cdn_config.url
    else:
        # e.g 'https://s3.eu-central-1.amazonaws.com' or
        # f'https://<bucket>.ams3.digitaloceanspaces.com'
        object_base_url = _get_endpoint_url(
            account_config=account_config,
            bucket=bucket,
        )

    if bucket_config.add_bucket_name_to_url:
        return '/'.join([object_base_url, bucket, object_key])
    else:
        return '/'.join([object_base_url, object_key])


def upload_django_in_memory_file(
    *,
    account_type: AccountType,
    s3_config: AccountConfigsRegistry,
    in_memory_file: UploadedFile,
    unique_filename_prefix: Optional[str] = None,
    preserve_original_filename: bool = True,
    new_filename: Optional[str] = None,
    subfolder: Optional[str] = None,
    # NOTE: if there is only one bucket in account_type then there is no reason
    # to specify bucket name. Otherwise error will be rised.
    bucket: Optional[str] = None,
    client_config: Optional[botocore.config.Config] = None,
) -> str:
    """Wrapper around `upload_file` for django in-memory image files uploading.
    File name, file content type, file itself - it's all inferred from
    in_memory_file (UploadedFile).
    """

    filename = new_filename or in_memory_file.name
    if preserve_original_filename:
        if unique_filename_prefix is not None:
            filename = f'{unique_filename_prefix}-{filename}'
    else:
        assert unique_filename_prefix is not None
        filename = unique_filename_prefix

    return upload_file(
        account_type=account_type,
        file=in_memory_file.file,
        filename=filename,
        content_type=in_memory_file.content_type,
        subfolder=subfolder,
        bucket=bucket,
        client_config=client_config,
        s3_config=s3_config,
    )


def upload_django_in_memory_public_image(
    *,
    in_memory_file: UploadedFile,
    s3_config: AccountConfigsRegistry,
    unique_filename_prefix: Optional[str] = None,
    preserve_original_filename: bool = True,
    new_filename: Optional[str] = None,
    subfolder: Optional[str] = None,
    bucket: Optional[str] = None,
    client_config: Optional[botocore.config.Config] = None,
) -> str:
    """Wrapper around `upload_file` for static django in-memory image files
    uploading.
    Currently there is only one account for public static files, so this
    wrapper makes sense.
    """

    return upload_django_in_memory_file(
        account_type=AccountType.PUBLIC_STATIC,
        in_memory_file=in_memory_file,
        unique_filename_prefix=unique_filename_prefix,
        preserve_original_filename=preserve_original_filename,
        new_filename=new_filename,
        subfolder=subfolder,
        bucket=bucket,
        client_config=client_config,
        s3_config=s3_config,
    )


def generate_presigned_post_data(
    *,
    account_type: AccountType,
    unique_filename_prefix: str,
    s3_config: AccountConfigsRegistry,
    acl: str = 'private',
    file_max_size: int = DEFAULT_UPLOAD_FILE_MAX_FILE_SIZE,
    expiration: int = DEFAULT_PRESIGNED_DATA_EXPIRATION,
    use_server_side_encryption: bool = True,
    preserve_original_filename: bool = True,
    subfolder: Optional[str] = None,
    bucket: Optional[str] = None,
    client_config: Optional[botocore.config.Config] = None,
) -> Dict:

    account_config = s3_config.get_account_config(account_type)
    bucket_config = account_config.get_bucket_config(bucket=bucket)
    bucket = bucket_config.name

    client = _client_factory(
        account_type=account_type,
        config=client_config,
        bucket=bucket,
        s3_config=s3_config,
    )

    if subfolder is not None:
        object_key_prefix = os.path.join(subfolder, unique_filename_prefix)
    else:
        object_key_prefix = unique_filename_prefix

    # See docs for more details:
    #   https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-HTTPPOSTConstructPolicy.html
    #   https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
    if preserve_original_filename:
        object_key = f'{object_key_prefix}-${{filename}}'
    else:
        object_key = object_key_prefix

    fields = {'acl': acl}
    conditions = [
        {'acl': acl},
        {'bucket': bucket},
        ['starts-with', '$key', object_key_prefix],
        # ['starts-with', '$Content-Type', 'image/'],
        ['content-length-range', 0, file_max_size],
    ]
    if use_server_side_encryption:
        fields.update({'x-amz-server-side-encryption': SERVER_SIDE_ENCRYPTION})
        conditions.append({'x-amz-server-side-encryption': SERVER_SIDE_ENCRYPTION})
    return client.generate_presigned_post(
        Bucket=bucket,
        Key=object_key,
        Fields=fields,
        ExpiresIn=expiration,
        Conditions=conditions,
    )


def generate_presigned_post_data_for_private_account(
    *,
    unique_filename_prefix: str,
    s3_config: AccountConfigsRegistry,
    file_max_size: int = DEFAULT_UPLOAD_FILE_MAX_FILE_SIZE,
    expiration: int = DEFAULT_PRESIGNED_DATA_EXPIRATION,
    preserve_original_filename: bool = True,
    subfolder: Optional[str] = None,
    bucket: Optional[str] = None,
    client_config: Optional[botocore.config.Config] = None,
) -> Dict:
    """Wrapper around `generate_presigned_post_data` with predefined security
    options.
    Currently there is only one private account + bucket, where encryption is
    required by bucket policy, so this wrapper makes sense.
    """
    return generate_presigned_post_data(
        account_type=AccountType.PRIVATE,
        unique_filename_prefix=unique_filename_prefix,
        acl='private',
        file_max_size=file_max_size,
        expiration=expiration,
        use_server_side_encryption=True,
        preserve_original_filename=preserve_original_filename,
        subfolder=subfolder,
        bucket=bucket,
        client_config=client_config,
        s3_config=s3_config,
    )


def generate_presigned_get_url(
    *,
    account_type: AccountType,
    object_key: str,
    s3_config: AccountConfigsRegistry,
    expiration: int = DEFAULT_PRESIGNED_DATA_EXPIRATION,
    bucket: Optional[str] = None,
    client_config: Optional[botocore.config.Config] = None,
) -> str:

    account_config = s3_config.get_account_config(account_type)
    bucket_config = account_config.get_bucket_config(bucket=bucket)
    bucket = bucket_config.name

    client = _client_factory(
        account_type=account_type,
        config=client_config,
        bucket=bucket,
        s3_config=s3_config,
    )

    return client.generate_presigned_url(
        'get_object',
        Params={
            'Bucket': bucket,
            'Key': object_key,
        },
        ExpiresIn=expiration,
        HttpMethod='GET',
    )


def list_objects(
    account_type: AccountType,
    s3_config: AccountConfigsRegistry,
    prefix: str,
    bucket: Optional[str] = None,
) -> list[str]:
    """Lists objects in specified S3 account and bucket+prefix.
    If bucket is not specified and there is only one bucket in account_type
    then it will be used automatically. Otherwise error will be raised.
    """

    account_config = s3_config.get_account_config(account_type)
    bucket_config = account_config.get_bucket_config(bucket=bucket)
    bucket = bucket_config.name

    client = _client_factory(
        account_type=account_type,
        bucket=bucket,
        s3_config=s3_config,
    )
    paginator = client.get_paginator('list_objects_v2')
    page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)

    object_keys: list[str] = []
    for page in page_iterator:
        contents = page.get('Contents', [])
        for obj in contents:
            object_keys.append(obj['Key'])
    return object_keys


def delete_objects(
    account_type: AccountType,
    object_keys: list[str],
    s3_config: AccountConfigsRegistry,
    bucket: Optional[str] = None,
    client_config: Optional[botocore.config.Config] = None,
) -> dict:
    """Deletes object in specified S3 account and bucket.
    If bucket is not specified and there is only one bucket in account_type
    then it will be used automatically. Otherwise error will be rised.
    """

    account_config = s3_config.get_account_config(account_type)
    bucket_config = account_config.get_bucket_config(bucket=bucket)
    bucket = bucket_config.name

    client = _client_factory(
        account_type=account_type,
        config=client_config,
        bucket=bucket,
        s3_config=s3_config,
    )
    objects = [{'Key': k} for k in object_keys]
    response = client.delete_objects(Bucket=bucket, Delete={'Objects': objects, 'Quiet': False})
    return response


def _client_factory(
    *,
    account_type: AccountType,
    s3_config: AccountConfigsRegistry,
    # NOTE: if there is only one bucket in account_type then there is no reason
    # to specify bucket name. Otherwise error will be rised.
    bucket: Optional[str] = None,
    config: Optional[botocore.config.Config] = None,
) -> botocore.client.BaseClient:

    client_config = config or botocore.config.Config(signature_version='s3v4')

    account_config = s3_config.get_account_config(account_type)
    if account_config.region_name is not None:
        client_config.region_name = account_config.region_name

    bucket_config = account_config.get_bucket_config(bucket=bucket)

    # access_key_id.get_value() is dropped because SettingsReferenceProxy is not currently used
    aws_access_key_id = account_config.credentials.access_key_id
    aws_secret_access_key = (
        account_config.credentials.secret_access_key
        if isinstance(account_config.credentials.secret_access_key, str)
        else account_config.credentials.secret_access_key
    )

    return boto3.client(
        's3',
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        endpoint_url=_get_endpoint_url(account_config=account_config, bucket=bucket_config.name),
        config=client_config,
    )


def _get_endpoint_url(*, account_config: AccountConfig, bucket: str) -> str:
    endpoint_url = account_config.endpoint_url
    if not account_config.bucket_as_dns:
        return endpoint_url

    parsed_url = urlparse(endpoint_url)
    endpoint_domain = parsed_url.netloc
    return parsed_url._replace(netloc=f'{bucket}.{endpoint_domain}').geturl()
