import re

from django.core.files.uploadedfile import UploadedFile

from admin_customize.images_management.init import get_s3


def get_file_extension(uploaded_file: UploadedFile) -> str:
    return uploaded_file.name.rsplit('.', maxsplit=1)[-1]


s3_domain_regex = re.compile(r'(?P<schema>https?:\/\/)(?P<domain>.*?)\/(?P<bucket>.*)')


def maybe_patch_static_s3_url_to_use_proxy(file_url: str) -> str:
    """
    Try to make s3 url same and if it is our s3 url then patch it to use proxy

    if used third-party urls 'https://s3.amazonaws.com/static.example.com/file.png' ->
    'https://s3.amazonaws.com/static.example.com/file.png'
    if used our s3 url 'https://s3.eu-central-1.amazonaws.com/bmstorage/image.png' ->
    'https://bmstatic.cloud/bmstorage/image.png'
    if used another url of our s3 'https://bmstorage.s3.eu-central-1.amazonaws.com/image.png' ->
    'https://bmstatic.cloud/bmstorage/image.png'

    """
    s3_config = get_s3()
    private_url_parsed = s3_domain_regex.search(s3_config.private_url_for_public_static_bucket)
    if not private_url_parsed:
        return file_url

    schema = private_url_parsed.group('schema')
    domain = private_url_parsed.group('domain')
    bucket = private_url_parsed.group('bucket')
    possible_domains = (
        f'{schema}{domain}/{bucket}',
        f'{schema}{bucket}.{domain}',
    )
    # As there can be multiple possible domains, here we make it use the same
    for possible_domain in possible_domains:
        if possible_domain in file_url:
            file_url = file_url.replace(possible_domain, s3_config.private_url_for_public_static_bucket)

    # Trying to replace url to use proxy
    file_url = file_url.replace(
        s3_config.private_url_for_public_static_bucket,
        s3_config.public_url_for_public_static_bucket,
    )

    return file_url
