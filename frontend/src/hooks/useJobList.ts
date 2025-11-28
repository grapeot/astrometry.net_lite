import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchJobList, fetchJobDetail, type JobListItem, type JobListResponse } from '../api';

const POLL_INTERVAL = 10000; // 10 seconds

export function useJobList(initialLimit: number = 20) {
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(initialLimit);
  const [total, setTotal] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<number | null>(null);

  const loadJobs = useCallback(async (pageNum: number, append: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const data: JobListResponse = await fetchJobList(pageNum, limit);
      const jobList = data.jobs ?? [];
      if (append) {
        setJobs(prev => [...prev, ...jobList]);
      } else {
        setJobs(jobList);
      }
      setTotal(data.pagination?.total ?? 0);
      setHasNext(data.pagination?.has_next ?? false);
      setPage(pageNum);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load jobs');
    } finally {
      setLoading(false);
    }
  }, [limit]);

  // Poll for solving jobs to update their status
  const pollSolvingJobs = useCallback(async () => {
    setJobs(prev => {
      const solvingJobs = prev.filter(job => job.status === 'solving' || job.status === 'queued');
      if (solvingJobs.length === 0) {
        return prev;
      }

      // Update jobs in parallel
      Promise.all(
        solvingJobs.map(async (job) => {
          try {
            const detail = await fetchJobDetail(job.job_id);
            return detail.job;
          } catch {
            return null;
          }
        })
      ).then((updatedJobs) => {
        setJobs(current => {
          const updatedMap = new Map(updatedJobs.filter((job): job is NonNullable<typeof job> => job !== null).map(job => [job.job_id, job]));
          return current.map(job => {
            const updated = updatedMap.get(job.job_id);
            if (updated) {
              // Convert JobDetail to JobListItem format
              return {
                job_id: updated.job_id,
                status: updated.status,
                created_at: updated.created_at,
                started_at: updated.started_at,
                finished_at: updated.finished_at,
                has_annotated_image: updated.has_annotated_image || false,
                annotated_image_url: updated.annotated_image_url,
                original_image_url: updated.original_image_url,
                stage: updated.stage,
                message: updated.message,
              };
            }
            return job;
          });
        });
      });

      return prev;
    });
  }, []);

  const refresh = useCallback(() => {
    setJobs([]);
    loadJobs(1, false);
  }, [loadJobs]);

  const loadMore = useCallback(() => {
    if (hasNext && !loading) {
      loadJobs(page + 1, true);
    }
  }, [hasNext, loading, page, loadJobs]);

  // Initial load
  useEffect(() => {
    loadJobs(1, false);
  }, [loadJobs]);

  // Poll for solving jobs
  useEffect(() => {
    // Start polling immediately
    pollSolvingJobs();
    // Then poll every 10 seconds
    intervalRef.current = window.setInterval(pollSolvingJobs, POLL_INTERVAL);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [pollSolvingJobs]);

  return {
    jobs,
    loading,
    error,
    total,
    hasNext,
    refresh,
    loadMore,
  };
}
