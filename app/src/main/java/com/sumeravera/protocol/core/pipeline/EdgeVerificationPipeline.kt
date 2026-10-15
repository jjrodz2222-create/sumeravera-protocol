package com.sumeravera.protocol.core.pipeline

import com.sumeravera.protocol.core.engine.SumerAStateEngine
import com.sumeravera.protocol.core.pool.ObjectPool
import com.sumeravera.protocol.model.ValidationResult
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.concurrent.atomic.AtomicLong

/**
 * Reusable signal envelope representing an ingress verification task.
 * Recycled through [ObjectPool] to guarantee 0 heap allocation.
 */
class SignalEnvelope {
    var source: String = ""
    var timestamp: Long = 0L
    var category: String = "SIGNAL"
    var payload: String = ""
    var onComplete: ((ValidationResult) -> Unit)? = null

    fun reset() {
        source = ""
        timestamp = 0L
        category = "SIGNAL"
        payload = ""
        onComplete = null
    }
}

data class PipelineMetrics(
    val processedSignals: Long = 0L,
    val batchesFlushed: Long = 0L,
    val recycledEnvelopes: Long = 0L,
    val averageBatchSize: Float = 0f,
    val isRunning: Boolean = false
)

/**
 * Edge Verification Background Pipeline.
 *
 * Micro-batches incoming verification tasks to coalesce CPU awake cycles,
 * preventing mobile/embedded core wakeups on every single byte.
 * Reuses envelopes via lock-free object pools for zero GC allocation.
 */
class EdgeVerificationPipeline(
    private val stateEngine: SumerAStateEngine,
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Default + SupervisorJob())
) {
    companion object {
        private const val POOL_CAPACITY = 128
        private const val CHANNEL_CAPACITY = 256
        private const val MAX_BATCH_SIZE = 16
        private const val FLUSH_DELAY_MS = 40L
    }

    private val envelopePool = ObjectPool(
        capacity = POOL_CAPACITY,
        factory = { SignalEnvelope() },
        reset = { it.reset() }
    )

    private val ingressChannel = Channel<SignalEnvelope>(
        capacity = CHANNEL_CAPACITY,
        onBufferOverflow = BufferOverflow.SUSPEND
    )

    private val _metrics = MutableStateFlow(PipelineMetrics())
    val metrics: StateFlow<PipelineMetrics> = _metrics.asStateFlow()

    private val processedCounter = AtomicLong(0L)
    private val batchCounter = AtomicLong(0L)
    private val recycledCounter = AtomicLong(0L)

    private var workerJob: Job? = null

    init {
        startWorker()
    }

    fun startWorker() {
        if (workerJob?.isActive == true) return

        workerJob = scope.launch {
            _metrics.value = _metrics.value.copy(isRunning = true)
            val batch = ArrayList<SignalEnvelope>(MAX_BATCH_SIZE)

            while (isActive) {
                // Suspends with 0 CPU cycles until the first item arrives
                val first = ingressChannel.receiveCatching().getOrNull() ?: break
                batch.add(first)

                // Coalesce additional items without blocking the CPU
                var deadline = System.currentTimeMillis() + FLUSH_DELAY_MS
                while (batch.size < MAX_BATCH_SIZE && System.currentTimeMillis() < deadline) {
                    val poll = ingressChannel.tryReceive().getOrNull()
                    if (poll != null) {
                        batch.add(poll)
                    } else {
                        // Short yield to allow ingress bursts to coalesce
                        delay(2)
                    }
                }

                // Execute batch verification in one tight CPU burst
                processBatch(batch)
                batch.clear()
            }
            _metrics.value = _metrics.value.copy(isRunning = false)
        }
    }

    private fun processBatch(batch: List<SignalEnvelope>) {
        if (batch.isEmpty()) return

        for (envelope in batch) {
            val result = stateEngine.verifySignal(
                source = envelope.source,
                timestamp = envelope.timestamp,
                category = envelope.category,
                payload = envelope.payload
            )
            envelope.onComplete?.invoke(result)

            // Recycle envelope back to pool (0 allocation)
            envelopePool.release(envelope)
            recycledCounter.incrementAndGet()
            processedCounter.incrementAndGet()
        }

        val bCount = batchCounter.incrementAndGet()
        val pCount = processedCounter.get()
        _metrics.value = PipelineMetrics(
            processedSignals = pCount,
            batchesFlushed = bCount,
            recycledEnvelopes = recycledCounter.get(),
            averageBatchSize = if (bCount > 0) pCount.toFloat() / bCount else 0f,
            isRunning = true
        )
    }

    /**
     * Submit an ingress verification task to the pipeline.
     * Uses the pre-allocated envelope pool to eliminate object creation.
     */
    suspend fun submit(
        source: String,
        timestamp: Long,
        category: String,
        payload: String,
        onComplete: ((ValidationResult) -> Unit)? = null
    ) {
        val envelope = envelopePool.acquire()
        envelope.source = source
        envelope.timestamp = timestamp
        envelope.category = category
        envelope.payload = payload
        envelope.onComplete = onComplete

        ingressChannel.send(envelope)
    }

    /**
     * Direct synchronous verification bypass (for immediate UI responses while sharing the same engine).
     */
    fun verifyImmediate(
        source: String,
        timestamp: Long,
        category: String,
        payload: String
    ): ValidationResult {
        return stateEngine.verifySignal(source, timestamp, category, payload)
    }

    fun stop() {
        workerJob?.cancel()
        _metrics.value = _metrics.value.copy(isRunning = false)
    }
}
