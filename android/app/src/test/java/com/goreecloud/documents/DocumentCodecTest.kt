package com.goreecloud.documents

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import java.nio.charset.CharacterCodingException

class DocumentCodecTest {
    @Test fun gcdocRoundtripPreservesUnicode() {
        val source = PortableDocument(
            title = "Family ✨", body = "# Privacy\n\nBonjour — 🔒",
            folder = "Family/Policies", format = DocumentFormat.GCDOC
        )
        val encoded = DocumentCodec.encode(source)
        val decoded = DocumentCodec.parse("memo.gcdoc", encoded)
        assertEquals(source, decoded)
        assertTrue(String(encoded, Charsets.UTF_8).contains("\"schema_version\": 1"))
    }

    @Test fun markdownImportAndExport() {
        val imported = DocumentCodec.parse("message.md", "# Hello".toByteArray(Charsets.UTF_8))
        assertEquals(DocumentFormat.MARKDOWN, imported.format)
        assertEquals("message", imported.title)
        assertEquals("# Hello", imported.body)
        assertEquals("# Hello", String(DocumentCodec.encode(imported), Charsets.UTF_8))
        assertEquals("message.md", DocumentCodec.suggestedFilename(imported))
    }

    @Test fun canonicalPythonAndAndroidReferenceFixture() {
        val stream = requireNotNull(
            javaClass.classLoader?.getResourceAsStream("fixtures/reference-v1.gcdoc")
        ) { "Shared portable document fixture is missing" }
        val originalBytes = stream.use { DocumentCodec.readLimited(it) }
        val imported = DocumentCodec.parse("reference-v1.gcdoc", originalBytes)
        assertEquals("Reference Notes ✨", imported.title)
        assertEquals("Team/Reference", imported.folder)
        assertEquals("# Interoperability\n\nRésumé — 🔒\n\n- Markdown\n- UTF-8\n", imported.body)
        assertEquals(DocumentFormat.GCDOC, imported.format)
        val exported = DocumentCodec.encode(imported)
        val reopened = DocumentCodec.parse("re-exported.gcdoc", exported)
        assertEquals(imported, reopened)
    }

    @Test fun malformedAndUnexpectedEnvelopeRejected() {
        val wrong = listOf(
            "{}",
            """{"kind":"goreecloud.document","schema_version":2,"title":"x","body":"a"}""",
            """{"kind":"goreecloud.document","schema_version":1,"title":"x","body":"a","extra":"bad"}""",
            """{"kind":"goreecloud.document","schema_version":1,"title":"x","body":42}""",
            """{"kind":"goreecloud.document","schema_version":"1","title":"x","body":"a"}""",
            """{"kind":"goreecloud.document","schema_version":1,"title":"x","body":"a","folder":"../private"}""",
        )
        for (value in wrong) {
            assertThrows(Exception::class.java) {
                DocumentCodec.parse("bad.gcdoc", value.toByteArray(Charsets.UTF_8))
            }
        }
        assertThrows(Exception::class.java) {
            DocumentCodec.parse("relative/secret.md", "data".toByteArray(Charsets.UTF_8))
        }
    }

    @Test fun strictUtf8AndBoundedFiles() {
        assertThrows(CharacterCodingException::class.java) {
            DocumentCodec.parse("bad.md", byteArrayOf(0xC3.toByte(), 0x28))
        }
        assertThrows(IllegalArgumentException::class.java) {
            DocumentCodec.parse("big.md", ByteArray(DocumentCodec.MAX_PACKAGE_BYTES + 1))
        }
        assertThrows(IllegalArgumentException::class.java) {
            DocumentCodec.readLimited(
                ByteArrayInputStream(ByteArray(DocumentCodec.MAX_PACKAGE_BYTES + 1))
            )
        }
    }

    @Test fun folderAndBodyValidation() {
        assertThrows(IllegalArgumentException::class.java) {
            DocumentCodec.encode(PortableDocument("a", "ok", "../secret"))
        }
        assertThrows(IllegalArgumentException::class.java) {
            DocumentCodec.encode(PortableDocument("a", "x".repeat(DocumentCodec.MAX_BODY_BYTES + 1)))
        }
        assertThrows(IllegalArgumentException::class.java) {
            DocumentCodec.encode(PortableDocument("   ", "empty"))
        }
        assertFalse(DocumentCodec.suggestedFilename(
            PortableDocument("Family/notes", "hi")
        ).contains("/"))
    }
}
