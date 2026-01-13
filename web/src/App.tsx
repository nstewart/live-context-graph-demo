import { BrowserRouter, Routes, Route } from 'react-router-dom'

import OntologyPage from './pages/OntologyPage'
import TriplesBrowserPage from './pages/TriplesBrowserPage'
import OrdersDashboardPage from './pages/OrdersDashboardPage'
import StoresInventoryPage from './pages/StoresInventoryPage'
import CouriersSchedulePage from './pages/CouriersSchedulePage'
import SettingsPage from './pages/SettingsPage'
import MetricsDashboardPage from './pages/MetricsDashboardPage'
import QueryStatisticsPage from './pages/QueryStatisticsPage'
import BundlingPage from './pages/BundlingPage'
import { PropagationProvider } from './contexts/PropagationContext'
import { ChatProvider, useChat } from './contexts/ChatContext'
import { LayoutProvider } from './contexts/LayoutContext'
import PropagationWidget from './components/PropagationWidget'
import ChatWidget from './components/ChatWidget'
import Sidebar from './components/Sidebar'

function AppLayout() {
  const { isOpen: chatOpen, isExpanded: chatExpanded } = useChat()

  return (
    <div className="flex h-screen">
      {/* Sidebar */}
      <Sidebar />

      {/* Main content */}
      <main className="flex-1 overflow-auto pb-10 transition-all duration-300">
        <Routes>
          <Route path="/" element={<QueryStatisticsPage />} />
          <Route path="/metrics" element={<MetricsDashboardPage />} />
          <Route path="/bundling" element={<BundlingPage />} />
          <Route path="/orders" element={<OrdersDashboardPage />} />
          <Route path="/stores" element={<StoresInventoryPage />} />
          <Route path="/couriers" element={<CouriersSchedulePage />} />
          <Route path="/ontology" element={<OntologyPage />} />
          <Route path="/triples" element={<TriplesBrowserPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>

      {/* Chat Panel - part of flex layout when open and not expanded */}
      {chatOpen && !chatExpanded && (
        <div className="w-[400px] flex-shrink-0 transition-all duration-300">
          <ChatWidget />
        </div>
      )}

      {/* Chat Widget handles its own modal when expanded, or shows floating button when closed */}
      {(!chatOpen || chatExpanded) && <ChatWidget />}

      {/* Propagation Widget */}
      <PropagationWidget />
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <LayoutProvider>
        <PropagationProvider>
          <ChatProvider>
            <AppLayout />
          </ChatProvider>
        </PropagationProvider>
      </LayoutProvider>
    </BrowserRouter>
  )
}

export default App
