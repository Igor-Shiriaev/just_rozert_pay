from django.conf import settings
from django.http import HttpRequest
from django.utils.version import get_main_version


def admin_site_title_processor(request: HttpRequest) -> dict:
    namespace = getattr(settings, 'ENV_NAMESPACE', '__default__')

    site_titles = {
        '/admin': 'Admin dashboard',
        '/promo-admin': 'Promotion admin dashboard',
        '/messaging-admin': 'Messaging admin dashboard',
    }
    site_title = 'Admin dashboard'
    for prefix, title in site_titles.items():
        if request.path.startswith(prefix):
            site_title = title
            break
    env_marker = {
        'production': '(Main)',
        'production-malta': '(MT)',
    }.get(namespace, '(DEV)')

    return {'custom_site_header': f'{site_title} {env_marker}'}


def common_processor(request: HttpRequest) -> dict:
    namespace = getattr(settings, 'ENV_NAMESPACE', '__default__')
    return {
        'ENV_NAMESPACE': namespace,
        'DJANGO_VERSION': get_main_version(),
    }
