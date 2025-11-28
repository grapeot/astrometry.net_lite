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
  objects_in_field?: string[];
  tags?: string[];
  machine_tags?: string[];
}

export interface JobCalibrationResponse {
  ra?: number;
  dec?: number;
  radius?: number;
  pixscale?: number;
  orientation?: number;
  parity?: number;
  width_arcsec?: number;
  height_arcsec?: number;
  error?: string;
}

export interface JobAnnotationsResponse {
  annotations: Array<{ text?: string; [key: string]: unknown }>;
}

export interface JobObjectsResponse {
  objects_in_field: string[];
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

export async function uploadFromUrl(session: string, url: string): Promise<UploadResponse> {
  const params = new URLSearchParams();
  params.append('request-json', JSON.stringify({ session, url }));
  const res = await fetch(`${API_BASE}/url_upload`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
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

export async function fetchJobCalibration(jobId: number): Promise<JobCalibrationResponse> {
  return request<JobCalibrationResponse>(`/jobs/${jobId}/calibration`, {
    method: 'GET',
  });
}

export async function fetchJobAnnotations(jobId: number): Promise<JobAnnotationsResponse> {
  return request<JobAnnotationsResponse>(`/jobs/${jobId}/annotations`, {
    method: 'GET',
  });
}

export async function fetchJobObjects(jobId: number): Promise<JobObjectsResponse> {
  return request<JobObjectsResponse>(`/jobs/${jobId}/objects_in_field`, {
    method: 'GET',
  });
}

// ============================================
// Frontend API (public, no auth required)
// ============================================

export interface JobListItem {
  job_id: number;
  status: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  has_annotated_image: boolean;
  annotated_image_url?: string;
  original_image_url?: string;
  stage?: string;
  message?: string;
}

export interface JobListResponse {
  status: string;
  jobs: JobListItem[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    has_next: boolean;
  };
}

export interface JobDetail {
  job_id: number;
  status: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  failure_reason: string | null;
  has_annotated_image: boolean;
  annotated_image_url?: string;
  original_image_url?: string;
  original_filename?: string;
  calibration?: JobCalibrationResponse;
  objects_in_field?: string[];
  artifacts?: Record<string, string>;
  stage?: string;
  message?: string;
}

export interface JobDetailResponse {
  status: string;
  job: JobDetail;
}

export interface JobLogResponse {
  status: string;
  job_status: string;
  stage: string | null;
  message: string | null;
  log: string;
  offset: number;
  is_running: boolean;
}

export async function fetchJobList(page: number = 1, limit: number = 20, status?: string): Promise<JobListResponse> {
  const params = new URLSearchParams({ page: String(page), limit: String(limit) });
  if (status) params.set('status', status);
  return request<JobListResponse>(`/jobs/list?${params}`, { method: 'GET' });
}

export async function fetchJobDetail(jobId: number): Promise<JobDetailResponse> {
  return request<JobDetailResponse>(`/jobs/${jobId}/detail`, { method: 'GET' });
}

export async function fetchJobLog(jobId: number, offset: number = 0): Promise<JobLogResponse> {
  return request<JobLogResponse>(`/jobs/${jobId}/log?offset=${offset}`, { method: 'GET' });
}
