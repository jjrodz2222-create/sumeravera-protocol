package com.sumeravera.protocol.core.pool

import java.util.concurrent.atomic.AtomicInteger

/**
 * Lock-free, zero-waste object pool designed for high-frequency edge execution.
 * Pre-allocates elements on initialization so the background worker pipeline
 * performs 0 heap allocations during active signal ingestion.
 */
class ObjectPool<T : Any>(
    val capacity: Int,
    private val factory: () -> T,
    private val reset: (T) -> Unit
) {
    @Suppress("UNCHECKED_CAST")
    private val pool: Array<Any?> = arrayOfNulls(capacity)
    private val top = AtomicInteger(0)

    init {
        for (i in 0 until capacity) {
            pool[i] = factory()
        }
        top.set(capacity)
    }

    /**
     * Acquire an object from the pool.
     * Falls back to factory only if pool is temporarily depleted.
     */
    @Suppress("UNCHECKED_CAST")
    fun acquire(): T {
        while (true) {
            val current = top.get()
            if (current <= 0) {
                // Temporary pool exhaustion fallback
                return factory()
            }
            if (top.compareAndSet(current, current - 1)) {
                val obj = pool[current - 1] as T
                pool[current - 1] = null
                return obj
            }
        }
    }

    /**
     * Release an object back to the pool for reuse.
     */
    fun release(instance: T) {
        reset(instance)
        while (true) {
            val current = top.get()
            if (current >= capacity) {
                // Pool is full, let instance be reclaimed
                break
            }
            if (top.compareAndSet(current, current + 1)) {
                pool[current] = instance
                break
            }
        }
    }

    /**
     * Available free items ready for immediate zero-allocation retrieval.
     */
    val available: Int
        get() = top.get()
}
