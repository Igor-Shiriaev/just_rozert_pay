import json
from logging import getLogger

from django_json_widget.widgets import JSONEditorWidget as BaseJSONEditorWidget

logger = getLogger(__name__)


class JSONEditorWidget(BaseJSONEditorWidget):
    MODE_TREE = 'tree'
    MODE_CODE = 'code'

    class Media:
        extend = False
        css = {
            'all': (
                'https://cdnjs.cloudflare.com/ajax/libs/jsoneditor/9.7.4/jsoneditor.min.css',
            )
        }
        js = (
            'https://cdnjs.cloudflare.com/ajax/libs/jsoneditor/9.7.4/jsoneditor.min.js',
        )

    def __init__(self, *args, **kwargs):  # type: ignore
        kwargs.setdefault('mode', self.MODE_TREE)
        super().__init__(*args, **kwargs)

    def format_value(self, value):  # type: ignore
        if value == 'null':
            value = ''
        try:
            value = json.dumps(json.loads(value), indent=2, sort_keys=True)
            return value
        except Exception as exc:
            logger.warning(
                'Error while formatting JSON',
                extra={'error': exc},
            )
            return super().format_value(value)
