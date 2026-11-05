package com.goreecloud.documents

import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.onAllNodes
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Runtime contract on a real Android emulator:
 * create -> Save -> Activity recreation -> reload from app-private storage.
 *
 * Activity recreation is not complete process-death or low-storage testing.
 */
@RunWith(AndroidJUnit4::class)
class DocumentsActivityTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    private fun awaitText(value: String) {
        rule.waitUntil(20_000) {
            rule.onAllNodesWithText(value).fetchSemanticsNodes().isNotEmpty()
        }
    }

    @Test fun savedDocumentRemainsVisibleAndEditableAfterActivityRecreation() {
        awaitText("+ New")
        rule.onNodeWithText("+ New").performClick()
        awaitText("Created and saved in private device storage")

        // In editor view, the title, folder and Markdown body are editable.
        rule.onAllNodes(hasSetTextAction())[0].performTextReplacement("Durable Android Proof")
        rule.onAllNodes(hasSetTextAction())[2].performTextReplacement("# Saved on-device")
        rule.onNodeWithText("Save").performClick()
        awaitText("Saved in private device storage")

        rule.activityRule.scenario.recreate()
        awaitText("Private document library ready")
        rule.onNodeWithText("Durable Android Proof").performClick()
        rule.onAllNodes(hasSetTextAction())[2].assertTextContains("# Saved on-device")

        // The on-device document is the single durable record after recreation.
        val docs = DocumentShelf(rule.activity.filesDir).scan().documents
        assertEquals(1, docs.count { it.document.title == "Durable Android Proof" })
        assertEquals("# Saved on-device",
            docs.first { it.document.title == "Durable Android Proof" }.document.body)
    }
}
