import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import {
  Database,
  Package,
  ShoppingCart,
  Warehouse,
  Truck,
  Settings,
  TrendingUp,
  BarChart3,
  Layers,
} from 'lucide-react'

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
import { ChatProvider } from './contexts/ChatContext'
import PropagationWidget from './components/PropagationWidget'
import ChatWidget from './components/ChatWidget'

const navItems = [
  { path: '/', icon: BarChart3, label: 'IVM Demo' },
  { path: '/metrics', icon: TrendingUp, label: 'Live Metrics' },
  { path: '/bundling', icon: Layers, label: 'Delivery Bundling' },
  { path: '/orders', icon: ShoppingCart, label: 'Orders' },
  { path: '/stores', icon: Warehouse, label: 'Stores & Inventory' },
  { path: '/couriers', icon: Truck, label: 'Couriers' },
  { path: '/ontology', icon: Database, label: 'Knowledge Graph (Ontology)' },
  { path: '/triples', icon: Package, label: 'Triples Browser' },
  { path: '/settings', icon: Settings, label: 'Settings' },
]

function App() {
  return (
    <BrowserRouter>
      <PropagationProvider>
        <ChatProvider>
          <div className="flex h-screen">
            {/* Sidebar */}
            <aside className="w-64 bg-gray-900 text-white">
              <div className="p-4">
                <h1 className="text-xl font-bold text-green-400">FreshMart</h1>
                <p className="text-sm text-gray-400">Digital Twin Admin</p>
              </div>
              <nav className="mt-4">
                {navItems.map((item) => (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    className={({ isActive }) =>
                      `flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                        isActive
                          ? 'bg-green-600 text-white'
                          : 'text-gray-300 hover:bg-gray-800'
                      }`
                    }
                  >
                    <item.icon className="h-5 w-5" />
                    {item.label}
                  </NavLink>
                ))}
              </nav>
            </aside>

            {/* Main content */}
            <main className="flex-1 overflow-auto pb-10">
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

            {/* Widgets */}
            <PropagationWidget />
            <ChatWidget />
          </div>
        </ChatProvider>
      </PropagationProvider>
    </BrowserRouter>
  )
}

export default App
