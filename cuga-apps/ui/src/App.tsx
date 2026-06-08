import { Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import McpServersPage from './pages/McpServersPage'
import UseCaseDetail from './pages/UseCaseDetail'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/mcp-servers" element={<McpServersPage />} />
        <Route path="/use-case/:id" element={<UseCaseDetail />} />
        {/* Catch-all: any unmatched path (e.g. a static host serving
            /index.html, or a hard refresh on a deep link) lands on Apps
            instead of a blank screen. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
