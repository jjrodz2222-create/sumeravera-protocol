package com.sumeravera.protocol

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sumeravera.protocol.ui.ProtocolViewModel
import com.sumeravera.protocol.ui.screens.*
import com.sumeravera.protocol.ui.theme.*

enum class AppDestination(val title: String, val icon: ImageVector, val tag: String) {
    DASHBOARD("Dashboard", Icons.Default.Dashboard, "nav_dashboard"),
    SUMERA("SumerA", Icons.Default.AccountBalance, "nav_sumera"),
    AVERA("Avera", Icons.Default.CheckCircle, "nav_avera"),
    HONEYPOT("Honeypot", Icons.Default.Shield, "nav_honeypot"),
    PAWS("Paws", Icons.Default.Pets, "nav_paws")
}

class MainActivity : ComponentActivity() {

    private val viewModel: ProtocolViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        setContent {
            SumerAveraTheme {
                MainAppShell(viewModel)
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MainAppShell(viewModel: ProtocolViewModel) {
    var currentDestination by remember { mutableStateOf(AppDestination.DASHBOARD) }
    val feedbackMessage by viewModel.userFeedbackMessage.collectAsState()
    val snackbarHostState = remember { SnackbarHostState() }

    LaunchedEffect(feedbackMessage) {
        feedbackMessage?.let { msg ->
            snackbarHostState.showSnackbar(msg, duration = SnackbarDuration.Short)
            viewModel.clearFeedback()
        }
    }

    // BackHandler returns to Dashboard if on another screen
    BackHandler(enabled = currentDestination != AppDestination.DASHBOARD) {
        currentDestination = AppDestination.DASHBOARD
    }

    BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
        val isWideScreen = maxWidth >= 600.dp

        Scaffold(
            modifier = Modifier.fillMaxSize(),
            topBar = {
                TopAppBar(
                    title = {
                        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
                            Icon(
                                imageVector = currentDestination.icon,
                                contentDescription = null,
                                tint = PrimaryCyan,
                                modifier = Modifier.size(22.dp)
                            )
                            Spacer(modifier = Modifier.width(10.dp))
                            Text(
                                text = "SVP // ${currentDestination.title.uppercase()}",
                                style = MaterialTheme.typography.titleMedium.copy(
                                    color = TextPrimary,
                                    fontSize = 16.sp
                                )
                            )
                        }
                    },
                    colors = TopAppBarDefaults.topAppBarColors(
                        containerColor = BgDark,
                        titleContentColor = TextPrimary
                    )
                )
            },
            bottomBar = {
                if (!isWideScreen) {
                    NavigationBar(
                        containerColor = SurfaceDark,
                        contentColor = TextPrimary
                    ) {
                        AppDestination.entries.forEach { dest ->
                            val selected = currentDestination == dest
                            NavigationBarItem(
                                selected = selected,
                                onClick = { currentDestination = dest },
                                icon = {
                                    Icon(
                                        imageVector = dest.icon,
                                        contentDescription = dest.title,
                                        tint = if (selected) PrimaryCyan else TextMuted
                                    )
                                },
                                label = {
                                    Text(
                                        text = dest.title,
                                        fontSize = 10.sp,
                                        color = if (selected) PrimaryCyan else TextMuted
                                    )
                                },
                                colors = NavigationBarItemDefaults.colors(
                                    indicatorColor = PrimaryCyan.copy(alpha = 0.15f)
                                ),
                                modifier = Modifier.testTag(dest.tag)
                            )
                        }
                    }
                }
            },
            snackbarHost = {
                SnackbarHost(
                    hostState = snackbarHostState,
                    modifier = Modifier.padding(16.dp)
                ) { data ->
                    Snackbar(
                        snackbarData = data,
                        containerColor = SurfaceCard,
                        contentColor = TextPrimary,
                        shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)
                    )
                }
            },
            containerColor = BgDark
        ) { innerPadding ->
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(innerPadding)
            ) {
                if (isWideScreen) {
                    NavigationRail(
                        containerColor = SurfaceDark,
                        contentColor = TextPrimary,
                        modifier = Modifier.fillMaxHeight()
                    ) {
                        Spacer(modifier = Modifier.height(8.dp))
                        AppDestination.entries.forEach { dest ->
                            val selected = currentDestination == dest
                            NavigationRailItem(
                                selected = selected,
                                onClick = { currentDestination = dest },
                                icon = {
                                    Icon(
                                        imageVector = dest.icon,
                                        contentDescription = dest.title,
                                        tint = if (selected) PrimaryCyan else TextMuted
                                    )
                                },
                                label = { Text(dest.title, fontSize = 10.sp) },
                                colors = NavigationRailItemDefaults.colors(
                                    indicatorColor = PrimaryCyan.copy(alpha = 0.15f)
                                ),
                                modifier = Modifier.testTag(dest.tag)
                            )
                        }
                    }
                }

                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(BgDark)
                ) {
                    when (currentDestination) {
                        AppDestination.DASHBOARD -> DashboardScreen(
                            viewModel = viewModel,
                            onNavigateToLedger = { currentDestination = AppDestination.SUMERA },
                            onNavigateToAvera = { currentDestination = AppDestination.AVERA },
                            onNavigateToPerimeter = { currentDestination = AppDestination.HONEYPOT },
                            onNavigateToPaws = { currentDestination = AppDestination.PAWS }
                        )
                        AppDestination.SUMERA -> SumeraLedgerScreen(viewModel = viewModel)
                        AppDestination.AVERA -> AveraEngineScreen(viewModel = viewModel)
                        AppDestination.HONEYPOT -> HoneypotPerimeterScreen(viewModel = viewModel)
                        AppDestination.PAWS -> PawsConnectScreen(viewModel = viewModel)
                    }
                }
            }
        }
    }
}
