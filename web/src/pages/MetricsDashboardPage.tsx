import { useState, useEffect, useMemo } from "react";
import { useZero, useQuery } from "@rocicorp/zero/react";
import { Schema } from "../schema";
import { formatAmount } from "../test/utils";
import {
  AlertTriangle,
  Activity,
  Wifi,
  WifiOff,
  DollarSign,
  Package,
  Store,
} from "lucide-react";

export default function MetricsDashboardPage() {
  const z = useZero<Schema>();
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now());

  // 🔥 ZERO - Real-time metrics data
  const [pricingYieldData] = useQuery(z.query.pricing_yield_mv);
  const [inventoryRiskData] = useQuery(z.query.inventory_risk_mv);
  const [capacityHealthData] = useQuery(z.query.store_capacity_health_mv);

  useEffect(() => {
    if (pricingYieldData.length > 0 || inventoryRiskData.length > 0 || capacityHealthData.length > 0) {
      setLastUpdateTime(Date.now());
    }
  }, [pricingYieldData, inventoryRiskData, capacityHealthData]);

  // Calculate aggregate metrics
  const metrics = useMemo(() => {
    // 1. Pricing Yield
    const totalPremium = pricingYieldData.reduce((sum, r) => sum + (r.price_premium || 0), 0);
    const totalBase = pricingYieldData.reduce((sum, r) => sum + ((r.base_price || 0) * (r.quantity || 0)), 0);
    const yieldRate = totalBase > 0 ? (totalPremium / totalBase) * 100 : 0;

    // 2. Inventory Risk
    const criticalItems = inventoryRiskData.filter(i => i.risk_level === 'CRITICAL').length;
    const highRiskItems = inventoryRiskData.filter(i => i.risk_level === 'HIGH').length;
    const totalRevAtRisk = inventoryRiskData
      .filter(i => i.risk_level === 'CRITICAL' || i.risk_level === 'HIGH')
      .reduce((sum, i) => sum + (i.revenue_at_risk || 0), 0);

    // 3. Capacity Health
    const criticalStores = capacityHealthData.filter(s => s.health_status === 'CRITICAL').length;
    const strainedStores = capacityHealthData.filter(s => s.health_status === 'STRAINED').length;
    const avgUtilization = capacityHealthData.length > 0
      ? capacityHealthData.reduce((sum, s) => sum + (s.current_utilization_pct || 0), 0) / capacityHealthData.length
      : 0;

    return {
      pricingYield: { totalPremium, totalBase, yieldRate },
      inventoryRisk: { criticalItems, highRiskItems, totalRevAtRisk },
      capacityHealth: { criticalStores, strainedStores, avgUtilization },
    };
  }, [pricingYieldData, inventoryRiskData, capacityHealthData]);

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Live Metrics Dashboard</h1>
            {z.online ? (
              <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">
                <Wifi className="h-3 w-3" />
                Real-time
              </span>
            ) : (
              <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-amber-700 bg-amber-100 rounded-full">
                <WifiOff className="h-3 w-3" />
                Connecting...
              </span>
            )}
            <span className="text-xs text-gray-500">
              Last update: {new Date(lastUpdateTime).toLocaleTimeString()}
            </span>
          </div>
          <p className="text-gray-600">Real-time business health indicators</p>
        </div>
      </div>

      {/* Top-line KPIs */}
      <div className="grid grid-cols-3 gap-6 mb-6">
        {/* Pricing Yield */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-500">Dynamic Pricing Yield</h3>
            <DollarSign className="h-5 w-5 text-green-600" />
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Revenue premium captured above base catalog prices through dynamic pricing
          </p>
          <div className="text-3xl font-bold text-gray-900 mb-2">
            {metrics.pricingYield.yieldRate.toFixed(1)}%
          </div>
          <div className="text-sm text-gray-600">
            ${formatAmount(metrics.pricingYield.totalPremium)} premium captured
          </div>
          <div className="text-xs text-gray-400 mt-1">
            from ${formatAmount(metrics.pricingYield.totalBase)} base revenue
          </div>
        </div>

        {/* Inventory Risk */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-500">Revenue at Risk</h3>
            <AlertTriangle className="h-5 w-5 text-red-600" />
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Order value at risk due to low inventory levels with pending customer orders
          </p>
          <div className="text-3xl font-bold text-gray-900 mb-2">
            ${formatAmount(metrics.inventoryRisk.totalRevAtRisk)}
          </div>
          <div className="text-sm text-gray-600">
            {metrics.inventoryRisk.criticalItems} critical, {metrics.inventoryRisk.highRiskItems} high risk items
          </div>
        </div>

        {/* Capacity Health */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-500">Avg Store Utilization</h3>
            <Activity className="h-5 w-5 text-blue-600" />
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Current order volume as percentage of maximum store capacity per hour
          </p>
          <div className="text-3xl font-bold text-gray-900 mb-2">
            {metrics.capacityHealth.avgUtilization.toFixed(1)}%
          </div>
          <div className="text-sm text-gray-600">
            {metrics.capacityHealth.criticalStores} critical, {metrics.capacityHealth.strainedStores} strained stores
          </div>
        </div>
      </div>

      {/* Detailed Tables */}
      <div className="grid grid-cols-2 gap-6">
        {/* Inventory Risk Detail */}
        <div className="bg-white rounded-lg shadow">
          <div className="p-4 border-b">
            <h3 className="font-semibold text-gray-900 flex items-center gap-2">
              <Package className="h-5 w-5" />
              High-Risk Inventory
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              Products with low stock levels that have pending customer orders (may cause stockouts)
            </p>
          </div>
          <div className="overflow-x-auto max-h-96">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Product</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Store</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Stock</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Pending</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Risk</th>
                  <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">$ at Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {inventoryRiskData
                  .filter(i => i.risk_level === 'CRITICAL' || i.risk_level === 'HIGH')
                  .sort((a, b) => (b.revenue_at_risk || 0) - (a.revenue_at_risk || 0))
                  .slice(0, 20)
                  .map((item) => (
                    <tr key={item.inventory_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">{item.product_name}</td>
                      <td className="px-4 py-2 text-gray-600">{item.store_name}</td>
                      <td className="px-4 py-2 text-center">{item.stock_level}</td>
                      <td className="px-4 py-2 text-center">
                        <span className="text-amber-600 font-medium">{item.pending_reservations || 0}</span>
                      </td>
                      <td className="px-4 py-2 text-center">
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          item.risk_level === 'CRITICAL' ? 'bg-red-100 text-red-800' : 'bg-orange-100 text-orange-800'
                        }`}>
                          {item.risk_level}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right font-medium">
                        ${formatAmount(item.revenue_at_risk || 0)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Store Capacity Detail */}
        <div className="bg-white rounded-lg shadow">
          <div className="p-4 border-b">
            <h3 className="font-semibold text-gray-900 flex items-center gap-2">
              <Store className="h-5 w-5" />
              Store Capacity Status
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              Real-time store workload with automated recommendations for demand management
            </p>
          </div>
          <div className="overflow-x-auto max-h-96">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Store</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Utilization</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {capacityHealthData
                  .sort((a, b) => (b.current_utilization_pct || 0) - (a.current_utilization_pct || 0))
                  .map((store) => (
                    <tr key={store.store_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">
                        <div>{store.store_name}</div>
                        <div className="text-xs text-gray-500">{store.store_zone}</div>
                      </td>
                      <td className="px-4 py-2 text-center font-medium">
                        {store.current_utilization_pct?.toFixed(1)}%
                      </td>
                      <td className="px-4 py-2 text-center">
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          store.health_status === 'CRITICAL' ? 'bg-red-100 text-red-800' :
                          store.health_status === 'STRAINED' ? 'bg-yellow-100 text-yellow-800' :
                          store.health_status === 'HEALTHY' ? 'bg-green-100 text-green-800' :
                          'bg-blue-100 text-blue-800'
                        }`}>
                          {store.health_status}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-sm text-gray-600">
                        {store.recommended_action?.replace('_', ' ')}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
