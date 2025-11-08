import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'
import {
  API_ROOT,
  fetchJobInfo,
  fetchJobStatus,
  fetchMyJobs,
  login,
  uploadFile,
} from './api'

type JobRow = {
  id: number
  status: string
  filename?: string
}

function App() {
  const [apiKey, setApiKey] = useState('')
  const [session, setSession] = useState<string | null>(null)
  const [jobs, setJobs] = useState<JobRow[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const handleLogin = async (event: React.FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setMessage(null)
    try {
      const res = await login(apiKey.trim())
      if (res.status === 'success' && res.session) {
        setSession(res.session)
      } else {
        setMessage(res.errormessage ?? '登录失败')
      }
    } catch (error) {
      setMessage('网络错误，稍后再试')
    } finally {
      setLoading(false)
    }
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
    } catch (error) {
      setMessage('无法获取任务列表')
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
      setMessage('请选择文件并先登录')
      return
    }
    setUploading(true)
    setMessage(null)
    try {
      const res = await uploadFile(session, selectedFile)
      if (res.status === 'success') {
        setSelectedFile(null)
        await refreshJobs()
        setMessage(`上传成功，Submission ${res.subid}`)
      } else {
        setMessage(res.errormessage ?? '上传失败')
      }
    } catch (error) {
      setMessage('上传出错')
    } finally {
      setUploading(false)
    }
  }

  const downloadBase = useMemo(() => API_ROOT, [])

  return (
    <div className="layout">
      <header>
        <h1>Astrometry Lite 控制台</h1>
        <p>使用 API key 登录，上传图片并跟踪 Job 状态。</p>
      </header>

      {!session && (
        <section className="panel">
          <h2>登录</h2>
          <form onSubmit={handleLogin} className="form">
            <label>
              API Key
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="粘贴在此"
              />
            </label>
            <button type="submit" disabled={loading || !apiKey.trim()}>
              {loading ? '登录中…' : '登录'}
            </button>
          </form>
        </section>
      )}

      {session && (
        <>
          <section className="panel">
            <h2>上传图像</h2>
            <form onSubmit={handleUpload} className="form">
              <input
                type="file"
                accept=".fits,.fit,.fts,.jpg,.jpeg,.png"
                onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
              />
              <button type="submit" disabled={!selectedFile || uploading}>
                {uploading ? '上传中…' : '上传并提交'}
              </button>
            </form>
          </section>

          <section className="panel">
            <div className="panel-header">
              <h2>Job 列表</h2>
              <button onClick={() => refreshJobs()} disabled={loading}>
                {loading ? '刷新中…' : '刷新'}
              </button>
            </div>
            {jobs.length === 0 ? (
              <p>暂无 job，可先上传一张图像。</p>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>状态</th>
                    <th>文件</th>
                    <th>下载</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <tr key={job.id}>
                      <td>{job.id}</td>
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
                  ))}
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
