package com.sumeravera.protocol.data

import com.sumeravera.protocol.core.crypto.FastCrypto
import com.sumeravera.protocol.core.engine.SumerAStateEngine
import com.sumeravera.protocol.core.pipeline.EdgeVerificationPipeline
import com.sumeravera.protocol.core.pipeline.PipelineMetrics
import com.sumeravera.protocol.model.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.*

class ProtocolRepository {

    private val repositoryScope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    // Core deterministic state & verification engine
    val stateEngine = SumerAStateEngine()

    // Low-power background worker pipeline for edge compute
    val pipeline = EdgeVerificationPipeline(stateEngine, repositoryScope)
    val pipelineMetrics: StateFlow<PipelineMetrics> = pipeline.metrics

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

    init {
        syncStateFromEngine()
        seedSampleData()
    }

    private fun syncStateFromEngine() {
        _ledgerEntries.value = stateEngine.getLedgerBlocks()
        _invariants.value = stateEngine.getInvariants()
    }

    // ── Cryptographic Hashing (Zero-Allocation FastCrypto) ────────────────────
    fun sha256(data: String): String = FastCrypto.sha256(data)

    // ── SumerA Layer (Immutable Ledger) ────────────────────────────────────────
    fun appendLedgerEntry(category: String, payload: String): LedgerEntry {
        val entry = stateEngine.appendRawBlock(category, payload, System.currentTimeMillis().toString())
        syncStateFromEngine()
        return entry
    }

    fun verifyChainIntegrity(): Boolean {
        return stateEngine.verifyChain(fullAudit = false)
    }

    fun tamperChainForDemo(): Boolean {
        val result = stateEngine.tamperBlockForDemo()
        syncStateFromEngine()
        return result
    }

    fun recalculateAndRepairChain() {
        stateEngine.repairChain()
        syncStateFromEngine()
    }

    // ── State Engine Invariants (Layer 1) ─────────────────────────────────────
    fun addInvariant(
        priority: String,
        category: String,
        key: String,
        value: String,
        immutable: Boolean
    ): Pair<Boolean, String> {
        val result = stateEngine.addInvariant(priority, category, key, value, immutable)
        syncStateFromEngine()
        return result
    }

    // ── Avera Ground-Truth Validation Engine (Layer 3) ─────────────────────────
    fun validatePayload(
        source: String,
        timestamp: Long?,
        category: String,
        rawJsonData: String
    ): ValidationResult {
        val t = timestamp ?: System.currentTimeMillis()
        val result = stateEngine.verifySignal(source, t, category, rawJsonData)
        _validationHistory.update { listOf(result) + it }
        syncStateFromEngine()
        return result
    }

    /**
     * Submit to the low-power background worker pipeline for edge batching.
     */
    fun enqueueSignalForVerification(
        source: String,
        timestamp: Long,
        category: String,
        rawJsonData: String,
        onComplete: (ValidationResult) -> Unit
    ) {
        repositoryScope.launch {
            pipeline.submit(source, timestamp, category, rawJsonData) { res ->
                _validationHistory.update { listOf(res) + it }
                syncStateFromEngine()
                onComplete(res)
            }
        }
    }

    // ── Honeypot Perimeter Defense (Low-Power Path Classification) ───────────
    fun classifyPathSeverity(path: String): String {
        // Fast-path character scanning without regex overhead or string allocations
        val len = path.length
        if (len == 0) return "info"

        // Critical detection
        if (path.contains("admin", ignoreCase = true) ||
            path.contains("config", ignoreCase = true) ||
            path.contains("env", ignoreCase = true) ||
            path.contains(".git", ignoreCase = true) ||
            path.contains("wp-login", ignoreCase = true) ||
            path.contains("phpmyadmin", ignoreCase = true)) {
            return "critical"
        }

        // Warning detection
        if (path.contains("login", ignoreCase = true) ||
            path.contains("auth", ignoreCase = true) ||
            path.contains("api/v", ignoreCase = true)) {
            return "warning"
        }

        return "info"
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
        val timestamp = System.currentTimeMillis().toString()
        val fingerprint = FastCrypto.sha256("$ip$method$path")

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

        // Append THREAT record directly to SumerA ledger
        appendLedgerEntry("THREAT", "{\"threat_id\":\"$id\",\"ip\":\"$ip\",\"severity\":\"$severity\",\"blocked\":$isAutoBlocked}")

        // Dynamic icon alert update
        updateDynamicIconState(severity)

        val fakeToken = FastCrypto.sha256(id).take(32)
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
        return FastCrypto.sha256("$species:$primaryMarkingHash:$stewardSignature")
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
            return Pair(false, null)
        }

        val payload = "{\"source\":\"paws-connect\",\"species\":\"$species\",\"node_id\":\"$nodeId\"}"
        val valResult = validatePayload("paws-connect", System.currentTimeMillis(), "PAWS_IDENTITY", payload)

        val node = PawsIdentityNode(
            nodeId = nodeId,
            speciesClassification = species.lowercase(Locale.ROOT).trim(),
            biometricMarkers = BiometricMarkers(
                primaryMarkingHash = primaryMarkingHash,
                chipIdentifier = chipIdentifier?.takeIf { it.isNotBlank() }
            ),
            stewardSignature = stewardSignature,
            immutableLedgerRecord = immutableLedgerRecord,
            createdAt = System.currentTimeMillis().toString(),
            ledgerEntryId = valResult.ledgerEntryId
        )

        _pawsNodes.update { listOf(node) + it }
        return Pair(true, node)
    }

    fun verifyPawsSignature(nodeId: String, signature: String): Boolean {
        val node = _pawsNodes.value.find { it.nodeId == nodeId } ?: return false
        return node.stewardSignature.trim() == signature.trim()
    }

    // ── Seed Sample Data ───────────────────────────────────────────────────────
    private fun seedSampleData() {
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

        recordProbe(
            ip = "198.51.100.42",
            method = "GET",
            path = "/.env"
        )
    }
}
