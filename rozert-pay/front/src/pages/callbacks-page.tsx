import React, { useEffect, useState } from 'react';

import Layout from '../layout';
import { TableComponent } from '@/common/table';

import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@material-ui/core';
import { ApiService, CabinetCallback } from '@/api';

export const CallbacksPage: React.FC = () => {
  const [data, setData] = useState<CabinetCallback[]>([]);

  useEffect(() => {
    ApiService.apiBackofficeV1CallbackList().then((response: any) => {
      setData(response);
    });
  }, []);

  const [resendCallbackId, setResendCallbackId] = useState<string | null>(null);

  const handleCallbackResend = () => {
    const id = resendCallbackId;
    ApiService.apiBackofficeV1CallbackRetryCreate({ id }).then(() => {
      ApiService.apiBackofficeV1CallbackList().then((response: any) => {
        setData(response);
      });
    });
    setResendCallbackId(null);
  };

  return (
    <>
      <Layout>
        <div>
          <h1>Callbacks</h1>
          <TableComponent
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'created_at', label: 'Created At', format: 'date' },
              { key: 'transaction', label: 'Transaction' },
              { key: 'callback_type', label: 'Callback Type' },
              { key: 'target', label: 'Target' },
              { key: 'body', label: 'Body' },
              { key: 'status', label: 'Status' },
              { key: 'error', label: 'Error' },
              {
                key: 'last_attempt_at',
                label: 'Last Attempt At',
                format: 'date',
              },
              { key: 'attempts_remained', label: 'Attempts Remained' },
            ]}
            data={data.map((row) => ({
              ...row,
              attempts_remained:
                row.status === 'failed'
                  ? row.max_attempts - row.current_attempt
                  : '-',
            }))}
            rowStyler={(row) => {
              if (row.status === 'success') {
                return { backgroundColor: 'lightgreen' };
              }
              if (row.status === 'failed') {
                return { backgroundColor: 'lightcoral' };
              }
              return {};
            }}
            actionsComponent={({ row }: { row: CabinetCallback }) => {
              if (row.status === 'failed') {
                return (
                  <Button
                    variant={'contained'}
                    color={'primary'}
                    onClick={() => setResendCallbackId(row.id)}
                  >
                    Retry Callback
                  </Button>
                );
              }
              return null;
            }}
          />
        </div>
      </Layout>
      <Dialog
        open={resendCallbackId !== null}
        onClose={() => {
          setResendCallbackId(null);
        }}
        aria-labelledby="alert-dialog-title"
        aria-describedby="alert-dialog-description"
      >
        <DialogTitle id="alert-dialog-title">Resend Callback</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to resend callback?
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setResendCallbackId(null);
            }}
          >
            No
          </Button>
          <Button onClick={handleCallbackResend}>Yes</Button>
        </DialogActions>
      </Dialog>
    </>
  );
};
