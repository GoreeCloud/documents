package com.goreecloud.documents

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.rules.TemporaryFolder
import org.robolectric.RobolectricTestRunner
import java.io.File

/** Reproducible app-private storage tests using an isolated filesystem. */
@RunWith(RobolectricTestRunner::class)
class DocumentShelfTest {
    @get:Rule val temporary = TemporaryFolder()

    @Test fun savedGcdocAndMarkdownSurviveReopeningTheLibrary() {
        val shelf = DocumentShelf(temporary.root)
        val first = shelf.create(PortableDocument("Family ✨", "# Private", "Policies"))
        val second = shelf.create(PortableDocument(
            "reference", "plain UTF-8", format = DocumentFormat.MARKDOWN
        ))
        val reopened = DocumentShelf(temporary.root).scan()
        assertEquals(0, reopened.invalidFiles)
        assertEquals(2, reopened.documents.size)
        assertEquals(first.document, reopened.documents.first { it.id == first.id }.document)
        assertEquals(DocumentFormat.MARKDOWN,
            reopened.documents.first { it.id == second.id }.document.format)
    }

    @Test fun overwriteIsBoundedAndRetainsOriginalIdentifier() {
        val shelf = DocumentShelf(temporary.root)
        val created = shelf.create(PortableDocument("First", "before"))
        shelf.save(created.id, PortableDocument("Revised", "after", "Family"))
        val scan = DocumentShelf(temporary.root).scan()
        assertEquals(1, scan.documents.size)
        assertEquals(created.id, scan.documents.single().id)
        assertEquals("after", scan.documents.single().document.body)
        assertEquals("Family", scan.documents.single().document.folder)
    }

    @Test fun invalidIdentityCannotEscapePrivateStorage() {
        val shelf = DocumentShelf(temporary.root)
        for (id in listOf("../outside", "/tmp/file", "bad.json", "..", "")) {
            assertThrows(IllegalArgumentException::class.java) {
                shelf.save(id, PortableDocument("Test", "body"))
            }
        }
        assertTrue(temporary.root.walkTopDown().none { it.isFile })
    }

    @Test fun unreadableEntryIsPreservedAndReported() {
        val shelf = DocumentShelf(temporary.root)
        val good = shelf.create(PortableDocument("Working", "content"))
        val other = File(temporary.root, "documents/00000000-0000-0000-0000-000000000000.json")
        other.writeText("{truncated", Charsets.UTF_8)
        val reloaded = shelf.scan()
        assertEquals(1, reloaded.documents.size)
        assertEquals(good.id, reloaded.documents.single().id)
        assertEquals(1, reloaded.invalidFiles)
        assertEquals("{truncated", other.readText(Charsets.UTF_8))
    }

    @Test fun failedOversizedWriteDoesNotDestroyExistingDocument() {
        val shelf = DocumentShelf(temporary.root)
        val initial = shelf.create(PortableDocument("Original", "unchanged"))
        assertThrows(IllegalArgumentException::class.java) {
            shelf.save(initial.id, PortableDocument("Oversized", "x".repeat(1_048_577)))
        }
        assertEquals("unchanged", shelf.scan().documents.single().document.body)
    }
}
