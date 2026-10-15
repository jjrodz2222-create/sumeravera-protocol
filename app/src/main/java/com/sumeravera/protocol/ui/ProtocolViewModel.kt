package com.sumeravera.protocol.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.sumeravera.protocol.data.ProtocolRepository
import com.sumeravera.protocol.model.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch

class ProtocolViewModel(
    val repository: ProtocolRepository = ProtocolRepository()
) : ViewModel() {

    val ledgerEntries: StateFlow<List<LedgerEntry>> = repository.ledgerEntries
    val invariants: StateFlow<List<StateInvariant>> = repository.invariants
    val threatEvents: StateFlow<List<ThreatEvent>> = repository.threatEvents
    val blocklist: StateFlow<Set<String>> = repository.blocklist
    val pawsNodes: StateFlow<List<PawsIdentityNode>> = repository.pawsNodes
    val dynamicIconState: StateFlow<DynamicIconState> = repository.dynamicIconState
    val validationHistory: StateFlow<List<ValidationResult>> = repository.validationHistory
    val rules: StateFlow<List<ValidationRule>> = repository.rules
    val pipelineMetrics: StateFlow<com.sumeravera.protocol.core.pipeline.PipelineMetrics> = repository.pipelineMetrics

    private val _isChainValid = MutableStateFlow(true)
    val isChainValid: StateFlow<Boolean> = _isChainValid.asStateFlow()

    private val _userFeedbackMessage = MutableStateFlow<String?>(null)
    val userFeedbackMessage: StateFlow<String?> = _userFeedbackMessage.asStateFlow()

    init {
        checkChainIntegrity()
    }

    fun checkChainIntegrity() {
        _isChainValid.value = repository.verifyChainIntegrity()
    }

    fun clearFeedback() {
        _userFeedbackMessage.value = null
    }

    fun showMessage(msg: String) {
        _userFeedbackMessage.value = msg
    }

    fun tamperChainForDemo() {
        val success = repository.tamperChainForDemo()
        checkChainIntegrity()
        if (success) {
            _userFeedbackMessage.value = "Tamper injected into block! Chain verification will now detect cryptographic corruption."
        }
    }

    fun repairChain() {
        repository.recalculateAndRepairChain()
        checkChainIntegrity()
        _userFeedbackMessage.value = "Cryptographic chain repaired and re-hashed."
    }

    fun addInvariant(
        priority: String,
        category: String,
        key: String,
        value: String,
        immutable: Boolean
    ) {
        val (success, message) = repository.addInvariant(priority, category, key, value, immutable)
        checkChainIntegrity()
        _userFeedbackMessage.value = message
    }

    fun validatePayload(
        source: String,
        timestamp: Long?,
        category: String,
        rawJsonData: String
    ): ValidationResult {
        val result = repository.validatePayload(source, timestamp, category, rawJsonData)
        checkChainIntegrity()
        _userFeedbackMessage.value = if (result.valid) {
            "Payload validated & anchored into SumerA ledger (Seq #${repository.ledgerEntries.value.lastOrNull()?.seq})"
        } else {
            "Validation rejected: ${result.failures.firstOrNull()?.description ?: "Invalid"}"
        }
        return result
    }

    fun enqueueSignal(
        source: String,
        timestamp: Long,
        category: String,
        rawJsonData: String
    ) {
        repository.enqueueSignalForVerification(source, timestamp, category, rawJsonData) { result ->
            checkChainIntegrity()
            _userFeedbackMessage.value = if (result.valid) {
                "Pipeline batch verified: ${result.payloadHash.take(12)}... (0 GC allocated)"
            } else {
                "Pipeline batch rejected: ${result.failures.firstOrNull()?.description}"
            }
        }
    }

    fun recordProbe(
        ip: String,
        method: String,
        path: String
    ): Pair<ThreatEvent, String> {
        val (event, decoy) = repository.recordProbe(ip, method, path)
        checkChainIntegrity()
        _userFeedbackMessage.value = "Perimeter probe detected (${event.severity.uppercase()}) from $ip: ${if (event.blocked) "IP Blocked" else "Decoy Served"}"
        return Pair(event, decoy)
    }

    fun toggleBlockIp(ip: String) {
        repository.toggleBlockIp(ip)
    }

    fun registerPawsNode(
        species: String,
        markingHash: String,
        chipIdentifier: String?,
        stewardSignature: String,
        immutable: Boolean
    ): Boolean {
        val (ok, node) = repository.registerPawsNode(species, markingHash, chipIdentifier, stewardSignature, immutable)
        checkChainIntegrity()
        if (ok && node != null) {
            _userFeedbackMessage.value = "Identity Node created for ${node.speciesClassification}: ${node.nodeId.take(12)}... Anchored to SumerA!"
            return true
        } else {
            _userFeedbackMessage.value = "Failed to register node. Check required fields or duplicate."
            return false
        }
    }

    fun verifyPawsSignature(nodeId: String, signature: String): Boolean {
        return repository.verifyPawsSignature(nodeId, signature)
    }
}
