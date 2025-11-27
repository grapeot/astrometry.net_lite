import { describe, it, expect, beforeAll } from 'vitest'
import { fetchJobList, fetchJobDetail, fetchJobLog } from './api'

// Note: MSW server is started in setup.ts

describe('API Client', () => {
  describe('fetchJobList', () => {
    it('fetches job list successfully', async () => {
      const result = await fetchJobList(1, 20)

      expect(result.status).toBe('success')
      expect(result.jobs).toBeDefined()
      expect(Array.isArray(result.jobs)).toBe(true)
      expect(result.pagination).toBeDefined()
    })

    it('returns pagination info', async () => {
      const result = await fetchJobList(1, 20)

      expect(result.pagination.page).toBe(1)
      expect(result.pagination.limit).toBe(20)
      expect(typeof result.pagination.total).toBe('number')
      expect(typeof result.pagination.has_next).toBe('boolean')
    })

    it('returns jobs with required fields', async () => {
      const result = await fetchJobList(1, 20)

      expect(result.jobs.length).toBeGreaterThan(0)
      const job = result.jobs[0]
      expect(job).toHaveProperty('job_id')
      expect(job).toHaveProperty('status')
      expect(job).toHaveProperty('created_at')
    })

    it('supports status filter', async () => {
      const result = await fetchJobList(1, 20, 'success')

      expect(result.status).toBe('success')
      // All returned jobs should have success status
      result.jobs.forEach(job => {
        expect(job.status).toBe('success')
      })
    })
  })

  describe('fetchJobDetail', () => {
    it('fetches job detail successfully', async () => {
      const result = await fetchJobDetail(1)

      expect(result.status).toBe('success')
      expect(result.job).toBeDefined()
      expect(result.job.job_id).toBe(1)
    })

    it('returns calibration data', async () => {
      const result = await fetchJobDetail(1)

      expect(result.job.calibration).toBeDefined()
      expect(result.job.calibration?.ra).toBe(180.0)
      expect(result.job.calibration?.dec).toBe(45.0)
      expect(result.job.calibration?.radius).toBe(1.5)
    })

    it('returns artifacts', async () => {
      const result = await fetchJobDetail(1)

      expect(result.job.artifacts).toBeDefined()
      expect(result.job.artifacts?.wcs).toBe('/wcs_file/1')
      expect(result.job.artifacts?.annotated).toBe('/annotated_display/1')
    })

    it('returns objects in field', async () => {
      const result = await fetchJobDetail(1)

      expect(result.job.objects_in_field).toBeDefined()
      expect(result.job.objects_in_field).toContain('M31')
    })
  })

  describe('fetchJobLog', () => {
    it('fetches job log successfully', async () => {
      const result = await fetchJobLog(1, 0)

      expect(result.status).toBe('success')
      expect(result.log).toBeDefined()
      expect(typeof result.offset).toBe('number')
      expect(typeof result.is_running).toBe('boolean')
    })

    it('returns stage and message for running jobs', async () => {
      const result = await fetchJobLog(1, 0)

      expect(result.stage).toBeDefined()
      expect(result.message).toBeDefined()
    })

    it('includes job status', async () => {
      const result = await fetchJobLog(1, 0)

      expect(result.job_status).toBeDefined()
    })
  })
})
