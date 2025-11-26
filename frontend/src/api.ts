export const API_BASE: string = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8002/api';
export const API_ROOT = API_BASE.replace(/\/api\/?$/, '');

async function request<T>(path: string, init: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  const data = await res.json();
  return data as T;
}

export interface LoginResponse {
  status: string;
  session?: string;
  errormessage?: string;
}

export interface UploadResponse {
  status: string;
  subid?: string;
  job_id?: number;
  errormessage?: string;
}

export interface JobInfoResponse {
  status: string;
  original_filename?: string;
  calibration?: Record<string, unknown>;
}

export async function login(apikey: string): Promise<LoginResponse> {
  return request<LoginResponse>('/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ apikey }),
  });
}

export async function uploadFile(session: string, file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('request-json', JSON.stringify({ session }));
  form.append('file', file);
  const res = await fetch(`${API_BASE}/upload`, {
    method: 'POST',
    body: form,
  });
  return res.json();
}

export interface MyJobsResponse {
  status: string;
  jobs?: number[];
}

export async function fetchMyJobs(session: string): Promise<number[]> {
  const data = await request<MyJobsResponse>('/myjobs/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session }),
  });
  return data.jobs ?? [];
}

export interface JobStatusResponse {
  status: string;
}

export async function fetchJobStatus(jobId: number): Promise<JobStatusResponse> {
  return request<JobStatusResponse>(`/jobs/${jobId}`, {
    method: 'GET',
  });
}

export async function fetchJobInfo(jobId: number): Promise<JobInfoResponse> {
  return request<JobInfoResponse>(`/jobs/${jobId}/info`, {
    method: 'GET',
  });
}
