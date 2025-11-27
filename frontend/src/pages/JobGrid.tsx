import { useJobList } from '../hooks/useJobList';
import { JobCard } from '../components/JobCard';

export function JobGrid() {
  const { jobs, loading, error, total, hasNext, refresh, loadMore } = useJobList(20);

  return (
    <div className="job-grid-page">
      <header className="page-header">
        <h1>Astrometry.net Lite</h1>
        <p>Public job gallery - click any job to view details</p>
        <div className="header-actions">
          <span className="job-count">{total} jobs</span>
          <button onClick={refresh} disabled={loading} className="btn-refresh">
            {loading ? 'Loading...' : 'Refresh'}
          </button>
        </div>
      </header>

      {error && <div className="error-message">{error}</div>}

      <div className="job-grid">
        {jobs?.map(job => (
          <JobCard key={job.job_id} job={job} />
        ))}
      </div>

      {(!jobs || jobs.length === 0) && !loading && (
        <div className="empty-state">No jobs yet</div>
      )}

      {hasNext && (
        <div className="load-more">
          <button onClick={loadMore} disabled={loading} className="btn-load-more">
            {loading ? 'Loading...' : 'Load More'}
          </button>
        </div>
      )}
    </div>
  );
}
