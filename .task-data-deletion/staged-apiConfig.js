import axios from 'axios';
import toast from 'react-hot-toast';
import { io } from 'socket.io-client';

/* =========================
   BASE URL
========================= */
const backendOrigin =
  import.meta.env.VITE_BACKEND_URL ||
  import.meta.env.VITE_API_URL ||
  (import.meta.env.PROD ? '/' : 'http://localhost:8000');

export const BASE_URL = backendOrigin.replace(/\/$/, '');
export const SOCKET_URL = BASE_URL;
export const SOCKET_PROGRESS_ENABLED =
  import.meta.env.VITE_ENABLE_SOCKET_PROGRESS === 'true';

/* =========================
   WHATSAPP CONFIG (FIXED)
========================= */
export const whatsappApiMode =
  import.meta.env.VITE_WHATSAPP_API_MODE || 'api';

export const whatsappSendPath =
  import.meta.env.VITE_WHATSAPP_SEND_PATH ||
  '/api/communications/whatsapp/send';

export const whatsappProvider =
  import.meta.env.VITE_WHATSAPP_PROVIDER || 'meta_cloud';

export const whatsappGraphVersion =
  import.meta.env.VITE_WHATSAPP_GRAPH_VERSION || 'v23.0';

export const whatsappPhoneNumberId =
  import.meta.env.VITE_WHATSAPP_PHONE_NUMBER_ID || '';

/* =========================
   AUTH TOKEN
========================= */
export const getStoredAuthToken = () => {
  const storedAuth = localStorage.getItem('auth-storage');

  if (!storedAuth) return null;

  try {
    const parsed = JSON.parse(storedAuth);
    return parsed?.state?.token || null;
  } catch {
    return null;
  }
};

/* =========================
   ERROR FORMATTER
========================= */
export const formatApiError = (error) => {
  const detail = error?.response?.data?.detail;
  return (typeof detail === 'string' ? detail : detail?.provider_message || detail?.message) ||
    error?.response?.data?.message || error?.response?.data?.error ||
    error?.message || 'Something went wrong';
};

/* =========================
   AXIOS INSTANCE
========================= */
const api = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
  withCredentials: true,
});

/* =========================
   REQUEST INTERCEPTOR
========================= */
api.interceptors.request.use(
  (config) => {
    const token = getStoredAuthToken();

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Handle FormData safely
    if (config.data instanceof FormData) {
      delete config.headers['Content-Type'];
      delete config.headers['content-type'];
    } else {
      config.headers['Content-Type'] = 'application/json';
    }

    return config;
  },
  (error) => Promise.reject(error)
);

/* =========================
   RESPONSE INTERCEPTOR
========================= */
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error?.response?.status;
    const message = formatApiError(error);

    if (status === 401) {
      localStorage.removeItem('auth-storage');

      if (!['/login', '/register'].includes(window.location.pathname)) {
        window.location.replace('/login');
      }
    } else if (status >= 500) {
      toast.error('Server error. Please try again later.');
    } else if (status >= 400) {
      console.error('API Error:', message);
    }

    return Promise.reject(error);
  }
);

/* =========================
   API WRAPPER
========================= */
export const apiWrapper = async ({
  url,
  method = 'GET',
  data,
  params,
  headers = {},
  responseType,
}) => {
  return api({
    url,
    method,
    data,
    params,
    headers,
    responseType,
  });
};

/* =========================
   SOCKET CLIENT
========================= */
let socketInstance = null;

export const getSocketClient = () => {
  const token = getStoredAuthToken();

  if (!socketInstance) {
    socketInstance = io(SOCKET_URL, {
      autoConnect: false,
      transports: ['websocket', 'polling'],
      auth: { token },
    });
  } else {
    socketInstance.auth = { token };
  }

  return socketInstance;
};

export default api;
