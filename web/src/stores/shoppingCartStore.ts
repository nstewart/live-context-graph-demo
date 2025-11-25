import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface CartLineItem {
  product_id: string
  product_name: string
  quantity: number
  unit_price: number
  line_amount: number
  perishable_flag: boolean
  available_stock: number
  category?: string
}

interface ShoppingCartState {
  store_id: string | null
  line_items: CartLineItem[]

  // Actions
  addItem: (item: Omit<CartLineItem, 'line_amount'>) => void
  removeItem: (product_id: string) => void
  updateQuantity: (product_id: string, quantity: number) => void
  clearCart: () => void
  setStore: (store_id: string | null, confirmClear?: boolean) => boolean

  // Computed values
  getTotal: () => number
  getItemCount: () => number
  hasPerishableItems: () => boolean
  loadLineItems: (items: CartLineItem[]) => void
}

export const useShoppingCartStore = create<ShoppingCartState>()(
  persist(
    (set, get) => ({
      store_id: null,
      line_items: [],

      addItem: (item) => {
        const state = get()

        // Check if item already exists in cart
        const existingItemIndex = state.line_items.findIndex(
          i => i.product_id === item.product_id
        )

        if (existingItemIndex !== -1) {
          // Update existing item quantity
          const existingItem = state.line_items[existingItemIndex]
          const newQuantity = existingItem.quantity + item.quantity

          // Validate against available stock
          if (newQuantity > item.available_stock) {
            throw new Error(
              `Cannot add ${item.quantity} more. Only ${item.available_stock - existingItem.quantity} remaining in stock.`
            )
          }

          const updatedItems = [...state.line_items]
          updatedItems[existingItemIndex] = {
            ...existingItem,
            quantity: newQuantity,
            line_amount: newQuantity * existingItem.unit_price,
            available_stock: item.available_stock, // Update stock level
          }

          set({ line_items: updatedItems })
        } else {
          // Add new item
          if (item.quantity > item.available_stock) {
            throw new Error(
              `Cannot add ${item.quantity}. Only ${item.available_stock} available in stock.`
            )
          }

          const newItem: CartLineItem = {
            ...item,
            line_amount: item.quantity * item.unit_price,
          }

          set({ line_items: [...state.line_items, newItem] })
        }
      },

      removeItem: (product_id) => {
        set(state => ({
          line_items: state.line_items.filter(item => item.product_id !== product_id),
        }))
      },

      updateQuantity: (product_id, quantity) => {
        const state = get()

        if (quantity <= 0) {
          // Remove item if quantity is 0 or negative
          state.removeItem(product_id)
          return
        }

        const item = state.line_items.find(i => i.product_id === product_id)

        if (!item) return

        // Validate against available stock
        if (quantity > item.available_stock) {
          throw new Error(
            `Cannot set quantity to ${quantity}. Only ${item.available_stock} available in stock.`
          )
        }

        set(state => ({
          line_items: state.line_items.map(i =>
            i.product_id === product_id
              ? { ...i, quantity, line_amount: quantity * i.unit_price }
              : i
          ),
        }))
      },

      clearCart: () => {
        set({ line_items: [] })
      },

      setStore: (store_id, confirmClear = false) => {
        const state = get()

        // If store is changing and cart has items, require confirmation
        if (state.store_id && state.store_id !== store_id && state.line_items.length > 0) {
          if (!confirmClear) {
            // Return false to indicate confirmation needed
            return false
          }
        }

        // Clear cart when store changes
        set({ store_id, line_items: [] })
        return true
      },

      getTotal: () => {
        const state = get()
        return state.line_items.reduce((sum, item) => sum + item.line_amount, 0)
      },

      getItemCount: () => {
        const state = get()
        return state.line_items.reduce((sum, item) => sum + item.quantity, 0)
      },

      hasPerishableItems: () => {
        const state = get()
        return state.line_items.some(item => item.perishable_flag)
      },

      loadLineItems: (items) => {
        set({ line_items: items })
      },
    }),
    {
      name: 'shopping-cart-storage',
      // Only persist store_id and line_items, not functions
      partialize: (state) => ({
        store_id: state.store_id,
        line_items: state.line_items,
      }),
    }
  )
)
