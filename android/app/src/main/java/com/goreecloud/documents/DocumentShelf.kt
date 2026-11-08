package com.goreecloud.documents

import android.util.AtomicFile
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.nio.file.Files
import java.util.UUID

data class LocalDocument(val id: String, val document: PortableDocument)
data class ShelfScan(val documents: List<LocalDocument>, val invalidFiles: Int)

/** App-private durable document library, separate from user-selected SAF exports.
 *
 * Each record lives under the Android application's filesDir/documents directory.
 * AtomicFile prevents truncated drafts after interrupted writes. No raw paths or
 * filenames from an imported document are used as local storage paths.
 */
class DocumentShelf(private val appFilesDir: File) {
    private val folder = File(appFilesDir, "documents")
    private val identifier = Regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

    private fun recordFile(id: String): File {
        require(identifier.matches(id)) { "Invalid local document ID" }
        return File(folder, "$id.json")
    }

    private fun ensureFolder() {
        require(!Files.isSymbolicLink(folder.toPath())) {
            "Document directory must not be a symbolic link"
        }
        require(folder.isDirectory || folder.mkdirs()) { "Cannot create private document directory" }
        require(folder.canonicalFile.parentFile == appFilesDir.canonicalFile) {
            "Document directory must remain inside application storage"
        }
    }

    private fun requireSafeAtomicPaths(record: File) {
        // Android AtomicFile uses a .new temporary file and can restore a
        // legacy .bak sidecar. No one of these paths may redirect outside
        // the app-private shelf before openRead() or startWrite().
        for (candidate in listOf(record, File(record.path + ".new"), File(record.path + ".bak"))) {
            require(!Files.isSymbolicLink(candidate.toPath())) {
                "Symbolic links are not permitted in private document records"
            }
        }
    }

    fun save(id: String, document: PortableDocument) {
        // Shared validation contract; keep source format metadata in local record.
        DocumentCodec.encode(document)
        ensureFolder()
        val payload = JSONObject()
            .put("kind", "goreecloud.android.local-document")
            .put("schema_version", 1)
            .put("id", id)
            .put("title", document.title)
            .put("body", document.body)
            .put("folder", document.folder)
            .put("format", if (document.format == DocumentFormat.GCDOC) "gcdoc" else "md")
            .toString()
            .toByteArray(Charsets.UTF_8)
        require(payload.size <= DocumentCodec.MAX_PACKAGE_BYTES) {
            "Local document exceeds maximum storage size"
        }
        val target = recordFile(id)
        requireSafeAtomicPaths(target)
        val atomic = AtomicFile(target)
        val stream = atomic.startWrite()
        try {
            stream.write(payload)
            stream.fd.sync()
            atomic.finishWrite(stream)
        } catch (failure: Exception) {
            atomic.failWrite(stream)
            throw failure
        }
    }

    fun create(document: PortableDocument): LocalDocument {
        val result = LocalDocument(UUID.randomUUID().toString(), document)
        save(result.id, document)
        return result
    }

    private fun read(record: File): LocalDocument {
        val id = record.name.removeSuffix(".json")
        require(record.name == "$id.json" && identifier.matches(id)) {
            "Unsupported document filename"
        }
        requireSafeAtomicPaths(record)
        val atomic = AtomicFile(record)
        val bytes = atomic.openRead().use { DocumentCodec.readLimited(it) }
        // A damaged local record must not be silently decoded with U+FFFD replacements.
        val payload = JSONObject(DocumentCodec.decodeUtf8(bytes))
        val allowed = setOf("kind", "schema_version", "id", "title", "body", "folder", "format")
        val keys = payload.keys()
        while (keys.hasNext()) require(keys.next() in allowed) { "Unknown local document field" }
        require(payload.opt("kind") == "goreecloud.android.local-document") {
            "Unexpected local record"
        }
        require(payload.opt("schema_version") == 1 && payload.opt("id") == id) {
            "Wrong local record version or identity"
        }
        val title = payload.opt("title") as? String ?: error("Missing title")
        val body = payload.opt("body") as? String ?: error("Missing body")
        val folderName = payload.opt("folder") as? String ?: error("Missing folder")
        val format = when (payload.opt("format")) {
            "gcdoc" -> DocumentFormat.GCDOC
            "md" -> DocumentFormat.MARKDOWN
            else -> error("Unknown local document format")
        }
        val document = PortableDocument(title, body, folderName, format)
        DocumentCodec.encode(document) // schema and size validation
        return LocalDocument(id, document)
    }

    fun scan(): ShelfScan {
        ensureFolder()
        val entries = folder.listFiles() ?: throw IOException("Cannot list private documents")
        require(entries.size <= 5000) { "Too many local document entries for this preview" }
        var invalid = 0
        val recovered = mutableListOf<LocalDocument>()
        // Android AtomicFile can restore a legacy .bak during openRead(), but only
        // if we include its matching base path in this discovery pass.
        val records = entries.asSequence()
            .filter {
                (it.isFile || Files.isSymbolicLink(it.toPath())) &&
                    (it.name.endsWith(".json") || it.name.endsWith(".json.bak"))
            }
            .map { if (it.name.endsWith(".json.bak")) File(folder, it.name.removeSuffix(".bak")) else it }
            .distinctBy { it.name }
            .sortedWith(compareByDescending<File> { AtomicFile(it).lastModifiedTime }.thenBy { it.name })
        for (file in records) {
            // Do not resolve attacker-controlled links to files outside app-private storage.
            val backup = File(file.path + ".bak")
            if (Files.isSymbolicLink(file.toPath()) ||
                Files.isSymbolicLink(backup.toPath()) ||
                Files.isSymbolicLink(File(file.path + ".new").toPath())) {
                invalid++
                continue
            }
            try {
                recovered.add(read(file))
            } catch (_: Exception) {
                // Do not delete corrupted or unrecognized content. Warn users and
                // leave files intact for recovery rather than silently erasing them.
                invalid++
            }
        }
        return ShelfScan(recovered, invalid)
    }
}
