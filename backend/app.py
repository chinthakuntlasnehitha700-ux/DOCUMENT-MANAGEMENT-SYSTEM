
import os
import uuid
import re
from pathlib import Path
from collections import Counter

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document

from database import get_connection, create_tables


app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"

UPLOAD_FOLDER.mkdir(exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}


# ---------------------------------
# TEXT SUMMARIZATION
# ---------------------------------

STOP_WORDS = {
    "the", "is", "are", "was", "were", "a", "an", "and",
    "or", "but", "in", "on", "at", "to", "of", "for",
    "with", "by", "from", "as", "it", "this", "that",
    "these", "those", "be", "been", "being", "has",
    "have", "had", "do", "does", "did", "will", "would",
    "can", "could", "should", "may", "might", "must",
    "we", "you", "they", "he", "she", "i", "them",
    "their", "our", "your", "its", "not", "if", "then"
}


def generate_summary(text, length):

    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    sentences = [
        sentence.strip()
        for sentence in sentences
        if len(sentence.split()) > 3
    ]

    if not sentences:
        return "Not enough readable text to generate a summary."

    word_frequency = Counter()

    for sentence in sentences:
        words = re.findall(r'\b[a-zA-Z]{3,}\b', sentence.lower())

        word_frequency.update(
            word for word in words if word not in STOP_WORDS
        )

    if not word_frequency:
        return "Not enough meaningful text to generate a summary."

    max_frequency = max(word_frequency.values())

    for word in word_frequency:
        word_frequency[word] /= max_frequency

    scored_sentences = []

    for index, sentence in enumerate(sentences):

        words = re.findall(r'\b[a-zA-Z]{3,}\b', sentence.lower())

        meaningful_words = [
            word for word in words if word not in STOP_WORDS
        ]

        if meaningful_words:
            score = sum(
                word_frequency[word] for word in meaningful_words
            ) / len(meaningful_words)
        else:
            score = 0

        scored_sentences.append((score, index, sentence))

    sentence_limits = {
        "short": 3,
        "medium": 6,
        "detailed": 10
    }

    limit = sentence_limits.get(length, 3)

    selected = sorted(
        scored_sentences,
        key=lambda item: item[0],
        reverse=True
    )[:limit]

    selected.sort(key=lambda item: item[1])

    return " ".join(item[2] for item in selected)


# ---------------------------------
# KEY INFORMATION EXTRACTION
# ---------------------------------

def extract_key_information(text):

    information = {
        "names": [],
        "dates": [],
        "deadlines": [],
        "amounts": [],
        "important_terms": []
    }

    # Extract possible names
    names = re.findall(
        r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b',
        text
    )

    information["names"] = list(dict.fromkeys(names))[:20]

    # Extract dates
    dates = re.findall(
        r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|'
        r'\d{1,2}\s+(?:January|February|March|April|May|June|'
        r'July|August|September|October|November|December)\s+\d{4})\b',
        text,
        re.IGNORECASE
    )

    information["dates"] = list(dict.fromkeys(dates))[:20]

    # Extract deadline-related sentences
    deadline_sentences = re.findall(
        r'[^.!?]*(?:deadline|due date|submit by|submission date|'
        r'last date|before the date)[^.!?]*[.!?]?',
        text,
        re.IGNORECASE
    )

    information["deadlines"] = [
        sentence.strip()
        for sentence in deadline_sentences[:10]
    ]

    # Extract monetary amounts
    amounts = re.findall(
        r'(?:₹|Rs\.?|INR|\$|USD|€|£)\s?[\d,]+(?:\.\d{1,2})?',
        text,
        re.IGNORECASE
    )

    information["amounts"] = list(dict.fromkeys(amounts))[:20]

    # Identify important terms
    terms = [
        "agreement", "payment", "deadline", "submission",
        "contract", "project", "salary", "invoice",
        "approval", "requirement", "penalty", "renewal"
    ]

    lower_text = text.lower()

    information["important_terms"] = [
        term for term in terms if term in lower_text
    ]

    return information


# ---------------------------------
# FILE VALIDATION
# ---------------------------------

def allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ---------------------------------
# DOCUMENT TEXT EXTRACTION
# ---------------------------------

def extract_text(file_path, extension):

    if extension == "pdf":

        reader = PdfReader(str(file_path))

        return "\n".join(
            page.extract_text() or "" for page in reader.pages
        )

    if extension == "docx":

        document = Document(str(file_path))

        return "\n".join(
            paragraph.text for paragraph in document.paragraphs
        )

    if extension == "txt":

        return file_path.read_text(encoding="utf-8-sig")

    return ""


# ---------------------------------
# HEALTH API
# ---------------------------------

@app.route("/api/health", methods=["GET"])
def health():

    return jsonify({
        "status": "success",
        "message": "Document Management System backend is running"
    })


# ---------------------------------
# UPLOAD DOCUMENT
# ---------------------------------

@app.route("/api/documents", methods=["POST"])
def upload_document():

    if "file" not in request.files:
        return jsonify({"error": "Please select a document"}), 400

    uploaded_file = request.files["file"]

    if uploaded_file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(uploaded_file.filename):
        return jsonify({
            "error": "Only PDF, DOCX and TXT files are allowed"
        }), 400

    original_name = secure_filename(uploaded_file.filename)

    if not original_name:
        return jsonify({"error": "Invalid filename"}), 400

    extension = original_name.rsplit(".", 1)[1].lower()

    stored_name = f"{uuid.uuid4().hex}.{extension}"

    file_path = UPLOAD_FOLDER / stored_name

    uploaded_file.save(file_path)

    try:

        extracted_text = extract_text(file_path, extension)

        if not extracted_text.strip():

            file_path.unlink(missing_ok=True)

            return jsonify({
                "error": "No readable text found in this document. Scanned PDFs may need OCR."
            }), 400

        connection = get_connection()

        cursor = connection.execute("""
            INSERT INTO documents
            (filename, stored_name, file_type, category, extracted_text)
            VALUES (?, ?, ?, ?, ?)
        """, (
            original_name,
            stored_name,
            extension.upper(),
            "Uncategorized",
            extracted_text
        ))

        document_id = cursor.lastrowid

        connection.commit()
        connection.close()

        return jsonify({
            "message": "Document uploaded successfully",
            "document_id": document_id,
            "filename": original_name,
            "file_type": extension.upper()
        }), 201

    except Exception as error:

        file_path.unlink(missing_ok=True)

        return jsonify({
            "error": f"Document processing failed: {str(error)}"
        }), 500


# ---------------------------------
# GET ALL DOCUMENTS
# ---------------------------------

@app.route("/api/documents", methods=["GET"])
def get_documents():

    connection = get_connection()

    documents = connection.execute("""
        SELECT id, filename, file_type, category, uploaded_at
        FROM documents
        ORDER BY uploaded_at DESC
    """).fetchall()

    connection.close()

    return jsonify([dict(document) for document in documents])


# ---------------------------------
# GET SINGLE DOCUMENT
# ---------------------------------

@app.route("/api/documents/<int:document_id>", methods=["GET"])
def get_document(document_id):

    connection = get_connection()

    document = connection.execute("""
        SELECT * FROM documents WHERE id = ?
    """, (document_id,)).fetchone()

    connection.close()

    if document is None:
        return jsonify({"error": "Document not found"}), 404

    result = dict(document)

    return jsonify(result)


# ---------------------------------
# VIEW DOCUMENT
# ---------------------------------

@app.route("/api/documents/<int:document_id>/view", methods=["GET"])
def view_document(document_id):

    connection = get_connection()

    document = connection.execute("""
        SELECT stored_name FROM documents WHERE id = ?
    """, (document_id,)).fetchone()

    connection.close()

    if document is None:
        return jsonify({"error": "Document not found"}), 404

    return send_from_directory(
        UPLOAD_FOLDER,
        document["stored_name"],
        as_attachment=False
    )


# ---------------------------------
# DELETE DOCUMENT
# ---------------------------------

@app.route("/api/documents/<int:document_id>", methods=["DELETE"])
def delete_document(document_id):

    connection = get_connection()

    document = connection.execute("""
        SELECT stored_name FROM documents WHERE id = ?
    """, (document_id,)).fetchone()

    if document is None:

        connection.close()

        return jsonify({"error": "Document not found"}), 404

    connection.execute("""
        DELETE FROM documents WHERE id = ?
    """, (document_id,))

    connection.commit()
    connection.close()

    file_path = UPLOAD_FOLDER / document["stored_name"]

    file_path.unlink(missing_ok=True)

    return jsonify({
        "message": "Document deleted successfully"
    })


# ---------------------------------
# SEARCH DOCUMENTS
# ---------------------------------

@app.route("/api/search", methods=["GET"])
def search_documents():

    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"error": "Enter a search term"}), 400

    connection = get_connection()

    documents = connection.execute("""
        SELECT id, filename, file_type, category, uploaded_at
        FROM documents
        WHERE filename LIKE ? OR extracted_text LIKE ?
        ORDER BY uploaded_at DESC
    """, (f"%{query}%", f"%{query}%")).fetchall()

    connection.close()

    return jsonify([dict(document) for document in documents])


# ---------------------------------
# DOCUMENT SUMMARIZATION API
# ---------------------------------

@app.route("/api/documents/<int:document_id>/summarize", methods=["POST"])
def summarize_document(document_id):

    data = request.get_json(silent=True) or {}

    length = data.get("length", "short").lower()

    if length not in ["short", "medium", "detailed"]:

        return jsonify({
            "error": "Choose short, medium or detailed summary"
        }), 400

    connection = get_connection()

    document = connection.execute("""
        SELECT filename, extracted_text
        FROM documents
        WHERE id = ?
    """, (document_id,)).fetchone()

    connection.close()

    if document is None:
        return jsonify({"error": "Document not found"}), 404

    summary = generate_summary(
        document["extracted_text"],
        length
    )

    return jsonify({
        "filename": document["filename"],
        "summary_type": length,
        "summary": summary
    })


# ---------------------------------
# KEY INFORMATION EXTRACTION API
# ---------------------------------

@app.route(
    "/api/documents/<int:document_id>/extract",
    methods=["GET"]
)
def extract_document_information(document_id):

    connection = get_connection()

    document = connection.execute("""
        SELECT filename, extracted_text
        FROM documents
        WHERE id = ?
    """, (document_id,)).fetchone()

    connection.close()

    if document is None:
        return jsonify({"error": "Document not found"}), 404

    information = extract_key_information(
        document["extracted_text"]
    )

    return jsonify({
        "filename": document["filename"],
        "information": information
    })


# ---------------------------------
# FILE SIZE ERROR
# ---------------------------------

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({
        "error": "File is too large. Maximum size is 10 MB."
    }), 413


# ---------------------------------
# START BACKEND
# ---------------------------------

if __name__ == "__main__":

    create_tables()

    print("Document Management System backend started!")

    app.run(host="127.0.0.1", port=5000, debug=False)
