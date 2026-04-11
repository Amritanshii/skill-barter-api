import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401 && !window.location.pathname.includes('/login')) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const authAPI = {
  login: (identifier, password) => api.post('/auth/login', { identifier, password }),
  register: (data) => api.post('/auth/register', data),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
};

export const usersAPI = {
  getProfile: () => api.get('/users/me/profile'),
  updateProfile: (data) => api.patch('/users/me/profile', data),
  getOffered: () => api.get('/users/me/offered'),
  addOffered: (data) => api.post('/users/me/offered', data),
  removeOffered: (id) => api.delete(`/users/me/offered/${id}`),
  getWanted: () => api.get('/users/me/wanted'),
  addWanted: (data) => api.post('/users/me/wanted', data),
  removeWanted: (id) => api.delete(`/users/me/wanted/${id}`),
};

export const skillsAPI = {
  list: (params) => api.get('/skills', { params }),
  autocomplete: (q) => api.get('/skills/autocomplete', { params: { q, limit: 10 } }),
  create: (data) => api.post('/skills', data),
};

export const matchesAPI = {
  getMatches: (refresh = false) => api.get('/matches', { params: { refresh } }),
  getMatch: (id) => api.get(`/matches/${id}`),
  updateStatus: (id, status) => api.patch(`/matches/${id}`, { status }),
};

export default api;
