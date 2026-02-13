import os

import sentry_sdk


def set_global_pod_base_tag() -> None:
    """
    Add tag 'host_base' to Sentry events with the base part of the server name.
    Usage:
    ```
    sentry_sdk.init(dsn="YOUR_DSN")
    set_global_pod_base_tag()
    ```
    """
    server_name = os.environ.get('HOSTNAME')
    if not server_name:
        return

    parts = server_name.split('-')
    if len(parts) >= 3:
        pod_base = '-'.join(parts[:-2])
    else:
        pod_base = server_name

    sentry_sdk.set_tag('server_name.host_base', pod_base)
