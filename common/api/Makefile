openapi-ytt:
	ytt -f spec-ytt.yml -f data-values.yml -f spec-partner_program.lib.yml -f spec-payment.autogenerate.lib.yml -f spec-payment.lib.yml -f spec-partner.autogenerate.lib.yml -f spec-promotion.presets.lib.yml -f spec-promotion.lib.yml > spec-intermediate.yml

openapi-add-get-requests-schemas: openapi-ytt
	python3 add_get_requests_schemas.py spec-intermediate.yml > spec.yml

openapi-generate-python: openapi-add-get-requests-schemas
	datamodel-codegen --version
	rm -rf ../../back/back/openapi_autogen_datamodel && datamodel-codegen --input spec.yml --output ../../back/back/openapi_autogen_datamodel --use-schema-description --field-constraints --target-python-version 3.13 --strict-nullable --enum-field-as-literal one
