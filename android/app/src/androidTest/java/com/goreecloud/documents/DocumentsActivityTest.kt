package com.goreecloud.documents

import android.app.Activity
import android.app.Instrumentation
import android.content.Intent
import android.net.Uri
import android.content.ContentValues
import android.provider.MediaStore
import androidx.compose.ui.test.assertIsEnabled
import androidx.test.espresso.intent.Intents
import androidx.test.espresso.intent.matcher.IntentMatchers.hasAction
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextReplacement
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertArrayEquals
import java.io.File
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
    @Test fun discardingUnsavedEditsDoesNotOverwritePrivateDocument() {
        awaitText("+ New")
        rule.onNodeWithText("+ New").performClick()
        awaitText("Created and saved in private device storage")

        val original = DocumentShelf(rule.activity.filesDir).scan().documents
            .first { it.document.title == "Untitled document" }

        rule.onAllNodes(hasSetTextAction())[0]
            .performTextReplacement("Unsaved scratch title")
        rule.onAllNodes(hasSetTextAction())[2]
            .performTextReplacement("# This must not reach the saved record")
        rule.onNodeWithText("Library").performClick()
        awaitText("Discard unsaved edits?")

        rule.onNodeWithText("Keep editing").performClick()
        rule.onAllNodes(hasSetTextAction())[0]
            .assertTextContains("Unsaved scratch title")

        rule.onNodeWithText("Library").performClick()
        rule.onNodeWithText("Discard and continue").performClick()
        awaitText("+ New")

        val afterDiscard = DocumentShelf(rule.activity.filesDir).scan().documents
            .single { it.id == original.id }
        assertEquals(original.document, afterDiscard.document)

        rule.activityRule.scenario.recreate()
        awaitText("Private document library ready")
        val afterRecreation = DocumentShelf(rule.activity.filesDir).scan().documents
            .single { it.id == original.id }
        assertEquals(original.document, afterRecreation.document)
    }

    @Test fun cancellingExternalExportKeepsLocalEditsUnsaved() {
        awaitText("+ New")
        rule.onNodeWithText("+ New").performClick()
        awaitText("Created and saved in private device storage")

        val original = DocumentShelf(rule.activity.filesDir).scan().documents
            .first { it.document.title == "Untitled document" }
        rule.onAllNodes(hasSetTextAction())[0]
            .performTextReplacement("Draft not exported")
        rule.onNodeWithText("Save").assertIsEnabled()

        Intents.init()
        try {
            Intents.intending(hasAction(Intent.ACTION_CREATE_DOCUMENT)).respondWith(
                Instrumentation.ActivityResult(Activity.RESULT_CANCELED, null)
            )
            rule.onNodeWithText("Export…").performClick()
            rule.waitForIdle()

            // Cancelling an external picker must not clear unsaved local edits.
            rule.onNodeWithText("Save").assertIsEnabled()
            val onDisk = DocumentShelf(rule.activity.filesDir).scan().documents
                .single { it.id == original.id }
            assertEquals(original.document, onDisk.document)
        } finally {
            Intents.release()
        }
    }

    @Test fun corruptedPrivateRecordIsPreservedAndWarnedAfterRecreation() {
        awaitText("Private document library ready")
        val directory = File(rule.activity.filesDir, "documents")
        check(directory.isDirectory || directory.mkdirs())
        val filename = "00000000-0000-0000-0000-000000000099.json"
        val damaged = File(directory, filename)
        val originalBytes = byteArrayOf(0x7B, 0xC3.toByte(), 0x28, 0x7D)
        check(!damaged.exists()) { "Test fixture already exists" }

        try {
            damaged.writeBytes(originalBytes)
            rule.activityRule.scenario.recreate()
            awaitText("Some saved entries are unreadable. Their files were preserved.")
            assertArrayEquals(originalBytes, damaged.readBytes())
        } finally {
            // Remove only the temporary malformed fixture created by this test.
            damaged.delete()
        }
    }

    @Test fun failedExternalProviderWriteLeavesSavedDocumentIntact() {
        awaitText("+ New")
        val priorIds = DocumentShelf(rule.activity.filesDir).scan().documents
            .map { it.id }.toSet()
        rule.onNodeWithText("+ New").performClick()
        awaitText("Created and saved in private device storage")

        // Instrumentation tests share an app sandbox. Select the newly created
        // record by ID, never by a title another test may also have used.
        val original = DocumentShelf(rule.activity.filesDir).scan().documents
            .single { it.id !in priorIds }
        rule.onAllNodes(hasSetTextAction())[0]
            .performTextReplacement("Unsaved after provider failure")
        rule.onNodeWithText("Save").assertIsEnabled()

        Intents.init()
        try {
            val unavailable = Uri.parse(
                "content://com.goreecloud.documents.unavailable-test-provider/export.gcdoc"
            )
            Intents.intending(hasAction(Intent.ACTION_CREATE_DOCUMENT)).respondWith(
                Instrumentation.ActivityResult(
                    Activity.RESULT_OK, Intent().setData(unavailable)
                )
            )
            rule.onNodeWithText("Export…").performClick()

            // A provider error must release the busy state without claiming
            // that the local edits were saved.
            rule.waitUntil(20_000) {
                runCatching {
                    rule.onNodeWithText("Save").assertIsEnabled()
                    true
                }.getOrDefault(false)
            }
            val onDisk = DocumentShelf(rule.activity.filesDir).scan().documents
                .single { it.id == original.id }
            assertEquals(original.document, onDisk.document)

            rule.onNodeWithText("Library").performClick()
            awaitText("Discard unsaved edits?")
            rule.onNodeWithText("Keep editing").performClick()
        } finally {
            Intents.release()
        }
    }

    @Test fun successfulExternalExportWritesValidGcdocWithoutSavingLocalEdits() {
        awaitText("+ New")
        val priorIds = DocumentShelf(rule.activity.filesDir).scan().documents
            .map { it.id }.toSet()
        rule.onNodeWithText("+ New").performClick()
        awaitText("Created and saved in private device storage")

        val original = DocumentShelf(rule.activity.filesDir).scan().documents
            .single { it.id !in priorIds }
        rule.onAllNodes(hasSetTextAction())[0]
            .performTextReplacement("Safely exported draft")
        rule.onAllNodes(hasSetTextAction())[2]
            .performTextReplacement("# Exported independently\\n\\nPrivate Save still pending")
        rule.onNodeWithText("Save").assertIsEnabled()

        // A disposable MediaStore item exercises the real content-provider
        // write path. Only this test-created entry is removed in finally.
        val resolver = rule.activity.contentResolver
        val name = "goreecloud-export-test-" + java.util.UUID.randomUUID() + ".gcdoc"
        val metadata = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            put(MediaStore.MediaColumns.MIME_TYPE, "application/octet-stream")
        }
        val destination = requireNotNull(
            resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, metadata)
        ) { "Could not create disposable emulator export destination" }

        try {
            Intents.init()
            try {
                Intents.intending(hasAction(Intent.ACTION_CREATE_DOCUMENT)).respondWith(
                    Instrumentation.ActivityResult(
                        Activity.RESULT_OK, Intent().setData(destination)
                    )
                )
                rule.onNodeWithText("Export…").performClick()
                awaitText("Exported file copy. Local changes remain unsaved until Save.")

                val exported = requireNotNull(
                    resolver.openInputStream(destination)
                ).use { DocumentCodec.readLimited(it) }
                val parsed = DocumentCodec.parse(name, exported)
                assertEquals("Safely exported draft", parsed.title)
                assertEquals("# Exported independently\\n\\nPrivate Save still pending", parsed.body)
                rule.onNodeWithText("Save").assertIsEnabled()

                val afterExport = DocumentShelf(rule.activity.filesDir).scan().documents
                    .single { it.id == original.id }
                assertEquals(original.document, afterExport.document)
            } finally {
                Intents.release()
            }
        } finally {
            resolver.delete(destination, null, null)
        }
    }

}
