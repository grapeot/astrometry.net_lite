import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchJobDetail, fetchJobLog, type JobDetail, type JobLogResponse } from '../api';

const POLL_INTERVAL = 10000; // 10 seconds

export function useJobDetail(jobId: number) {
  const [job, setJob] = useState<JobDetail | null>(null);
  const [log, setLog] = useState<string>('');
  const [logOffset, setLogOffset] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<number | null>(null);

  // Load initial job detail
  const loadDetail = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchJobDetail(jobId);
      setJob(data.job);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load job');
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  // Poll for log updates
  const pollLog = useCallback(async () => {
    try {
      const data: JobLogResponse = await fetchJobLog(jobId, logOffset);

      // Append new log content
      if (data.log) {
        setLog(prev => prev + data.log);
        setLogOffset(data.offset);
      }

      // Update job status info
      if (data.job_status !== 'solving') {
        // Job completed or failed, reload full detail
        const detailData = await fetchJobDetail(jobId);
        setJob(detailData.job);
        // Stop polling
        if (intervalRef.current) {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
        }
      } else {
        // Update stage/message while still running
        setJob(prev => prev ? {
          ...prev,
          status: data.job_status,
          stage: data.stage ?? undefined,
          message: data.message ?? undefined,
        } : null);
      }
    } catch (err) {
      console.error('Failed to poll log:', err);
    }
  }, [jobId, logOffset]);

  // Load initial log content (for completed jobs too)
  const loadInitialLog = useCallback(async () => {
    try {
      const data: JobLogResponse = await fetchJobLog(jobId, 0);
      if (data.log) {
        setLog(data.log);
        setLogOffset(data.offset);
      }
    } catch (err) {
      console.error('Failed to load initial log:', err);
    }
  }, [jobId]);

  // Initial load
  useEffect(() => {
    loadDetail();
    loadInitialLog();
  }, [loadDetail, loadInitialLog]);

  // Start polling when job is solving
  useEffect(() => {
    if (job?.status === 'solving') {
      // Poll immediately
      pollLog();
      // Then poll every 10 seconds
      intervalRef.current = window.setInterval(pollLog, POLL_INTERVAL);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [job?.status, pollLog]);

  const refresh = useCallback(() => {
    setLog('');
    setLogOffset(0);
    loadDetail();
    loadInitialLog();
  }, [loadDetail, loadInitialLog]);

  return {
    job,
    log,
    loading,
    error,
    refresh,
  };
}
