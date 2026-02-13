import React, { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { List, ListItem, ListItemText, Typography } from '@material-ui/core';
import { ApiService, Account } from '@/api';

const NavbarLink = ({
  to,
  text,
  reloadDocument,
}: {
  to: string;
  text: string;
  reloadDocument?: boolean;
}) => {
  const location = useLocation();
  const isActive = to === location.pathname;
  return (
    <ListItem
      button
      component={Link}
      to={to}
      reloadDocument={reloadDocument}
      style={{
        backgroundColor: isActive ? '#cfe8fc' : 'transparent',
      }}
    >
      <ListItemText primary={text} />
    </ListItem>
  );
};

const useAccount = () => {
  const [isLoading, setIsLoading] = useState(true);

  const [account, setAccount] = useState<Account | null>(null);

  useEffect(() => {
    ApiService.apiBackofficeV1DepositAccountList()
      .then((response: any) => {
        setAccount(response);
        setIsLoading(false);
      })
      .catch((e: any) => {
        setIsLoading(false);
        console.error(e);
      });
  }, []);

  return { account, isLoading };
};

const Navbar = () => {
  const { account, isLoading } = useAccount();
  const isAuthenticated = !!account;
  const logout = async () => {
    await ApiService.apiAccountV1LogoutCreate();
    window.location.reload();
  };

  let role = null;
  if (account && account.role) {
    if (account.role.merchant_id) {
      role = 'merchant';
    }
    if (account.role.merchant_group_id) {
      role = 'merchant_group';
    }
  }

  return (
    <div
      style={{
        width: '200px',
        background: '#f4f4f4',
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {!isLoading && (
        <>
          <List component="nav" style={{ flexGrow: 1 }}>
            <NavbarLink to="/backoffice/" text="Home" />
            {isAuthenticated ? (
              <>
                <NavbarLink to="/backoffice/account" text="Account info" />
                <NavbarLink to="/backoffice/wallets" text="Wallets info" />
                <NavbarLink
                  to="/backoffice/deposit-accounts"
                  text="Deposit accounts"
                />
                <NavbarLink to="/backoffice/transactions" text="Transactions" />
                <NavbarLink to="/backoffice/callbacks" text="Callbacks" />
              </>
            ) : (
              <NavbarLink to="/backoffice/login" text="Login" />
            )}
          </List>
          <div style={{ marginTop: 'auto', padding: '16px' }}>
            <NavbarLink to="/redoc" text="Docs" reloadDocument />
            {account && (
              <>
                <Typography variant="caption">
                  Logged in as: {account?.email}
                </Typography>
                <br />
                {role && (
                  <Typography variant="caption">Role: {role}</Typography>
                )}
                <ListItem button>
                  <ListItemText primary="Logout" onClick={logout} />
                </ListItem>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
};

const Layout = ({ children }: { children: React.ReactNode }) => {
  return (
    <div style={{ display: 'flex' }}>
      <Navbar />
      <main style={{ flexGrow: 1, padding: '20px' }}>{children}</main>
    </div>
  );
};

export default Layout;
