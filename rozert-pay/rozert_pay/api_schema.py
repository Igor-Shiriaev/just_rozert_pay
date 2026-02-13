def public_schema_pre_process_hook(endpoints):  # type: ignore
    result = []
    excluded_paths = [
        "/api/payment/v1/card-bin-data/",
    ]

    for path, path_regex, method, view in endpoints:
        if not any(path.startswith(excluded) for excluded in excluded_paths):
            result.append((path, path_regex, method, view))

    return result
