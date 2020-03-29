import logging
from typing import Any, Callable, Union

from django_swagger_tester.case_checks import case_check
from django_swagger_tester.exceptions import SwaggerDocumentationError
from django_swagger_tester.validate_response.base.configuration import load_settings

logger = logging.getLogger('django_swagger_tester')


class SwaggerTester(object):

    def __init__(self):
        self.case_func = None
        self.schema = None
        self._validation()

    def _validation(self):
        """
        Loads Django settings.

        Currently, the case-check preference is the only base setting required.
        This might be extended in the future.
        """
        settings = load_settings()
        self.case_func = case_check(settings['CASE'])

    def _dict(self, schema: dict, data: Union[list, dict]) -> None:
        """
        Verifies that a schema dict matches a response dict.

        :param schema: OpenAPI schema
        :param data: Response data
        :return: None
        """
        logger.debug('Verifying that response dict layer matches schema layer')
        # Check that the response data is the right type and unpack dict keys
        if not isinstance(data, dict):
            if isinstance(data, list) and len(data) == 0:
                # If a list of objects is documented, but no objects are included in the response, that doesnt make the
                # documentation incorrect.
                return
            else:
                raise SwaggerDocumentationError(f"The response is {type(data)} where it should be <class 'dict'>")
        schema_keys = schema['properties'].keys()
        response_keys = data.keys()

        # Verify that the length of both dicts match - A length mismatch will always indicate an error
        if len(schema_keys) != len(response_keys):
            logger.debug('The number of schema dict elements does not match the number of response dict elements')
            if len(set(response_keys)) > len(set(schema_keys)):
                missing_keys = ', '.join([f'`{key}`' for key in list(set(response_keys) - set(schema_keys))])
                raise SwaggerDocumentationError(
                    f'The following properties seem to be missing from your OpenAPI/Swagger documentation: {missing_keys}')
            else:
                missing_keys = ', '.join([f'{key}' for key in list(set(schema_keys) - set(response_keys))])
                raise SwaggerDocumentationError(
                    f'The following properties seem to be missing from your response body' f': {missing_keys}')

        for schema_key, response_key in zip(schema_keys, response_keys):

            # Check the keys for case inconsistencies
            self.case_func(schema_key)
            self.case_func(response_key)

            # Check that each element in the schema exists in the response, and vice versa
            if schema_key not in response_keys:
                raise SwaggerDocumentationError(
                    f'Schema key `{schema_key}` was not found in the API response. '
                    f'Response keys include: {", ".join([i for i in data.keys()])}'
                )
            elif response_key not in schema_keys:
                raise SwaggerDocumentationError(f'Response key `{response_key}` is missing from your API documentation')

            # Check what further check are needed for the values contained in the dict
            schema_value = schema['properties'][schema_key]
            response_value = data[schema_key]

            if schema_value['type'] == 'object':
                logger.debug('Calling _dict from _dict. Response: %s, Schema', response_value, schema_value)
                self._dict(schema=schema_value, data=response_value)
            elif schema_value['type'] == 'array':
                self._list(schema=schema_value, data=response_value)
            elif schema_value['type'] == 'string' or schema_value['type'] == 'boolean' or schema_value['type'] == 'integer':
                self._item(schema=schema_value, data=response_value)
            else:
                raise Exception(f'Unexpected error.\nSchema: {schema}\n Response: {data}')  # TODO: Remove after testing

    def _list(self, schema: dict, data: Union[list, dict]) -> None:
        """
        Verifies that the response item matches the schema documentation, when the schema layer is an array.

        :param schema: OpenAPI schema
        :param data: Response data
        :return: None.
        """
        logger.debug('Verifying that response list layer matches schema layer')
        if not isinstance(data, list):
            raise SwaggerDocumentationError(f"The response is {type(data)} when it should be <class 'list'>")

        # A schema array can only hold one item, e.g., {"type": "array", "items": {"type": "object", "properties": {...}}}
        # At the same time we want to test each of the response objects, as they *should* match the schema.
        if not schema['items'] and data:
            raise SwaggerDocumentationError(f'Response list contains values `{data}` '
                                            f'where schema suggests there should be an empty list.')
        elif not schema['items'] and not data:
            return
        else:
            item = schema['items']

        for index in range(len(data)):
            # If the schema says all listed items are to be dictionaries and the dictionaries should have values...
            if item['type'] == 'object' and item['properties']:
                # ... then check those values
                self._dict(schema=item, data=data[index])
            # If the schema says all listed items are to be dicts, and the response has values but the schema is empty
            elif (item['type'] == 'object' and not item['properties']) and data[index]:
                # ... then raise an error
                raise SwaggerDocumentationError(f'Response dict contains value `{data[index]}` '
                                                f'where schema suggests there should be an empty dict.')
            # If the schema says all listed items are to be arrays and the lists should have values
            elif item['type'] == 'array' and item['items']:
                # ... then check those values
                self._list(schema=item, data=data[index])
            # If the schema says all listed items are to be arrays, and the response has values but the schema is empty
            elif (item['type'] == 'array' and not item['items']) and data[index]:
                raise SwaggerDocumentationError(f'Response list contains value `{data[index]}` '
                                                f'where schema suggests there should be an empty list.')
            elif item['type'] == 'string' or item['type'] == 'boolean' or item['type'] == 'integer':
                self._item(schema=item, data=data)
            else:
                raise Exception(f'Unexpected error.\nSchema: {schema}\n Response: {data}')  # TODO: Remove after testing

    @staticmethod
    def _item(schema: dict, data: Any) -> None:
        """
        Verifies that a response value matches the example value in the schema.

        :param schema: OpenAPI schema
        :param data:
        :return:
        """
        if schema['type'] == 'boolean':
            if not isinstance(data, bool) and not (
                    isinstance(data, str) and (data.lower() == 'true' or data.lower() == 'false')):
                raise SwaggerDocumentationError(
                    f"The example value `{schema['example']}` does not match the specified data type <type 'bool'>.")
        elif schema['type'] == 'string':
            if not isinstance(data, str):
                raise SwaggerDocumentationError(
                    f"The example value `{schema['example']}` does not match the specified data type <type 'str>'.")
        elif schema['type'] == 'integer':
            if not isinstance(data, int):
                raise SwaggerDocumentationError(
                    f"The example value `{schema['example']}` does not match the specified data type <class 'int'>.")
        else:
            raise Exception(f'Unexpected error.\nSchema: {schema}\n Response: {data}')  # TODO: Remove after testing