package com.goreecloud.documents

import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.InputStream
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.util.Locale

enum class DocumentFormat { GCDOC, MARKDOWN }

data class PortableDocument(
    val title: String,
    val body: String,
    val folder: String = "",
    val format: DocumentFormat = DocumentFormat.GCDOC,
)

/** Compatible with the server's v1 .gcdoc JSON envelope and plain Markdown. */
object DocumentCodec {
    const val MAX_BODY_BYTES = 1_048_576
    const val MAX_PACKAGE_BYTES = MAX_BODY_BYTES + 4096

    fun readLimited(source: InputStream): ByteArray {
        val output = ByteArrayOutputStream()
        val buffer = ByteArray(8192)
        while (true) {
            val received = source.read(buffer)
            if (received == -1) break
            require(output.size() + received <= MAX_PACKAGE_BYTES) {
                "Document exceeds the maximum import size"
            }
            output.write(buffer, 0, received)
        }
        return output.toByteArray()
    }

    internal fun decodeUtf8(bytes: ByteArray): String =
        StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes))
            .toString()

    private fun validate(doc: PortableDocument) {
        require(doc.title.isNotBlank() && doc.title.trim().length <= 160 &&
            '\n' !in doc.title && '\r' !in doc.title) {
            "Document title must be 1 to 160 characters"
        }
        require('\u0000' !in doc.body && doc.body.toByteArray(Charsets.UTF_8).size <= MAX_BODY_BYTES) {
            "Markdown body is invalid or exceeds 1 MiB"
        }
        require(doc.folder.length <= 240 && '\u0000' !in doc.folder && '\\' !in doc.folder) {
            "Invalid document folder"
        }
        val parts = doc.folder.trim('/').takeIf { it.isNotEmpty() }?.split('/') ?: emptyList()
        require(parts.size <= 8 && parts.none { it.isBlank() || it != it.trim() || it == "." || it == ".." }) {
            "Invalid document folder"
        }
    }

    fun parse(filename: String, bytes: ByteArray): PortableDocument {
        require(bytes.size <= MAX_PACKAGE_BYTES) { "Document is too large" }
        require(filename.isNotBlank() && filename.length <= 180 && !filename.startsWith(".") &&
            '/' !in filename && '\\' !in filename && '\u0000' !in filename) {
            "Invalid filename"
        }
        val text = decodeUtf8(bytes)
        val lower = filename.lowercase(Locale.ROOT)
        val document = when {
            lower.endsWith(".md") -> {
                PortableDocument(filename.dropLast(3), text, format = DocumentFormat.MARKDOWN)
            }
            lower.endsWith(".gcdoc") -> {
                val obj = JSONObject(text)
                val allowed = setOf("kind", "schema_version", "title", "body", "folder", "format")
                val keys = obj.keys()
                while (keys.hasNext()) {
                    require(keys.next() in allowed) { "Unsupported document property" }
                }
                require(obj.opt("kind") == "goreecloud.document") { "Invalid document kind" }
                val version = obj.opt("schema_version")
                require(version is Int && version == 1) { "Unsupported document version" }
                val title = obj.opt("title") as? String
                    ?: throw IllegalArgumentException("Missing document title")
                val body = obj.opt("body") as? String
                    ?: throw IllegalArgumentException("Missing Markdown body")
                val folder = when (val value = obj.opt("folder")) {
                    null -> ""
                    is String -> value
                    else -> throw IllegalArgumentException("Invalid document folder")
                }
                require(obj.opt("format") in listOf(null, "gcdoc")) {
                    "Invalid document format"
                }
                PortableDocument(title, body, folder)
            }
            else -> throw IllegalArgumentException("Only .gcdoc and .md are supported")
        }
        validate(document)
        return document
    }

    fun encode(doc: PortableDocument): ByteArray {
        validate(doc)
        return if (doc.format == DocumentFormat.MARKDOWN) {
            doc.body.toByteArray(Charsets.UTF_8)
        } else {
            val obj = JSONObject()
                .put("kind", "goreecloud.document")
                .put("schema_version", 1)
                .put("title", doc.title.trim())
                .put("body", doc.body)
                .put("folder", doc.folder.trim('/'))
                .put("format", "gcdoc")
            (obj.toString(2) + "\n").toByteArray(Charsets.UTF_8)
        }
    }

    fun suggestedFilename(doc: PortableDocument): String {
        val stem = doc.title.filter {
            it.isLetterOrDigit() || it == '-' || it == '_' || it == ' ' || it == '.'
        }.trim(' ', '.').take(80).ifBlank { "document" }
        val suffix = if (doc.format == DocumentFormat.GCDOC) ".gcdoc" else ".md"
        return stem + suffix
    }
}
