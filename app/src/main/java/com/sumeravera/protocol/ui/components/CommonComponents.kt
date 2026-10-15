package com.sumeravera.protocol.ui.components

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.widget.Toast
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sumeravera.protocol.ui.theme.*

@Composable
fun HashBadge(
    hash: String,
    label: String = "HASH",
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val shortHash = if (hash.length > 16) "${hash.take(8)}...${hash.takeLast(8)}" else hash

    Row(
        modifier = modifier
            .clip(RoundedCornerShape(6.dp))
            .background(SurfaceDark.copy(alpha = 0.8f))
            .border(1.dp, SurfaceCardBorder, RoundedCornerShape(6.dp))
            .clickable {
                val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                val clip = ClipData.newPlainText("hash", hash)
                clipboard.setPrimaryClip(clip)
                Toast.makeText(context, "Copied hash to clipboard", Toast.LENGTH_SHORT).show()
            }
            .padding(horizontal = 8.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = "$label: ",
            style = MaterialTheme.typography.labelSmall.copy(color = TextMuted, fontSize = 10.sp)
        )
        Text(
            text = shortHash,
            style = MaterialTheme.typography.labelSmall.copy(
                color = HashGreen,
                fontWeight = FontWeight.Medium,
                fontFamily = FontFamily.Monospace,
                fontSize = 11.sp
            )
        )
        Spacer(modifier = Modifier.width(4.dp))
        Icon(
            imageVector = Icons.Default.ContentCopy,
            contentDescription = "Copy hash",
            tint = TextMuted,
            modifier = Modifier.size(12.dp)
        )
    }
}

@Composable
fun SeverityChip(severity: String) {
    val (bgColor, textColor) = when (severity.lowercase()) {
        "critical" -> Pair(StatusRed.copy(alpha = 0.2f), StatusRed)
        "warning" -> Pair(StatusYellow.copy(alpha = 0.2f), StatusYellow)
        "action_required" -> Pair(AccentPurple.copy(alpha = 0.2f), AccentPurple)
        else -> Pair(PrimaryCyan.copy(alpha = 0.2f), PrimaryCyan)
    }

    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(bgColor)
            .border(1.dp, textColor.copy(alpha = 0.5f), RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Text(
            text = severity.uppercase(),
            style = MaterialTheme.typography.labelSmall.copy(
                color = textColor,
                fontWeight = FontWeight.Bold,
                fontSize = 10.sp
            )
        )
    }
}

@Composable
fun PriorityChip(priority: String) {
    val (bgColor, textColor) = when (priority.uppercase()) {
        "P0" -> Pair(StatusRed.copy(alpha = 0.2f), StatusRed)
        "P1" -> Pair(InvariantGold.copy(alpha = 0.2f), InvariantGold)
        else -> Pair(SecondaryBlue.copy(alpha = 0.2f), SecondaryBlue)
    }

    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(4.dp))
            .background(bgColor)
            .border(1.dp, textColor.copy(alpha = 0.5f), RoundedCornerShape(4.dp))
            .padding(horizontal = 6.dp, vertical = 2.dp)
    ) {
        Text(
            text = priority.uppercase(),
            style = MaterialTheme.typography.labelSmall.copy(
                color = textColor,
                fontWeight = FontWeight.Bold,
                fontSize = 10.sp
            )
        )
    }
}

@Composable
fun MetricCard(
    title: String,
    value: String,
    subtitle: String,
    icon: ImageVector,
    accentColor: Color = PrimaryCyan,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .border(1.dp, SurfaceCardBorder, RoundedCornerShape(12.dp)),
        colors = CardDefaults.cardColors(containerColor = SurfaceCard),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier.padding(14.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = title.uppercase(),
                    style = MaterialTheme.typography.labelSmall.copy(
                        color = TextMuted,
                        fontWeight = FontWeight.SemiBold,
                        fontSize = 10.sp
                    )
                )
                Icon(
                    imageVector = icon,
                    contentDescription = null,
                    tint = accentColor,
                    modifier = Modifier.size(18.dp)
                )
            }
            Spacer(modifier = Modifier.height(6.dp))
            Text(
                text = value,
                style = MaterialTheme.typography.headlineMedium.copy(
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
            )
            Spacer(modifier = Modifier.height(2.dp))
            Text(
                text = subtitle,
                style = MaterialTheme.typography.bodyMedium.copy(
                    color = TextSecondary,
                    fontSize = 11.sp
                )
            )
        }
    }
}
