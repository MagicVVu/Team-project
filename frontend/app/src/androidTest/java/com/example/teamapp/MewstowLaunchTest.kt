package com.example.teamapp

import androidx.compose.material3.Text
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import com.example.teamapp.ui.MewstowLaunch
import com.example.teamapp.ui.theme.TeamAppTheme
import org.junit.Rule
import org.junit.Test

class MewstowLaunchTest {
    @get:Rule val compose = createComposeRule()

    @Test fun lightLaunchHoldsTheBrandThenRevealsTheEntry() = checkLaunch(dark = false)
    @Test fun darkLaunchHoldsTheBrandThenRevealsTheEntry() = checkLaunch(dark = true)

    private fun checkLaunch(dark: Boolean) {
        compose.mainClock.autoAdvance = false
        compose.setContent {
            TeamAppTheme(darkTheme = dark) {
                MewstowLaunch(showIntro = true) { Text("Entry") }
            }
        }
        val launch = compose.onNodeWithTag("mewstow-launch")
        launch.assertIsDisplayed()
        compose.onNodeWithText("Entry").assertDoesNotExist()
        compose.mainClock.advanceTimeBy(1450)
        launch.assertIsDisplayed()
        compose.mainClock.advanceTimeBy(500)
        launch.assertDoesNotExist()
        compose.onNodeWithText("Entry").assertIsDisplayed()
    }

    @Test fun restoredEntryDoesNotReplayTheLaunch() {
        compose.setContent {
            TeamAppTheme(darkTheme = true) {
                MewstowLaunch(showIntro = false) { Text("Entry") }
            }
        }
        compose.onNodeWithTag("mewstow-launch").assertDoesNotExist()
        compose.onNodeWithText("Entry").assertIsDisplayed()
    }
}
