import { useParams, Link } from 'react-router-dom';
import { useJobDetail } from '../hooks/useJobDetail';
import { LogViewer } from '../components/LogViewer';
import { API_ROOT } from '../api';

function getStatusColor(status: string): string {
  switch (status) {
    case 'success':
      return '#4ade80';
    case 'failure':
      return '#f87171';
    case 'solving':
      return '#fbbf24';
    case 'queued':
      return '#60a5fa';
    default:
      return '#9ca3af';
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'N/A';
  const date = new Date(dateStr);
  return date.toLocaleString();
}

export function JobDetail() {
  const { jobId } = useParams<{ jobId: string }>();
  const { job, log, loading, error, refresh } = useJobDetail(Number(jobId));

  if (loading && !job) {
    return (
      <div className="job-detail-page">
        <div className="loading">Loading job details...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="job-detail-page">
        <div className="error-message">{error}</div>
        <Link to="/" className="back-link">&larr; Back to gallery</Link>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="job-detail-page">
        <div className="error-message">Job not found</div>
        <Link to="/" className="back-link">&larr; Back to gallery</Link>
      </div>
    );
  }

  const isRunning = job.status === 'solving';
  const isCompleted = job.status === 'success';
  const isFailed = job.status === 'failure';

  return (
    <div className="job-detail-page">
      <header className="detail-header">
        <Link to="/" className="back-link">&larr; Back to gallery</Link>
        <h1>Job #{job.job_id}</h1>
        <button onClick={refresh} className="btn-refresh">Refresh</button>
      </header>

      <div className="detail-status-bar">
        <span
          className="status-badge"
          style={{ backgroundColor: getStatusColor(job.status) }}
        >
          {job.status}
        </span>
        {isRunning && job.stage && (
          <span className="stage-info">
            Stage: {job.stage} - {job.message}
          </span>
        )}
      </div>

      {/* Main content area */}
      <div className="detail-content">
        {/* Image display */}
        {isCompleted && job.has_annotated_image && job.annotated_image_url && (
          <div className="detail-image">
            <img
              src={`${API_ROOT}${job.annotated_image_url}`}
              alt={`Annotated Job ${job.job_id}`}
            />
          </div>
        )}

        {!isCompleted && job.original_image_url && (
          <div className="detail-image">
            <img
              src={`${API_ROOT}${job.original_image_url}`}
              alt={`Original Job ${job.job_id}`}
            />
            {isRunning && <div className="image-overlay">Processing...</div>}
          </div>
        )}

        {/* Failure reason */}
        {isFailed && job.failure_reason && (
          <div className="failure-reason">
            <h3>Error</h3>
            <pre>{job.failure_reason}</pre>
          </div>
        )}

        {/* Objects in field */}
        {isCompleted && job.objects_in_field && job.objects_in_field.length > 0 && (
          <div className="objects-section">
            <h3>Objects in Field</h3>
            <div className="objects-list">
              {job.objects_in_field.map((obj, idx) => (
                <span key={idx} className="object-tag">{obj}</span>
              ))}
            </div>
          </div>
        )}

        {/* Calibration data */}
        {isCompleted && job.calibration && (
          <div className="calibration-section">
            <h3>Calibration</h3>
            <div className="calibration-grid">
              {job.calibration.ra !== undefined && (
                <div className="calibration-item">
                  <span className="label">RA:</span>
                  <span className="value">{job.calibration.ra.toFixed(6)}&deg;</span>
                </div>
              )}
              {job.calibration.dec !== undefined && (
                <div className="calibration-item">
                  <span className="label">Dec:</span>
                  <span className="value">{job.calibration.dec.toFixed(6)}&deg;</span>
                </div>
              )}
              {job.calibration.pixscale !== undefined && (
                <div className="calibration-item">
                  <span className="label">Pixel Scale:</span>
                  <span className="value">{job.calibration.pixscale.toFixed(4)} arcsec/px</span>
                </div>
              )}
              {job.calibration.orientation !== undefined && (
                <div className="calibration-item">
                  <span className="label">Orientation:</span>
                  <span className="value">{job.calibration.orientation.toFixed(2)}&deg;</span>
                </div>
              )}
              {job.calibration.radius !== undefined && (
                <div className="calibration-item">
                  <span className="label">Radius:</span>
                  <span className="value">{job.calibration.radius.toFixed(4)}&deg;</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Download links */}
        {isCompleted && job.artifacts && Object.keys(job.artifacts).length > 0 && (
          <div className="downloads-section">
            <h3>Downloads</h3>
            <div className="download-links">
              {job.artifacts.wcs && (
                <a href={`${API_ROOT}${job.artifacts.wcs}`} className="download-btn">WCS</a>
              )}
              {job.artifacts.new_fits && (
                <a href={`${API_ROOT}${job.artifacts.new_fits}`} className="download-btn">New FITS</a>
              )}
              {job.artifacts.corr && (
                <a href={`${API_ROOT}${job.artifacts.corr}`} className="download-btn">Corr</a>
              )}
              {job.artifacts.kml && (
                <a href={`${API_ROOT}${job.artifacts.kml}`} className="download-btn">KML</a>
              )}
              {job.artifacts.annotated && (
                <a href={`${API_ROOT}${job.artifacts.annotated}`} className="download-btn">Annotated</a>
              )}
            </div>
          </div>
        )}

        {/* Log viewer */}
        <div className="log-section">
          <h3>
            Log Output
            {isRunning && <span className="polling-indicator"> (updating every 10s)</span>}
          </h3>
          <LogViewer log={log} autoScroll={isRunning} />
        </div>

        {/* Timestamps */}
        <div className="timestamps-section">
          <div className="timestamp-item">
            <span className="label">Created:</span>
            <span className="value">{formatDate(job.created_at)}</span>
          </div>
          {job.started_at && (
            <div className="timestamp-item">
              <span className="label">Started:</span>
              <span className="value">{formatDate(job.started_at)}</span>
            </div>
          )}
          {job.finished_at && (
            <div className="timestamp-item">
              <span className="label">Finished:</span>
              <span className="value">{formatDate(job.finished_at)}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
