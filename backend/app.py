
import os
import uuid
import re
from pathlib import Path
from collections import Counter
from io import BytesIO
from datetime import datetime, timezone

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document
from supabase import create_client
from dotenv import load_dotenv

from database import (
    create_tables,
    get_documents_collection,
    next_document_id
)


# ---------------------------------
# ENVIRONMENT AND CONFIGURATION
# ---------------------------------

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError(
        "Missing Supabase environment variables. "
        "Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
    )

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain"
}

documents_collection = get_documents_collection()


# ---------------------------------
# DOCUMENT RESPONSE FORMAT
# ---------------------------------

def format_document(document):

    if document is None:
        return None

    result = dict(document)

    result.pop("_id", None)

    uploaded_at = result.get("uploaded_at")

    if isinstance(uploaded_at, datetime):
        result["uploaded_at"] = uploaded_at.isoformat()

    return result


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

    names = re.findall(
        r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b',
        text
    )

    information["names"] = list(dict.fromkeys(names))[:20]

    dates = re.findall(
        r'\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|'
        r'\d{1,2}\s+(?:January|February|March|April|May|June|'
        r'July|August|September|October|November|December)\s+\d{4})\b',
        text,
        re.IGNORECASE
    )

    information["dates"] = list(dict.fromkeys(dates))[:20]

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

    amounts = re.findall(
        r'(?:₹|Rs\.?|INR|\$|USD|€|£)\s?[\d,]+(?:\.\d{1,2})?',
        text,
        re.IGNORECASE
    )

    information["amounts"] = list(dict.fromkeys(amounts))[:20]

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

    try:
        from database import client
        client.admin.command("ping")

        return jsonify({
            "status": "success",
            "message": "Document Management System backend is running",
            "mongodb": "connected",
            "database": "documind_ai"
        })

    except Exception as error:

        print("MONGODB HEALTH ERROR:", str(error))

        return jsonify({
            "status": "error",
            "message": "MongoDB connection failed",
            "mongodb": "disconnected"
        }), 503


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

    storage_uploaded = False

    try:

        uploaded_file.save(file_path)

        extracted_text = extract_text(file_path, extension)

        if not extracted_text.strip():

            return jsonify({
                "error": (
                    "No readable text found in this document. "
                    "Scanned PDFs may need OCR."
                )
            }), 400

        # Store the actual file in Supabase
        with open(file_path, "rb") as file:

            supabase.storage.from_("documents").upload(
                path=stored_name,
                file=file,
                file_options={
                    "content-type": CONTENT_TYPES[extension],
                    "upsert": "false"
                }
            )

        storage_uploaded = True

        # Store document details in MongoDB
        document_id = next_document_id()

        document = {
            "id": document_id,
            "filename": original_name,
            "stored_name": stored_name,
            "file_type": extension.upper(),
            "category": "Uncategorized",
            "extracted_text": extracted_text,
            "uploaded_at": datetime.now(timezone.utc)
        }

        documents_collection.insert_one(document)

        return jsonify({
            "message": "Document uploaded successfully",
            "document_id": document_id,
            "filename": original_name,
            "file_type": extension.upper()
        }), 201

    except Exception as error:

        print("UPLOAD ERROR:", str(error))

        if storage_uploaded:
            try:
                supabase.storage.from_("documents").remove([stored_name])
            except Exception as storage_error:
                print("SUPABASE CLEANUP ERROR:", str(storage_error))

        return jsonify({
            "error": "Document processing failed. Please try again."
        }), 500

    finally:

        file_path.unlink(missing_ok=True)


# ---------------------------------
# GET ALL DOCUMENTS
# ---------------------------------

@app.route("/api/documents", methods=["GET"])
def get_documents():

    try:

        documents = documents_collection.find().sort(
            "uploaded_at",
            -1
        )

        return jsonify([
            format_document(document)
            for document in documents
        ])

    except Exception as error:

        print("GET DOCUMENTS ERROR:", str(error))

        return jsonify({"error": "Unable to retrieve documents"}), 500


# ---------------------------------
# GET SINGLE DOCUMENT
# ---------------------------------

@app.route("/api/documents/<int:document_id>", methods=["GET"])
def get_document(document_id):

    try:

        document = documents_collection.find_one({
            "id": document_id
        })

        if document is None:
            return jsonify({"error": "Document not found"}), 404

        return jsonify(format_document(document))

    except Exception as error:

        print("GET DOCUMENT ERROR:", str(error))

        return jsonify({"error": "Unable to retrieve document"}), 500


# ---------------------------------
# VIEW DOCUMENT
# ---------------------------------

@app.route("/api/documents/<int:document_id>/view", methods=["GET"])
def view_document(document_id):

    try:

        document = documents_collection.find_one({
            "id": document_id
        })

        if document is None:
            return jsonify({"error": "Document not found"}), 404

        stored_name = document["stored_name"]
        filename = document["filename"]
        extension = document["file_type"].lower()

        file_data = supabase.storage.from_("documents").download(
            stored_name
        )

        return send_file(
            BytesIO(file_data),
            mimetype=CONTENT_TYPES.get(
                extension,
                "application/octet-stream"
            ),
            download_name=filename,
            as_attachment=False
        )

    except Exception as error:

        print("SUPABASE VIEW ERROR:", str(error))

        return jsonify({
            "error": "Unable to retrieve document from storage"
        }), 500


# ---------------------------------
# DELETE DOCUMENT
# ---------------------------------

@app.route("/api/documents/<int:document_id>", methods=["DELETE"])
def delete_document(document_id):

    try:

        document = documents_collection.find_one({
            "id": document_id
        })

        if document is None:
            return jsonify({"error": "Document not found"}), 404

        stored_name = document["stored_name"]

        try:

            supabase.storage.from_("documents").remove([stored_name])

        except Exception as storage_error:

            print("SUPABASE DELETE ERROR:", str(storage_error))

            return jsonify({
                "error": "Could not delete document from storage"
            }), 500

        documents_collection.delete_one({
            "id": document_id
        })

        local_file = UPLOAD_FOLDER / stored_name
        local_file.unlink(missing_ok=True)

        return jsonify({
            "message": "Document deleted successfully"
        })

    except Exception as error:

        print("DELETE DOCUMENT ERROR:", str(error))

        return jsonify({"error": "Unable to delete document"}), 500


# ---------------------------------
# SEARCH DOCUMENTS
# ---------------------------------

@app.route("/api/search", methods=["GET"])
def search_documents():

    query = request.args.get("q", "").strip()

    if not query:
        return jsonify({"error": "Enter a search term"}), 400

    try:

        search_pattern = re.escape(query)

        documents = documents_collection.find({
            "$or": [
                {"filename": {"$regex": search_pattern, "$options": "i"}},
                {"extracted_text": {"$regex": search_pattern, "$options": "i"}},
                {"category": {"$regex": search_pattern, "$options": "i"}}
            ]
        }).sort("uploaded_at", -1)

        return jsonify([
            format_document(document)
            for document in documents
        ])

    except Exception as error:

        print("SEARCH ERROR:", str(error))

        return jsonify({"error": "Search failed"}), 500


# ---------------------------------
# DOCUMENT SUMMARIZATION API
# ---------------------------------

@app.route(
    "/api/documents/<int:document_id>/summarize",
    methods=["POST"]
)
def summarize_document(document_id):

    data = request.get_json(silent=True) or {}

    length = data.get("length", "short")

    if not isinstance(length, str):
        return jsonify({
            "error": "Choose short, medium or detailed summary"
        }), 400

    length = length.lower()

    if length not in ["short", "medium", "detailed"]:

        return jsonify({
            "error": "Choose short, medium or detailed summary"
        }), 400

    try:

        document = documents_collection.find_one(
            {"id": document_id},
            {"filename": 1, "extracted_text": 1, "_id": 0}
        )

        if document is None:
            return jsonify({"error": "Document not found"}), 404

        summary = generate_summary(
            document.get("extracted_text", ""),
            length
        )

        return jsonify({
            "filename": document["filename"],
            "summary_type": length,
            "summary": summary
        })

    except Exception as error:

        print("SUMMARY ERROR:", str(error))

        return jsonify({"error": "Unable to summarize document"}), 500


# ---------------------------------
# KEY INFORMATION EXTRACTION API
# ---------------------------------

@app.route(
    "/api/documents/<int:document_id>/extract",
    methods=["GET"]
)
def extract_document_information(document_id):

    try:

        document = documents_collection.find_one(
            {"id": document_id},
            {"filename": 1, "extracted_text": 1, "_id": 0}
        )

        if document is None:
            return jsonify({"error": "Document not found"}), 404

        information = extract_key_information(
            document.get("extracted_text", "")
        )

        return jsonify({
            "filename": document["filename"],
            "information": information
        })

    except Exception as error:

        print("EXTRACTION ERROR:", str(error))

        return jsonify({
            "error": "Unable to extract document information"
        }), 500


# ---------------------------------
# FILE SIZE ERROR
# ---------------------------------

@app.errorhandler(413)
def file_too_large(error):

    return jsonify({
        "error": "File is too large. Maximum size is 10 MB."
    }), 413


# ---------------------------------
# CONNECT TO MONGODB
# ---------------------------------

create_tables()


# ---------------------------------
# START BACKEND
# ---------------------------------

if __name__ == "__main__":

    print("Document Management System backend started!")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
