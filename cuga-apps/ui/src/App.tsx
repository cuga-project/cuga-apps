import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import UseCaseDetail from './pages/UseCaseDetail'
import Features from './pages/Features'
import ComparisonPage from './pages/ComparisonPage'
import ManusPage from './pages/ManusPage'
import RoadmapPage from './pages/RoadmapPage'
import VisionPage from './pages/VisionPage'
import CoveragePage from './pages/CoveragePage'
import IdeasPage from './pages/IdeasPage'
import MoatPage from './pages/MoatPage'
import ProposalPage from './pages/ProposalPage'
import DeliverablesPage from './pages/DeliverablesPage'
import ArchitecturesPage from './pages/ArchitecturesPage'
import BuildingBlocksPage from './pages/BuildingBlocksPage'
import ExamplesPage from './pages/ExamplesPage'
import UseCaseIdeasPage from './pages/UseCaseIdeasPage'

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/use-case/:id" element={<UseCaseDetail />} />
        <Route path="/coverage" element={<CoveragePage />} />
        <Route path="/features" element={<Features />} />
        <Route path="/vs-openclaw" element={<ComparisonPage />} />
        <Route path="/manus" element={<ManusPage />} />
        <Route path="/roadmap" element={<RoadmapPage />} />
        <Route path="/vision" element={<VisionPage />} />
        <Route path="/ideas" element={<IdeasPage />} />
        <Route path="/moat" element={<MoatPage />} />
        <Route path="/proposal" element={<ProposalPage />} />
        <Route path="/deliverables" element={<DeliverablesPage />} />
        <Route path="/architectures" element={<ArchitecturesPage />} />
        <Route path="/building-blocks" element={<BuildingBlocksPage />} />
        <Route path="/examples" element={<ExamplesPage />} />
        <Route path="/use-case-ideas" element={<UseCaseIdeasPage />} />
      </Routes>
    </Layout>
  )
}
