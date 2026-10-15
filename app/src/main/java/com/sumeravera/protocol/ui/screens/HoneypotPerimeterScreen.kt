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
import com.sumeravera.protocol.model.ThreatEvent
import com.sumeravera.protocol.ui.ProtocolViewModel
import com.sumeravera.protocol.ui.components.HashBadge
import com.sumeravera.protocol.ui.components.SeverityChip
import com.sumeravera.protocol.ui.theme.*

@Composable
fun HoneypotPerimeterScreen(viewModel: ProtocolViewModel) {
    var probeIp by remember { mutableStateOf("198.51.100.99") }
    var probeMethod by remember { mutableStateOf("GET") }
    var probePath by remember { mutableStateOf("/admin/config.env") }
    var lastDecoyResponse by remember { mutableStateOf<String?>(null) }
    var selectedSeverityFilter by remember { mutableStateOf("ALL") }

    var showManualBlockDialog by remember { mutableStateOf(false) }

    val threatEvents by viewModel.threatEvents.collectAsState()
    val blocklist by viewModel.blocklist.collectAsState()

    val filteredThreats = remember(threatEvents, selectedSeverityFilter) {
        if (selectedSeverityFilter == "ALL") {
            threatEvents
        } else {
            threatEvents.filter { it.severity.equals(selectedSeverityFilter, ignoreCase = true) }
        }
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(BgDark)
            .padding(horizontal = 16.dp),
        contentPadding = PaddingValues(vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Perimeter Header Card
        item {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, StatusRed.copy(alpha = 0.3f), RoundedCornerShape(14.dp)),
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
                            Icon(Icons.Default.Shield, contentDescription = null, tint = StatusRed, modifier = Modifier.size(20.dp))
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = "Honeypot Action-Edge Perimeter",
                                style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.Bold)
                            )
                        }
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(6.dp))
                                .background(StatusRed.copy(alpha = 0.2f))
                                .padding(horizontal = 8.dp, vertical = 2.dp)
                        ) {
                            Text(
                                text = "${blocklist.size} BLOCKED IPS",
                                style = MaterialTheme.typography.labelSmall.copy(color = StatusRed, fontWeight = FontWeight.Bold)
                            )
                        }
                    }

                    Spacer(modifier = Modifier.height(6.dp))
                    Text(
                        text = "Low-interaction decoy surface. Inbound probes are fingerprinted, threat telemetry is logged to SumerA ledger, and malicious IPs are added to the dynamic firewall blocklist.",
                        style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary, fontSize = 12.sp)
                    )
                }
            }
        }

        // Decoy Simulator Tool
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
                        text = "ACTION-EDGE DECOY PROBE SIMULATOR",
                        style = MaterialTheme.typography.labelSmall.copy(color = PrimaryCyan, fontWeight = FontWeight.Bold)
                    )

                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(
                            value = probeIp,
                            onValueChange = { probeIp = it },
                            label = { Text("Attacker IP") },
                            modifier = Modifier.weight(1.2f).testTag("input_probe_ip"),
                            singleLine = true
                        )
                        OutlinedTextField(
                            value = probeMethod,
                            onValueChange = { probeMethod = it },
                            label = { Text("Method") },
                            modifier = Modifier.weight(0.8f).testTag("input_probe_method"),
                            singleLine = true
                        )
                    }

                    OutlinedTextField(
                        value = probePath,
                        onValueChange = { probePath = it },
                        label = { Text("Probe Path (Triggers dynamic severity)") },
                        modifier = Modifier.fillMaxWidth().testTag("input_probe_path"),
                        singleLine = true
                    )

                    // Quick probe targets
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        OutlinedButton(
                            onClick = {
                                probeIp = "203.0.113.${(2..250).random()}"
                                probePath = "/.env"
                            },
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 4.dp)
                        ) {
                            Text("/.env (Crit)", fontSize = 10.sp, color = StatusRed)
                        }

                        OutlinedButton(
                            onClick = {
                                probeIp = "198.51.100.${(2..250).random()}"
                                probePath = "/wp-login.php"
                            },
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 4.dp)
                        ) {
                            Text("wp-login (Crit)", fontSize = 10.sp, color = StatusRed)
                        }

                        OutlinedButton(
                            onClick = {
                                probeIp = "192.168.1.55"
                                probePath = "/api/v2/auth"
                            },
                            modifier = Modifier.weight(1f),
                            contentPadding = PaddingValues(horizontal = 4.dp, vertical = 4.dp)
                        ) {
                            Text("api/auth (Warn)", fontSize = 10.sp, color = StatusYellow)
                        }
                    }

                    Button(
                        onClick = {
                            val (_, decoy) = viewModel.recordProbe(probeIp, probeMethod, probePath)
                            lastDecoyResponse = decoy
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .testTag("btn_send_probe"),
                        colors = ButtonDefaults.buttonColors(containerColor = StatusRed),
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Icon(Icons.Default.Radar, contentDescription = null, tint = TextPrimary, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Send Probe & Intercept with Decoy", color = TextPrimary, fontWeight = FontWeight.Bold)
                    }

                    // Decoy Response Box
                    lastDecoyResponse?.let { resp ->
                        Spacer(modifier = Modifier.height(4.dp))
                        Text("Decoy Trap Response (Attacker sees fake PHP service):", fontSize = 11.sp, color = TextMuted)
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .clip(RoundedCornerShape(8.dp))
                                .background(SurfaceDark)
                                .padding(10.dp)
                        ) {
                            Text(
                                text = resp,
                                style = MaterialTheme.typography.labelSmall.copy(
                                    fontFamily = FontFamily.Monospace,
                                    color = PrimaryCyan,
                                    fontSize = 10.sp
                                )
                            )
                        }
                    }
                }
            }
        }

        // Active Firewall Blocklist
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "DYNAMIC FIREWALL BLOCKLIST (${blocklist.size})",
                    style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold)
                )

                TextButton(
                    onClick = { showManualBlockDialog = true },
                    modifier = Modifier.testTag("btn_open_block_ip")
                ) {
                    Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("Block IP", fontSize = 12.sp)
                }
            }

            if (blocklist.isEmpty()) {
                Text("No active firewall blocks.", style = MaterialTheme.typography.bodyMedium.copy(color = TextMuted))
            } else {
                LazyRow(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    items(blocklist.toList()) { ip ->
                        Row(
                            modifier = Modifier
                                .clip(RoundedCornerShape(8.dp))
                                .background(SurfaceDark)
                                .border(1.dp, StatusRed.copy(alpha = 0.5f), RoundedCornerShape(8.dp))
                                .padding(horizontal = 10.dp, vertical = 6.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = ip,
                                style = MaterialTheme.typography.labelSmall.copy(
                                    color = TextPrimary,
                                    fontFamily = FontFamily.Monospace
                                )
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Icon(
                                imageVector = Icons.Default.Close,
                                contentDescription = "Unblock",
                                tint = StatusRed,
                                modifier = Modifier
                                    .size(14.dp)
                                    .clickable { viewModel.toggleBlockIp(ip) }
                            )
                        }
                    }
                }
            }
        }

        // Threat Telemetry Feed
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "THREAT TELEMETRY FEED (${filteredThreats.size})",
                    style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontWeight = FontWeight.Bold)
                )

                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    listOf("ALL", "CRITICAL", "WARNING", "INFO").forEach { sev ->
                        FilterChip(
                            selected = selectedSeverityFilter == sev,
                            onClick = { selectedSeverityFilter = sev },
                            label = { Text(sev, fontSize = 9.sp) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = StatusRed.copy(alpha = 0.2f),
                                selectedLabelColor = StatusRed
                            )
                        )
                    }
                }
            }
        }

        items(filteredThreats, key = { it.id }) { threat ->
            ThreatEventCard(threat = threat, onToggleBlock = { viewModel.toggleBlockIp(threat.ip) })
        }
    }

    // Manual Block IP Dialog
    if (showManualBlockDialog) {
        var ipInput by remember { mutableStateOf("") }
        AlertDialog(
            onDismissRequest = { showManualBlockDialog = false },
            title = { Text("Add IP to Firewall Blocklist", fontWeight = FontWeight.Bold) },
            text = {
                OutlinedTextField(
                    value = ipInput,
                    onValueChange = { ipInput = it },
                    label = { Text("IP Address") },
                    placeholder = { Text("e.g., 203.0.113.88") },
                    modifier = Modifier.fillMaxWidth().testTag("input_manual_ip"),
                    singleLine = true
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        if (ipInput.isNotBlank()) {
                            viewModel.toggleBlockIp(ipInput.trim())
                            showManualBlockDialog = false
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = StatusRed)
                ) {
                    Text("Add to Blocklist", color = TextPrimary)
                }
            },
            dismissButton = {
                TextButton(onClick = { showManualBlockDialog = false }) {
                    Text("Cancel", color = TextSecondary)
                }
            },
            containerColor = SurfaceCard
        )
    }
}

@Composable
fun ThreatEventCard(
    threat: ThreatEvent,
    onToggleBlock: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .border(1.dp, SurfaceCardBorder, RoundedCornerShape(10.dp))
            .testTag("threat_event_${threat.id}"),
        colors = CardDefaults.cardColors(containerColor = SurfaceCard),
        shape = RoundedCornerShape(10.dp)
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    SeverityChip(severity = threat.severity)
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "${threat.method} ${threat.path}",
                        style = MaterialTheme.typography.bodyMedium.copy(
                            fontWeight = FontWeight.Bold,
                            fontFamily = FontFamily.Monospace,
                            color = TextPrimary
                        )
                    )
                }

                if (threat.blocked) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(StatusRed.copy(alpha = 0.2f))
                            .padding(horizontal = 6.dp, vertical = 2.dp)
                    ) {
                        Text("BLOCKED", color = StatusRed, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    }
                }
            }

            Spacer(modifier = Modifier.height(6.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Source IP: ${threat.ip}",
                    style = MaterialTheme.typography.labelSmall.copy(color = TextSecondary, fontFamily = FontFamily.Monospace)
                )
                Text(
                    text = threat.timestamp.take(19).replace("T", " "),
                    style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontSize = 10.sp)
                )
            }

            Spacer(modifier = Modifier.height(6.dp))
            HashBadge(hash = threat.fingerprint, label = "FINGERPRINT")
        }
    }
}
