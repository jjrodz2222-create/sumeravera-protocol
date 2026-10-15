package com.sumeravera.protocol.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
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
import com.sumeravera.protocol.model.ValidationResult
import com.sumeravera.protocol.ui.ProtocolViewModel
import com.sumeravera.protocol.ui.components.HashBadge
import com.sumeravera.protocol.ui.theme.*

@Composable
fun AveraEngineScreen(viewModel: ProtocolViewModel) {
    var source by remember { mutableStateOf("avera-telemetry-agent") }
    var category by remember { mutableStateOf("SIGNAL") }
    var payloadJson by remember {
        mutableStateOf("{\n  \"source\": \"avera-telemetry-agent\",\n  \"timestamp\": 1729001234,\n  \"node_status\": \"active\",\n  \"ground_truth_score\": 0.994\n}")
    }
    var latestResult by remember { mutableStateOf<ValidationResult?>(null) }

    val rules by viewModel.rules.collectAsState()
    val validationHistory by viewModel.validationHistory.collectAsState()
    val pipelineMetrics by viewModel.pipelineMetrics.collectAsState()

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(BgDark)
            .padding(horizontal = 16.dp),
        contentPadding = PaddingValues(vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Overview card
        item {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, StatusGreen.copy(alpha = 0.3f), RoundedCornerShape(14.dp)),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(14.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Default.CheckCircle, contentDescription = null, tint = StatusGreen, modifier = Modifier.size(20.dp))
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Avera Ground-Truth Engine",
                            style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
                        )
                    }
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Cross-references signals against cryptographic origins and Layer 1 invariants to eliminate hallucination before ledger commit.",
                        style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary, fontSize = 12.sp)
                    )
                }
            }
        }

        // Edge Worker Pipeline Telemetry
        item {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, PrimaryCyan.copy(alpha = 0.3f), RoundedCornerShape(14.dp)),
                colors = CardDefaults.cardColors(containerColor = SurfaceDark),
                shape = RoundedCornerShape(14.dp)
            ) {
                Column(modifier = Modifier.padding(14.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.Bolt, contentDescription = null, tint = PrimaryCyan, modifier = Modifier.size(18.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "EDGE PIPELINE (LOW-POWER COALESCING)",
                                style = MaterialTheme.typography.labelSmall.copy(color = PrimaryCyan, fontWeight = FontWeight.Bold)
                            )
                        }
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(if (pipelineMetrics.isRunning) StatusGreen.copy(alpha = 0.2f) else StatusYellow.copy(alpha = 0.2f))
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Text(
                                text = if (pipelineMetrics.isRunning) "ACTIVE COALESCING" else "IDLE SUSPEND",
                                color = if (pipelineMetrics.isRunning) StatusGreen else StatusYellow,
                                fontSize = 9.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(10.dp))
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Signals Processed", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontSize = 10.sp))
                            Text("${pipelineMetrics.processedSignals}", style = MaterialTheme.typography.titleMedium.copy(color = TextPrimary, fontWeight = FontWeight.Bold))
                        }
                        Column(modifier = Modifier.weight(1f)) {
                            Text("Batches Flushed", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontSize = 10.sp))
                            Text("${pipelineMetrics.batchesFlushed}", style = MaterialTheme.typography.titleMedium.copy(color = TextPrimary, fontWeight = FontWeight.Bold))
                        }
                        Column(modifier = Modifier.weight(1.2f)) {
                            Text("Envelopes Recycled", style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontSize = 10.sp))
                            Text("${pipelineMetrics.recycledEnvelopes} (0 GC)", style = MaterialTheme.typography.titleMedium.copy(color = HashGreen, fontWeight = FontWeight.Bold))
                        }
                    }
                }
            }
        }

        // Active Rules Catalog
        item {
            Text(
                text = "ACTIVE VALIDATION RULES",
                style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold)
            )
            Spacer(modifier = Modifier.height(6.dp))
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                rules.forEach { rule ->
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .background(SurfaceDark)
                            .border(1.dp, SurfaceCardBorder, RoundedCornerShape(8.dp))
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = rule.id,
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = PrimaryCyan,
                                fontWeight = FontWeight.Bold,
                                fontFamily = FontFamily.Monospace
                            )
                        )
                        Spacer(modifier = Modifier.width(10.dp))
                        Text(
                            text = rule.description,
                            style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary, fontSize = 12.sp)
                        )
                    }
                }
            }
        }

        // Interactive Validation Playground
        item {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, SurfaceCardBorder, RoundedCornerShape(14.dp)),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(14.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        text = "SIGNAL INGRESS VALIDATOR",
                        style = MaterialTheme.typography.labelSmall.copy(color = PrimaryCyan, fontWeight = FontWeight.Bold)
                    )

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(
                            value = source,
                            onValueChange = { source = it },
                            label = { Text("Source ID") },
                            modifier = Modifier.weight(1f).testTag("input_avera_source"),
                            singleLine = true
                        )
                        OutlinedTextField(
                            value = category,
                            onValueChange = { category = it },
                            label = { Text("Category") },
                            modifier = Modifier.weight(1f).testTag("input_avera_category"),
                            singleLine = true
                        )
                    }

                    OutlinedTextField(
                        value = payloadJson,
                        onValueChange = { payloadJson = it },
                        label = { Text("Payload JSON") },
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("input_avera_payload"),
                        minLines = 4,
                        textStyle = MaterialTheme.typography.bodyMedium.copy(fontFamily = FontFamily.Monospace)
                    )

                    // Quick Template Pre-sets
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        OutlinedButton(
                            onClick = {
                                source = "telemetry-probe-41"
                                category = "SIGNAL"
                                payloadJson = "{\n  \"source\": \"telemetry-probe-41\",\n  \"timestamp\": ${System.currentTimeMillis()},\n  \"metric\": 98.4\n}"
                            },
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 4.dp)
                        ) {
                            Text("Valid Signal", fontSize = 10.sp)
                        }

                        OutlinedButton(
                            onClick = {
                                source = "" // Missing source error
                                category = "SIGNAL"
                                payloadJson = "{\n  \"metric\": 102.1\n}"
                            },
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 4.dp)
                        ) {
                            Text("Rule-002 Fail", fontSize = 10.sp)
                        }

                        OutlinedButton(
                            onClick = {
                                source = "context-agent"
                                category = "SIGNAL"
                                // Contains "blinkers" forbidden by INV-002
                                payloadJson = "{\n  \"source\": \"context-agent\",\n  \"timestamp\": ${System.currentTimeMillis()},\n  \"observation\": \"Node operating with blinkers on\"\n}"
                            },
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 4.dp)
                        ) {
                            Text("Drift Test", fontSize = 10.sp)
                        }
                    }

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(
                            onClick = {
                                val result = viewModel.validatePayload(
                                    source = source,
                                    timestamp = System.currentTimeMillis(),
                                    category = category,
                                    rawJsonData = payloadJson
                                )
                                latestResult = result
                            },
                            modifier = Modifier
                                .weight(1f)
                                .testTag("btn_run_avera_validation"),
                            colors = ButtonDefaults.buttonColors(containerColor = PrimaryCyan),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Text("Direct Validate", color = BgDark, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        }

                        Button(
                            onClick = {
                                viewModel.enqueueSignal(
                                    source = source,
                                    timestamp = System.currentTimeMillis(),
                                    category = category,
                                    rawJsonData = payloadJson
                                )
                            },
                            modifier = Modifier
                                .weight(1f)
                                .testTag("btn_enqueue_pipeline"),
                            colors = ButtonDefaults.buttonColors(containerColor = SecondaryBlue),
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Text("Enqueue Pipeline", color = BgDark, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        }
                    }

                    // Result presentation
                    latestResult?.let { res ->
                        Spacer(modifier = Modifier.height(4.dp))
                        Card(
                            modifier = Modifier
                                .fillMaxWidth()
                                .border(
                                    1.dp,
                                    if (res.valid) StatusGreen.copy(alpha = 0.5f) else StatusRed.copy(alpha = 0.5f),
                                    RoundedCornerShape(8.dp)
                                ),
                            colors = CardDefaults.cardColors(
                                containerColor = if (res.valid) StatusGreen.copy(alpha = 0.1f) else StatusRed.copy(alpha = 0.1f)
                            )
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Row(
                                    modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text(
                                        text = if (res.valid) "GROUND-TRUTH ACCEPTED" else "VALIDATION REJECTED",
                                        fontWeight = FontWeight.Bold,
                                        color = if (res.valid) StatusGreen else StatusRed,
                                        fontSize = 12.sp
                                    )
                                    res.ledgerEntryId?.let { id ->
                                        Text(
                                            text = "Anchored: ${id.take(8)}...",
                                            style = MaterialTheme.typography.labelSmall.copy(color = TextMuted)
                                        )
                                    }
                                }

                                if (res.failures.isNotEmpty()) {
                                    Spacer(modifier = Modifier.height(6.dp))
                                    res.failures.forEach { f ->
                                        Text(
                                            text = "• [${f.id}] ${f.description}",
                                            color = StatusRed,
                                            fontSize = 11.sp
                                        )
                                    }
                                }

                                Spacer(modifier = Modifier.height(6.dp))
                                HashBadge(hash = res.payloadHash, label = "PAYLOAD SHA-256")
                            }
                        }
                    }
                }
            }
        }

        // Validation History Feed
        item {
            Text(
                text = "RECENT INGRESS AUDITS (${validationHistory.size})",
                style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold)
            )
            Spacer(modifier = Modifier.height(6.dp))
        }

        items(validationHistory) { audit ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, SurfaceCardBorder, RoundedCornerShape(10.dp)),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(10.dp)
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = if (audit.valid) Icons.Default.CheckCircle else Icons.Default.Cancel,
                                contentDescription = null,
                                tint = if (audit.valid) StatusGreen else StatusRed,
                                modifier = Modifier.size(16.dp)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = if (audit.valid) "Accepted" else "Rejected (${audit.failures.size} errors)",
                                fontWeight = FontWeight.Bold,
                                color = if (audit.valid) StatusGreen else StatusRed,
                                fontSize = 12.sp
                            )
                        }
                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = audit.payloadHash.take(24) + "...",
                            style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontFamily = FontFamily.Monospace)
                        )
                    }

                    audit.ledgerEntryId?.let {
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(PrimaryCyan.copy(alpha = 0.15f))
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Text("SumerA Block", color = PrimaryCyan, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}
