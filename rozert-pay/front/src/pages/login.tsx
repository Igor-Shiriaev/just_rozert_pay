import React, { useState } from 'react';
import {
  Button,
  Container,
  Select,
  TextField,
  Typography,
} from '@material-ui/core';
import Layout from '@/layout';
import { ApiService } from '@/api';

const Login: React.FC = () => {
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [formErrors, setFormErrors] = useState<{ [key: string]: any }>({});
  const [selectedRole, setSelectedRole] = useState<string>(''); // [1

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    // Handle login logic here
    try {
      await ApiService.apiAccountV1LoginCreate({
        requestBody: {
          email,
          password,
          role: (isParsedRoleValid()
            ? roleStringToDict(selectedRole)
            : undefined) as any,
        },
      });
      window.location.href = '/backoffice';
    } catch (e) {
      console.error(e);
      setFormErrors(e.body);
    }
  };

  const roleDictToString = (role: {
    merchant_id: string | null;
    merchant_group_id: string | null;
  }) => {
    return `${role.merchant_id || ''}:${role.merchant_group_id || ''}`;
  };

  const roleStringToDict = (role: string) => {
    const [merchant_id, merchant_group_id] = role.split(':');
    return {
      merchant_id: merchant_id || null,
      merchant_group_id: merchant_group_id || null,
    };
  };

  const isParsedRoleValid = () => {
    const parsedRole = roleStringToDict(selectedRole);
    if (parsedRole.merchant_id || parsedRole.merchant_group_id) {
      return true;
    }
    return false;
  };

  const buttonDisabled = () => {
    if (email == '' || password == '') {
      return true;
    }
    if (formErrors.role) {
      const parsedRole = roleStringToDict(selectedRole);
      if (parsedRole.merchant_id || parsedRole.merchant_group_id) {
        return false;
      }
      return true;
    }
    return false;
  };

  return (
    <Layout>
      <Container maxWidth="sm">
        <Typography variant="h4" gutterBottom>
          Login
        </Typography>
        {formErrors.detail && (
          <Typography variant="body1" color="error">
            {formErrors.detail}
          </Typography>
        )}
        <form onSubmit={handleLogin}>
          <TextField
            label="Username"
            variant="outlined"
            fullWidth
            margin="normal"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            error={!!formErrors.email}
            helperText={formErrors.email}
          />
          <TextField
            label="Password"
            type="password"
            variant="outlined"
            fullWidth
            margin="normal"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            error={!!formErrors.password}
            helperText={formErrors.password}
          />
          {formErrors.role && (
            <>
              <Typography color="error">
                You have multiple roles. Please select one
              </Typography>
              <Select
                native
                fullWidth
                value={selectedRole}
                error={true}
                margin="none"
                onChange={(e) => setSelectedRole(e.target.value as string)}
              >
                <option value="">Select a role</option>
                {formErrors.role.map((role: any) => (
                  <option
                    key={roleDictToString(role)}
                    value={roleDictToString(role)}
                  >
                    {role.name}
                  </option>
                ))}
              </Select>
            </>
          )}

          <Button
            type="submit"
            variant="contained"
            color="primary"
            fullWidth
            disabled={buttonDisabled()}
          >
            Login
          </Button>
        </form>
      </Container>
    </Layout>
  );
};

export default Login;
