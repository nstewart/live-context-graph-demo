/**
 * Test utility functions for the FreshMart Admin UI.
 */

import type { OntologyProperty, OrderFlat } from '../api/client'

/**
 * Format a date string for display.
 */
export function formatDate(dateString: string | null): string {
  if (!dateString) return '-'
  const date = new Date(dateString)
  return date.toLocaleString()
}

/**
 * Get status badge color class.
 */
export function getStatusColor(status: string | null): string {
  const colors: Record<string, string> = {
    CREATED: 'bg-gray-100 text-gray-800',
    PICKING: 'bg-yellow-100 text-yellow-800',
    OUT_FOR_DELIVERY: 'bg-blue-100 text-blue-800',
    DELIVERED: 'bg-green-100 text-green-800',
    CANCELLED: 'bg-red-100 text-red-800',
    AVAILABLE: 'bg-green-100 text-green-800',
    ON_DELIVERY: 'bg-blue-100 text-blue-800',
    OFF_SHIFT: 'bg-gray-100 text-gray-800',
    OPEN: 'bg-green-100 text-green-800',
    CLOSED: 'bg-red-100 text-red-800',
  }
  return colors[status || ''] || 'bg-gray-100 text-gray-800'
}

/**
 * Extract class prefix from a subject ID.
 */
export function extractPrefix(subjectId: string): string {
  return subjectId.split(':')[0]
}

/**
 * Filter properties by domain class.
 */
export function filterPropertiesByClass(
  properties: OntologyProperty[],
  classId: number
): OntologyProperty[] {
  return properties.filter((p) => p.domain_class_id === classId)
}

/**
 * Group orders by status.
 */
export function groupOrdersByStatus(
  orders: OrderFlat[]
): Record<string, OrderFlat[]> {
  return orders.reduce(
    (acc, order) => {
      const status = order.order_status || 'UNKNOWN'
      if (!acc[status]) acc[status] = []
      acc[status].push(order)
      return acc
    },
    {} as Record<string, OrderFlat[]>
  )
}

/**
 * Format a currency amount for display.
 * Handles both string and number inputs (API may return decimals as strings).
 */
export function formatAmount(amount: string | number | null | undefined): string {
  if (amount == null) return '0.00'
  const num = typeof amount === 'string' ? parseFloat(amount) : amount
  if (isNaN(num)) return '0.00'
  return num.toFixed(2)
}

/**
 * Calculate order totals by status.
 */
export function calculateOrderTotalsByStatus(
  orders: OrderFlat[]
): Record<string, number> {
  const grouped = groupOrdersByStatus(orders)
  return Object.entries(grouped).reduce(
    (acc, [status, statusOrders]) => {
      acc[status] = statusOrders.reduce(
        (sum, o) => {
          // Handle both string and number amounts from API
          const amount = o.order_total_amount
          const numAmount = typeof amount === 'string' ? parseFloat(amount) : (amount || 0)
          return sum + (isNaN(numAmount) ? 0 : numAmount)
        },
        0
      )
      return acc
    },
    {} as Record<string, number>
  )
}
