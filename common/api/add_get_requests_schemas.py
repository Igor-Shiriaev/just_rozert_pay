import sys
from typing import Dict

import yaml

http_methods = ('get', 'post', 'put', 'delete')


def main(spec_file_path: str) -> Dict:
    with open(spec_file_path) as f:
        spec_yaml = yaml.safe_load(f)

    new_models: Dict[str, Dict] = {}

    for path, path_data in spec_yaml['paths'].items():
        common_params = path_data.get('parameters')
        for http_method in http_methods:
            if not path_data.get(http_method):
                print(f'skipping {path}, no {http_method} requests', file=sys.stderr)
                continue
            method_data = path_data[http_method]

            params = {}
            if common_params is not None:
                params.update({p['name']: p for p in common_params if p['in'] == 'query'})
            if 'parameters' in method_data:
                print(method_data, file=sys.stderr)
                params.update({p['name']: p for p in method_data['parameters'] if p['in'] == 'query'})
            if not params:
                continue
            operation_id = method_data['operationId']
            model_name = f'request.{operation_id}'
            model_data = {
                'type': 'object',
                'required': [name for name, p in params.items() if p.get('required')],
                'properties': {},
            }
            for _, p in params.items():
                field_data = {}
                if 'deprecated' in p:
                    field_data['deprecated'] = p['deprecated']
                if 'schema' in p:
                    if '$ref' not in p['schema']:
                        # inline schema
                        field_data.update(p['schema'])
                    else:
                        # schema via reference
                        field_data['$ref'] = p['schema']['$ref']
                else:
                    if p.get('type') in ['string', 'number']:
                        field_data['type'] = p['type']
                    if 'description' in p:
                        field_data['description'] = p['description']
                model_data['properties'][p['name']] = field_data
            request_body_schema = None
            if 'requestBody' in method_data:
                request_body_schema = method_data['requestBody']['content']['application/json']['schema']
            if request_body_schema is None:
                new_models[model_name] = model_data
            else:
                new_models[model_name] = {
                    'allOf': [model_data, request_body_schema]
                }

    spec_yaml['components']['schemas'].update(new_models)

    yaml.safe_dump(spec_yaml, sort_keys=False, stream=sys.stdout)


if __name__ == '__main__':
    main(sys.argv[1])
