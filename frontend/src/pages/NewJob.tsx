import { useState, FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { uploadFile, uploadFromUrl, login, type UploadResponse } from '../api';

const SESSION_STORAGE_KEY = 'astrometry_session';

export function NewJob() {
  const navigate = useNavigate();
  const [apiKey, setApiKey] = useState('');
  const [session, setSession] = useState<string | null>(() => {
    return localStorage.getItem(SESSION_STORAGE_KEY);
  });
  const [uploadType, setUploadType] = useState<'url' | 'file'>('url');
  const [url, setUrl] = useState('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await login(apiKey.trim());
      if (res.status === 'success' && res.session) {
        setSession(res.session);
        localStorage.setItem(SESSION_STORAGE_KEY, res.session);
      } else {
        setError(res.errormessage ?? '登录失败');
      }
    } catch (err) {
      setError('网络错误，稍后再试');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!session) {
      setError('请先登录');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      let result: UploadResponse;
      if (uploadType === 'url') {
        if (!url.trim()) {
          setError('请输入图片 URL');
          setLoading(false);
          return;
        }
        result = await uploadFromUrl(session, url.trim());
      } else {
        if (!selectedFile) {
          setError('请选择文件');
          setLoading(false);
          return;
        }
        result = await uploadFile(session, selectedFile);
      }

      if (result.status === 'success' && result.job_id) {
        // 跳转到 job status page
        navigate(`/jobs/${result.job_id}`);
      } else {
        setError(result.errormessage ?? '提交失败');
      }
    } catch (err) {
      setError('提交出错，请稍后再试');
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
          <h2>登录</h2>
          <p style={{ color: '#9ca3af', marginBottom: '1rem' }}>
            请使用 API key 登录以提交新的解析任务
          </p>
          <form onSubmit={handleLogin} className="form">
            <label>
              API Key
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="粘贴 API key"
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
              {loading ? '登录中…' : '登录'}
            </button>
          </form>
          {error && <div className="error-message" style={{ marginTop: '1rem' }}>{error}</div>}
        </div>
      ) : (
        <div className="panel">
          <div className="panel-header">
            <h2>提交新任务</h2>
            <button
              onClick={() => {
                setSession(null);
                setApiKey('');
                localStorage.removeItem(SESSION_STORAGE_KEY);
              }}
              style={{
                background: 'rgba(248, 113, 113, 0.2)',
                color: '#f87171',
                padding: '0.5rem 1rem',
                fontSize: '0.9rem',
              }}
            >
              登出
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
                <span>从 URL 上传</span>
              </label>
              <label style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                <input
                  type="radio"
                  checked={uploadType === 'file'}
                  onChange={() => setUploadType('file')}
                  style={{ width: 'auto' }}
                />
                <span>上传文件</span>
              </label>
            </div>

            {uploadType === 'url' ? (
              <label>
                图片 URL
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
                选择文件
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
                    已选择: {selectedFile.name}
                  </p>
                )}
              </label>
            )}

            <button type="submit" disabled={loading || (uploadType === 'url' && !url.trim()) || (uploadType === 'file' && !selectedFile)}>
              {loading ? '提交中…' : '提交任务'}
            </button>
          </form>

          {error && <div className="error-message" style={{ marginTop: '1rem' }}>{error}</div>}
        </div>
      )}
    </div>
  );
}

