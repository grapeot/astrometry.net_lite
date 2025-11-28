import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import './index.css'
import './App.css'
import { JobGrid } from './pages/JobGrid'
import { JobDetail } from './pages/JobDetail'
import { NewJob } from './pages/NewJob'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<JobGrid />} />
        <Route path="/jobs/:jobId" element={<JobDetail />} />
        <Route path="/new" element={<NewJob />} />
        <Route path="/console" element={<App />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
