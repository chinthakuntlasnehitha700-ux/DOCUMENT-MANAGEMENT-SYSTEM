
const API = "https://documind-ai-api-3jx2.onrender.com/api";

let selectedFiles = [];
let allDocuments = [];

const $ = (id) => document.getElementById(id);

// SHOW NOTIFICATION
function showToast(message) {
    const toast = $("toast");
    toast.textContent = message;
    toast.classList.add("show");

    setTimeout(() => toast.classList.remove("show"), 3000);
}

// PAGE NAVIGATION
function showPage(page) {
    document.querySelectorAll(".page").forEach(section =>
        section.classList.remove("active-page")
    );

    $(page + "-page").classList.add("active-page");

    document.querySelectorAll(".nav-btn").forEach(button => {
        button.classList.toggle("active", button.dataset.page === page);
    });

    const titles = {
        dashboard: "Dashboard",
        documents: "My Documents",
        upload: "Upload Documents"
    };

    $("page-title").textContent = titles[page];

    if (page === "dashboard" || page === "documents") {
        loadDocuments();
    }
}

document.querySelectorAll(".nav-btn").forEach(button => {
    button.addEventListener("click", () => showPage(button.dataset.page));
});

$("header-upload").addEventListener("click", () => showPage("upload"));
$("documents-upload").addEventListener("click", () => showPage("upload"));
$("view-all").addEventListener("click", () => showPage("documents"));

// LOAD DOCUMENTS
async function loadDocuments() {
    try {
        const response = await fetch(`${API}/documents`);

        if (!response.ok) {
            throw new Error("Unable to load documents");
        }

        allDocuments = await response.json();

        updateDashboard(allDocuments);

        renderDocuments(allDocuments, "all-documents");

        const recent = allDocuments.slice(0, 5);
        renderDocuments(recent, "recent-documents");

    } catch (error) {
        showToast("Cannot connect to backend. Check whether Flask is running.");
    }
}

// UPDATE DASHBOARD
function updateDashboard(documents) {
    $("total-documents").textContent = documents.length;

    $("pdf-count").textContent =
        documents.filter(doc => doc.file_type === "PDF").length;

    $("docx-count").textContent =
        documents.filter(doc => doc.file_type === "DOCX").length;

    $("txt-count").textContent =
        documents.filter(doc => doc.file_type === "TXT").length;

    $("sidebar-count").textContent = documents.length + " Documents";
}

// DISPLAY DOCUMENTS
function renderDocuments(documents, containerId) {
    const container = $(containerId);
    container.innerHTML = "";

    if (documents.length === 0) {
        container.innerHTML =
            '<div class="empty-state">No documents found. Upload your first document!</div>';
        return;
    }

    documents.forEach(doc => {
        const row = document.createElement("div");
        row.className = "document-row";

        const info = document.createElement("div");
        info.className = "file-info";

        const icon = document.createElement("div");
        icon.className = "file-icon";
        icon.textContent = doc.file_type;

        const details = document.createElement("div");

        const name = document.createElement("h4");
        name.textContent = doc.filename;

        const date = document.createElement("small");
        date.textContent =
            "Uploaded: " + new Date(doc.uploaded_at + "Z").toLocaleString();

        details.append(name, date);
        info.append(icon, details);

        const actions = document.createElement("div");
        actions.className = "row-actions";

        const viewButton = document.createElement("button");
        viewButton.className = "action-btn";
        viewButton.textContent = "View";
        viewButton.addEventListener("click", () => previewDocument(doc.id));

        const summaryButton = document.createElement("button");
        summaryButton.className = "action-btn";
        summaryButton.textContent = "Summarize";
        summaryButton.addEventListener("click", () => summarizeDocument(doc.id));

        const extractButton = document.createElement("button");
        extractButton.className = "action-btn";
        extractButton.textContent = "Extract Info";
        extractButton.addEventListener("click", () => extractInformation(doc.id));

        const deleteButton = document.createElement("button");
        deleteButton.className = "action-btn delete-btn";
        deleteButton.textContent = "Delete";
        deleteButton.addEventListener("click", () => deleteDocument(doc.id));

        actions.append(viewButton, summaryButton, extractButton, deleteButton);
        row.append(info, actions);

        container.appendChild(row);
    });
}

// PREVIEW DOCUMENT
async function previewDocument(id) {
    try {
        const response = await fetch(`${API}/documents/${id}`);

        if (!response.ok) {
            throw new Error("Document not found");
        }

        const documentData = await response.json();

        $("preview-title").textContent = documentData.filename;
        $("preview-body").innerHTML = "";

        const information = document.createElement("p");
        information.textContent = `File type: ${documentData.file_type}`;

        const text = document.createElement("div");
        text.className = "preview-text";
        text.textContent =
            documentData.extracted_text || "No extracted text available.";

        $("preview-body").append(information, text);
        $("preview-modal").classList.add("show");

    } catch (error) {
        showToast(error.message);
    }
}

// SUMMARIZE DOCUMENT
async function summarizeDocument(id) {
    const previewBody = $("preview-body");

    $("preview-title").textContent = "Document Summary";
    previewBody.innerHTML = "";

    const description = document.createElement("p");
    description.textContent = "Choose the type of summary you want:";

    const select = document.createElement("select");

    const options = [
        { value: "short", label: "Short Summary" },
        { value: "medium", label: "Medium Summary" },
        { value: "detailed", label: "Detailed Summary" }
    ];

    options.forEach(option => {
        const item = document.createElement("option");
        item.value = option.value;
        item.textContent = option.label;
        select.appendChild(item);
    });

    const button = document.createElement("button");
    button.className = "action-btn";
    button.textContent = "Generate Summary";

    const result = document.createElement("div");
    result.className = "preview-text";

    button.addEventListener("click", async () => {
        button.disabled = true;
        button.textContent = "Generating...";
        result.textContent = "Analyzing your document...";

        try {
            const response = await fetch(`${API}/documents/${id}/summarize`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ length: select.value })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Summary generation failed");
            }

            result.textContent = data.summary;

        } catch (error) {
            result.textContent = error.message;

        } finally {
            button.disabled = false;
            button.textContent = "Generate Summary";
        }
    });

    previewBody.append(description, select, button, result);
    $("preview-modal").classList.add("show");
}

// EXTRACT INFORMATION
async function extractInformation(id) {
    const previewBody = $("preview-body");

    $("preview-title").textContent = "Key Information";
    previewBody.textContent = "Extracting information...";

    $("preview-modal").classList.add("show");

    try {
        const response = await fetch(`${API}/documents/${id}/extract`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || "Extraction failed");
        }

        previewBody.innerHTML = "";

        const information = data.information;

        Object.entries(information).forEach(([key, values]) => {
            const heading = document.createElement("h3");
            heading.textContent = key.replace("_", " ").toUpperCase();

            const list = document.createElement("ul");

            if (values.length === 0) {
                const item = document.createElement("li");
                item.textContent = "No information found";
                list.appendChild(item);

            } else {
                values.forEach(value => {
                    const item = document.createElement("li");
                    item.textContent = value;
                    list.appendChild(item);
                });
            }

            previewBody.append(heading, list);
        });

    } catch (error) {
        previewBody.textContent = error.message;
    }
}

// CLOSE PREVIEW
$("close-preview").addEventListener("click", () => {
    $("preview-modal").classList.remove("show");
});

$("preview-modal").addEventListener("click", event => {
    if (event.target === $("preview-modal")) {
        $("preview-modal").classList.remove("show");
    }
});

// DELETE DOCUMENT
async function deleteDocument(id) {
    if (!confirm("Are you sure you want to delete this document?")) {
        return;
    }

    try {
        const response = await fetch(`${API}/documents/${id}`, {
            method: "DELETE"
        });

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Delete failed");
        }

        showToast(result.message);
        await loadDocuments();

    } catch (error) {
        showToast(error.message);
    }
}

// CHOOSE FILE
$("choose-file").addEventListener("click", () => {
    $("file-input").click();
});

$("file-input").addEventListener("change", event => {
    addFiles(event.target.files);
    event.target.value = "";
});

// ADD FILES
function addFiles(files) {
    const allowed = ["pdf", "docx", "txt"];

    for (const file of files) {
        const extension = file.name.split(".").pop().toLowerCase();

        if (!allowed.includes(extension)) {
            showToast("Only PDF, DOCX and TXT files are supported.");
            continue;
        }

        if (file.size > 10 * 1024 * 1024) {
            showToast(file.name + " exceeds the 10 MB limit.");
            continue;
        }

        if (selectedFiles.some(item =>
            item.name === file.name && item.size === file.size
        )) {
            continue;
        }

        selectedFiles.push(file);
    }

    renderSelectedFiles();
}

// DISPLAY SELECTED FILES
function renderSelectedFiles() {
    const container = $("selected-files");
    container.innerHTML = "";

    selectedFiles.forEach((file, index) => {
        const row = document.createElement("div");
        row.className = "selected-file";

        const name = document.createElement("span");
        name.textContent =
            `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;

        const remove = document.createElement("button");
        remove.className = "remove-file";
        remove.textContent = "Remove";

        remove.addEventListener("click", () => {
            selectedFiles.splice(index, 1);
            renderSelectedFiles();
        });

        row.append(name, remove);
        container.appendChild(row);
    });

    $("upload-button").disabled = selectedFiles.length === 0;
}

// DRAG AND DROP
const dropZone = $("drop-zone");

dropZone.addEventListener("dragover", event => {
    event.preventDefault();
    dropZone.classList.add("dragging");
});

dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragging");
});

dropZone.addEventListener("drop", event => {
    event.preventDefault();
    dropZone.classList.remove("dragging");
    addFiles(event.dataTransfer.files);
});

// UPLOAD BUTTON
$("upload-button").addEventListener("click", uploadDocuments);

// UPLOAD DOCUMENTS
async function uploadDocuments() {
    if (selectedFiles.length === 0) return;

    const button = $("upload-button");
    const message = $("upload-message");

    button.disabled = true;
    button.textContent = "Uploading...";
    message.textContent = "";

    let successful = 0;
    const errors = [];

    for (const file of selectedFiles) {
        const formData = new FormData();
        formData.append("file", file);

        try {
            const response = await fetch(`${API}/documents`, {
                method: "POST",
                body: formData
            });

            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.error || "Upload failed");
            }

            successful++;

        } catch (error) {
            errors.push(`${file.name}: ${error.message}`);
        }
    }

    selectedFiles = [];
    renderSelectedFiles();

    button.textContent = "Upload Documents";
    button.disabled = true;

    if (successful > 0) {
        message.style.color = "#15803d";
        message.textContent =
            `${successful} document(s) uploaded successfully.`;
    }

    if (errors.length > 0) {
        message.style.color = "#dc4545";
        message.textContent += " " + errors.join(" | ");
    }

    await loadDocuments();

    showToast(`${successful} document(s) uploaded`);

    if (successful > 0) {
        setTimeout(() => showPage("documents"), 1200);
    }
}

// SEARCH DOCUMENTS
async function searchDocuments() {
    const query = $("search-input").value.trim();

    if (!query) {
        showToast("Please enter a search term.");
        return;
    }

    try {
        const response = await fetch(
            `${API}/search?q=${encodeURIComponent(query)}`
        );

        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.error || "Search failed");
        }

        renderDocuments(result, "all-documents");

    } catch (error) {
        showToast(error.message);
    }
}

$("search-button").addEventListener("click", searchDocuments);

$("search-input").addEventListener("keydown", event => {
    if (event.key === "Enter") {
        searchDocuments();
    }
});

// CLEAR SEARCH
$("clear-search").addEventListener("click", () => {
    $("search-input").value = "";
    renderDocuments(allDocuments, "all-documents");
});

// CHECK BACKEND
async function checkBackend() {
    try {
        const response = await fetch(`${API}/health`);

        if (!response.ok) {
            throw new Error("Backend unavailable");
        }

        await loadDocuments();

    } catch (error) {
        showToast("Backend is not running. Start Flask first.");
    }
}

checkBackend();
