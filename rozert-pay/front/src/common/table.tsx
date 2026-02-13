import {
  InputBase,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableFooter,
  TableHead,
  TablePagination,
  TableRow,
} from '@material-ui/core';
import React, { useCallback } from 'react';
import { formatDatetime } from '../pages/wallets-page';

export interface TableRowType {
  id?: string;

  [key: string]: any;
}

// declare TableProps interface below
export interface TableProps<T extends TableRowType> {
  columns: {
    key: string;
    label: string;
    format?: 'string' | 'number' | 'date';
    component?: React.FC<{ row: T }>;
  }[];
  data: T[];
  //eslint-disable-next-line
  rowStyler?: (row: T) => React.CSSProperties;
  actionsComponent?: React.FC<{ row: T }>;
}

const getFormatter = (format: 'string' | 'number' | 'date') => {
  switch (format) {
    case 'number':
      return (v: any) => new Intl.NumberFormat('en-US').format(v);
    case 'date':
      return (v: any) => formatDatetime(v);
    default:
      return (v: any) => v;
  }
};

const TableCellComponent = <T extends TableRowType>({
  row,
  rowKey,
  format,
  component,
}: {
  row: T;
  rowKey: string;
  format?: 'string' | 'number' | 'date';
  component?: React.FC<{ row: T }>;
}) => {
  const key = rowKey;
  const formatter = getFormatter(format || 'string');
  return (
    <TableCell key={key} style={{ whiteSpace: 'nowrap' }}>
      {component
        ? React.createElement(component, { row })
        : formatter(row[key])}
    </TableCell>
  );
};

export const TableComponent = <T extends TableRowType>(
  props: TableProps<T>,
) => {
  const { data } = props;
  const [page, setPage] = React.useState(0);
  const [rowsPerPage, setRowsPerPage] = React.useState(10);
  const [search, setSearch] = React.useState('');

  const handleChangePage = (
    event: React.MouseEvent<HTMLButtonElement> | null,
    newPage: number,
  ) => {
    setPage(newPage);
  };

  const applySearch = (d: T[]) => {
    return d.filter((row) => {
      if (!search) return true;
      return Object.values(row).some((value) => {
        return value?.toString().includes(search);
      });
    });
  };
  const searchResults = applySearch(data);
  const displayedData = searchResults.slice(
    page * rowsPerPage,
    page * rowsPerPage + rowsPerPage,
  );

  const handleChangeRowsPerPage = (event: any) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };
  const handleSearch = useCallback((event) => {
    setSearch(event.target.value);
  }, []);

  return (
    <TableContainer component={Paper}>
      <div>
        <InputBase
          placeholder="Search…"
          inputProps={{ 'aria-label': 'search' }}
          value={search}
          onChange={handleSearch}
        />
      </div>
      <Table>
        <TableHead>
          <TableRow>
            {props.columns.map((column) => (
              <TableCell key={column.key}>{column.label}</TableCell>
            ))}
            {props.actionsComponent && (
              <TableCell key="actions">Actions</TableCell>
            )}
          </TableRow>
        </TableHead>
        <TableBody>
          {displayedData.map((row) => {
            const style = props.rowStyler ? props.rowStyler(row) : {};
            return (
              <TableRow key={row.id} style={style}>
                {props.columns.map((column) => {
                  return (
                    <TableCellComponent
                      key={column.key}
                      rowKey={column.key}
                      row={row}
                      format={column.format}
                      component={column.component}
                    />
                  );
                })}
                {props.actionsComponent && (
                  <TableCell>
                    {React.createElement(props.actionsComponent, { row })}
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
        <TableFooter>
          <TableRow>
            <TablePagination
              count={searchResults.length}
              rowsPerPage={rowsPerPage}
              page={page}
              rowsPerPageOptions={[10, 20, 50, 100]}
              onPageChange={handleChangePage}
              onRowsPerPageChange={handleChangeRowsPerPage}
            />
          </TableRow>
        </TableFooter>
      </Table>
    </TableContainer>
  );
};
