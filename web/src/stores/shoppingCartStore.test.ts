import { describe, it, expect, beforeEach } from 'vitest'
import { useShoppingCartStore, CartLineItem } from './shoppingCartStore'

describe('Shopping Cart Store', () => {
  beforeEach(() => {
    // Reset store before each test
    const { clearCart, setStore } = useShoppingCartStore.getState()
    clearCart()
    setStore(null, true)
  })

  describe('addItem', () => {
    it('should add a new item to the cart', () => {
      const { addItem } = useShoppingCartStore.getState()

      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      const items = useShoppingCartStore.getState().line_items
      expect(items).toHaveLength(1)
      expect(items[0].product_id).toBe('product:001')
      expect(items[0].quantity).toBe(2)
      expect(items[0].line_amount).toBeCloseTo(7.98, 2)
    })

    it('should increase quantity when adding existing item', () => {
      const { addItem } = useShoppingCartStore.getState()

      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 1,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      const items = useShoppingCartStore.getState().line_items
      expect(items).toHaveLength(1)
      expect(items[0].quantity).toBe(3)
      expect(items[0].line_amount).toBeCloseTo(11.97, 2)
    })

    it('should throw error when adding more than available stock', () => {
      const { addItem } = useShoppingCartStore.getState()

      expect(() =>
        addItem({
          product_id: 'product:001',
          product_name: 'Milk',
          quantity: 100,
          unit_price: 3.99,
          perishable_flag: true,
          available_stock: 50,
        })
      ).toThrow('Cannot add 100. Only 50 available in stock.')
    })

    it('should throw error when adding to existing item exceeds stock', () => {
      const { addItem } = useShoppingCartStore.getState()

      // Add 45 items first
      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 45,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      // Try to add 10 more (total would be 55, but only 50 available)
      expect(() =>
        addItem({
          product_id: 'product:001',
          product_name: 'Milk',
          quantity: 10,
          unit_price: 3.99,
          perishable_flag: true,
          available_stock: 50,
        })
      ).toThrow('Cannot add 10 more. Only 5 remaining in stock.')
    })
  })

  describe('removeItem', () => {
    it('should remove an item from the cart', () => {
      const { addItem, removeItem } = useShoppingCartStore.getState()

      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      addItem({
        product_id: 'product:002',
        product_name: 'Bread',
        quantity: 1,
        unit_price: 2.50,
        perishable_flag: false,
        available_stock: 30,
      })

      removeItem('product:001')

      const items = useShoppingCartStore.getState().line_items
      expect(items).toHaveLength(1)
      expect(items[0].product_id).toBe('product:002')
    })
  })

  describe('updateQuantity', () => {
    beforeEach(() => {
      useShoppingCartStore.getState().addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })
    })

    it('should update quantity of an item', () => {
      const { updateQuantity } = useShoppingCartStore.getState()

      updateQuantity('product:001', 5)

      const items = useShoppingCartStore.getState().line_items
      expect(items[0].quantity).toBe(5)
      expect(items[0].line_amount).toBeCloseTo(19.95, 2)
    })

    it('should remove item when quantity is set to 0', () => {
      const { updateQuantity } = useShoppingCartStore.getState()

      updateQuantity('product:001', 0)

      const items = useShoppingCartStore.getState().line_items
      expect(items).toHaveLength(0)
    })

    it('should throw error when quantity exceeds stock', () => {
      const { updateQuantity } = useShoppingCartStore.getState()

      expect(() => updateQuantity('product:001', 100)).toThrow(
        'Cannot set quantity to 100. Only 50 available in stock.'
      )
    })
  })

  describe('clearCart', () => {
    it('should remove all items from cart', () => {
      const { addItem, clearCart } = useShoppingCartStore.getState()

      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      addItem({
        product_id: 'product:002',
        product_name: 'Bread',
        quantity: 1,
        unit_price: 2.50,
        perishable_flag: false,
        available_stock: 30,
      })

      clearCart()

      const items = useShoppingCartStore.getState().line_items
      expect(items).toHaveLength(0)
    })
  })

  describe('setStore', () => {
    it('should set store when cart is empty', () => {
      const { setStore } = useShoppingCartStore.getState()

      const result = setStore('store:001')

      expect(result).toBe(true)
      expect(useShoppingCartStore.getState().store_id).toBe('store:001')
    })

    it('should clear cart when store is set', () => {
      const { addItem, setStore } = useShoppingCartStore.getState()

      // Set initial store and add items
      setStore('store:001')
      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      // Change store with confirmation
      const result = setStore('store:002', true)

      expect(result).toBe(true)
      expect(useShoppingCartStore.getState().store_id).toBe('store:002')
      expect(useShoppingCartStore.getState().line_items).toHaveLength(0)
    })

    it('should require confirmation when changing store with items', () => {
      const { addItem, setStore } = useShoppingCartStore.getState()

      // Set initial store and add items
      setStore('store:001')
      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      // Try to change store without confirmation
      const result = setStore('store:002', false)

      expect(result).toBe(false)
      expect(useShoppingCartStore.getState().store_id).toBe('store:001')
      expect(useShoppingCartStore.getState().line_items).toHaveLength(1)
    })

    it('should allow changing to same store without clearing', () => {
      const { addItem, setStore } = useShoppingCartStore.getState()

      setStore('store:001')
      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      // Set to same store
      const result = setStore('store:001')

      expect(result).toBe(true)
      expect(useShoppingCartStore.getState().line_items).toHaveLength(0) // Still clears
    })
  })

  describe('computed values', () => {
    beforeEach(() => {
      const { addItem, setStore } = useShoppingCartStore.getState()
      setStore('store:001')

      addItem({
        product_id: 'product:001',
        product_name: 'Milk',
        quantity: 2,
        unit_price: 3.99,
        perishable_flag: true,
        available_stock: 50,
      })

      addItem({
        product_id: 'product:002',
        product_name: 'Bread',
        quantity: 3,
        unit_price: 2.50,
        perishable_flag: false,
        available_stock: 30,
      })
    })

    it('should calculate total amount correctly', () => {
      const { getTotal } = useShoppingCartStore.getState()
      const total = getTotal()

      // 2 * 3.99 + 3 * 2.50 = 7.98 + 7.50 = 15.48
      expect(total).toBeCloseTo(15.48, 2)
    })

    it('should calculate total item count correctly', () => {
      const { getItemCount } = useShoppingCartStore.getState()
      const count = getItemCount()

      // 2 + 3 = 5
      expect(count).toBe(5)
    })

    it('should detect perishable items', () => {
      const { hasPerishableItems } = useShoppingCartStore.getState()
      expect(hasPerishableItems()).toBe(true)
    })

    it('should return false when no perishable items', () => {
      const { clearCart, addItem, hasPerishableItems, setStore } = useShoppingCartStore.getState()
      clearCart()
      setStore('store:001')

      addItem({
        product_id: 'product:002',
        product_name: 'Bread',
        quantity: 1,
        unit_price: 2.50,
        perishable_flag: false,
        available_stock: 30,
      })

      expect(hasPerishableItems()).toBe(false)
    })
  })

  describe('loadLineItems', () => {
    it('should load line items into cart (for edit mode)', () => {
      const { loadLineItems } = useShoppingCartStore.getState()

      const items: CartLineItem[] = [
        {
          product_id: 'product:001',
          product_name: 'Milk',
          quantity: 2,
          unit_price: 3.99,
          line_amount: 7.98,
          perishable_flag: true,
          available_stock: 50,
        },
        {
          product_id: 'product:002',
          product_name: 'Bread',
          quantity: 1,
          unit_price: 2.50,
          line_amount: 2.50,
          perishable_flag: false,
          available_stock: 30,
        },
      ]

      loadLineItems(items)

      const state = useShoppingCartStore.getState()
      expect(state.line_items).toHaveLength(2)
      expect(state.line_items[0].product_id).toBe('product:001')
      expect(state.line_items[1].product_id).toBe('product:002')
    })
  })
})
