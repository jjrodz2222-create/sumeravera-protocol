package com.sumeravera.protocol.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sumeravera.protocol.ui.ProtocolViewModel
import com.sumeravera.protocol.ui.components.MetricCard
import com.sumeravera.protocol.ui.components.SeverityChip
import com.sumeravera.protocol.ui.theme.*

@Composable
fun DashboardScreen(
    viewModel: ProtocolViewModel,
    onNavigateToLedger: () -> Unit,
    onNavigateToAvera: () -> Unit,
    onNavigateToPerimeter: () -> Unit,
    onNavigateToPaws: () -> Unit
) {
    val ledgerEntries by viewModel.ledgerEntries.collectAsState()
    val isChainValid by viewModel.isChainValid.collectAsState()
    val threatEvents by viewModel.threatEvents.collectAsState()
    val blocklist by viewModel.blocklist.collectAsState()
    val pawsNodes by viewModel.pawsNodes.collectAsState()
    val dynamicIconState by viewModel.dynamicIconState.collectAsState()
    val validationHistory by viewModel.validationHistory.collectAsState()
    val invariants by viewModel.invariants.collectAsState()

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(BgDark)
            .padding(horizontal = 16.dp),
        contentPadding = PaddingValues(vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Hero Header & Protocol Status
        item {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .border(1.dp, PrimaryCyan.copy(alpha = 0.3f), RoundedCornerShape(16.dp)),
                colors = CardDefaults.cardColors(containerColor = SurfaceCard),
                shape = RoundedCornerShape(16.dp)
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                modifier = Modifier
                                    .size(10.dp)
                                    .clip(CircleShape)
                                    .background(if (isChainValid) StatusGreen else StatusRed)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = if (isChainValid) "CONSENSUS SYNCHRONIZED" else "CHAIN TAMPER DETECTED",
                                style = MaterialTheme.typography.labelSmall.copy(
                                    color = if (isChainValid) StatusGreen else StatusRed,
                                    fontWeight = FontWeight.Bold
                                )
                            )
                        }
                        SeverityChip(severity = dynamicIconState.severity)
                    }

                    Spacer(modifier = Modifier.height(10.dp))
                    Text(
                        text = "SumerAvera Protocol",
                        style = MaterialTheme.typography.headlineLarge.copy(
                            color = TextPrimary,
                            fontWeight = FontWeight.ExtraBold
                        )
                    )
                    Text(
                        text = "Intent-Driven Decentralized Computing & Ground-Truth Verification Engine",
                        style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary)
                    )

                    Spacer(modifier = Modifier.height(12.dp))
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(8.dp))
                            .background(SurfaceDark)
                            .padding(horizontal = 12.dp, vertical = 8.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Active State Alias:",
                            style = MaterialTheme.typography.labelSmall.copy(color = TextMuted)
                        )
                        Text(
                            text = dynamicIconState.activeStateAlias,
                            style = MaterialTheme.typography.labelSmall.copy(
                                color = PrimaryCyan,
                                fontFamily = FontFamily.Monospace,
                                fontWeight = FontWeight.Bold
                            )
                        )
                    }
                }
            }
        }

        // Live Telemetry Grid
        item {
            Text(
                text = "REAL-TIME TELEMETRY",
                style = MaterialTheme.typography.labelSmall.copy(
                    color = TextMuted,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.sp
                )
            )
            Spacer(modifier = Modifier.height(8.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MetricCard(
                    title = "Ledger Blocks",
                    value = "${ledgerEntries.size}",
                    subtitle = if (isChainValid) "All SHA-256 Valid" else "Integrity Error",
                    icon = Icons.Default.Layers,
                    accentColor = if (isChainValid) PrimaryCyan else StatusRed,
                    modifier = Modifier.weight(1f)
                )
                MetricCard(
                    title = "Invariants (L1)",
                    value = "${invariants.size}",
                    subtitle = "${invariants.count { it.immutable }} Immutable Rules",
                    icon = Icons.Default.Gavel,
                    accentColor = InvariantGold,
                    modifier = Modifier.weight(1f)
                )
            }

            Spacer(modifier = Modifier.height(10.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                MetricCard(
                    title = "Threat Probes",
                    value = "${threatEvents.size}",
                    subtitle = "${blocklist.size} Blocked IPs",
                    icon = Icons.Default.Security,
                    accentColor = if (threatEvents.any { it.severity == "critical" }) StatusRed else StatusYellow,
                    modifier = Modifier.weight(1f)
                )
                MetricCard(
                    title = "Paws Nodes",
                    value = "${pawsNodes.size}",
                    subtitle = "Anchored Species Nodes",
                    icon = Icons.Default.Pets,
                    accentColor = SecondaryBlue,
                    modifier = Modifier.weight(1f)
                )
            }
        }

        // Quick Actions Bar
        item {
            Text(
                text = "QUICK VERIFICATION CONTROLS",
                style = MaterialTheme.typography.labelSmall.copy(
                    color = TextMuted,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.sp
                )
            )
            Spacer(modifier = Modifier.height(8.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(
                    onClick = { viewModel.checkChainIntegrity() },
                    modifier = Modifier
                        .weight(1f)
                        .testTag("btn_verify_chain"),
                    colors = ButtonDefaults.buttonColors(containerColor = SurfaceCard),
                    shape = RoundedCornerShape(8.dp),
                    border = ButtonDefaults.outlinedButtonBorder.copy(brush = androidx.compose.ui.graphics.SolidColor(SurfaceCardBorder))
                ) {
                    Icon(Icons.Default.Verified, contentDescription = null, tint = PrimaryCyan, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Verify Chain", color = TextPrimary, fontSize = 12.sp)
                }

                Button(
                    onClick = {
                        viewModel.recordProbe(
                            ip = "192.0.2.${(10..250).random()}",
                            method = "GET",
                            path = "/admin/credentials.env"
                        )
                    },
                    modifier = Modifier
                        .weight(1f)
                        .testTag("btn_simulate_probe"),
                    colors = ButtonDefaults.buttonColors(containerColor = SurfaceCard),
                    shape = RoundedCornerShape(8.dp),
                    border = ButtonDefaults.outlinedButtonBorder.copy(brush = androidx.compose.ui.graphics.SolidColor(SurfaceCardBorder))
                ) {
                    Icon(Icons.Default.Warning, contentDescription = null, tint = StatusRed, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Simulate Probe", color = TextPrimary, fontSize = 12.sp)
                }
            }
        }

        // Architecture Pillars
        item {
            Text(
                text = "ARCHITECTURE PILLARS",
                style = MaterialTheme.typography.labelSmall.copy(
                    color = TextMuted,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 1.sp
                )
            )
            Spacer(modifier = Modifier.height(8.dp))

            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                PillarNavigationCard(
                    title = "SumerA Layer",
                    subtitle = "Append-only cryptographic consensus ledger and Layer 1 deterministic invariant store.",
                    icon = Icons.Default.AccountBalance,
                    accentColor = PrimaryCyan,
                    badgeText = "${ledgerEntries.size} Entries",
                    onClick = onNavigateToLedger,
                    testTag = "card_sumera_pillar"
                )

                PillarNavigationCard(
                    title = "Avera Validation Engine",
                    subtitle = "Empirical ground-truth verification gate. Eliminates hallucination and synthetic noise.",
                    icon = Icons.Default.CheckCircle,
                    accentColor = StatusGreen,
                    badgeText = "${validationHistory.size} Validated",
                    onClick = onNavigateToAvera,
                    testTag = "card_avera_pillar"
                )

                PillarNavigationCard(
                    title = "Honeypot Perimeter",
                    subtitle = "Containerized action-edge decoys. Inbound threat telemetry logging and dynamic blocklist.",
                    icon = Icons.Default.Shield,
                    accentColor = StatusRed,
                    badgeText = "${threatEvents.size} Telemetry",
                    onClick = onNavigateToPerimeter,
                    testTag = "card_perimeter_pillar"
                )

                PillarNavigationCard(
                    title = "Paws Connect Protocol",
                    subtitle = "Species-agnostic biometric identity nodes anchored into SumerA ledger with steward verification.",
                    icon = Icons.Default.Pets,
                    accentColor = SecondaryBlue,
                    badgeText = "${pawsNodes.size} Registered",
                    onClick = onNavigateToPaws,
                    testTag = "card_paws_pillar"
                )
            }
        }
    }
}

@Composable
fun PillarNavigationCard(
    title: String,
    subtitle: String,
    icon: ImageVector,
    accentColor: Color,
    badgeText: String,
    onClick: () -> Unit,
    testTag: String
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
            .border(1.dp, SurfaceCardBorder, RoundedCornerShape(12.dp))
            .testTag(testTag),
        colors = CardDefaults.cardColors(containerColor = SurfaceCard),
        shape = RoundedCornerShape(12.dp)
    ) {
        Row(
            modifier = Modifier
                .padding(14.dp)
                .fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                modifier = Modifier
                    .size(42.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(accentColor.copy(alpha = 0.15f))
                    .border(1.dp, accentColor.copy(alpha = 0.4f), RoundedCornerShape(10.dp)),
                contentAlignment = Alignment.Center
            ) {
                Icon(imageVector = icon, contentDescription = null, tint = accentColor, modifier = Modifier.size(24.dp))
            }

            Spacer(modifier = Modifier.width(14.dp))

            Column(modifier = Modifier.weight(1f)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleMedium.copy(
                            color = TextPrimary,
                            fontWeight = FontWeight.Bold
                        )
                    )
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(6.dp))
                            .background(SurfaceDark)
                            .padding(horizontal = 8.dp, vertical = 2.dp)
                    ) {
                        Text(
                            text = badgeText,
                            style = MaterialTheme.typography.labelSmall.copy(color = accentColor, fontSize = 10.sp)
                        )
                    }
                }
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.bodyMedium.copy(color = TextSecondary, fontSize = 12.sp),
                    maxLines = 2
                )
            }

            Spacer(modifier = Modifier.width(8.dp))
            Icon(
                imageVector = Icons.Default.ChevronRight,
                contentDescription = null,
                tint = TextMuted,
                modifier = Modifier.size(20.dp)
            )
        }
    }
}
