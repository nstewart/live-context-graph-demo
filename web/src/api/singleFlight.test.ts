import { describe, it, expect, vi } from 'vitest'
import { singleFlight } from './singleFlight'

// A deferred promise we can resolve manually to control when an in-flight call settles.
function deferred() {
  let resolve!: () => void
  const promise = new Promise<void>((r) => { resolve = r })
  return { promise, resolve }
}

describe('singleFlight', () => {
  it('skips overlapping calls while one is in flight', async () => {
    const d = deferred()
    const fn = vi.fn(() => d.promise)
    const guarded = singleFlight(fn)

    guarded() // starts the in-flight call
    guarded() // should be skipped
    guarded() // should be skipped

    expect(fn).toHaveBeenCalledTimes(1)

    d.resolve()
    await Promise.resolve()
  })

  it('allows a new call once the previous one settles', async () => {
    let d = deferred()
    const fn = vi.fn(() => d.promise)
    const guarded = singleFlight(fn)

    const first = guarded()
    expect(fn).toHaveBeenCalledTimes(1)

    d.resolve()
    await first

    d = deferred()
    fn.mockImplementation(() => d.promise)
    guarded()
    expect(fn).toHaveBeenCalledTimes(2)
    d.resolve()
  })

  it('clears the in-flight flag even when the wrapped fn rejects', async () => {
    const fn = vi
      .fn()
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(undefined)
    const guarded = singleFlight(fn)

    await expect(guarded()).rejects.toThrow('boom')

    // A rejection must not leave the guard stuck — the next call should run.
    await guarded()
    expect(fn).toHaveBeenCalledTimes(2)
  })

  it('forwards arguments to the wrapped fn', async () => {
    const fn = vi.fn(async (_a: string, _b: number) => {})
    const guarded = singleFlight(fn)

    await guarded('a', 1)
    expect(fn).toHaveBeenCalledWith('a', 1)
  })
})
