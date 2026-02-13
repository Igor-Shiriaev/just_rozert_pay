import React from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import Layout from './layout';
import Login from './pages/login';
import { WalletsPage } from './pages/wallets-page';
import { DepositAccountsPage } from './pages/deposit-accounts-page';
import { TransactionsPage } from './pages/transactions-page';
import { CallbacksPage } from './pages/callbacks-page';

const App = () => {
  return (
    <Layout>
      <main>
        <div>Hello world!</div>
      </main>
    </Layout>
  );
};

createRoot(document.getElementById('root')).render(
  <Router>
    <Routes>
      <Route path="/backoffice/login" element={<Login />} />
      <Route path="/backoffice/wallets" element={<WalletsPage />} />
      <Route path="/backoffice/transactions" element={<TransactionsPage />} />
      <Route path="/backoffice/callbacks" element={<CallbacksPage />} />
      <Route
        path="/backoffice/deposit-accounts"
        element={<DepositAccountsPage />}
      />
      <Route path="/backoffice" element={<App />} />
    </Routes>
  </Router>,
);
