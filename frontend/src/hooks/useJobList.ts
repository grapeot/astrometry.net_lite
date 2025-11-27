import { useState, useEffect, useCallback } from 'react';
import { fetchJobList, type JobListItem, type JobListResponse } from '../api';

export function useJobList(initialLimit: number = 20) {
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [page, setPage] = useState(1);
  const [limit] = useState(initialLimit);
  const [total, setTotal] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const refresh = useCallback(() => {
    setJobs([]);
    loadJobs(1, false);
  }, [loadJobs]);

  const loadMore = useCallback(() => {
    if (hasNext && !loading) {
      loadJobs(page + 1, true);
    }
  }, [hasNext, loading, page, loadJobs]);

  useEffect(() => {
    loadJobs(1, false);
  }, [loadJobs]);

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
