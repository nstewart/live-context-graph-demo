import { NavLink } from 'react-router-dom'
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
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useLayout } from '../contexts/LayoutContext'

const navItems = [
  { path: '/', icon: BarChart3, label: 'Agent Ref. Architecture' },
  { path: '/metrics', icon: TrendingUp, label: 'Live Metrics' },
  { path: '/bundling', icon: Layers, label: 'Delivery Bundling' },
  { path: '/orders', icon: ShoppingCart, label: 'Orders' },
  { path: '/stores', icon: Warehouse, label: 'Stores & Inventory' },
  { path: '/couriers', icon: Truck, label: 'Couriers' },
  { path: '/ontology', icon: Database, label: 'Knowledge Graph (Ontology)' },
  { path: '/triples', icon: Package, label: 'Triples Browser' },
  { path: '/settings', icon: Settings, label: 'Settings' },
]

export default function Sidebar() {
  const { sidebarCollapsed, toggleSidebar } = useLayout()

  return (
    <aside
      className={`${
        sidebarCollapsed ? 'w-16' : 'w-64'
      } bg-gray-900 text-white flex flex-col transition-all duration-300 flex-shrink-0`}
    >
      {/* Header */}
      <div className={`p-4 flex items-center ${sidebarCollapsed ? 'justify-center' : 'justify-between'}`}>
        {!sidebarCollapsed && (
          <div>
            <h1 className="text-xl font-bold text-green-400">FreshMart</h1>
            <p className="text-sm text-gray-400">Digital Twin Admin</p>
          </div>
        )}
        <button
          onClick={toggleSidebar}
          className="p-1.5 hover:bg-gray-800 rounded transition-colors"
          title={sidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {sidebarCollapsed ? (
            <ChevronRight className="h-5 w-5 text-gray-400" />
          ) : (
            <ChevronLeft className="h-5 w-5 text-gray-400" />
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className="mt-4 flex-1">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            title={sidebarCollapsed ? item.label : undefined}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 text-sm transition-colors ${
                sidebarCollapsed ? 'justify-center' : ''
              } ${
                isActive
                  ? 'bg-green-600 text-white'
                  : 'text-gray-300 hover:bg-gray-800'
              }`
            }
          >
            <item.icon className="h-5 w-5 flex-shrink-0" />
            {!sidebarCollapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}
