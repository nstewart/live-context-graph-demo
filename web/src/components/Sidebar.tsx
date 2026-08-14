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
  Search,
  QrCode,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useLayout } from '../contexts/LayoutContext'
import { brand, navItems as labelNav } from '../label'

// Icons stay in code and are keyed by route; the labels and their order come
// from the active label so a vertical can rename or reorder the demo's sections.
const iconsByPath: Record<string, typeof BarChart3> = {
  '/': BarChart3,
  '/vector-search': Search,
  '/orders': ShoppingCart,
  '/couriers': Truck,
  '/metrics': TrendingUp,
  '/stores': Warehouse,
  '/ontology': Database,
  '/triples': Package,
  '/bundling': Layers,
  '/settings': Settings,
}

const navItems = labelNav.map((item) => ({
  ...item,
  icon: iconsByPath[item.path] ?? Package,
}))

export default function Sidebar() {
  const { sidebarCollapsed, toggleSidebar, setShowQr } = useLayout()

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
            <h1 className="text-xl font-bold text-brand-400">{brand.name}</h1>
            <p className="text-sm text-gray-400">{brand.tagline}</p>
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
                  ? 'bg-brand-600 text-white'
                  : 'text-gray-300 hover:bg-gray-800'
              }`
            }
          >
            <item.icon className="h-5 w-5 flex-shrink-0" />
            {!sidebarCollapsed && <span>{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* QR Code Button */}
      <button
        onClick={() => setShowQr(true)}
        title={sidebarCollapsed ? 'Show QR Code' : undefined}
        className={`flex items-center gap-3 px-4 py-3 text-sm transition-colors border-t border-gray-700 text-gray-300 hover:bg-gray-800 ${sidebarCollapsed ? 'justify-center' : ''}`}
      >
        <QrCode className="h-5 w-5 flex-shrink-0" />
        {!sidebarCollapsed && <span>Show QR Code</span>}
      </button>
    </aside>
  )
}
