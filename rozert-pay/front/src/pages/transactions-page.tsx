import React, { useEffect, useState } from 'react';
import Layout from '../layout';
import { TableComponent } from '@/common/table';
import { ApiService, Transaction } from '@/api';

export const TransactionsPage: React.FC = () => {
  const [data, setData] = useState<Transaction[]>([]);
  useEffect(() => {
    ApiService.apiBackofficeV1TransactionList().then(
      (response: Transaction[]) => {
        setData(response);
      },
    );
  }, []);

  return (
    <Layout>
      <div>
        <h1>Transactions</h1>
        <TableComponent
          columns={[
            { key: 'id', label: 'ID' },
            { key: 'created_at', label: 'Created At', format: 'date' },
            { key: 'updated_at', label: 'Updated At', format: 'date' },
            { key: 'status', label: 'Status' },
            { key: 'type', label: 'Type' },
            { key: 'amount', label: 'Amount' },
            { key: 'currency', label: 'Currency' },
            { key: 'decline_code', label: 'Decline Code' },
            { key: 'decline_reason', label: 'Decline Reason' },
          ]}
          rowStyler={(row: Transaction) => {
            if (row.status === 'success') {
              return { backgroundColor: 'lightgreen' };
            }
            if (row.status === 'failed') {
              return { backgroundColor: 'lightcoral' };
            }
            return {};
          }}
          data={data}
        />
      </div>
    </Layout>
  );
};
