/**
 * ClaimFlow - Core API client service.
 * Handles authentication headers, tenant context, request/response normalization.
 */

const BASE_URL = import.meta.env?.VITE_API_BASE_URL || '/api';

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

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({ detail: response.statusText }));
    const error: any = new Error(errorBody.detail || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = errorBody;
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
    throw error;
  }
  return resp.blob();
}

export const apiService = {
  get,
  post,
  put,
  patch,
  delete: del,
  upload,
  downloadBlob,
  setAuthToken,
  setTenantId,
};

export default apiService;
