import Layout from '../layout';
import React, { useEffect, useState } from 'react';
import { ApiService, CabinetDepositAccount } from '@/api';
import { TableComponent } from '@/common/table';
import { formatDatetime } from './wallets-page';

export const DepositAccountsPage: React.FC = () => {
  const [data, setData] = useState<CabinetDepositAccount[]>([]);

  useEffect(() => {
    ApiService.apiBackofficeV1DepositAccountList().then(
      (response: CabinetDepositAccount[]) => {
        setData(response);
      },
    );
  }, []);

  return (
    <Layout>
      <TableComponent
        columns={[
          { key: 'id', label: 'ID' },
          { key: 'created_at', label: 'Created At' },
          { key: 'customer_id', label: 'Customer ID' },
          { key: 'unique_account_identifier', label: 'Account for deposit' },
          { key: 'wallet', label: 'Wallet' },
        ]}
        data={data.map((depositAccount) => ({
          ...depositAccount,
          created_at: formatDatetime(depositAccount.created_at),
        }))}
      />
    </Layout>
  );
};
