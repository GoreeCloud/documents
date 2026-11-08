package com.goreecloud.documents

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.io.File
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Two separate instrumentations on a disposable emulator, with an ADB
 * force-stop + real Activity relaunch between them. There are no live users.
 * The normal connectedDebugAndroidTest run skips this unless phase is explicit.
 */
@RunWith(AndroidJUnit4::class)
class ProcessDeathDurabilityTest {
    @Test fun committedRecordSurvivesHostDrivenForceStop() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val phase = InstrumentationRegistry.getArguments().getString("gcdocs.phase")
        assumeTrue("Explicit host-driven force-stop phase required",
            phase == "seed" || phase == "verify")
        val context = instrumentation.targetContext
        val id = "c0ffee00-0000-4000-8000-000000000077"
        val record = File(context.filesDir, "documents/$id.json")
        val content = PortableDocument("Synthetic force-stop fixture",
            "# Committed before process restart", "Private/Synthetic")

        when (phase) {
            "seed" -> {
                assertFalse("Never overwrite an existing file", record.exists())
                DocumentShelf(context.filesDir).save(id, content)
                assertEquals(content,
                    DocumentShelf(context.filesDir).scan().documents.single { it.id == id }.document)
                assertTrue(record.isFile)
            }
            "verify" -> {
                try {
                    assertEquals(content,
                        DocumentShelf(context.filesDir).scan().documents.single { it.id == id }.document)
                } finally {
                    // Delete only the fixture created for the isolated emulator.
                    assertTrue("Expected synthetic fixture to exist", record.isFile)
                    assertTrue("Could not remove synthetic fixture", record.delete())
                }
            }
        }
    }
}
