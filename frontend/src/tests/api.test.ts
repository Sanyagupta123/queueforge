import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'

afterEach(() => vi.unstubAllGlobals())

describe('API client', () => {
  it('returns decoded response data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ok' }), { status: 200 })))
    await expect(api.health()).resolves.toEqual({ status: 'ok' })
  })

  it('surfaces backend error details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'lease expired' }), { status: 409 })))
    await expect(api.health()).rejects.toThrow('lease expired')
  })

  it('reports unavailable API', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network failure')))
    await expect(api.health()).rejects.toThrow('API is unavailable')
  })
})
