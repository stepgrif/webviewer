"""Web file viewer.

Browse a mounted directory tree, render Markdown/HTML files, and download
any file. The served root is fixed to ROOT_DIR (a read-only volume mount).
"""

import os
import stat
from datetime import datetime, timezone

import markdown
from flask import Flask, Response, abort, render_template, request, send_file

ROOT_DIR = os.path.realpath(os.environ.get("ROOT_DIR", "/data"))
SHOW_HIDDEN = os.environ.get("SHOW_HIDDEN", "false").lower() == "true"

MARKDOWN_EXTENSIONS = {".md", ".markdown", ".mdown", ".mkd"}
HTML_EXTENSIONS = {".html", ".htm"}
TEXT_EXTENSIONS = {
    ".txt", ".log", ".csv", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".py", ".js", ".ts", ".sh", ".bash", ".c", ".h",
    ".cpp", ".hpp", ".java", ".go", ".rs", ".rb", ".php", ".sql", ".xml",
    ".css", ".env.example", ".dockerfile", ".makefile",
}

app = Flask(__name__)


def is_hidden(rel_path: str) -> bool:
    if SHOW_HIDDEN:
        return False
    return any(part.startswith(".") for part in rel_path.split("/") if part)


def safe_resolve(rel_path: str) -> str:
    """Resolve a user-supplied relative path inside ROOT_DIR or abort."""
    rel_path = rel_path.strip("/")
    candidate = os.path.realpath(os.path.join(ROOT_DIR, rel_path))
    if candidate != ROOT_DIR and not candidate.startswith(ROOT_DIR + os.sep):
        abort(403, "Path escapes the served root.")
    if rel_path and is_hidden(rel_path):
        abort(404)
    return candidate


def human_size(num: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num < 1024 or unit == "TB":
            return f"{num:,.0f} {unit}" if unit == "B" else f"{num:,.1f} {unit}"
        num /= 1024
    return f"{num:,.1f} TB"


def breadcrumbs(rel_path: str):
    crumbs = [{"name": "Home", "path": ""}]
    accumulated = []
    for part in [p for p in rel_path.split("/") if p]:
        accumulated.append(part)
        crumbs.append({"name": part, "path": "/".join(accumulated)})
    return crumbs


def list_directory(abs_path: str, rel_path: str):
    entries = []
    try:
        names = os.listdir(abs_path)
    except PermissionError:
        abort(403, "Permission denied reading this directory.")
    for name in sorted(names, key=str.lower):
        if not SHOW_HIDDEN and name.startswith("."):
            continue
        full = os.path.join(abs_path, name)
        try:
            st = os.stat(full)
        except OSError:
            continue
        is_dir = stat.S_ISDIR(st.st_mode)
        ext = os.path.splitext(name)[1].lower()
        entries.append({
            "name": name,
            "path": f"{rel_path}/{name}".strip("/"),
            "is_dir": is_dir,
            "size": "—" if is_dir else human_size(st.st_size),
            "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                     .strftime("%Y-%m-%d %H:%M"),
            "kind": ("dir" if is_dir
                     else "md" if ext in MARKDOWN_EXTENSIONS
                     else "html" if ext in HTML_EXTENSIONS
                     else "file"),
        })
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return entries


@app.route("/", defaults={"rel_path": ""})
@app.route("/browse/", defaults={"rel_path": ""})
@app.route("/browse/<path:rel_path>")
def browse(rel_path: str):
    abs_path = safe_resolve(rel_path)
    if not os.path.exists(abs_path):
        abort(404)

    if os.path.isdir(abs_path):
        return render_template(
            "listing.html",
            entries=list_directory(abs_path, rel_path),
            crumbs=breadcrumbs(rel_path),
            rel_path=rel_path,
        )
    return serve_file(abs_path, rel_path)


def serve_file(abs_path: str, rel_path: str) -> Response:
    if request.args.get("download") == "1":
        return send_file(abs_path, as_attachment=True,
                         download_name=os.path.basename(abs_path))

    ext = os.path.splitext(abs_path)[1].lower()

    if ext in MARKDOWN_EXTENSIONS and request.args.get("raw") != "1":
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except PermissionError:
            abort(403)
        body = markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "codehilite", "toc",
                        "sane_lists", "nl2br"],
            extension_configs={"codehilite": {"guess_lang": False,
                                              "noclasses": False}},
        )
        return render_template(
            "markdown.html",
            body=body,
            crumbs=breadcrumbs(rel_path),
            rel_path=rel_path,
            filename=os.path.basename(abs_path),
        )

    if ext in HTML_EXTENSIONS and request.args.get("raw") != "1":
        return send_file(abs_path, mimetype="text/html")

    if ext in MARKDOWN_EXTENSIONS or ext in HTML_EXTENSIONS or ext in TEXT_EXTENSIONS:
        return send_file(abs_path, mimetype="text/plain")

    return send_file(abs_path, as_attachment=True,
                     download_name=os.path.basename(abs_path))


@app.route("/download/<path:rel_path>")
def download(rel_path: str):
    abs_path = safe_resolve(rel_path)
    if not os.path.isfile(abs_path):
        abort(404)
    return send_file(abs_path, as_attachment=True,
                     download_name=os.path.basename(abs_path))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}


@app.errorhandler(403)
@app.errorhandler(404)
def error_page(err):
    return render_template("error.html", code=err.code,
                           message=err.description), err.code
