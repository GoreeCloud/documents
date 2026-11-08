package com.goreecloud.documents

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.rules.TemporaryFolder
import org.robolectric.RobolectricTestRunner
import java.io.File
import java.nio.file.Files
import android.util.AtomicFile
import org.junit.Assert.assertArrayEquals
import org.json.JSONObject

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

    @Test fun invalidUtf8IsNotSilentlyReplacedOrLoaded() {
        val shelf = DocumentShelf(temporary.root)
        val valid = shelf.create(PortableDocument("Safe", "saved"))
        val invalidId = "00000000-0000-0000-0000-000000000001"
        val file = File(temporary.root, "documents/$invalidId.json")
        val prefix = (
            """{"kind":"goreecloud.android.local-document","schema_version":1,"id":"$invalidId","title":"Bad """
        ).toByteArray(Charsets.UTF_8)
        val suffix = (
            """","body":"private","folder":"","format":"gcdoc"}"""
        ).toByteArray(Charsets.UTF_8)
        // Invalid two-byte UTF-8 start followed by a plain ASCII byte.
        val original = prefix + byteArrayOf(0xC3.toByte(), 0x28) + suffix
        file.writeBytes(original)

        val scan = shelf.scan()
        assertEquals(1, scan.documents.size)
        assertEquals(valid.id, scan.documents.single().id)
        assertEquals(1, scan.invalidFiles)
        assertTrue(file.readBytes().contentEquals(original))
    }

    @Test fun failedOversizedWriteDoesNotDestroyExistingDocument() {
        val shelf = DocumentShelf(temporary.root)
        val initial = shelf.create(PortableDocument("Original", "unchanged"))
        assertThrows(IllegalArgumentException::class.java) {
            shelf.save(initial.id, PortableDocument("Oversized", "x".repeat(1_048_577)))
        }
        assertEquals("unchanged", shelf.scan().documents.single().document.body)
    }
    @Test fun mismatchedStoredIdentityIsNotLoadedOrSilentlyRewritten() {
        val shelf = DocumentShelf(temporary.root)
        val original = shelf.create(PortableDocument("Safe", "unchanged"))
        val record = File(temporary.root, "documents/${original.id}.json")
        val foreign = "00000000-0000-0000-0000-000000000010"
        val replaced = JSONObject(record.readText(Charsets.UTF_8))
            .put("id", foreign).toString()
        record.writeText(replaced, Charsets.UTF_8)

        val scan = DocumentShelf(temporary.root).scan()
        assertEquals(1, scan.invalidFiles)
        assertTrue(scan.documents.isEmpty())
        assertEquals(replaced, record.readText(Charsets.UTF_8))
    }

    @Test fun symlinkedDocumentDirectoryDoesNotWriteOutsideAppSandbox() {
        val app = temporary.newFolder("app")
        val outside = temporary.newFolder("outside")
        val shortcut = File(app, "documents")
        Files.createSymbolicLink(shortcut.toPath(), outside.toPath())

        assertThrows(IllegalArgumentException::class.java) {
            DocumentShelf(app).create(PortableDocument("Private", "secret"))
        }
        assertTrue(outside.listFiles().isNullOrEmpty())
        assertTrue(Files.isSymbolicLink(shortcut.toPath()))
    }

    @Test fun interruptedPendingAtomicWriteRetainsLastCommittedDocument() {
        val shelf = DocumentShelf(temporary.root)
        val original = shelf.create(PortableDocument("Recovery", "# Last committed"))
        val record = File(temporary.root, "documents/${original.id}.json")
        val committed = record.readBytes()

        // Simulate process interruption after writing a truncated temporary
        // file: do not call finishWrite() or failWrite() on this stream.
        val pending = AtomicFile(record).startWrite()
        pending.write("{\"body\":\"incomplete".toByteArray(Charsets.UTF_8))
        pending.fd.sync()
        pending.close()

        val reopened = DocumentShelf(temporary.root).scan()
        assertEquals(0, reopened.invalidFiles)
        assertEquals(1, reopened.documents.size)
        assertEquals(original, reopened.documents.single())
        assertArrayEquals(committed, record.readBytes())
    }

    @Test fun legacyBackupWithoutBaseIsDiscoveredAndRecovered() {
        val shelf = DocumentShelf(temporary.root)
        val saved = shelf.create(PortableDocument("Last committed", "# Recover me"))
        val record = File(temporary.root, "documents/${saved.id}.json")
        val originalBytes = record.readBytes()
        val backup = File(record.path + ".bak")
        Files.move(record.toPath(), backup.toPath())
        assertFalse(record.exists())

        val reopened = DocumentShelf(temporary.root).scan()
        assertEquals(0, reopened.invalidFiles)
        assertEquals(listOf(saved), reopened.documents)
        assertArrayEquals(originalBytes, record.readBytes())
        assertFalse(backup.exists())
    }

    @Test fun malformedLegacyBackupIsReportedWithoutLosingBytes() {
        val shelf = DocumentShelf(temporary.root)
        val folder = File(temporary.root, "documents")
        assertTrue(folder.isDirectory || folder.mkdirs())
        val record = File(folder, "00000000-0000-0000-0000-000000000012.json")
        val backup = File(record.path + ".bak")
        val originalBytes = "{truncated".toByteArray(Charsets.UTF_8)
        backup.writeBytes(originalBytes)

        val result = shelf.scan()
        assertEquals(1, result.invalidFiles)
        assertTrue(result.documents.isEmpty())
        val preserved = if (record.exists()) record else backup
        assertArrayEquals(originalBytes, preserved.readBytes())
    }

    @Test fun symlinkedLegacyBackupIsRejectedWithoutReadingOutsideSandbox() {
        val outside = temporary.newFile("outside-synthetic.txt")
        outside.writeText("Do not import", Charsets.UTF_8)
        val folder = File(temporary.root, "documents")
        assertTrue(folder.isDirectory || folder.mkdirs())
        val backup = File(folder, "00000000-0000-0000-0000-000000000013.json.bak")
        Files.createSymbolicLink(backup.toPath(), outside.toPath())

        val result = DocumentShelf(temporary.root).scan()
        assertEquals(1, result.invalidFiles)
        assertTrue(result.documents.isEmpty())
        assertTrue(Files.isSymbolicLink(backup.toPath()))
        assertEquals("Do not import", outside.readText(Charsets.UTF_8))
    }

    @Test fun explicitAtomicWriteRollbackPreservesOriginalPrivateRecord() {
        val shelf = DocumentShelf(temporary.root)
        val original = shelf.create(PortableDocument("Recovery", "original bytes"))
        val record = File(temporary.root, "documents/${original.id}.json")
        val committed = record.readBytes()

        val atomic = AtomicFile(record)
        val writing = atomic.startWrite()
        writing.write("partially written content".toByteArray(Charsets.UTF_8))
        atomic.failWrite(writing)

        val reopened = DocumentShelf(temporary.root).scan()
        assertEquals(0, reopened.invalidFiles)
        assertEquals(listOf(original), reopened.documents)
        assertArrayEquals(committed, record.readBytes())
    }

}
