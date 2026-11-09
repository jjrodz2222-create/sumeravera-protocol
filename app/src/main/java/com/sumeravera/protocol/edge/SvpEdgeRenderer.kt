package com.sumeravera.protocol.edge

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import androidx.core.content.pm.ShortcutInfoCompat
import androidx.core.content.pm.ShortcutManagerCompat
import androidx.core.graphics.drawable.IconCompat

class ScreenOffReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_SCREEN_OFF) {
            val statusColor = Color.parseColor("#00FF66")
            val updatedBitmap = IconBitmapRenderer.generateStatusIcon(context, statusColor, "V2.5")
            updateDynamicAppIcon(context, updatedBitmap)
        }
    }

    private fun updateDynamicAppIcon(context: Context, bitmap: Bitmap) {
        val icon = IconCompat.createWithBitmap(bitmap)
        val targetIntent = Intent(Intent.ACTION_VIEW).apply {
            setPackage(context.packageName)
        }
        val shortcut = ShortcutInfoCompat.Builder(context, "svp_sentinel_shortcut")
            .setShortLabel("SVP Sentinel")
            .setIcon(icon)
            .setIntent(targetIntent)
            .build()
        ShortcutManagerCompat.pushDynamicShortcut(context, shortcut)
    }
}

object IconBitmapRenderer {
    fun generateStatusIcon(context: Context, indicatorColor: Int, badgeText: String): Bitmap {
        val width = 192
        val height = 192
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)

        val bgPaint = Paint().apply {
            color = Color.parseColor("#0B0E14")
            isAntiAlias = true
        }
        canvas.drawCircle(width / 2f, height / 2f, width / 2f, bgPaint)

        val ringPaint = Paint().apply {
            color = indicatorColor
            style = Paint.Style.STROKE
            strokeWidth = 10f
            isAntiAlias = true
        }
        canvas.drawCircle(width / 2f, height / 2f, (width / 2f) - 12f, ringPaint)

        val textPaint = Paint().apply {
            color = Color.WHITE
            textSize = 36f
            textAlign = Paint.Align.CENTER
            isAntiAlias = true
            isFakeBoldText = true
        }
        canvas.drawText(badgeText, width / 2f, (height / 2f) + 12f, textPaint)

        return bitmap
    }
}
