import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { freshmartApi, ProductInfo } from '../api/client'
import { Search, Package, Snowflake, Loader } from 'lucide-react'

interface ProductSelectorProps {
  storeId: string | null
  onProductSelect: (product: ProductWithStock) => void
  disabled?: boolean
}

export interface ProductWithStock extends ProductInfo {
  stock_level: number
  inventory_id: string
}

export function ProductSelector({ storeId, onProductSelect, disabled }: ProductSelectorProps) {
  const [searchTerm, setSearchTerm] = useState('')

  // Fetch products
  const { data: products = [], isLoading: productsLoading } = useQuery({
    queryKey: ['products'],
    queryFn: () => freshmartApi.listProducts().then(r => r.data),
  })

  // Fetch store inventory
  const { data: store, isLoading: inventoryLoading } = useQuery({
    queryKey: ['store', storeId],
    queryFn: () => freshmartApi.getStore(storeId!).then(r => r.data),
    enabled: !!storeId,
  })

  // Combine products with inventory data
  const availableProducts = useMemo(() => {
    if (!store || !products.length) return []

    const inventoryMap = new Map(
      store.inventory_items
        .filter(item => item.stock_level && item.stock_level > 0)
        .map(item => [item.product_id, item])
    )

    return products
      .filter(product => inventoryMap.has(product.product_id))
      .map(product => {
        const inventory = inventoryMap.get(product.product_id)!
        return {
          ...product,
          stock_level: inventory.stock_level || 0,
          inventory_id: inventory.inventory_id,
        }
      })
      .sort((a, b) => (a.product_name || '').localeCompare(b.product_name || ''))
  }, [store, products])

  // Filter products based on search term
  const filteredProducts = useMemo(() => {
    if (!searchTerm.trim()) return availableProducts

    const search = searchTerm.toLowerCase()
    return availableProducts.filter(
      product =>
        product.product_name?.toLowerCase().includes(search) ||
        product.category?.toLowerCase().includes(search) ||
        product.product_id.toLowerCase().includes(search)
    )
  }, [availableProducts, searchTerm])

  const handleSelect = (productId: string) => {
    const product = availableProducts.find(p => p.product_id === productId)
    if (product) {
      onProductSelect(product)
      setSearchTerm('')
    }
  }

  const isLoading = productsLoading || inventoryLoading
  const isDisabled = disabled || !storeId

  return (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700">
        Add Products
        {isDisabled && (
          <span className="ml-2 text-xs text-gray-500">(Select a store first)</span>
        )}
      </label>

      {/* Search Input */}
      <div className="relative">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          {isLoading ? (
            <Loader className="h-4 w-4 text-gray-400 animate-spin" />
          ) : (
            <Search className="h-4 w-4 text-gray-400" />
          )}
        </div>
        <input
          type="text"
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          disabled={isDisabled || isLoading}
          placeholder="Search products..."
          className="w-full pl-10 pr-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
        />
      </div>

      {/* Dropdown/List */}
      {!isDisabled && searchTerm && (
        <div className="border rounded-lg shadow-lg bg-white max-h-64 overflow-y-auto">
          {isLoading ? (
            <div className="p-4 text-center text-gray-500">
              <Loader className="h-5 w-5 animate-spin inline-block mr-2" />
              Loading products...
            </div>
          ) : filteredProducts.length === 0 ? (
            <div className="p-4 text-center text-gray-500">
              {availableProducts.length === 0 ? (
                <>
                  <Package className="h-12 w-12 mx-auto mb-2 text-gray-300" />
                  <p className="font-medium">No products available</p>
                  <p className="text-sm">This store has no products in stock</p>
                </>
              ) : (
                <>
                  <Search className="h-12 w-12 mx-auto mb-2 text-gray-300" />
                  <p className="font-medium">No products found</p>
                  <p className="text-sm">Try a different search term</p>
                </>
              )}
            </div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {filteredProducts.map(product => (
                <li key={product.product_id}>
                  <button
                    onClick={() => handleSelect(product.product_id)}
                    className="w-full px-4 py-3 text-left hover:bg-gray-50 transition-colors flex items-center justify-between group"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900">
                          {product.product_name || 'Unknown Product'}
                        </span>
                        {product.perishable && (
                          <span
                            className="inline-flex items-center text-blue-600"
                            title="Perishable - requires cold chain"
                          >
                            <Snowflake className="h-4 w-4" />
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
                        <span>{product.category || 'Uncategorized'}</span>
                        <span className="text-gray-300">|</span>
                        <span className="font-medium text-green-600">
                          ${typeof product.unit_price === 'number' ? product.unit_price.toFixed(2) : parseFloat(product.unit_price || '0').toFixed(2)}
                        </span>
                      </div>
                    </div>
                    <div className="text-right ml-4">
                      <div
                        className={`text-sm font-medium ${
                          product.stock_level < 10
                            ? 'text-orange-600'
                            : 'text-gray-700'
                        }`}
                      >
                        {product.stock_level} in stock
                      </div>
                      {product.stock_level < 10 && (
                        <div className="text-xs text-orange-600">Low stock</div>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Empty State (when no store selected) */}
      {!storeId && (
        <div className="border-2 border-dashed border-gray-200 rounded-lg p-8 text-center">
          <Package className="h-12 w-12 mx-auto mb-3 text-gray-300" />
          <p className="text-gray-500 font-medium">Select a store to view products</p>
          <p className="text-sm text-gray-400 mt-1">
            Products will be filtered based on store inventory
          </p>
        </div>
      )}

      {/* Info when store is selected but no search */}
      {storeId && !searchTerm && (
        <div className="text-sm text-gray-500 mt-2">
          {isLoading ? (
            <span className="flex items-center gap-2">
              <Loader className="h-3 w-3 animate-spin" />
              Loading inventory...
            </span>
          ) : (
            <span>
              {availableProducts.length} product{availableProducts.length !== 1 ? 's' : ''}{' '}
              available at this store
            </span>
          )}
        </div>
      )}
    </div>
  )
}
