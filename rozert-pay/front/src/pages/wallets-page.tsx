import React, { useEffect, useState } from 'react';
import Layout from '../layout';
import { ApiService, Balance, Wallet } from '@/api';
import { TableComponent } from '@/common/table';

export const formatDatetime = (datetime: string): string => {
  return new Date(datetime).toLocaleString();
};

export const WalletsPage: React.FC = () => {
  const [data, setData] = useState<Wallet[]>([]);

  useEffect(() => {
    ApiService.apiBackofficeV1WalletList().then((response: any) => {
      setData(response);
    });
  }, []);

  return (
    <Layout>
      <div>
        <h1>Wallets</h1>
        <TableComponent
          columns={[
            { key: 'id', label: 'ID' },
            { key: 'created_at', label: 'Created At', format: 'date' },
            {
              key: 'balances',
              label: 'Balances',
              component: (props: { row: Wallet }) => {
                const wallet = props.row;
                if (!wallet.id || !wallet.balances) {
                  return null;
                }
                return (
                  <>
                    {wallet.balances.map((balance: Balance) => (
                      <div key={balance.currency}>
                        <p>
                          {balance.currency}: {balance.balance}
                        </p>
                      </div>
                    ))}
                  </>
                );
              },
            },
          ]}
          data={data}
        />
      </div>
    </Layout>
  );
};
