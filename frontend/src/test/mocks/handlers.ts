import { http, HttpResponse } from 'msw'

// API base URL - must match the one in api.ts
const API_BASE = 'http://127.0.0.1:8002/api'

// Sample job data for testing
const sampleJobs = [
  {
    job_id: 1,
    status: 'success',
    created_at: '2024-01-15T10:30:00Z',
    started_at: '2024-01-15T10:30:05Z',
    finished_at: '2024-01-15T10:35:00Z',
    has_annotated_image: true,
    annotated_image_url: '/annotated_display/1',
    original_image_url: '/api/files/original/1',
  },
  {
    job_id: 2,
    status: 'solving',
    created_at: '2024-01-15T11:00:00Z',
    started_at: '2024-01-15T11:00:05Z',
    finished_at: null,
    has_annotated_image: false,
    original_image_url: '/api/files/original/2',
    stage: 'extracting',
    message: 'Extracting sources...',
  },
  {
    job_id: 3,
    status: 'failure',
    created_at: '2024-01-15T09:00:00Z',
    started_at: '2024-01-15T09:00:05Z',
    finished_at: '2024-01-15T09:05:00Z',
    has_annotated_image: false,
    original_image_url: '/api/files/original/3',
  },
]

const sampleJobDetail = {
  job_id: 1,
  status: 'success',
  created_at: '2024-01-15T10:30:00Z',
  started_at: '2024-01-15T10:30:05Z',
  finished_at: '2024-01-15T10:35:00Z',
  failure_reason: null,
  has_annotated_image: true,
  annotated_image_url: '/annotated_display/1',
  original_image_url: '/api/files/original/1',
  original_filename: 'galaxy.jpg',
  calibration: {
    ra: 180.0,
    dec: 45.0,
    radius: 1.5,
    pixscale: 1.2,
    orientation: 0.0,
    parity: 1,
  },
  objects_in_field: ['M31', 'NGC 224', 'HD 3914'],
  artifacts: {
    wcs: '/wcs_file/1',
    new_fits: '/new_fits_file/1/',
    corr: '/corr_file/1',
    annotated: '/annotated_display/1',
  },
}

export const handlers = [
  // List jobs
  http.get(`${API_BASE}/jobs/list`, ({ request }) => {
    const url = new URL(request.url)
    const page = parseInt(url.searchParams.get('page') || '1')
    const limit = parseInt(url.searchParams.get('limit') || '20')
    const status = url.searchParams.get('status')

    let filteredJobs = sampleJobs
    if (status) {
      filteredJobs = sampleJobs.filter(j => j.status === status)
    }

    return HttpResponse.json({
      status: 'success',
      jobs: filteredJobs,
      pagination: {
        page,
        limit,
        total: filteredJobs.length,
        has_next: false,
      },
    })
  }),

  // Get job detail
  http.get(`${API_BASE}/jobs/:jobId/detail`, ({ params }) => {
    const jobId = parseInt(params.jobId as string)

    if (jobId === 1) {
      return HttpResponse.json({
        status: 'success',
        job: sampleJobDetail,
      })
    }

    if (jobId === 999) {
      return HttpResponse.json(
        { detail: 'Job not found' },
        { status: 404 }
      )
    }

    return HttpResponse.json({
      status: 'success',
      job: {
        ...sampleJobDetail,
        job_id: jobId,
      },
    })
  }),

  // Get job log
  http.get(`${API_BASE}/jobs/:jobId/log`, ({ params, request }) => {
    const url = new URL(request.url)
    const offset = parseInt(url.searchParams.get('offset') || '0')
    const jobId = parseInt(params.jobId as string)

    return HttpResponse.json({
      status: 'success',
      job_status: 'solving',
      stage: 'extracting',
      message: 'Extracting sources...',
      log: 'Log content from offset ' + offset,
      offset: offset + 100,
      is_running: true,
    })
  }),

  // Login
  http.post(`${API_BASE}/login`, async ({ request }) => {
    const formData = await request.formData()
    const requestJson = formData.get('request-json')
    if (!requestJson) {
      return HttpResponse.json({
        status: 'error',
        errormessage: 'missing request-json',
      })
    }

    const data = JSON.parse(requestJson as string)

    if (data.apikey === 'valid_key') {
      return HttpResponse.json({
        status: 'success',
        session: 'valid_key',
        message: 'authenticated',
      })
    }

    return HttpResponse.json({
      status: 'error',
      errormessage: 'bad apikey',
    })
  }),

  // Upload
  http.post(`${API_BASE}/upload`, async () => {
    return HttpResponse.json({
      status: 'success',
      subid: '507f1f77bcf86cd799439011',
      hash: 'abc123_test.jpg',
      job_id: 100,
      queue_id: '507f1f77bcf86cd799439012',
    })
  }),
]
