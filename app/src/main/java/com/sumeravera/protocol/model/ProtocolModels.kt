package com.sumeravera.protocol.model

import kotlinx.serialization.Serializable

@Serializable
data class LedgerEntry(
    val seq: Long,
    val entryId: String,
    val timestamp: String,
    val category: String, // SIGNAL, THREAT, PAWS_IDENTITY, INVARIANT, SYSTEM
    val payloadHash: String,
    val payload: String,
    val prevHash: String,
    val chainHash: String
)

@Serializable
data class StateInvariant(
    val id: String,
    val timestamp: String,
    val priority: String, // P0, P1, P2
    val category: String, // DIRECTIVE, CORRECTION, PROJECT_SPEC, SYSTEM
    val key: String,
    val value: String,
    val immutable: Boolean
)

@Serializable
data class ValidationRule(
    val id: String,
    val description: String,
    val isSystemRule: Boolean = true
)

@Serializable
data class ValidationRuleFailure(
    val id: String,
    val description: String
)

@Serializable
data class ValidationResult(
    val valid: Boolean,
    val payloadHash: String,
    val reason: String? = null,
    val failures: List<ValidationRuleFailure> = emptyList(),
    val ledgerEntryId: String? = null,
    val invariantConflicts: List<String> = emptyList()
)

@Serializable
data class ThreatEvent(
    val id: String,
    val ip: String,
    val timestamp: String,
    val method: String,
    val path: String,
    val fingerprint: String,
    val severity: String, // critical, warning, info
    val headers: Map<String, String> = emptyMap(),
    val body: String? = null,
    val blocked: Boolean = false
)

@Serializable
data class BiometricMarkers(
    val primaryMarkingHash: String,
    val chipIdentifier: String? = null
)

@Serializable
data class PawsIdentityNode(
    val nodeId: String,
    val speciesClassification: String,
    val biometricMarkers: BiometricMarkers,
    val stewardSignature: String,
    val immutableLedgerRecord: Boolean = true,
    val createdAt: String,
    val ledgerEntryId: String? = null
)

@Serializable
data class DynamicIconState(
    val appId: String = "com.aistudio.sumeravera.svpnet",
    val activeStateAlias: String = "icon_default",
    val severity: String = "info", // info, warning, critical, action_required
    val showIndicator: Boolean = false,
    val overlayIconRef: String = "shield_normal",
    val primaryColorHex: String = "#00F5D4"
)

data class ProtocolMetrics(
    val totalLedgerEntries: Int,
    val isChainValid: Boolean,
    val totalValidations: Int,
    val acceptedValidations: Int,
    val rejectedValidations: Int,
    val threatsCaptured: Int,
    val blocklistSize: Int,
    val registeredPawsNodes: Int
)
