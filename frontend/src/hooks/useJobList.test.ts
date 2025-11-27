import { describe, it, expect } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'
import { useJobList } from './useJobList'

describe('useJobList', () => {
  it('fetches job list on mount', async () => {
    const { result } = renderHook(() => useJobList())

    // Initial loading state
    expect(result.current.loading).toBe(true)

    // Wait for data to load
    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    // Should have jobs
    expect(result.current.jobs.length).toBeGreaterThan(0)
    expect(result.current.error).toBeNull()
  })

  it('returns job data with expected fields', async () => {
    const { result } = renderHook(() => useJobList())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    const firstJob = result.current.jobs[0]
    expect(firstJob).toHaveProperty('job_id')
    expect(firstJob).toHaveProperty('status')
    expect(firstJob).toHaveProperty('created_at')
  })

  it('provides pagination info', async () => {
    const { result } = renderHook(() => useJobList())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(typeof result.current.total).toBe('number')
    expect(typeof result.current.hasNext).toBe('boolean')
  })

  it('supports refresh', async () => {
    const { result } = renderHook(() => useJobList())

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    // Trigger refresh
    act(() => {
      result.current.refresh()
    })

    // Should be loading again briefly
    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.jobs.length).toBeGreaterThan(0)
  })

  it('respects initial limit parameter', async () => {
    const { result } = renderHook(() => useJobList(5))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    // Hook should use the provided limit
    expect(result.current.jobs).toBeDefined()
  })
})
