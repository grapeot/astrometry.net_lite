import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useJobDetail } from './useJobDetail'

describe('useJobDetail', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('fetches job detail by id', async () => {
    vi.useRealTimers()
    const { result } = renderHook(() => useJobDetail(1))

    // Initial loading state
    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.job).not.toBeNull()
    expect(result.current.job?.job_id).toBe(1)
    expect(result.current.error).toBeNull()
  })

  it('returns job with calibration data', async () => {
    vi.useRealTimers()
    const { result } = renderHook(() => useJobDetail(1))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.job?.calibration).toBeDefined()
    expect(result.current.job?.calibration?.ra).toBe(180.0)
    expect(result.current.job?.calibration?.dec).toBe(45.0)
  })

  it('returns job with artifacts', async () => {
    vi.useRealTimers()
    const { result } = renderHook(() => useJobDetail(1))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.job?.artifacts).toBeDefined()
    expect(result.current.job?.artifacts?.wcs).toBe('/wcs_file/1')
  })

  it('returns objects in field', async () => {
    vi.useRealTimers()
    const { result } = renderHook(() => useJobDetail(1))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.job?.objects_in_field).toBeDefined()
    expect(result.current.job?.objects_in_field).toContain('M31')
  })

  it('loads log content', async () => {
    vi.useRealTimers()
    const { result } = renderHook(() => useJobDetail(1))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    // Log should be loaded
    await waitFor(() => {
      expect(result.current.log).toBeDefined()
    })
  })

  it('supports refresh', async () => {
    vi.useRealTimers()
    const { result } = renderHook(() => useJobDetail(1))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    // Trigger refresh
    act(() => {
      result.current.refresh()
    })

    await waitFor(() => {
      expect(result.current.job).not.toBeNull()
    })
  })
})
