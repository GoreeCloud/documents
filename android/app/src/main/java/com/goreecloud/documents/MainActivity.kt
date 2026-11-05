package com.goreecloud.documents

import android.content.ContentResolver
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items as listItems
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import java.util.UUID

/** Native Android storage-access and editing preview. No network permission. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { DocumentsScreen(this) }
    }
}

private val Iris = Color(0xFF5145D9)
private val IrisContainer = Color(0xFFE8E6FF)
private val IrisInk = Color(0xFF2C227C)
private data class RecentDocument(val id: String, val document: PortableDocument)

private fun displayName(resolver: ContentResolver, uri: Uri): String {
    resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
        if (cursor.moveToFirst()) {
            val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (column >= 0) return cursor.getString(column)
        }
    }
    return uri.lastPathSegment?.substringAfterLast('/') ?: "document.gcdoc"
}

@Composable
private fun DocumentsScreen(activity: MainActivity) {
    val dark = isSystemInDarkTheme()
    val colors = if (dark) darkColorScheme(
        primary = Color(0xFFC5BFFF), onPrimary = Color(0xFF241B66),
        background = Color(0xFF10131E), surface = Color(0xFF1D2231)
    ) else lightColorScheme(
        primary = Iris, onPrimary = Color.White,
        background = Color(0xFFF6F7FB), surface = Color.White
    )
    MaterialTheme(colorScheme = colors) {
        val prefs = remember { activity.getSharedPreferences("gcdocs-ui", 0) }
        var grid by remember { mutableStateOf(prefs.getBoolean("grid", true)) }
        val recent = remember { mutableStateListOf<RecentDocument>() }
        var selectedId by remember { mutableStateOf<String?>(null) }
        val selected = recent.firstOrNull { it.id == selectedId }
        var title by remember { mutableStateOf("") }
        var folder by remember { mutableStateOf("") }
        var body by remember { mutableStateOf("") }
        var savedFields by remember { mutableStateOf(Triple("", "", "")) }
        var search by remember { mutableStateOf("") }
        var notice by remember { mutableStateOf("Open or create a document to get started") }
        var busy by remember { mutableStateOf(false) }
        var discardAction by remember { mutableStateOf<(() -> Unit)?>(null) }
        var exportBytes by remember { mutableStateOf<ByteArray?>(null) }
        var exportSnapshot by remember { mutableStateOf<Triple<String, String, String>?>(null) }
        var exportDocument by remember { mutableStateOf<RecentDocument?>(null) }
        val dirty = selected != null && Triple(title, folder, body) != savedFields

        fun openEditor(item: RecentDocument) {
            selectedId = item.id
            title = item.document.title
            folder = item.document.folder
            body = item.document.body
            savedFields = Triple(title, folder, body)
            notice = "Editing locally; changes are not saved until you export"
        }

        fun guarded(action: () -> Unit) {
            if (busy) {
                notice = "Finish the current file operation first"
            } else if (dirty) {
                discardAction = action
            } else {
                action()
            }
        }

        fun openUri(uri: Uri) {
            busy = true
            notice = "Opening local document…"
            Thread {
                try {
                    val filename = displayName(activity.contentResolver, uri)
                    val bytes = activity.contentResolver.openInputStream(uri)?.use {
                        DocumentCodec.readLimited(it)
                    } ?: error("The selected document could not be read")
                    val doc = DocumentCodec.parse(filename, bytes)
                    activity.runOnUiThread {
                        val item = RecentDocument(UUID.randomUUID().toString(), doc)
                        recent.add(0, item)
                        openEditor(item)
                        notice = "Opened " + filename + "; use Save as to create a new file"
                        busy = false
                    }
                } catch (failure: Exception) {
                    activity.runOnUiThread {
                        notice = failure.message ?: "Could not open the document"
                        busy = false
                    }
                }
            }.start()
        }

        val openLauncher = rememberLauncherForActivityResult(
            ActivityResultContracts.OpenDocument()
        ) { uri -> if (uri != null) openUri(uri) }

        val saveLauncher = rememberLauncherForActivityResult(
            ActivityResultContracts.CreateDocument("application/octet-stream")
        ) { uri ->
            val bytes = exportBytes
            val snapshot = exportSnapshot
            val item = exportDocument
            exportBytes = null
            exportSnapshot = null
            exportDocument = null
            if (uri != null && bytes != null && snapshot != null && item != null) {
                busy = true
                notice = "Writing selected file…"
                Thread {
                    try {
                        val stream = activity.contentResolver.openOutputStream(uri, "w")
                            ?: error("Could not open the selected save destination")
                        stream.use { it.write(bytes); it.flush() }
                        activity.runOnUiThread {
                            val index = recent.indexOfFirst { it.id == item.id }
                            if (index >= 0) recent[index] = item
                            if (selectedId == item.id) savedFields = snapshot
                            notice = "Document saved to selected location"
                            busy = false
                        }
                    } catch (failure: Exception) {
                        activity.runOnUiThread {
                            notice = failure.message ?: "Could not save the document"
                            busy = false
                        }
                    }
                }.start()
            }
        }

        if (discardAction != null) {
            AlertDialog(
                onDismissRequest = { discardAction = null },
                title = { Text("Discard unsaved edits?") },
                text = { Text("Unsaved changes will be lost. Saved files are not modified.") },
                confirmButton = {
                    TextButton(onClick = {
                        val action = discardAction
                        discardAction = null
                        action?.invoke()
                    }) { Text("Discard and continue") }
                },
                dismissButton = {
                    TextButton(onClick = { discardAction = null }) { Text("Keep editing") }
                }
            )
        }

        Column(
            modifier = Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)
                .systemBarsPadding()
        ) {
            Row(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    "GoreeCloud Documents",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.weight(1f)
                )
                if (selected != null) {
                    TextButton(onClick = { guarded { selectedId = null } }) {
                        Text("Library")
                    }
                }
            }
            if (selected == null) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Button(onClick = {
                        guarded {
                            val item = RecentDocument(
                                UUID.randomUUID().toString(),
                                PortableDocument(title = "Untitled document", body = "")
                            )
                            recent.add(0, item)
                            openEditor(item)
                        }
                    }) { Text("+ New") }
                    OutlinedButton(onClick = {
                        guarded { openLauncher.launch(arrayOf("*/*")) }
                    }) { Text("Open file") }
                    Spacer(Modifier.weight(1f))
                    TextButton(onClick = {
                        grid = !grid
                        prefs.edit().putBoolean("grid", grid).apply()
                    }) { Text(if (grid) "List" else "Grid") }
                }
                OutlinedTextField(
                    value = search, onValueChange = { search = it },
                    label = { Text("Search session documents") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(18.dp)
                )
                val results = recent.filter {
                    it.document.title.contains(search, ignoreCase = true) ||
                        it.document.folder.contains(search, ignoreCase = true) ||
                        it.document.body.contains(search, ignoreCase = true)
                }
                if (results.isEmpty()) {
                    Box(Modifier.fillMaxWidth().weight(1f).padding(28.dp), contentAlignment = Alignment.Center) {
                        Text(
                            "Your opened documents appear here during this session.\n" +
                                "Use Open file for .gcdoc or .md, or create a new page.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                } else if (grid) {
                    LazyVerticalGrid(
                        columns = GridCells.Adaptive(minSize = 170.dp),
                        modifier = Modifier.weight(1f),
                        contentPadding = PaddingValues(18.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        gridItems(results, key = { it.id }) { item ->
                            DocumentCard(item) { guarded { openEditor(item) } }
                        }
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.weight(1f),
                        contentPadding = PaddingValues(18.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        listItems(results, key = { it.id }) { item ->
                            DocumentCard(item) { guarded { openEditor(item) } }
                        }
                    }
                }
            } else {
                val format = if (selected.document.format == DocumentFormat.GCDOC) "GC DOC" else "MD"
                Text(
                    "$format · Local document",
                    modifier = Modifier.padding(horizontal = 20.dp),
                    color = MaterialTheme.colorScheme.primary,
                    style = MaterialTheme.typography.labelLarge
                )
                OutlinedTextField(
                    value = title, onValueChange = { title = it },
                    label = { Text("Title") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 6.dp)
                )
                OutlinedTextField(
                    value = folder, onValueChange = { folder = it },
                    label = { Text("Folder") }, singleLine = true,
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 6.dp)
                )
                OutlinedTextField(
                    value = body, onValueChange = { body = it },
                    label = { Text("Markdown source") },
                    modifier = Modifier.fillMaxWidth().weight(1f).padding(18.dp)
                )
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 18.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Button(onClick = {
                        try {
                            val document = selected.document.copy(
                                title = title, folder = folder, body = body
                            )
                            exportBytes = DocumentCodec.encode(document)
                            exportSnapshot = Triple(title, folder, body)
                            exportDocument = RecentDocument(selected.id, document)
                            saveLauncher.launch(DocumentCodec.suggestedFilename(document))
                        } catch (failure: Exception) {
                            notice = failure.message ?: "Invalid document"
                        }
                    }, enabled = !busy) { Text("Save as…") }
                    TextButton(onClick = {
                        title = selected.document.title
                        folder = selected.document.folder
                        body = selected.document.body
                        savedFields = Triple(title, folder, body)
                        notice = "Edits discarded"
                    }, enabled = !busy && dirty) { Text("Discard edits") }
                }
            }
            Text(
                notice,
                modifier = Modifier.fillMaxWidth().padding(18.dp),
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}

@Composable
private fun DocumentCard(item: RecentDocument, onOpen: () -> Unit) {
    val paperColor = if (isSystemInDarkTheme()) Color(0xFF302B4B) else IrisContainer
    val paperInk = if (isSystemInDarkTheme()) Color(0xFFF3F0FF) else IrisInk
    Card(
        onClick = onOpen, modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp)
    ) {
        Column {
            Box(
                modifier = Modifier.fillMaxWidth().height(105.dp)
                    .background(paperColor, RoundedCornerShape(topStart = 18.dp, topEnd = 18.dp))
            ) {
                Text(
                    item.document.body.ifBlank { "A new page to write…" },
                    color = paperInk,
                    maxLines = 3, overflow = TextOverflow.Ellipsis,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.align(Alignment.BottomStart).padding(14.dp)
                )
                val fmt = if (item.document.format == DocumentFormat.GCDOC) "GC DOC" else "MD"
                Text(
                    fmt, color = MaterialTheme.colorScheme.onPrimary,
                    style = MaterialTheme.typography.labelSmall,
                    modifier = Modifier.align(Alignment.TopEnd).padding(9.dp)
                        .background(MaterialTheme.colorScheme.primary, RoundedCornerShape(8.dp))
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                )
            }
            Text(
                item.document.title, maxLines = 1, overflow = TextOverflow.Ellipsis,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.padding(start = 14.dp, end = 14.dp, top = 12.dp)
            )
            Text(
                item.document.folder.ifBlank { "Unfiled" },
                maxLines = 1, overflow = TextOverflow.Ellipsis,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(start = 14.dp, end = 14.dp, bottom = 12.dp, top = 4.dp)
            )
        }
    }
}
