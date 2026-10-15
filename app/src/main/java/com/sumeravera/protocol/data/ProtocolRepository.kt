package com.sumeravera.protocol.data

import com.sumeravera.protocol.model.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONObject
import java.security.MessageDigest
import java.text.SimpleDateFormat
import java.util.*

class ProtocolRepository {

    private val _ledgerEntries = MutableStateFlow<List<LedgerEntry>>(emptyList())
    val ledgerEntries: StateFlow<List<LedgerEntry>> = _ledgerEntries.asStateFlow()

    private val _invariants = MutableStateFlow<List<StateInvariant>>(emptyList())
    val invariants: StateFlow<List<StateInvariant>> = _invariants.asStateFlow()

    private val _threatEvents = MutableStateFlow<List<ThreatEvent>>(emptyList())
    val threatEvents: StateFlow<List<ThreatEvent>> = _threatEvents.asStateFlow()

    private val _blocklist = MutableStateFlow<Set<String>>(emptySet())
    val blocklist: StateFlow<Set<String>> = _blocklist.asStateFlow()

    private val _pawsNodes = MutableStateFlow<List<PawsIdentityNode>>(emptyList())
    val pawsNodes: StateFlow<List<PawsIdentityNode>> = _pawsNodes.asStateFlow()

    private val _dynamicIconState = MutableStateFlow(DynamicIconState())
    val dynamicIconState: StateFlow<DynamicIconState> = _dynamicIconState.asStateFlow()

    private val _validationHistory = MutableStateFlow<List<ValidationResult>>(emptyList())
    val validationHistory: StateFlow<List<ValidationResult>> = _validationHistory.asStateFlow()

    private val _rules = MutableStateFlow<List<ValidationRule>>(
        listOf(
            ValidationRule("RULE-001", "Payload must not be empty"),
            ValidationRule("RULE-002", "Payload must include a source identifier"),
            ValidationRule("RULE-003", "Payload must include a timestamp"),
            ValidationRule("RULE-004", "Payload must not contradict Layer 1 immutable state invariants")
        )
    )
    val rules: StateFlow<List<ValidationRule>> = _rules.asStateFlow()

    private var nextSeq = 1L

    init {
        seedInitialState()
    }

    // ── Cryptographic Hashing ──────────────────────────────────────────────────
    fun sha256(data: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val bytes = digest.digest(data.toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it) }
    }

    private fun nowIso(): String {
        val sdf = SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", Locale.US)
        sdf.timeZone = TimeZone.getTimeZone("UTC")
        return sdf.format(Date())
    }

    // ── SumerA Layer (Immutable Ledger) ────────────────────────────────────────
    @Synchronized
    fun appendLedgerEntry(category: String, payload: String): LedgerEntry {
        val currentEntries = _ledgerEntries.value
        val prevHash = if (currentEntries.isEmpty()) {
            "0".repeat(64)
        } else {
            currentEntries.last().chainHash
        }

        val entryId = UUID.randomUUID().toString()
        val timestamp = nowIso()
        val payloadHash = sha256(payload)
        val chainHash = sha256("$prevHash$payloadHash$timestamp")

        val entry = LedgerEntry(
            seq = nextSeq++,
            entryId = entryId,
            timestamp = timestamp,
            category = category,
            payloadHash = payloadHash,
            payload = payload,
            prevHash = prevHash,
            chainHash = chainHash
        )

        _ledgerEntries.update { it + entry }
        return entry
    }

    fun verifyChainIntegrity(): Boolean {
        val entries = _ledgerEntries.value
        if (entries.isEmpty()) return true

        var prevHash = "0".repeat(64)
        for (entry in entries) {
            if (entry.prevHash != prevHash) return false
            val expectedHash = sha256("${entry.prevHash}${entry.payloadHash}${entry.timestamp}")
            if (entry.chainHash != expectedHash) return false
            prevHash = entry.chainHash
        }
        return true
    }

    fun tamperChainForDemo(): Boolean {
        val entries = _ledgerEntries.value.toMutableList()
        if (entries.size >= 2) {
            val idx = entries.size - 2
            val old = entries[idx]
            entries[idx] = old.copy(payload = old.payload + " [UNAUTHORIZED_MODIFICATION]")
            _ledgerEntries.value = entries
            return true
        }
        return false
    }

    fun recalculateAndRepairChain() {
        val entries = _ledgerEntries.value
        if (entries.isEmpty()) return

        var prevHash = "0".repeat(64)
        val repaired = entries.map { entry ->
            val payloadHash = sha256(entry.payload)
            val chainHash = sha256("$prevHash$payloadHash${entry.timestamp}")
            val fixed = entry.copy(
                prevHash = prevHash,
                payloadHash = payloadHash,
                chainHash = chainHash
            )
            prevHash = chainHash
            fixed
        }
        _ledgerEntries.value = repaired
    }

    // ── State Engine Invariants (Layer 1) ─────────────────────────────────────
    fun addInvariant(
        priority: String,
        category: String,
        key: String,
        value: String,
        immutable: Boolean
    ): Pair<Boolean, String> {
        val existing = _invariants.value.find { it.key.equals(key, ignoreCase = true) }
        if (existing != null && existing.immutable) {
            return Pair(false, "Cannot overwrite immutable invariant with key: $key")
        }

        val id = "INV-" + String.format(Locale.US, "%03d", _invariants.value.size + 1)
        val timestamp = nowIso()
        val newInv = StateInvariant(
            id = id,
            timestamp = timestamp,
            priority = priority,
            category = category,
            key = key,
            value = value,
            immutable = immutable
        )

        if (existing != null) {
            _invariants.update { list -> list.map { if (it.key.equals(key, ignoreCase = true)) newInv else it } }
        } else {
            _invariants.update { it + newInv }
        }

        // Anchor into SumerA ledger
        val payloadJson = JSONObject().apply {
            put("action", "APPEND_INVARIANT")
            put("id", id)
            put("priority", priority)
            put("category", category)
            put("key", key)
            put("value", value)
            put("immutable", immutable)
        }.toString()
        appendLedgerEntry("INVARIANT", payloadJson)

        return Pair(true, "Invariant $id successfully anchored to SumerA ledger.")
    }

    // ── Avera Ground-Truth Validation Engine ───────────────────────────────────
    fun validatePayload(
        source: String,
        timestamp: Long?,
        category: String,
        rawJsonData: String
    ): ValidationResult {
        val failures = mutableListOf<ValidationRuleFailure>()
        val invariantConflicts = mutableListOf<String>()

        // RULE-001: Payload must not be empty
        if (rawJsonData.isBlank() || rawJsonData.trim() == "{}") {
            failures.add(ValidationRuleFailure("RULE-001", "Payload must not be empty"))
        }

        // RULE-002: Payload must include a source identifier
        if (source.isBlank()) {
            failures.add(ValidationRuleFailure("RULE-002", "Payload must include a source identifier"))
        }

        // RULE-003: Payload must include a timestamp
        if (timestamp == null || timestamp <= 0) {
            failures.add(ValidationRuleFailure("RULE-003", "Payload must include a valid timestamp"))
        }

        // RULE-004: Invariant anti-drift check
        // If payload contains terminology explicitly forbidden by immutable invariants
        val terminologyInvariant = _invariants.value.find { it.key == "terminology_rules" }
        if (terminologyInvariant != null) {
            if (rawJsonData.contains("blinkers", ignoreCase = true)) {
                invariantConflicts.add("Violates INV-002: term 'blinkers' detected; use 'blinders'")
            }
            if (rawJsonData.contains("expand", ignoreCase = true) && !rawJsonData.contains("expound", ignoreCase = true)) {
                invariantConflicts.add("Violates INV-002: preference for 'expound' over 'expand'")
            }
        }

        if (invariantConflicts.isNotEmpty()) {
            failures.add(ValidationRuleFailure("RULE-004", invariantConflicts.joinToString("; ")))
        }

        val payloadHash = sha256(rawJsonData)
        val passed = failures.isEmpty()

        var ledgerEntryId: String? = null
        if (passed) {
            val recordJson = JSONObject().apply {
                put("source", source)
                put("timestamp", timestamp ?: System.currentTimeMillis())
                put("validated_category", category)
                put("payload_hash", payloadHash)
                put("data", rawJsonData)
            }.toString()
            val entry = appendLedgerEntry(category, recordJson)
            ledgerEntryId = entry.entryId
        }

        val result = ValidationResult(
            valid = passed,
            payloadHash = payloadHash,
            reason = if (passed) "Validated against Avera Ground-Truth Engine" else "Rule failure",
            failures = failures,
            ledgerEntryId = ledgerEntryId,
            invariantConflicts = invariantConflicts
        )

        _validationHistory.update { listOf(result) + it }
        return result
    }

    // ── Honeypot Perimeter Defense ─────────────────────────────────────────────
    fun classifyPathSeverity(path: String): String {
        val lower = path.lowercase(Locale.ROOT)
        return when {
            lower.contains("admin") || lower.contains("config") || lower.contains("env") ||
                    lower.contains(".git") || lower.contains("wp-login") || lower.contains("phpmyadmin") -> "critical"
            lower.contains("login") || lower.contains("auth") || lower.contains("api/v") -> "warning"
            else -> "info"
        }
    }

    fun recordProbe(
        ip: String,
        method: String,
        path: String,
        headers: Map<String, String> = mapOf("user-agent" to "Scanner/2.1", "host" to "node.svp.net"),
        body: String? = null
    ): Pair<ThreatEvent, String> {
        val severity = classifyPathSeverity(path)
        val id = UUID.randomUUID().toString()
        val timestamp = nowIso()
        val rawData = "$ip$method$path${headers.entries.sortedBy { it.key }.joinToString()}"
        val fingerprint = sha256(rawData)

        val isAutoBlocked = severity == "critical" || _blocklist.value.contains(ip)
        if (severity == "critical") {
            _blocklist.update { it + ip }
        }

        val threat = ThreatEvent(
            id = id,
            ip = ip,
            timestamp = timestamp,
            method = method,
            path = path,
            fingerprint = fingerprint,
            severity = severity,
            headers = headers,
            body = body,
            blocked = isAutoBlocked
        )

        _threatEvents.update { listOf(threat) + it.take(99) }

        // Also record threat onto SumerA ledger
        val threatJson = JSONObject().apply {
            put("threat_id", id)
            put("attacker_ip", ip)
            put("severity", severity)
            put("fingerprint", fingerprint)
            put("path", path)
            put("method", method)
            put("blocked", isAutoBlocked)
        }.toString()
        appendLedgerEntry("THREAT", threatJson)

        // Dynamic icon alert update
        updateDynamicIconState(severity)

        // Plausible decoy token response (PHP/7.4.3 decoy emulation)
        val fakeToken = sha256(UUID.randomUUID().toString()).take(32)
        val decoyResponse = "HTTP/1.1 200 OK\nX-Powered-By: PHP/7.4.3\nContent-Type: application/json\n\n{\"status\":\"ok\",\"token\":\"$fakeToken\"}"

        return Pair(threat, decoyResponse)
    }

    fun toggleBlockIp(ip: String) {
        _blocklist.update { current ->
            if (current.contains(ip)) current - ip else current + ip
        }
    }

    private fun updateDynamicIconState(latestSeverity: String) {
        val (alias, color, indicator) = when (latestSeverity) {
            "critical" -> Triple("icon_alert_critical", "#EF4444", true)
            "warning" -> Triple("icon_alert_warning", "#F59E0B", true)
            else -> Triple("icon_default", "#00F5D4", false)
        }
        _dynamicIconState.value = DynamicIconState(
            activeStateAlias = alias,
            severity = latestSeverity,
            showIndicator = indicator,
            primaryColorHex = color
        )
    }

    // ── Paws Connect Identity Network ──────────────────────────────────────────
    fun deriveNodeId(species: String, primaryMarkingHash: String, stewardSignature: String): String {
        return sha256("$species:$primaryMarkingHash:$stewardSignature")
    }

    fun registerPawsNode(
        species: String,
        primaryMarkingHash: String,
        chipIdentifier: String?,
        stewardSignature: String,
        immutableLedgerRecord: Boolean = true
    ): Pair<Boolean, PawsIdentityNode?> {
        if (species.isBlank() || primaryMarkingHash.isBlank() || stewardSignature.isBlank()) {
            return Pair(false, null)
        }

        val nodeId = deriveNodeId(species, primaryMarkingHash, stewardSignature)
        if (_pawsNodes.value.any { it.nodeId == nodeId }) {
            return Pair(false, null) // Already exists
        }

        // Validate signal via Avera Engine
        val payloadObj = JSONObject().apply {
            put("source", "paws-connect")
            put("species", species)
            put("node_id", nodeId)
            put("primary_marking_hash", primaryMarkingHash)
            put("chip_identifier", chipIdentifier ?: "")
            put("steward_signature", stewardSignature)
        }
        val valResult = validatePayload("paws-connect", System.currentTimeMillis(), "PAWS_IDENTITY", payloadObj.toString())

        val node = PawsIdentityNode(
            nodeId = nodeId,
            speciesClassification = species.lowercase(Locale.ROOT).trim(),
            biometricMarkers = BiometricMarkers(
                primaryMarkingHash = primaryMarkingHash,
                chipIdentifier = chipIdentifier?.takeIf { it.isNotBlank() }
            ),
            stewardSignature = stewardSignature,
            immutableLedgerRecord = immutableLedgerRecord,
            createdAt = nowIso(),
            ledgerEntryId = valResult.ledgerEntryId
        )

        _pawsNodes.update { listOf(node) + it }
        return Pair(true, node)
    }

    fun verifyPawsSignature(nodeId: String, signature: String): Boolean {
        val node = _pawsNodes.value.find { it.nodeId == nodeId } ?: return false
        return node.stewardSignature.trim() == signature.trim()
    }

    // ── Aggregated Metrics ─────────────────────────────────────────────────────
    fun getMetrics(): ProtocolMetrics {
        val ledger = _ledgerEntries.value
        val validations = _validationHistory.value
        return ProtocolMetrics(
            totalLedgerEntries = ledger.size,
            isChainValid = verifyChainIntegrity(),
            totalValidations = validations.size,
            acceptedValidations = validations.count { it.valid },
            rejectedValidations = validations.count { !it.valid },
            threatsCaptured = _threatEvents.value.size,
            blocklistSize = _blocklist.value.size,
            registeredPawsNodes = _pawsNodes.value.size
        )
    }

    // ── Initial State Seeding ──────────────────────────────────────────────────
    private fun seedInitialState() {
        // 1. Seed Genesis Invariants from STATE_ENGINE_SPEC.md
        val inv1 = StateInvariant(
            id = "INV-001",
            timestamp = "2026-07-30T15:33:00Z",
            priority = "P0",
            category = "DIRECTIVE",
            key = "user_communication_style",
            value = "Direct, explicit, grounded. Zero fluff, no sugarcoating, no mincing words.",
            immutable = true
        )
        val inv2 = StateInvariant(
            id = "INV-002",
            timestamp = "2026-07-30T15:33:00Z",
            priority = "P0",
            category = "CORRECTION",
            key = "terminology_rules",
            value = "Use 'expound' not 'expand'; use 'blinders' not 'blinkers'.",
            immutable = true
        )
        val inv3 = StateInvariant(
            id = "INV-003",
            timestamp = "2026-07-30T15:33:00Z",
            priority = "P1",
            category = "PROJECT_SPEC",
            key = "active_architecture",
            value = "SumerAvera Protocol (SVP) - Intent-Driven Decentralized Computing & Ground-Truth Verification Engine.",
            immutable = false
        )
        _invariants.value = listOf(inv1, inv2, inv3)

        // 2. Seed Genesis Blocks in SumerA Layer
        appendLedgerEntry(
            "SYSTEM",
            JSONObject().apply {
                put("protocol", "SumerAvera Protocol (SVP)")
                put("version", "1.0.0")
                put("consensus", "Append-Only SHA-256 Merkle Chain")
                put("state_engine", "Deterministic Invariant Gate")
            }.toString()
        )

        appendLedgerEntry(
            "INVARIANT",
            JSONObject().apply {
                put("action", "SEED_GENESIS_INVARIANTS")
                put("count", 3)
                put("invariants", listOf("INV-001", "INV-002", "INV-003"))
            }.toString()
        )

        // 3. Seed Sample Identity Nodes for Paws Connect
        val sampleNode1 = PawsIdentityNode(
            nodeId = deriveNodeId("canine", "7a8b9c0d1e2f3a4b", "secp256k1_steward_9901"),
            speciesClassification = "canine",
            biometricMarkers = BiometricMarkers("7a8b9c0d1e2f3a4b", "985141002345678"),
            stewardSignature = "secp256k1_steward_9901",
            immutableLedgerRecord = true,
            createdAt = "2026-09-10T12:00:00Z"
        )
        val sampleNode2 = PawsIdentityNode(
            nodeId = deriveNodeId("feline", "2b3c4d5e6f7a8b9c", "secp256k1_steward_4412"),
            speciesClassification = "feline",
            biometricMarkers = BiometricMarkers("2b3c4d5e6f7a8b9c", "985141009876543"),
            stewardSignature = "secp256k1_steward_4412",
            immutableLedgerRecord = true,
            createdAt = "2026-09-20T14:30:00Z"
        )
        _pawsNodes.value = listOf(sampleNode1, sampleNode2)

        // 4. Seed Honeypot Telemetry Sample
        recordProbe(
            ip = "198.51.100.42",
            method = "GET",
            path = "/.env",
            headers = mapOf("user-agent" to "curl/7.81.0", "host" to "node.svp.net")
        )
        recordProbe(
            ip = "203.0.113.19",
            method = "POST",
            path = "/wp-login.php",
            headers = mapOf("user-agent" to "Python-urllib/3.10", "host" to "node.svp.net")
        )
    }
}
