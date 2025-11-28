import { Link } from 'react-router-dom';
import { API_ROOT } from '../api';
import type { JobListItem } from '../api';

interface JobCardProps {
  job: JobListItem;
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'success':
      return '#4ade80'; // green
    case 'failure':
      return '#f87171'; // red
    case 'solving':
      return '#fbbf24'; // yellow
    case 'queued':
      return '#60a5fa'; // blue
    default:
      return '#9ca3af'; // gray
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function JobCard({ job }: JobCardProps) {
  // Prefer annotated image if available, fallback to original
  const annotatedUrl = job.has_annotated_image && job.annotated_image_url
    ? `${API_ROOT}${job.annotated_image_url}`
    : null;
  const originalUrl = job.original_image_url
    ? `${API_ROOT}${job.original_image_url}`
    : null;
  const imageUrl = annotatedUrl || originalUrl;
  const isRunning = job.status === 'solving' || job.status === 'queued';

  return (
    <Link to={`/jobs/${job.job_id}`} className="job-card">
      <div className="job-card-image">
        {imageUrl ? (
          <>
            <img
              src={imageUrl}
              alt={`Job ${job.job_id}`}
              loading="lazy"
              onError={(e) => {
                // If annotated image fails, try original
                const target = e.target as HTMLImageElement;
                if (imageUrl === annotatedUrl && originalUrl) {
                  target.src = originalUrl;
                }
              }}
            />
            {isRunning && <div className="image-overlay">Processing...</div>}
          </>
        ) : (
          <div className="job-card-placeholder">No Image</div>
        )}
        <div
          className="job-card-status"
          style={{ backgroundColor: getStatusColor(job.status) }}
        >
          {job.status}
        </div>
      </div>
      <div className="job-card-info">
        <div className="job-card-id">Job #{job.job_id}</div>
        {job.status === 'solving' && job.stage && (
          <div className="job-card-stage">{job.stage}: {job.message}</div>
        )}
        <div className="job-card-date">{formatDate(job.created_at)}</div>
      </div>
    </Link>
  );
}
