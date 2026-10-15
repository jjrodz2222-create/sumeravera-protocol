package com.sumeravera.protocol.core.engine

import com.sumeravera.protocol.core.crypto.FastCrypto
import com.sumeravera.protocol.model.*
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicLong

/**
 * Deterministic State & Verification Engine (Layers 1 & 3).
 * Optimized strictly for edge compute:
 * - Zero-allocation string scanning for invariant enforcement
 * - Direct byte-level cryptographic chain verification
 * - Incremental verification checkpoints to conserve CPU cycles
 */
class SumerAStateEngine {

    private val invariants = CopyOnWriteArrayList<StateInvariant>()
    private val ledgerBlocks = CopyOnWriteArrayList<LedgerEntry>()
    private val nextSequence = AtomicLong(1L)

    // Checkpoint for incremental verification: avoids re-verifying old blocks on every tick
    @Volatile
    private var lastVerifiedSeq: Long = 0L
    @Volatile
    private var isChainIntegrityIntact: Boolean = true

    init {
        seedGenesisState()
    }

    /**
     * Layer 1: Seed initial immutable invariants per STATE_ENGINE_SPEC.md
     */
    private fun seedGenesisState() {
        invariants.add(
            StateInvariant(
                id = "INV-001",
                timestamp = "2026-07-30T15:33:00Z",
                priority = "P0",
                category = "DIRECTIVE",
                key = "user_communication_style",
                value = "Direct, explicit, grounded. Zero fluff, no sugarcoating, no mincing words.",
                immutable = true
            )
        )
        invariants.add(
            StateInvariant(
                id = "INV-002",
                timestamp = "2026-07-30T15:33:00Z",
                priority = "P0",
                category = "CORRECTION",
                key = "terminology_rules",
                value = "Use 'expound' not 'expand'; use 'blinders' not 'blinkers'.",
                immutable = true
            )
        )
        invariants.add(
            StateInvariant(
                id = "INV-003",
                timestamp = "2026-07-30T15:33:00Z",
                priority = "P1",
                category = "PROJECT_SPEC",
                key = "active_architecture",
                value = "SumerAvera Protocol (SVP) - Intent-Driven Decentralized Computing & Ground-Truth Verification Engine.",
                immutable = false
            )
        )

        // Seed Genesis Block
        appendRawBlock(
            category = "SYSTEM",
            payload = "{\"protocol\":\"SumerAvera Protocol (SVP)\",\"version\":\"1.0.0\",\"consensus\":\"Append-Only SHA-256 Merkle Chain\"}",
            timestamp = "2026-07-30T15:33:00Z"
        )
    }

    // ── Layer 1: Local Invariant Ledger ────────────────────────────────────────

    fun getInvariants(): List<StateInvariant> = invariants

    fun addInvariant(
        priority: String,
        category: String,
        key: String,
        value: String,
        immutable: Boolean
    ): Pair<Boolean, String> {
        val existingIndex = invariants.indexOfFirst { it.key.equals(key, ignoreCase = true) }
        if (existingIndex >= 0) {
            val existing = invariants[existingIndex]
            if (existing.immutable) {
                return Pair(false, "Cannot overwrite immutable invariant: $key")
            }
        }

        val id = "INV-${String.format(java.util.Locale.US, "%03d", invariants.size + 1)}"
        val timestamp = System.currentTimeMillis().toString()
        val newInv = StateInvariant(id, timestamp, priority, category, key, value, immutable)

        if (existingIndex >= 0) {
            invariants[existingIndex] = newInv
        } else {
            invariants.add(newInv)
        }

        // Commit invariant onto the SumerA ledger
        appendRawBlock("INVARIANT", "{\"id\":\"$id\",\"key\":\"$key\",\"value\":\"$value\",\"immutable\":$immutable}", timestamp)
        return Pair(true, "Invariant $id committed.")
    }

    // ── Layer 3: Ground-Truth Verification & Anti-Drift Gate ───────────────────

    /**
     * Zero-allocation, high-speed case-insensitive substring search across CharSequence.
     * Prevents allocation of .lowercase() Strings or Regex Matchers during high-throughput ingestion.
     */
    private fun containsIgnoreCase(source: CharSequence, target: CharSequence): Boolean {
        val srcLen = source.length
        val tgtLen = target.length
        if (tgtLen == 0) return true
        if (srcLen < tgtLen) return false

        val firstUpper = Character.toUpperCase(target[0])
        val firstLower = Character.toLowerCase(target[0])
        val max = srcLen - tgtLen

        for (i in 0..max) {
            val c = source[i]
            if (c == firstUpper || c == firstLower) {
                var match = true
                for (j in 1 until tgtLen) {
                    val sc = source[i + j]
                    val tc = target[j]
                    if (sc != Character.toUpperCase(tc) && sc != Character.toLowerCase(tc)) {
                        match = false
                        break
                    }
                }
                if (match) return true
            }
        }
        return false
    }

    /**
     * Evaluates ingress payloads strictly with minimal CPU cycle utilization:
     * - Fast-path empty checks
     * - Zero-alloc anti-drift scan for terminology violations (INV-002: blinders vs blinkers, expound vs expand)
     */
    fun verifySignal(
        source: CharSequence,
        timestamp: Long,
        category: String,
        payload: CharSequence
    ): ValidationResult {
        val failures = ArrayList<ValidationRuleFailure>(2)
        val conflicts = ArrayList<String>(1)

        // RULE-001: Payload must not be empty
        if (payload.isEmpty() || (payload.length == 2 && payload[0] == '{' && payload[1] == '}')) {
            failures.add(ValidationRuleFailure("RULE-001", "Payload must not be empty"))
        }

        // RULE-002: Payload must include a source identifier
        if (source.isEmpty()) {
            failures.add(ValidationRuleFailure("RULE-002", "Payload must include source identifier"))
        }

        // RULE-003: Payload must include a valid timestamp
        if (timestamp <= 0) {
            failures.add(ValidationRuleFailure("RULE-003", "Payload must include valid timestamp"))
        }

        // RULE-004: Anti-drift invariant verification
        if (containsIgnoreCase(payload, "blinkers")) {
            val err = "Violates INV-002: Forbidden term 'blinkers' detected; use 'blinders'"
            conflicts.add(err)
            failures.add(ValidationRuleFailure("RULE-004", err))
        }
        if (containsIgnoreCase(payload, "expand") && !containsIgnoreCase(payload, "expound")) {
            val err = "Violates INV-002: Preference for 'expound' over 'expand'"
            conflicts.add(err)
            failures.add(ValidationRuleFailure("RULE-004", err))
        }

        val payloadHash = FastCrypto.sha256(payload.toString())
        val valid = failures.isEmpty()

        var ledgerEntryId: String? = null
        if (valid) {
            val block = appendRawBlock(category, payload.toString(), timestamp.toString())
            ledgerEntryId = block.entryId
        }

        return ValidationResult(
            valid = valid,
            payloadHash = payloadHash,
            reason = if (valid) "Avera Engine Ground-Truth Verified" else "Verification Rejected",
            failures = failures,
            ledgerEntryId = ledgerEntryId,
            invariantConflicts = conflicts
        )
    }

    // ── SumerA Cryptographic Ledger ───────────────────────────────────────────

    @Synchronized
    fun appendRawBlock(category: String, payload: String, timestamp: String): LedgerEntry {
        val prevHash = if (ledgerBlocks.isEmpty()) {
            FastCrypto.GENESIS_HASH_STRING
        } else {
            ledgerBlocks.last().chainHash
        }

        val seq = nextSequence.getAndIncrement()
        val entryId = "SVP-BLK-${seq}-${System.nanoTime()}"
        val payloadHash = FastCrypto.sha256(payload)
        val chainHash = FastCrypto.sha256Chain(prevHash, payloadHash, timestamp)

        val block = LedgerEntry(
            seq = seq,
            entryId = entryId,
            timestamp = timestamp,
            category = category,
            payloadHash = payloadHash,
            payload = payload,
            prevHash = prevHash,
            chainHash = chainHash
        )

        ledgerBlocks.add(block)
        return block
    }

    fun getLedgerBlocks(): List<LedgerEntry> = ledgerBlocks

    /**
     * Efficient chain verification.
     * When [fullAudit] is false, starts from the last valid checkpoint to save CPU cycles.
     */
    fun verifyChain(fullAudit: Boolean = false): Boolean {
        if (ledgerBlocks.isEmpty()) {
            isChainIntegrityIntact = true
            return true
        }

        val startIndex = if (fullAudit || !isChainIntegrityIntact) 0 else lastVerifiedSeq.toInt().coerceAtMost(ledgerBlocks.size - 1)
        var prevHash = if (startIndex == 0) FastCrypto.GENESIS_HASH_STRING else ledgerBlocks[startIndex - 1].chainHash

        for (i in startIndex until ledgerBlocks.size) {
            val block = ledgerBlocks[i]
            if (block.prevHash != prevHash) {
                isChainIntegrityIntact = false
                return false
            }
            val expectedHash = FastCrypto.sha256Chain(block.prevHash, block.payloadHash, block.timestamp)
            if (block.chainHash != expectedHash) {
                isChainIntegrityIntact = false
                return false
            }
            prevHash = block.chainHash
        }

        lastVerifiedSeq = ledgerBlocks.size.toLong()
        isChainIntegrityIntact = true
        return true
    }

    fun tamperBlockForDemo(): Boolean {
        if (ledgerBlocks.size < 2) return false
        val targetIdx = ledgerBlocks.size - 1
        val victim = ledgerBlocks[targetIdx]
        ledgerBlocks[targetIdx] = victim.copy(payload = victim.payload + " [UNAUTHORIZED_TAMPER]")
        isChainIntegrityIntact = false
        return true
    }

    fun repairChain() {
        if (ledgerBlocks.isEmpty()) return
        var prevHash = FastCrypto.GENESIS_HASH_STRING
        for (i in 0 until ledgerBlocks.size) {
            val b = ledgerBlocks[i]
            val payloadHash = FastCrypto.sha256(b.payload)
            val chainHash = FastCrypto.sha256Chain(prevHash, payloadHash, b.timestamp)
            ledgerBlocks[i] = b.copy(prevHash = prevHash, payloadHash = payloadHash, chainHash = chainHash)
            prevHash = chainHash
        }
        lastVerifiedSeq = ledgerBlocks.size.toLong()
        isChainIntegrityIntact = true
    }

    val isIntact: Boolean
        get() = isChainIntegrityIntact
}
