/**
 * ClaimFlow - Core API client service.
 * Handles authentication headers, tenant context, request/response normalization.
 */

const BASE_URL = import.meta.env?.VITE_API_BASE_URL || '/api';
const TOKEN_KEY = 'claimflow_token';
const USER_KEY = 'claimflow_user';

let authToken: string | null = null;
let tenantId: string | null = null;

function setAuthToken(token: string | null): void {
  authToken = token;
}

function setTenantId(id: string | null): void {
  tenantId = id;
}

function buildHeaders(extra: Record<string, string> = {}): Record<string, string> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...extra,
  };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }
  if (tenantId) {
    headers['X-Tenant-ID'] = tenantId;
  }
  return headers;
}

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  if (tenantId) headers['X-Tenant-ID'] = tenantId;
  return headers;
}

function clearStoredSession(): void {
  authToken = null;
  tenantId = null;
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
  // Keep cleanup of old keys for users upgrading from localStorage-based sessions.
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
    const error: any = new Error(errorBody.detail || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = errorBody;

    // 401 on any authenticated request means the token is invalid/expired.
    // Clear local session and bounce to /login so the user can re-authenticate.
    // The login endpoint itself will surface 401 directly (its onError handles it).
    if (response.status === 401 && typeof window !== 'undefined') {
      const path = window.location.pathname;
      const isLoginPage = path === '/login' || path.endsWith('/login');
      const isLoginCall = response.url.endsWith('/auth/login');
      if (!isLoginPage && !isLoginCall) {
        clearStoredSession();
        // Use replace so the broken page is not in history
        window.location.replace('/login');
      }
    }

    throw error;
  }
  if (response.status === 204) return undefined as unknown as T;
  return response.json() as Promise<T>;
}

type ParamsInput = Record<string, string | number | boolean | undefined> | { params: Record<string, string | number | boolean | undefined> };

function resolveParams(input?: ParamsInput): Record<string, string | number | boolean> | undefined {
  if (!input) return undefined;
  if ('params' in input && typeof input.params === 'object') {
    return input.params as Record<string, string | number | boolean>;
  }
  return input as Record<string, string | number | boolean>;
}

async function get<T = any>(path: string, paramsInput?: ParamsInput): Promise<T> {
  let url = `${BASE_URL}${path}`;
  const params = resolveParams(paramsInput);
  if (params) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) qs.set(k, String(v));
    });
    const qsStr = qs.toString();
    if (qsStr) url += `?${qsStr}`;
  }
  const resp = await fetch(url, { method: 'GET', headers: buildHeaders() });
  return handleResponse<T>(resp);
}

async function post<T = any>(path: string, body?: any, options?: { headers?: Record<string, string> }): Promise<T> {
  if (body instanceof FormData) {
    return upload<T>(path, body);
  }
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: buildHeaders(options?.headers),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(resp);
}

async function put<T = any>(path: string, body?: any): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: 'PUT',
    headers: buildHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(resp);
}

async function patch<T = any>(path: string, body?: any): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: 'PATCH',
    headers: buildHeaders(),
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(resp);
}

async function del<T = any>(path: string): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, { method: 'DELETE', headers: buildHeaders() });
  return handleResponse<T>(resp);
}

async function upload<T = any>(path: string, formData: FormData): Promise<T> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });
  return handleResponse<T>(resp);
}

async function downloadBlob(path: string): Promise<Blob> {
  const resp = await fetch(`${BASE_URL}${path}`, {
    method: 'GET',
    headers: authHeaders(),
  });
  if (!resp.ok) {
    const errorBody = await resp.json().catch(() => ({ detail: resp.statusText }));
    const error: any = new Error(errorBody.detail || `HTTP ${resp.status}`);
    error.status = resp.status;
    if (resp.status === 401 && typeof window !== 'undefined') {
      clearStoredSession();
      window.location.replace('/login');
    }
    throw error;
  }
  return resp.blob();
}

/**
 * Fetch a CSV / file export and trigger the browser download.
 * Reads filename from Content-Disposition when present, falls back to `fallback`.
 */
async function downloadFile(path: string, fallback: string, query?: ParamsInput): Promise<void> {
  let url = `${BASE_URL}${path}`;
  const params = resolveParams(query);
  if (params) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) qs.set(k, String(v));
    });
    const qsStr = qs.toString();
    if (qsStr) url += `?${qsStr}`;
  }

  const resp = await fetch(url, { method: 'GET', headers: authHeaders() });
  if (!resp.ok) {
    const errorBody = await resp.json().catch(() => ({ detail: resp.statusText }));
    const error: any = new Error(errorBody.detail || `HTTP ${resp.status}`);
    error.status = resp.status;
    if (resp.status === 401 && typeof window !== 'undefined') {
      clearStoredSession();
      window.location.replace('/login');
    }
    throw error;
  }

  const cd = resp.headers.get('Content-Disposition') || '';
  const match = /filename="?([^"]+)"?/.exec(cd);
  const filename = match ? match[1] : fallback;

  const blob = await resp.blob();
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(blobUrl);
}

export const apiService = {
  get,
  post,
  put,
  patch,
  delete: del,
  upload,
  downloadBlob,
  downloadFile,
  setAuthToken,
  setTenantId,
};

export default apiService;
