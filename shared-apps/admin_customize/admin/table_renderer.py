"""
Allows to render a table from a dictionary.

The dictionary can be either flat or nested. If it is nested, the keys of the internal dictionaries must be the same.

If the dictionary is nested, the first level keys will be used as row IDs. The keys of the internal dictionaries will be
used as headers.

If the dictionary is flat, the keys will be used as headers.

TIP: If you want to have a flat table with a single row, you can pass a flat dictionary with param transposition=True.

Example:

    >>> TableData.from_dict({
        'row1': {'key1': 1, 'key2': 2, 'key3': 3},
        'row2': {'key1': 4, 'key2': 5, 'key3': 6},
        'row3': {'key1': 7, 'key2': 8, 'key3': 9},
    }, base_header_row_title='HTitle').render_html()
    |HTitle | key1  | key2  | key3  |
    |-------|-------|-------|-------|
    | row1  | 1     | 2     | 3     |
    | row2  | 4     | 5     | 6     |
    | row3  | 7     | 8     | 9     |

    >>> TableData.from_dict({'key1': 1, 'key2': 2, 'key3': 3}).render_html()
    | key1  | key2  | key3  |
    |-------|-------|-------|
    | 1     | 2     | 3     |

    >>> TableData.from_dict({'key1': 1, 'key2': 2, 'key3': 3}, transposition=True).render_html()
    |-------|-------|
    | key1  | 1     |
    | key2  | 2     |
    | key3  | 3     |

    >>> TableData.from_list([
        {'key1': 1, 'key2': 2, 'key3': 3},
        {'key1': 4, 'key2': 5, 'key3': 6},
    ]).render_html()
    | key1  | key2  | key3  |
    |-------|-------|-------|
    | 1     | 2     | 3     |
    | 4     | 5     | 6     |
"""
import datetime
from dataclasses import dataclass
from typing import Any, Optional

from admin_customize.const import get_bool_icon
from admin_customize.utils import humanize_string, humanize_datetime
from django.utils.safestring import SafeString, mark_safe


class BaseRenderable:
    @property
    def attributes_str(self) -> str:
        """
        Returns a string of attributes separated by spaces.
        """
        return ''

    def render_html(self) -> str:
        """
        Renders the element as an HTML string.
        """
        raise NotImplementedError

class ClassNameMixin:
    """
    Mixin to add class names to the rendered HTML.
    """
    classes: Optional[list[str]] = None

    @property
    def classes_str(self) -> str:
        """
        Returns a string of classes separated by spaces.
        """
        if self.classes:
            return f' class="{" ".join(self.classes)}"'
        return ''

class ColspanMixin:
    """
    Mixin to add colspan attribute to the rendered HTML.
    """
    colspan: Optional[int] = None

    @property
    def colspan_str(self) -> str:
        """
        Returns the colspan attribute as a string.
        """
        if self.colspan:
            return f' colspan="{self.colspan}"'
        return ''


@dataclass
class TableCell(ClassNameMixin,ColspanMixin,BaseRenderable):
    value: Any
    colspan: Optional[int] = None

    @property
    def attributes_str(self) -> str:
        """
        Returns a string of attributes separated by spaces.
        """
        attrs_str = ' '.join([self.colspan_str, self.classes_str]).strip()
        if attrs_str:
            return f' {attrs_str}'
        return ''

    def render_html(self) -> str:
        """
        Renders the cell as an HTML <td> element.
        """
        if self.value is None:
            value = '-'
        elif isinstance(self.value, bool):
            value = get_bool_icon(self.value)
        elif isinstance(self.value, datetime.datetime):
            value = humanize_datetime(self.value)
        else:
            value = SafeString(self.value)
        return f'<td{self.attributes_str}>{value}</td>'


@dataclass
class TableHeaderCell(TableCell):
    value: Any
    colspan: Optional[int] = None

    def render_html(self, preserve_header: bool = False) -> str:
        """
        Renders the header cell as an HTML <th> element.
        """
        if preserve_header:
            value_to_render = self.value
        else:
            value_to_render = self.format_value()

        return f'<th{self.attributes_str}>{SafeString(value_to_render)}</th>'

    def format_value(self) -> str:
        return humanize_string(self.value, html=True)


@dataclass
class TableRow(BaseRenderable):
    row_id: Optional[str]
    cells: list[TableCell]

    def render_html(self) -> str:
        """
        Renders the row as an HTML <tr> element.
        If row_id is provided, it is rendered as the first <th>.
        """
        if self.row_id is not None:
            row_id_html = f'<th>{SafeString(self.row_id)}</th>'
            cells_html = ''.join(cell.render_html() for cell in self.cells)
            return f'<tr>{row_id_html}{cells_html}</tr>'
        else:
            cells_html = ''.join(cell.render_html() for cell in self.cells)
            return f'<tr>{cells_html}</tr>'

    def __len__(self) -> int:
        cells_count = 0
        if self.row_id is not None:
            cells_count += 1
        for cell in self.cells:
            if cell.colspan:
                cells_count += cell.colspan
            else:
                cells_count += 1
        return cells_count


@dataclass
class TableHeaderRow(BaseRenderable):
    cells: list[TableHeaderCell]

    def render_html(self, preserve_header: bool = False) -> str:
        """
        Renders the header row within a <thead> element.
        """
        cells_html = ''.join(cell.render_html(preserve_header) for cell in self.cells)
        return f'<thead><tr>{cells_html}</tr></thead>'

    def __len__(self) -> int:
        cells_count = 0
        for cell in self.cells:
            if cell.colspan:
                cells_count += cell.colspan
            else:
                cells_count += 1
        return cells_count


@dataclass
class TableData:
    header: Optional[TableHeaderRow]
    rows: list[TableRow]
    keys: Optional[list[str]] = None  # Maintains the order of keys

    def render_html(
        self,
        *,
        name: Optional[str] = None,
        bordered: bool = True,
        full_width: bool = False,
        capitalize_headers: bool = False,
        preserve_header: bool = False,
        striped: bool = False,
        equal_cell_widths: bool = False,
    ) -> SafeString:
        """
        Renders the entire table as a SafeString containing HTML.

        :param name: The name of the table. If provided, it will be rendered as an <h3> element.
        :param bordered: If True, a border will be added to the table.
        :param full_width: If True, the table will take up the full width of the container.
        :param capitalize_headers: If True, header cells will be capitalized.
        :param preserve_header: If True, header cells will be rendered as is, without any formatting.
        :param striped: If True, the table will have striped rows.
        :param equal_cell_widths: If True, all cells will try to have equal width. Best for full-width tables.
        :return: SafeString containing the HTML representation of the table.
        """
        table_body = ''.join(row.render_html() for row in self.rows)
        table_name = f'<h3>{name}</h3>' if name else ''
        table_header = self.header.render_html(preserve_header) if self.header else ''

        classes = ['dict-table']
        if full_width:
            classes.append('full-width')
        if capitalize_headers:
            classes.append('capitalize-headers')
        if bordered:
            classes.append('bordered')
        if striped:
            classes.append('striped')
        if equal_cell_widths:
            classes.append('equal-cell-widths')

        table_html = (
            '<div class="responsive-table-container">'
            f'{table_name}'
            f'<table class="{" ".join(classes)}">'
            f'{table_header}'
            f'<tbody>{table_body}</tbody>'
            f'</table>'
            '</div>'
        )
        return mark_safe(table_html)

    @classmethod
    def from_list(cls, input_list: list[dict]):
        """
        Converts a list to a TableData instance.
        All inner dictionaries must have the same keys and be flat dicts.

        :param input_list: The input list to convert.
        :return: An instance of TableData representing the table.
        """

        if not isinstance(input_list, list):
            raise TypeError('Input must be a list.')

        if not input_list:
            return cls(header=None, rows=[], keys=None)

        if not all(isinstance(item, dict) for item in input_list):
            raise TypeError('All items in the list must be dictionaries.')

        if not all(input_list[0].keys() == item.keys() for item in input_list):
            raise ValueError('All dictionaries in the list must have the same keys.')

        header_keys = list(input_list[0].keys())
        header_row = TableHeaderRow(cells=[TableHeaderCell(value=key) for key in header_keys])

        rows = [
            TableRow(row_id=None, cells=[TableCell(value=item[key]) for key in header_keys])
            for item in input_list
        ]
        return cls(header=header_row, rows=rows, keys=header_keys)

    @classmethod
    def from_dict(
        cls,
        input_dict: dict,
        *,
        transposition: bool = False,
        base_header_row_title: Optional[str] = None,
    ) -> 'TableData':
        """
        Converts a dictionary to a TableData instance.

        :param input_dict: The input dictionary to convert.
        :param transposition: If True the dictionary will be transposed.
        :param base_header_row_title: The title for the first header cell.
        :return: An instance of TableData representing the table.
        :raises ValueError: If internal dictionaries have different keys or other inconsistencies.
        :raises TypeError: If the input is not a dictionary.
        """

        if not isinstance(input_dict, dict):
            raise TypeError('Input must be a dictionary.')

        if not input_dict:
            return cls(header=None, rows=[], keys=None)

        if transposition:
            input_dict = _transpose_dict(input_dict)

        is_nested = cls._is_nested_dict(input_dict)
        is_flat = cls._is_flat_dict(input_dict)

        if not (is_nested or is_flat):
            raise ValueError(
                'Dictionary contains mixed types: some values are dictionaries, others are not.'
            )

        if is_nested:
            return cls._from_nested_dict(input_dict, base_header_row_title)
        else:
            return cls._from_flat_dict(input_dict)

    @property
    def columns_count(self) -> int:
        """
        Returns the number of columns in the table.
        """
        if self.header:
            return len(self.header)
        if self.rows:
            return len(self.rows[0])
        return 0

    @property
    def rows_count(self) -> int:
        """
        Returns the number of rows in the table.
        """
        rows_count = len(self.rows)
        if self.header:
            rows_count += 1
        return rows_count

    def force_header(self, header: TableHeaderRow) -> 'TableData':
        """
        Forces a new header for the table. Can be used in call chains.

        :param header: The new header to use.
        :return: A new instance of TableData with the provided header.
        """
        if len(header) != self.columns_count:
            raise ValueError('New header must have the same number of columns as the table.')

        self.header = header
        return self

    @staticmethod
    def _is_nested_dict(input_dict: dict) -> bool:
        """
        Checks if all values in the dictionary are themselves dictionaries.

        :param input_dict: The dictionary to check.
        :return: True if all values are dictionaries, False otherwise.
        """
        return all(isinstance(v, dict) for v in input_dict.values())

    @staticmethod
    def _is_flat_dict(input_dict: dict) -> bool:
        """
        Checks if none of the values in the dictionary are dictionaries.

        :param input_dict: The dictionary to check.
        :return: True if none of the values are dictionaries, False otherwise.
        """
        return all(not isinstance(v, dict) for v in input_dict.values())

    @classmethod
    def _from_nested_dict(
        cls, input_dict: dict, base_header_row_title: Optional[str] = None
    ) -> 'TableData':
        """
        Converts a nested dictionary to TableData.

        :param input_dict: The nested dictionary to convert.
        :return: An instance of TableData.
        :raises ValueError: If internal dictionaries have different keys or other inconsistencies.
        """
        inner_keys_lists: list[list[str]] = [list(v.keys()) for v in input_dict.values()]

        if not inner_keys_lists:
            raise ValueError('Internal dictionaries are empty.')

        first_inner_keys = inner_keys_lists[0]
        for ik in inner_keys_lists[1:]:
            if set(ik) != set(first_inner_keys):
                raise ValueError(
                    f'All internal dictionaries must have the same keys. Expected %s, but got %s.',
                    ', '.join(first_inner_keys),
                    ', '.join(ik),
                )

        all_keys_none = all(key is None for key in first_inner_keys)

        if all_keys_none:
            return cls._from_nested_dict_all_keys_none(input_dict)
        else:
            return cls._from_nested_dict_standard(
                input_dict, first_inner_keys, base_header_row_title
            )

    @classmethod
    def _from_nested_dict_all_keys_none(cls, input_dict: dict) -> 'TableData':
        """
        Handles the case where all internal dictionary keys are None.

        :param input_dict: The nested dictionary to convert.
        :return: An instance of TableData without a header.
        :raises ValueError: If any internal dictionary does not contain the key None.
        """
        rows = []

        for row_id, inner_dict in input_dict.items():
            if None not in inner_dict:
                raise ValueError(f'Row "{row_id}" is missing the None key.')
            cell = TableCell(value=inner_dict[None])
            row = TableRow(row_id=row_id, cells=[cell])
            rows.append(row)

        return cls(header=None, rows=rows, keys=None)

    @classmethod
    def _from_nested_dict_standard(
        cls, input_dict: dict, header_keys: list[str], base_header_row_title: Optional[str] = None
    ) -> 'TableData':
        """
        Handles the standard nested dictionary conversion with headers.

        :param input_dict: The nested dictionary to convert.
        :param header_keys: The keys to be used as headers.
        :return: An instance of TableData with headers.
        :raises ValueError: If any row is missing a header key or if keys are not strings or None.
        """
        # Validate that all header keys are strings or None
        for key in header_keys:
            if key is not None and not isinstance(key, str):
                raise ValueError(f'Header key %s must be a string or None.', key)

        # Create header cells
        header_cells = [TableHeaderCell(value=base_header_row_title or '')] + [
            TableHeaderCell(value=key) for key in header_keys
        ]
        header_row = TableHeaderRow(cells=header_cells)

        rows = []
        keys = header_keys.copy()  # Preserve the order of keys as provided

        for row_id, inner_dict in input_dict.items():
            cells = []
            for key in header_keys:
                if key not in inner_dict:
                    raise ValueError(f'Row "{row_id}" is missing the key "{key}".')
                cells.append(TableCell(value=inner_dict[key]))
            row = TableRow(row_id=row_id, cells=cells)
            rows.append(row)

        return cls(header=header_row, rows=rows, keys=keys)

    @classmethod
    def _from_flat_dict(cls, input_dict: dict) -> 'TableData':
        """
        Converts a flat dictionary to TableData.

        :param input_dict: The flat dictionary to convert.
        :return: An instance of TableData.
        :raises ValueError: If all keys are None.
        """
        all_keys_none = all(key is None for key in input_dict.keys())

        if all_keys_none:
            # Special handling when all keys are None
            rows = []
            for key, value in input_dict.items():
                # Since all keys are None, row_id is None
                row = TableRow(row_id=None, cells=[TableCell(value=value)])
                rows.append(row)
            return cls(header=None, rows=rows, keys=None)
        else:
            # Standard flat dictionary
            header_keys = list(input_dict.keys())  # Preserve the order as provided
            header_cells = [TableHeaderCell(value=key) for key in header_keys]
            header_row = TableHeaderRow(cells=header_cells)

            cells = [TableCell(value=input_dict[key]) for key in header_keys]
            row = TableRow(row_id=None, cells=cells)

            return cls(header=header_row, rows=[row], keys=header_keys)

    def __bool__(self):
        return len(self.rows) > 0


def _transpose_dict(input_dict: dict) -> dict:
    """
    Transposes the dictionary. If the values are dictionaries, the internal dictionary keys become top-level keys.
    If the values are not dictionaries, they are associated with the None key.

    :param input_dict: Source dictionary for transposition
    :return: Transposed dictionary
    """
    output: dict = {}
    for key, value in input_dict.items():
        if isinstance(value, dict):
            for subkey, sub_value in value.items():
                if subkey not in output:
                    output[subkey] = {}
                output[subkey][key] = sub_value
        else:
            if key not in output:
                output[key] = {}
            output[key][None] = value
    return output
