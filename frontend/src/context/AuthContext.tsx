import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import type { User, AuthResponse, UserRole } from '../types';

interface AuthContextType {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (phone: string, password: string, intendedRole?: UserRole) => Promise<User>;
  registerVolunteer: (data: {
    full_name: string;
    phone: string;
    password: string;
    skills: string[];
    availability: string;
    zone_or_district?: string;
  }) => Promise<User>;
  initiateGoogleLogin: (intendedRole?: UserRole) => Promise<void>;
  handleGoogleCallback: (code: string, state?: string) => Promise<User>;
  loginWithGoogle: (data: { code?: string; token?: string; id_token?: string; intended_role?: UserRole }) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  getDashboardRouteForRole: (role: UserRole) => string;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const getDashboardRouteForRole = (role: UserRole): string => {
  switch (role) {
    case 'EMERGENCY_OFFICER':
      return '/command-center';
    case 'RESOURCE_MANAGER':
      return '/resource-operations';
    case 'VOLUNTEER':
      return '/volunteer-portal';
    case 'ADMIN':
      return '/admin-control';
    default:
      return '/';
  }
};

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('resilience_auth_token'));
  const [user, setUser] = useState<User | null>(() => {
    try {
      const savedUser = localStorage.getItem('resilience_auth_user');
      return savedUser ? JSON.parse(savedUser) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState<boolean>(() => {
    // If token exists, we start loading while verifying with /auth/me
    return Boolean(localStorage.getItem('resilience_auth_token'));
  });

  const saveAuth = useCallback((authData: AuthResponse) => {
    setToken(authData.access_token);
    setUser(authData.user);
    setLoading(false);
    localStorage.setItem('resilience_auth_token', authData.access_token);
    localStorage.setItem('resilience_auth_user', JSON.stringify(authData.user));
  }, []);

  const clearAuth = useCallback(() => {
    setToken(null);
    setUser(null);
    setLoading(false);
    localStorage.removeItem('resilience_auth_token');
    localStorage.removeItem('resilience_auth_user');
  }, []);

  const refreshUser = useCallback(async () => {
    const savedToken = localStorage.getItem('resilience_auth_token');
    if (!savedToken) {
      setLoading(false);
      return;
    }
    try {
      const response = await api.get<User>('/auth/me');
      setUser(response.data);
      localStorage.setItem('resilience_auth_user', JSON.stringify(response.data));
    } catch (err) {
      console.warn('Session verification failed, clearing credentials');
      clearAuth();
    } finally {
      setLoading(false);
    }
  }, [clearAuth]);

  useEffect(() => {
    refreshUser();
  }, [refreshUser]);

  const login = useCallback(
    async (phone: string, password: string, intendedRole?: UserRole): Promise<User> => {
      const response = await api.post<AuthResponse>('/auth/login', {
        phone,
        password,
        intended_role: intendedRole,
      });
      saveAuth(response.data);
      return response.data.user;
    },
    [saveAuth]
  );

  const registerVolunteer = useCallback(
    async (data: {
      full_name: string;
      phone: string;
      password: string;
      skills: string[];
      availability: string;
      zone_or_district?: string;
    }): Promise<User> => {
      const response = await api.post<AuthResponse>('/auth/register-volunteer', data);
      saveAuth(response.data);
      return response.data.user;
    },
    [saveAuth]
  );

  const initiateGoogleLogin = useCallback(async (intendedRole?: UserRole): Promise<void> => {
    const redirectUri = `${window.location.origin}/auth/google/callback`;
    const response = await api.get<{ auth_url: string; client_id: string; redirect_uri: string }>(
      '/auth/google/url',
      {
        params: {
          intended_role: intendedRole,
          redirect_uri: redirectUri,
        },
      }
    );
    if (response.data?.auth_url) {
      window.location.href = response.data.auth_url;
    } else {
      throw new Error('Google OAuth authorization URL could not be generated.');
    }
  }, []);

  const handleGoogleCallback = useCallback(
    async (code: string, state?: string): Promise<User> => {
      const redirectUri = `${window.location.origin}/auth/google/callback`;
      const response = await api.post<AuthResponse>('/auth/google/callback', {
        code,
        state,
        redirect_uri: redirectUri,
      });
      saveAuth(response.data);
      return response.data.user;
    },
    [saveAuth]
  );

  const loginWithGoogle = useCallback(
    async (data: {
      code?: string;
      token?: string;
      id_token?: string;
      intended_role?: UserRole;
    }): Promise<User> => {
      const redirectUri = `${window.location.origin}/auth/google/callback`;
      const response = await api.post<AuthResponse>('/auth/google/callback', {
        ...data,
        redirect_uri: redirectUri,
      });
      saveAuth(response.data);
      return response.data.user;
    },
    [saveAuth]
  );

  const logout = useCallback(async () => {
    try {
      const currentToken = localStorage.getItem('resilience_auth_token');
      if (currentToken) {
        await api.post('/auth/logout');
      }
    } catch (e) {
      // Ignore network errors on logout
    } finally {
      clearAuth();
    }
  }, [clearAuth]);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        login,
        registerVolunteer,
        initiateGoogleLogin,
        handleGoogleCallback,
        loginWithGoogle,
        logout,
        refreshUser,
        getDashboardRouteForRole,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
