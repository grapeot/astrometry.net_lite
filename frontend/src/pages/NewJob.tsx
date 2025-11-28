import { useState, useEffect, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { uploadFile, uploadFromUrl, login, type UploadResponse } from '../api';

const SESSION_STORAGE_KEY = 'astrometry_session';
const PUBLIC_API_KEY = 'public';

export function NewJob() {
  const navigate = useNavigate();
  const [apiKey, setApiKey] = useState(PUBLIC_API_KEY);
  const [session, setSession] = useState<string | null>(() => {
    return localStorage.getItem(SESSION_STORAGE_KEY);
  });
  const [uploadType, setUploadType] = useState<'url' | 'file'>('url');
  const [url, setUrl] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasLoggedOut, setHasLoggedOut] = useState(false);

  // Auto-login with public API key if no session exists (only on mount, not after logout)
  useEffect(() => {
    if (!session && !hasLoggedOut) {
      const autoLogin = async () => {
        try {
          const res = await login(PUBLIC_API_KEY);
          if (res.status === 'success' && res.session) {
            setSession(res.session);
            localStorage.setItem(SESSION_STORAGE_KEY, res.session);
          }
        } catch {
          // Silently fail, user can manually login
        }
      };
      void autoLogin();
    }
  }, [session, hasLoggedOut]);

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await login(apiKey.trim());
      if (res.status === 'success' && res.session) {
        setSession(res.session);
        setHasLoggedOut(false); // Reset logout flag on successful login
        localStorage.setItem(SESSION_STORAGE_KEY, res.session);
      } else {
        setError(res.errormessage ?? 'Login failed');
      }
    } catch {
      setError('Network error, please try again later');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!session) {
      setError('Please login first');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      let result: UploadResponse;
      if (uploadType === 'url') {
        if (!url.trim()) {
          setError('Please enter image URL');
          setLoading(false);
          return;
        }
        result = await uploadFromUrl(session, url.trim());
      } else {
        if (!selectedFile) {
          setError('Please select a file');
          setLoading(false);
          return;
        }
        result = await uploadFile(session, selectedFile);
      }

      if (result.status === 'success' && result.job_id) {
        // Navigate to job status page
        navigate(`/jobs/${result.job_id}`);
      } else {
        setError(result.errormessage ?? 'Submission failed');
      }
    } catch {
        setError('Submission failed. Please check your image URL or file and try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="job-detail-page">
      <header className="detail-header">
        <Link to="/" className="back-link">&larr; Back to gallery</Link>
        <h1>New Job</h1>
      </header>

      {!session ? (
        <div className="panel">
          <h2>Login</h2>
          <p style={{ color: '#9ca3af', marginBottom: '1rem' }}>
            Using public API key. You can enter a custom API key if needed.
          </p>
          <form onSubmit={handleLogin} className="form">
            <label>
              API Key
              <input
                type="text"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="public (default)"
                style={{
                  padding: '0.8rem 1rem',
                  borderRadius: '10px',
                  border: '1px solid rgba(255, 255, 255, 0.15)',
                  background: 'rgba(0, 0, 0, 0.3)',
                  color: '#f5f5f5',
                  fontSize: '1rem',
                  width: '100%',
                }}
              />
            </label>
            <button type="submit" disabled={loading || !apiKey.trim()}>
              {loading ? 'Logging in...' : 'Login'}
            </button>
          </form>
          {error && <div className="error-message" style={{ marginTop: '1rem' }}>{error}</div>}
        </div>
      ) : (
        <div className="panel">
          <div className="panel-header">
            <h2>Submit New Job</h2>
            <button
              onClick={() => {
                setSession(null);
                setApiKey(PUBLIC_API_KEY);
                setHasLoggedOut(true);
                localStorage.removeItem(SESSION_STORAGE_KEY);
              }}
              style={{
                background: 'rgba(59, 130, 246, 0.2)',
                color: '#3b82f6',
                padding: '0.5rem 1rem',
                fontSize: '0.9rem',
              }}
            >
              Change API Key
            </button>
          </div>
          <p style={{ color: '#9ca3af', marginBottom: '1rem' }}>
            Session: {session.substring(0, 20)}...
          </p>

          <form onSubmit={handleSubmit} className="form">
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
                <input
                  type="radio"
                  checked={uploadType === 'url'}
                  onChange={() => setUploadType('url')}
                  style={{ width: 'auto' }}
                />
                <span>Upload from URL</span>
              </label>
              <label style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={uploadType === 'file'}
                  onChange={() => setUploadType('file')}
                  style={{ width: 'auto' }}
                />
                <span>Upload file</span>
              </label>
            </div>

            {uploadType === 'url' ? (
              <label>
                Image URL
                <input
                  type="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/image.jpg"
                  style={{
                    padding: '0.8rem 1rem',
                    borderRadius: '10px',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    background: 'rgba(0, 0, 0, 0.3)',
                    color: '#f5f5f5',
                    fontSize: '1rem',
                    width: '100%',
                  }}
                />
              </label>
            ) : (
              <label>
                Select file
                <input
                  type="file"
                  accept=".fits,.fit,.fts,.jpg,.jpeg,.png"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
                  style={{
                    padding: '0.8rem 1rem',
                    borderRadius: '10px',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    background: 'rgba(0, 0, 0, 0.3)',
                    color: '#f5f5f5',
                    fontSize: '1rem',
                    width: '100%',
                  }}
                />
                {selectedFile && (
                  <p style={{ marginTop: '0.5rem', color: '#9ca3af', fontSize: '0.9rem' }}>
                    Selected: {selectedFile.name}
                  </p>
                )}
              </label>
            )}

            <button type="submit" disabled={loading || (uploadType === 'url' && !url.trim()) || (uploadType === 'file' && !selectedFile)}>
              {loading ? 'Submitting...' : 'Submit Job'}
            </button>
          </form>

          {error && <div className="error-message" style={{ marginTop: '1rem' }}>{error}</div>}
        </div>
      )}
    </div>
  );
}

