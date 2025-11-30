import { useState } from 'react'
import { Minus, Plus, Trash2, ShoppingCart as CartIcon, Snowflake } from 'lucide-react'
import { formatAmount } from '../test/utils'

export interface CartLineItem {
  product_id: string
  product_name: string
  quantity: number
  unit_price: number
  live_price?: number
  base_price?: number
  line_amount: number
  perishable_flag: boolean
  available_stock: number
  category?: string
}

interface ShoppingCartProps {
  lineItems: CartLineItem[]
  onUpdateQuantity: (productId: string, quantity: number) => void
  onRemoveItem: (productId: string) => void
  className?: string
}

export function ShoppingCart({
  lineItems,
  onUpdateQuantity,
  onRemoveItem,
  className = '',
}: ShoppingCartProps) {
  const [updatingItem, setUpdatingItem] = useState<string | null>(null)
  const [errorItem, setErrorItem] = useState<{ productId: string; message: string } | null>(null)

  const total = lineItems.reduce((sum, item) => sum + item.line_amount, 0)
  const hasPerishableItems = lineItems.some(item => item.perishable_flag)

  const handleQuantityChange = (productId: string, newQuantity: number) => {
    try {
      setErrorItem(null)
      setUpdatingItem(productId)
      // IMPORTANT: This only updates local state in the parent component
      // No database save occurs until the form's "Update" button is clicked
      onUpdateQuantity(productId, newQuantity)
    } catch (error) {
      setErrorItem({
        productId,
        message: error instanceof Error ? error.message : 'Failed to update quantity',
      })
    } finally {
      setUpdatingItem(null)
    }
  }

  const handleIncrement = (productId: string, currentQuantity: number) => {
    handleQuantityChange(productId, currentQuantity + 1)
  }

  const handleDecrement = (productId: string, currentQuantity: number) => {
    if (currentQuantity > 1) {
      handleQuantityChange(productId, currentQuantity - 1)
    } else {
      onRemoveItem(productId)
    }
  }

  const handleRemove = (productId: string) => {
    onRemoveItem(productId)
    setErrorItem(null)
  }

  // Empty cart state
  if (lineItems.length === 0) {
    return (
      <div className={`bg-white rounded-lg border-2 border-dashed border-gray-200 ${className}`}>
        <div className="p-8 text-center">
          <CartIcon className="h-16 w-16 mx-auto mb-4 text-gray-300" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">Your cart is empty</h3>
          <p className="text-gray-500">
            Search and select products above to add them to your order
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className={`bg-white rounded-lg shadow border border-gray-200 ${className}`}>
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <CartIcon className="h-5 w-5" />
            Shopping Cart ({lineItems.length} item{lineItems.length !== 1 ? 's' : ''})
          </h3>
          {hasPerishableItems && (
            <span className="flex items-center gap-1 text-sm text-blue-600">
              <Snowflake className="h-4 w-4" />
              Contains perishables
            </span>
          )}
        </div>
      </div>

      {/* Cart Items - Desktop Table */}
      <div className="hidden md:block overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Product
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-32">
                Quantity
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                Unit Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider w-24">
                Line Total
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider w-20">
                Action
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {lineItems.map(item => (
              <tr
                key={item.product_id}
                className={`hover:bg-gray-50 transition-colors ${
                  updatingItem === item.product_id ? 'opacity-50' : ''
                }`}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900">{item.product_name}</span>
                    {item.perishable_flag && (
                      <span title="Perishable">
                        <Snowflake className="h-4 w-4 text-blue-600" />
                      </span>
                    )}
                  </div>
                  {item.category && (
                    <div className="text-xs text-gray-500 mt-1">{item.category}</div>
                  )}
                  {errorItem?.productId === item.product_id && (
                    <div className="text-xs text-red-600 mt-1">{errorItem.message}</div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleDecrement(item.product_id, item.quantity)}
                      disabled={updatingItem === item.product_id}
                      className="p-1 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Decrease quantity"
                    >
                      <Minus className="h-4 w-4" />
                    </button>
                    <span className="w-12 text-center font-medium">{item.quantity}</span>
                    <button
                      type="button"
                      onClick={() => handleIncrement(item.product_id, item.quantity)}
                      disabled={updatingItem === item.product_id}
                      className="p-1 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      title="Increase quantity"
                    >
                      <Plus className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="text-xs text-gray-500 text-center mt-1">
                    {item.available_stock} available
                  </div>
                </td>
                <td className="px-4 py-3 text-right text-gray-900">
                  ${formatAmount(item.unit_price)}
                </td>
                <td className="px-4 py-3 text-right font-medium text-gray-900">
                  ${formatAmount(item.line_amount)}
                </td>
                <td className="px-4 py-3 text-center">
                  <button
                    type="button"
                    onClick={() => handleRemove(item.product_id)}
                    disabled={updatingItem === item.product_id}
                    className="p-1 text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                    title="Remove item"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Cart Items - Mobile Cards */}
      <div className="md:hidden divide-y divide-gray-200">
        {lineItems.map(item => (
          <div
            key={item.product_id}
            className={`p-4 ${updatingItem === item.product_id ? 'opacity-50' : ''}`}
          >
            <div className="flex justify-between items-start mb-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-medium text-gray-900">{item.product_name}</span>
                  {item.perishable_flag && (
                    <span title="Perishable">
                      <Snowflake className="h-4 w-4 text-blue-600" />
                    </span>
                  )}
                </div>
                {item.category && <div className="text-xs text-gray-500">{item.category}</div>}
              </div>
              <button
                type="button"
                onClick={() => handleRemove(item.product_id)}
                disabled={updatingItem === item.product_id}
                className="p-1 text-red-600 hover:bg-red-50 rounded disabled:opacity-50"
                title="Remove item"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => handleDecrement(item.product_id, item.quantity)}
                  disabled={updatingItem === item.product_id}
                  className="p-2 rounded-lg border hover:bg-gray-50 disabled:opacity-50"
                >
                  <Minus className="h-4 w-4" />
                </button>
                <div className="text-center">
                  <div className="font-medium">{item.quantity}</div>
                  <div className="text-xs text-gray-500">{item.available_stock} avail</div>
                </div>
                <button
                  type="button"
                  onClick={() => handleIncrement(item.product_id, item.quantity)}
                  disabled={updatingItem === item.product_id}
                  className="p-2 rounded-lg border hover:bg-gray-50 disabled:opacity-50"
                >
                  <Plus className="h-4 w-4" />
                </button>
              </div>

              <div className="text-right">
                <div className="text-sm text-gray-500">${formatAmount(item.unit_price)} each</div>
                <div className="font-semibold text-gray-900">${formatAmount(item.line_amount)}</div>
              </div>
            </div>

            {errorItem?.productId === item.product_id && (
              <div className="text-xs text-red-600 mt-2">{errorItem.message}</div>
            )}
          </div>
        ))}
      </div>

      {/* Total */}
      <div className="px-4 py-4 border-t border-gray-200 bg-gray-50">
        <div className="flex justify-between items-center">
          <span className="text-lg font-semibold text-gray-900">Order Total</span>
          <span className="text-2xl font-bold text-green-600">${formatAmount(total)}</span>
        </div>
        {hasPerishableItems && (
          <p className="text-xs text-gray-500 mt-2">
            This order contains perishable items requiring cold chain delivery
          </p>
        )}
      </div>
    </div>
  )
}
