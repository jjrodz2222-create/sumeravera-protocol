package com.sumeravera.protocol.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sumeravera.protocol.model.PawsIdentityNode
import com.sumeravera.protocol.ui.ProtocolViewModel
import com.sumeravera.protocol.ui.components.HashBadge
import com.sumeravera.protocol.ui.theme.*
import java.util.*

@Composable
fun PawsConnectScreen(viewModel: ProtocolViewModel) {
    var selectedSpeciesFilter by remember { mutableStateOf("ALL") }
    var showRegisterDialog by remember { mutableStateOf(false) }
    var verifyingNode by remember { mutableStateOf<PawsIdentityNode?>(null) }

    val pawsNodes by viewModel.pawsNodes.collectAsState()

    val speciesFilters = listOf("ALL", "CANINE", "FELINE", "EQUINE", "AVIAN")

    val filteredNodes = remember(pawsNodes, selectedSpeciesFilter) {
        if (selectedSpeciesFilter == "ALL") {
            pawsNodes
        } else {
            pawsNodes.filter { it.speciesClassification.equals(selectedSpeciesFilter, ignoreCase = true) }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BgDark)
            .padding(horizontal = 16.dp)
    ) {
        Spacer(modifier = Modifier.height(12.dp))

        // Header Card
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .border(1.dp, SecondaryBlue.copy(alpha = 0.3f), RoundedCornerShape(14.dp)),
            colors = CardDefaults.cardColors(containerColor = SurfaceCard),
            shape = RoundedCornerShape(14.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.Pets, contentDescription = null, tint = SecondaryBlue, modifier = Modifier.size(22.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Paws Connect Identity Network",
                            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
                        )
                    }

                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(SecondaryBlue.copy(alpha = 0.2f))
                            .padding(horizontal = 8.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "${pawsNodes.size} NODES",
                            style = MaterialTheme.typography.labelSmall.copy(color = SecondaryBlue, fontWeight = FontWeight.Bold)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(6.dp))
                Text(
                    text = "Species-agnostic biometric and identity node protocol. Generates deterministic node IDs and validates steward signatures with immutable SumerA ledger anchoring.",
                    style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary, fontSize = 12.sp)
                )

                Spacer(modifier = Modifier.height(12.dp))
                Button(
                    onClick = { showRegisterDialog = true },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testTag("btn_register_paws_node"),
                    colors = ButtonDefaults.buttonColors(containerColor = SecondaryBlue),
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Icon(Icons.Default.Add, contentDescription = null, tint = BgDark, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Register Biometric Identity Node", color = BgDark, fontWeight = FontWeight.Bold)
                }
            }
        }

        Spacer(modifier = Modifier.height(14.dp))

        // Species Filter Chips
        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(6.dp),
            modifier = Modifier.fillMaxWidth()
        ) {
            items(speciesFilters) { sp ->
                val isSelected = selectedSpeciesFilter == sp
                FilterChip(
                    selected = isSelected,
                    onClick = { selectedSpeciesFilter = sp },
                    label = { Text(sp, fontSize = 11.sp) },
                    colors = FilterChipDefaults.filterChipColors(
                        selectedContainerColor = SecondaryBlue.copy(alpha = 0.2f),
                        selectedLabelColor = SecondaryBlue
                    )
                )
            }
        }

        Spacer(modifier = Modifier.height(10.dp))

        // Identity Nodes List
        LazyColumn(
            verticalArrangement = Arrangement.spacedBy(10.dp),
            contentPadding = PaddingValues(bottom = 24.dp)
        ) {
            items(filteredNodes, key = { it.nodeId }) { node ->
                PawsNodeCard(
                    node = node,
                    onVerifyClick = { verifyingNode = node }
                )
            }
        }
    }

    // Register Node Dialog
    if (showRegisterDialog) {
        RegisterPawsNodeDialog(
            onDismiss = { showRegisterDialog = false },
            onRegister = { species, markingHash, chipId, stewardSig, immutable ->
                val success = viewModel.registerPawsNode(species, markingHash, chipId, stewardSig, immutable)
                if (success) showRegisterDialog = false
            }
        )
    }

    // Verify Steward Signature Dialog
    verifyingNode?.let { node ->
        VerifyStewardSignatureDialog(
            node = node,
            onDismiss = { verifyingNode = null },
            onVerify = { signature ->
                viewModel.verifyPawsSignature(node.nodeId, signature)
            }
        )
    }
}

@Composable
fun PawsNodeCard(
    node: PawsIdentityNode,
    onVerifyClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, SurfaceCardBorder, RoundedCornerShape(12.dp))
            .testTag("paws_node_${node.nodeId.take(8)}"),
        colors = CardDefaults.cardColors(containerColor = SurfaceCard),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(SecondaryBlue.copy(alpha = 0.15f))
                            .padding(horizontal = 8.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = node.speciesClassification.uppercase(),
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = SecondaryBlue,
                                fontWeight = FontWeight.Bold
                            )
                        )
                    }
                    if (node.immutableLedgerRecord) {
                        Spacer(modifier = Modifier.width(6.dp))
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(PrimaryCyan.copy(alpha = 0.15f))
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Text("SumerA Anchored", color = PrimaryCyan, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }

                Text(
                    text = node.createdAt.take(10),
                    style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontSize = 10.sp)
                )
            }

            Spacer(modifier = Modifier.height(10.dp))
            HashBadge(hash = node.nodeId, label = "NODE ID")

            Spacer(modifier = Modifier.height(6.dp))
            HashBadge(hash = node.biometricMarkers.primaryMarkingHash, label = "BIOMETRIC")

            node.biometricMarkers.chipIdentifier?.let { chip ->
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = "Microchip ID: $chip",
                    style = MaterialTheme.typography.labelSmall.copy(
                        color = TextSecondary,
                        fontFamily = FontFamily.Monospace,
                        fontSize = 11.sp
                    )
                )
            }

            Spacer(modifier = Modifier.height(6.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Steward: ${node.stewardSignature.take(18)}...",
                    style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontFamily = FontFamily.Monospace)
                )

                OutlinedButton(
                    onClick = onVerifyClick,
                    shape = RoundedCornerShape(6.dp),
                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 2.dp),
                    modifier = Modifier.testTag("btn_verify_steward_${node.nodeId.take(8)}")
                ) {
                    Icon(Icons.Default.VerifiedUser, contentDescription = null, modifier = Modifier.size(12.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Verify Sig", fontSize = 10.sp)
                }
            }
        }
    }
}

@Composable
fun RegisterPawsNodeDialog(
    onDismiss: () -> Unit,
    onRegister: (species: String, markingHash: String, chipId: String?, stewardSig: String, immutable: Boolean) -> Unit
) {
    var species by remember { mutableStateOf("Canine") }
    var markingHash by remember { mutableStateOf(UUID.randomUUID().toString().replace("-", "").take(16)) }
    var chipId by remember { mutableStateOf("98514100" + (100000..999999).random()) }
    var stewardSig by remember { mutableStateOf("secp256k1_steward_" + (1000..9999).random()) }
    var immutable by remember { mutableStateOf(true) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Register Identity Node", fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = species,
                    onValueChange = { species = it },
                    label = { Text("Species Classification") },
                    modifier = Modifier.fillMaxWidth().testTag("input_paws_species"),
                    singleLine = true
                )

                OutlinedTextField(
                    value = markingHash,
                    onValueChange = { markingHash = it },
                    label = { Text("Primary Biometric Marking Hash") },
                    modifier = Modifier.fillMaxWidth().testTag("input_paws_marking"),
                    singleLine = true
                )

                OutlinedTextField(
                    value = chipId,
                    onValueChange = { chipId = it },
                    label = { Text("Microchip Identifier (Optional)") },
                    modifier = Modifier.fillMaxWidth().testTag("input_paws_chip"),
                    singleLine = true
                )

                OutlinedTextField(
                    value = stewardSig,
                    onValueChange = { stewardSig = it },
                    label = { Text("Steward Public Key Signature") },
                    modifier = Modifier.fillMaxWidth().testTag("input_paws_signature"),
                    singleLine = true
                )

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = immutable,
                        onCheckedChange = { immutable = it }
                    )
                    Text("Anchor to SumerA Ledger", fontSize = 12.sp, color = TextPrimary)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onRegister(species, markingHash, chipId, stewardSig, immutable)
                },
                colors = ButtonDefaults.buttonColors(containerColor = SecondaryBlue),
                modifier = Modifier.testTag("btn_submit_paws_node")
            ) {
                Text("Register & Anchor", color = BgDark, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel", color = TextSecondary)
            }
        },
        containerColor = SurfaceCard
    )
}

@Composable
fun VerifyStewardSignatureDialog(
    node: PawsIdentityNode,
    onDismiss: () -> Unit,
    onVerify: (signature: String) -> Boolean
) {
    var testSignature by remember { mutableStateOf(node.stewardSignature) }
    var verificationResult by remember { mutableStateOf<Boolean?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Verify Steward Signature", fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Node ID: ${node.nodeId.take(16)}...", style = MaterialTheme.typography.labelSmall.copy(fontFamily = FontFamily.Monospace))
                Text("Species: ${node.speciesClassification.uppercase()}", style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary))

                OutlinedTextField(
                    value = testSignature,
                    onValueChange = { testSignature = it },
                    label = { Text("Steward Signature to Verify") },
                    modifier = Modifier.fillMaxWidth().testTag("input_test_sig"),
                    singleLine = true
                )

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    OutlinedButton(
                        onClick = { testSignature = node.stewardSignature },
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Valid Sig", fontSize = 10.sp)
                    }
                    OutlinedButton(
                        onClick = { testSignature = "invalid_forged_signature_0000" },
                        modifier = Modifier.weight(1f)
                    ) {
                        Text("Forged Sig", fontSize = 10.sp)
                    }
                }

                verificationResult?.let { isValid ->
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .border(
                                1.dp,
                                if (isValid) StatusGreen else StatusRed,
                                RoundedCornerShape(8.dp)
                            ),
                        colors = CardDefaults.cardColors(
                            containerColor = if (isValid) StatusGreen.copy(alpha = 0.15f) else StatusRed.copy(alpha = 0.15f)
                        )
                    ) {
                        Row(
                            modifier = Modifier.padding(10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                imageVector = if (isValid) Icons.Default.CheckCircle else Icons.Default.Cancel,
                                contentDescription = null,
                                tint = if (isValid) StatusGreen else StatusRed,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = if (isValid) "SIGNATURE MATCH - VERIFIED" else "SIGNATURE MISMATCH - REJECTED",
                                color = if (isValid) StatusGreen else StatusRed,
                                fontWeight = FontWeight.Bold,
                                fontSize = 11.sp
                            )
                        }
                    }
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    verificationResult = onVerify(testSignature)
                },
                colors = ButtonDefaults.buttonColors(containerColor = SecondaryBlue),
                modifier = Modifier.testTag("btn_run_sig_verify")
            ) {
                Text("Verify Against Node", color = BgDark, fontWeight = FontWeight.Bold)
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Close", color = TextSecondary)
            }
        },
        containerColor = SurfaceCard
    )
}
