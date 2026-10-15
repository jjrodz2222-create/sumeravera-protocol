package com.sumeravera.protocol.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import com.sumeravera.protocol.model.LedgerEntry
import com.sumeravera.protocol.model.StateInvariant
import com.sumeravera.protocol.ui.ProtocolViewModel
import com.sumeravera.protocol.ui.components.HashBadge
import com.sumeravera.protocol.ui.components.PriorityChip
import com.sumeravera.protocol.ui.theme.*

@Composable
fun SumeraLedgerScreen(viewModel: ProtocolViewModel) {
    var selectedTab by remember { mutableIntStateOf(0) } // 0: Chain Explorer, 1: Invariant Ledger
    var selectedCategoryFilter by remember { mutableStateOf("ALL") }
    var selectedEntryDetails by remember { mutableStateOf<LedgerEntry?>(null) }
    var showAddInvariantDialog by remember { mutableStateOf(false) }

    val ledgerEntries by viewModel.ledgerEntries.collectAsState()
    val invariants by viewModel.invariants.collectAsState()
    val isChainValid by viewModel.isChainValid.collectAsState()

    val categories = listOf("ALL", "SIGNAL", "THREAT", "PAWS_IDENTITY", "INVARIANT", "SYSTEM")

    val filteredEntries = remember(ledgerEntries, selectedCategoryFilter) {
        if (selectedCategoryFilter == "ALL") {
            ledgerEntries.reversed()
        } else {
            ledgerEntries.filter { it.category == selectedCategoryFilter }.reversed()
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(BgDark)
            .padding(horizontal = 16.dp)
    ) {
        Spacer(modifier = Modifier.height(12.dp))

        // Top Status & Integrity Banner
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .border(
                    1.dp,
                    if (isChainValid) StatusGreen.copy(alpha = 0.4f) else StatusRed.copy(alpha = 0.4f),
                    RoundedCornerShape(12.dp)
                ),
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
                        Icon(
                            imageVector = if (isChainValid) Icons.Default.CheckCircle else Icons.Default.Error,
                            contentDescription = null,
                            tint = if (isChainValid) StatusGreen else StatusRed,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = if (isChainValid) "CHAIN INTEGRITY VERIFIED" else "CRYPTOGRAPHIC CORRUPTION DETECTED",
                            style = MaterialTheme.typography.titleMedium.copy(
                                color = if (isChainValid) StatusGreen else StatusRed,
                                fontWeight = FontWeight.Bold,
                                fontSize = 13.sp
                            )
                        )
                    }

                    Text(
                        text = "${ledgerEntries.size} BLOCKS",
                        style = MaterialTheme.typography.labelSmall.copy(color = TextMuted)
                    )
                }

                Spacer(modifier = Modifier.height(10.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedButton(
                        onClick = { viewModel.checkChainIntegrity() },
                        modifier = Modifier
                            .weight(1f)
                            .testTag("btn_verify_ledger_chain"),
                        shape = RoundedCornerShape(8.dp),
                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp)
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(14.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("Re-Verify", fontSize = 11.sp)
                    }

                    if (isChainValid) {
                        OutlinedButton(
                            onClick = { viewModel.tamperChainForDemo() },
                            modifier = Modifier
                                .weight(1f)
                                .testTag("btn_tamper_demo"),
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.outlinedButtonColors(contentColor = StatusYellow),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp)
                        ) {
                            Icon(Icons.Default.BugReport, contentDescription = null, modifier = Modifier.size(14.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Tamper Demo", fontSize = 11.sp)
                        }
                    } else {
                        Button(
                            onClick = { viewModel.repairChain() },
                            modifier = Modifier
                                .weight(1f)
                                .testTag("btn_repair_chain"),
                            shape = RoundedCornerShape(8.dp),
                            colors = ButtonDefaults.buttonColors(containerColor = StatusGreen),
                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 6.dp)
                        ) {
                            Icon(Icons.Default.Build, contentDescription = null, modifier = Modifier.size(14.dp))
                            Spacer(modifier = Modifier.width(4.dp))
                            Text("Repair Chain", fontSize = 11.sp)
                        }
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(12.dp))

        // Tab Selector
        TabRow(
            selectedTabIndex = selectedTab,
            containerColor = SurfaceDark,
            contentColor = PrimaryCyan,
            modifier = Modifier.clip(RoundedCornerShape(10.dp))
        ) {
            Tab(
                selected = selectedTab == 0,
                onClick = { selectedTab = 0 },
                text = { Text("Chain Explorer", fontWeight = FontWeight.Bold, fontSize = 13.sp) },
                modifier = Modifier.testTag("tab_chain_explorer")
            )
            Tab(
                selected = selectedTab == 1,
                onClick = { selectedTab = 1 },
                text = { Text("Invariants (L1)", fontWeight = FontWeight.Bold, fontSize = 13.sp) },
                modifier = Modifier.testTag("tab_invariants")
            )
        }

        Spacer(modifier = Modifier.height(12.dp))

        if (selectedTab == 0) {
            // Category filter chips
            LazyRow(
                horizontalArrangement = Arrangement.spacedBy(6.dp),
                modifier = Modifier.fillMaxWidth()
            ) {
                items(categories) { cat ->
                    val isSelected = selectedCategoryFilter == cat
                    FilterChip(
                        selected = isSelected,
                        onClick = { selectedCategoryFilter = cat },
                        label = { Text(cat, fontSize = 11.sp) },
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = PrimaryCyan.copy(alpha = 0.2f),
                            selectedLabelColor = PrimaryCyan
                        )
                    )
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            // Blockchain entries list
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(bottom = 24.dp)
            ) {
                items(filteredEntries, key = { it.entryId }) { entry ->
                    LedgerEntryCard(
                        entry = entry,
                        onClick = { selectedEntryDetails = entry }
                    )
                }
            }
        } else {
            // Layer 1 Invariant Ledger Tab
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "LOCAL INVARIANT LEDGER",
                    style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold)
                )

                Button(
                    onClick = { showAddInvariantDialog = true },
                    shape = RoundedCornerShape(8.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = PrimaryCyan),
                    contentPadding = PaddingValues(horizontal = 10.dp, vertical = 6.dp),
                    modifier = Modifier.testTag("btn_add_invariant")
                ) {
                    Icon(Icons.Default.Add, contentDescription = null, tint = BgDark, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("New Invariant", color = BgDark, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }

            Spacer(modifier = Modifier.height(10.dp))

            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(bottom = 24.dp)
            ) {
                items(invariants, key = { it.id }) { inv ->
                    InvariantCard(inv)
                }
            }
        }
    }

    // Block Details Dialog
    selectedEntryDetails?.let { entry ->
        AlertDialog(
            onDismissRequest = { selectedEntryDetails = null },
            confirmButton = {
                TextButton(onClick = { selectedEntryDetails = null }) {
                    Text("Close", color = PrimaryCyan)
                }
            },
            title = {
                Text("Block #${entry.seq} - ${entry.category}", fontWeight = FontWeight.Bold)
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Entry ID: ${entry.entryId}", style = MaterialTheme.typography.labelSmall.copy(fontFamily = FontFamily.Monospace))
                    Text("Timestamp: ${entry.timestamp}", style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary))
                    HashBadge(hash = entry.payloadHash, label = "PAYLOAD")
                    HashBadge(hash = entry.prevHash, label = "PREV")
                    HashBadge(hash = entry.chainHash, label = "CHAIN")

                    Spacer(modifier = Modifier.height(6.dp))
                    Text("Payload Data:", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .background(SurfaceDark)
                            .padding(10.dp)
                    ) {
                        Text(
                            text = entry.payload,
                            style = MaterialTheme.typography.labelSmall.copy(
                                fontFamily = FontFamily.Monospace,
                                color = TextPrimary,
                                fontSize = 11.sp
                            )
                        )
                    }
                }
            },
            containerColor = SurfaceCard
        )
    }

    // Add Invariant Dialog
    if (showAddInvariantDialog) {
        AddInvariantDialog(
            onDismiss = { showAddInvariantDialog = false },
            onAdd = { priority, category, key, value, immutable ->
                viewModel.addInvariant(priority, category, key, value, immutable)
                showAddInvariantDialog = false
            }
        )
    }
}

@Composable
fun LedgerEntryCard(
    entry: LedgerEntry,
    onClick: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .border(1.dp, SurfaceCardBorder, RoundedCornerShape(12.dp))
            .testTag("ledger_block_${entry.seq}"),
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
                            .background(PrimaryCyan.copy(alpha = 0.15f))
                            .padding(horizontal = 8.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "SEQ #${entry.seq}",
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = PrimaryCyan,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                        )
                    }
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = entry.category,
                        style = MaterialTheme.typography.bodyMedium.copy(
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )
                    )
                }

                Text(
                    text = entry.timestamp.take(19).replace("T", " "),
                    style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontSize = 10.sp)
                )
            }

            Spacer(modifier = Modifier.height(10.dp))
            HashBadge(hash = entry.chainHash, label = "CHAIN")

            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = entry.payload,
                style = MaterialTheme.typography.bodyMedium.copy(
                    color = TextSecondary,
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace
                ),
                maxLines = 2
            )
        }
    }
}

@Composable
fun InvariantCard(inv: StateInvariant) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, SurfaceCardBorder, RoundedCornerShape(12.dp))
            .testTag("invariant_${inv.id}"),
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
                    PriorityChip(priority = inv.priority)
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = inv.id,
                        style = MaterialTheme.typography.labelSmall.copy(
                            color = PrimaryCyan,
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace
                        )
                    )
                    Spacer(modifier = Modifier.width(6.dp))
                    Text(
                        text = inv.category,
                        style = MaterialTheme.typography.labelSmall.copy(color = TextMuted)
                    )
                }

                if (inv.immutable) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(InvariantGold.copy(alpha = 0.2f))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = "IMMUTABLE",
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = InvariantGold,
                                fontWeight = FontWeight.Bold,
                                fontSize = 9.sp
                            )
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = inv.key,
                style = MaterialTheme.typography.titleMedium.copy(
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold,
                    fontFamily = FontFamily.Monospace,
                    fontSize = 14.sp
                )
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = inv.value,
                style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary, fontSize = 13.sp)
            )
        }
    }
}

@Composable
fun AddInvariantDialog(
    onDismiss: () -> Unit,
    onAdd: (priority: String, category: String, key: String, value: String, immutable: Boolean) -> Unit
) {
    var priority by remember { mutableStateOf("P0") }
    var category by remember { mutableStateOf("DIRECTIVE") }
    var key by remember { mutableStateOf("") }
    var value by remember { mutableStateOf("") }
    var immutable by remember { mutableStateOf(true) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Anchor New State Invariant", fontWeight = FontWeight.Bold) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(
                    value = key,
                    onValueChange = { key = it },
                    label = { Text("Invariant Key") },
                    placeholder = { Text("e.g., terminology_rules") },
                    modifier = Modifier.fillMaxWidth().testTag("input_inv_key"),
                    singleLine = true
                )

                OutlinedTextField(
                    value = value,
                    onValueChange = { value = it },
                    label = { Text("Directive Value") },
                    placeholder = { Text("e.g., Ground-truth specification text") },
                    modifier = Modifier.fillMaxWidth().testTag("input_inv_value"),
                    minLines = 2
                )

                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedTextField(
                        value = priority,
                        onValueChange = { priority = it },
                        label = { Text("Priority") },
                        modifier = Modifier.weight(1f)
                    )
                    OutlinedTextField(
                        value = category,
                        onValueChange = { category = it },
                        label = { Text("Category") },
                        modifier = Modifier.weight(1f)
                    )
                }

                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(
                        checked = immutable,
                        onCheckedChange = { immutable = it }
                    )
                    Text("Immutable (Cannot be overwritten)", fontSize = 12.sp, color = TextPrimary)
                }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    if (key.isNotBlank() && value.isNotBlank()) {
                        onAdd(priority, category, key, value, immutable)
                    }
                },
                colors = ButtonDefaults.buttonColors(containerColor = PrimaryCyan),
                modifier = Modifier.testTag("btn_submit_invariant")
            ) {
                Text("Anchor to SumerA", color = BgDark, fontWeight = FontWeight.Bold)
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
