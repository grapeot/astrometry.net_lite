import React, { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'
import {
  API_ROOT,
  fetchJobInfo,
  fetchJobStatus,
  fetchMyJobs,
  login,
  uploadFile,
  fetchJobCalibration,
  fetchJobAnnotations,
  fetchJobObjects,
  type JobCalibrationResponse,
  type JobAnnotationsResponse,
  type JobObjectsResponse,
} from './api'

type JobRow = {
  id: number
  status: string
  filename?: string
}

type JobDetails = {
  calibration?: JobCalibrationResponse
  annotations?: JobAnnotationsResponse
  objects?: JobObjectsResponse
  loading: boolean
}

const SESSION_STORAGE_KEY = 'astrometry_session'

function App() {
  const [apiKey, setApiKey] = useState('')
  const [session, setSession] = useState<string | null>(() => {
    // Restore session from localStorage
    return localStorage.getItem(SESSION_STORAGE_KEY)
  })
  const [jobs, setJobs] = useState<JobRow[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [selectedJobId, setSelectedJobId] = useState<number | null>(null)
  const [jobDetails, setJobDetails] = useState<Record<number, JobDetails>>({})

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setMessage(null)
    try {
      const res = await login(apiKey.trim())
      if (res.status === 'success' && res.session) {
        setSession(res.session)
        // Save to localStorage
        localStorage.setItem(SESSION_STORAGE_KEY, res.session)
      } else {
        setMessage(res.errormessage ?? 'Login failed')
      }
    } catch {
      setMessage('Network error, please try again later')
    } finally {
      setLoading(false)
    }
  }

  const handleLogout = () => {
    setSession(null)
    setApiKey('')
    setJobs([])
    setJobDetails({})
    // Clear localStorage
    localStorage.removeItem(SESSION_STORAGE_KEY)
  }

  const refreshJobs = useCallback(async () => {
    if (!session) return
    setLoading(true)
    try {
      const ids = await fetchMyJobs(session)
      const rows: JobRow[] = []
      for (const id of ids) {
        const [status, info] = await Promise.all([fetchJobStatus(id), fetchJobInfo(id)])
        rows.push({ id, status: status.status, filename: info.original_filename })
      }
      setJobs(rows)
    } catch {
      setMessage('Failed to fetch job list')
    } finally {
      setLoading(false)
    }
  }, [session])

  useEffect(() => {
    if (session) {
      void refreshJobs()
    }
  }, [session, refreshJobs])

  const handleUpload = async (event: React.FormEvent) => {
    event.preventDefault()
    if (!session || !selectedFile) {
      setMessage('Please select a file and login first')
      return
    }
    setUploading(true)
    setMessage(null)
    try {
      const res = await uploadFile(session, selectedFile)
      if (res.status === 'success') {
        setSelectedFile(null)
        await refreshJobs()
        setMessage(`Upload successful, Submission ${res.subid}`)
      } else {
        setMessage(res.errormessage ?? 'Upload failed')
      }
    } catch {
      setMessage('Upload error')
    } finally {
      setUploading(false)
    }
  }

  const downloadBase = useMemo(() => API_ROOT, [])

  const loadJobDetails = useCallback(async (jobId: number) => {
    if (jobDetails[jobId]?.loading) return
    setJobDetails((prev) => ({ ...prev, [jobId]: { loading: true } }))
    try {
      const [calibration, annotations, objects] = await Promise.all([
        fetchJobCalibration(jobId).catch(() => null),
        fetchJobAnnotations(jobId).catch(() => null),
        fetchJobObjects(jobId).catch(() => null),
      ])
      setJobDetails((prev) => ({
        ...prev,
        [jobId]: { calibration: calibration || undefined, annotations: annotations || undefined, objects: objects || undefined, loading: false },
      }))
    } catch {
      setJobDetails((prev) => ({ ...prev, [jobId]: { loading: false } }))
    }
  }, [jobDetails])

  const handleJobClick = (jobId: number) => {
    if (selectedJobId === jobId) {
      setSelectedJobId(null)
    } else {
      setSelectedJobId(jobId)
      if (!jobDetails[jobId]) {
        void loadJobDetails(jobId)
      }
    }
  }

  return (
    <div className="layout">
      <header>
        <h1>Astrometry Lite Console</h1>
        <p>Login with API key, upload images and track Job status.</p>
      </header>

      {!session && (
        <section className="panel">
          <h2>Login</h2>
          <form onSubmit={handleLogin} className="form">
            <label>
              API Key
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Paste here"
              />
            </label>
            <button type="submit" disabled={loading || !apiKey.trim()}>
              {loading ? 'Logging in...' : 'Login'}
            </button>
          </form>
        </section>
      )}

      {session && (
        <>
          <section className="panel">
            <div className="panel-header">
              <h2>Logged In</h2>
              <button onClick={handleLogout} style={{ background: 'rgba(248, 113, 113, 0.2)', color: '#f87171' }}>
                Logout
              </button>
            </div>
            <p style={{ fontSize: '0.9rem', color: '#999', marginTop: '0.5rem' }}>
              Session: {session.substring(0, 20)}...
            </p>
          </section>

          <section className="panel">
            <h2>Upload Image</h2>
            <form onSubmit={handleUpload} className="form">
              <input
                type="file"
                accept=".fits,.fit,.fts,.jpg,.jpeg,.png"
                onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
              />
              <button type="submit" disabled={!selectedFile || uploading}>
                {uploading ? 'Uploading...' : 'Upload and Submit'}
              </button>
            </form>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Job List</h2>
              <button onClick={() => refreshJobs()} disabled={loading}>
                {loading ? 'Refreshing...' : 'Refresh'}
              </button>
            </div>
            {jobs.length === 0 ? (
              <p>No jobs yet, please upload an image first.</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Status</th>
                    <th>File</th>
                    <th>Download</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => {
                    const details = jobDetails[job.id]
                    const isExpanded = selectedJobId === job.id
                    return (
                      <React.Fragment key={job.id}>
                        <tr>
                          <td>
                            <button
                              onClick={() => handleJobClick(job.id)}
                              style={{
                                background: 'none',
                                border: 'none',
                                color: '#76d3ff',
                                cursor: 'pointer',
                                textDecoration: 'underline',
                                padding: 0,
                                fontSize: 'inherit',
                              }}
                            >
                              {job.id} {isExpanded ? '▼' : '▶'}
                            </button>
                          </td>
                          <td className={`status status-${job.status}`}>{job.status}</td>
                          <td>{job.filename ?? 'N/A'}</td>
                          <td className="downloads">
                            <a href={`${downloadBase}/wcs_file/${job.id}`} target="_blank" rel="noreferrer">
                              WCS
                            </a>
                            <a href={`${downloadBase}/new_fits_file/${job.id}/`} target="_blank" rel="noreferrer">
                              New FITS
                            </a>
                            <a href={`${downloadBase}/corr_file/${job.id}`} target="_blank" rel="noreferrer">
                              Corr
                            </a>
                            <a href={`${downloadBase}/annotated_display/${job.id}`} target="_blank" rel="noreferrer">
                              Annotated
                            </a>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr>
                            <td colSpan={4} style={{ padding: '1.5rem', backgroundColor: 'rgba(0, 0, 0, 0.2)' }}>
                              {details?.loading ? (
                                <div>Loading...</div>
                              ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                                  {details?.calibration && !details.calibration.error && (
                                    <div>
                                      <h3 style={{ marginTop: 0, marginBottom: '0.75rem', fontSize: '1.1rem' }}>Calibration Data</h3>
                                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.5rem', fontSize: '0.9rem' }}>
                                        {details.calibration.ra !== undefined && (
                                          <div><strong>RA:</strong> {details.calibration.ra.toFixed(6)}°</div>
                                        )}
                                        {details.calibration.dec !== undefined && (
                                          <div><strong>Dec:</strong> {details.calibration.dec.toFixed(6)}°</div>
                                        )}
                                        {details.calibration.pixscale !== undefined && (
                                          <div><strong>Pixel Scale:</strong> {details.calibration.pixscale.toFixed(4)} arcsec/pixel</div>
                                        )}
                                        {details.calibration.orientation !== undefined && (
                                          <div><strong>Orientation:</strong> {details.calibration.orientation.toFixed(2)}°</div>
                                        )}
                                        {details.calibration.parity !== undefined && (
                                          <div><strong>Parity:</strong> {details.calibration.parity > 0 ? 'Positive' : 'Negative'}</div>
                                        )}
                                        {details.calibration.radius !== undefined && (
                                          <div><strong>Radius:</strong> {details.calibration.radius.toFixed(4)}°</div>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                  {details?.objects && details.objects.objects_in_field && details.objects.objects_in_field.length > 0 && (
                                    <div>
                                      <h3 style={{ marginTop: 0, marginBottom: '0.75rem', fontSize: '1.1rem' }}>Objects in Field</h3>
                                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                                        {details.objects.objects_in_field.map((obj, idx) => (
                                          <span key={idx} style={{ padding: '0.25rem 0.5rem', background: 'rgba(91, 213, 249, 0.15)', borderRadius: '4px', fontSize: '0.9rem' }}>
                                            {obj}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  {details?.annotations && details.annotations.annotations && details.annotations.annotations.length > 0 && (
                                    <div>
                                      <h3 style={{ marginTop: 0, marginBottom: '0.75rem', fontSize: '1.1rem' }}>Annotations</h3>
                                      <ul style={{ margin: 0, paddingLeft: '1.5rem', fontSize: '0.9rem' }}>
                                        {details.annotations.annotations.map((ann, idx) => (
                                          <li key={idx}>{ann.text || JSON.stringify(ann)}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}
                                  {details && !details.loading && !details.calibration && !details.objects && !details.annotations && (
                                    <div style={{ color: '#999', fontSize: '0.9rem' }}>No details available</div>
                                  )}
                                </div>
                              )}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    )
                  })}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}

      {message && <p className="flash">{message}</p>}
    </div>
  )
}

export default App
