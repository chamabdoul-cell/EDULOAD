"""File conversion service — hardened with size/MIME/timeout/path-traversal checks."""
import concurrent.futures
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from fastapi import HTTPException

# ── Configuration ─────────────────────────────────────────────────────────────

MAX_CONVERT_SIZE_MB = int(os.getenv("MAX_CONVERT_SIZE_MB", "50"))
CONVERT_TIMEOUT     = int(os.getenv("CONVERT_TIMEOUT", "120"))

# ── Tool detection ─────────────────────────────────────────────────────────────

def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffmpeg_exe() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


# ── Security guard 1: path traversal ─────────────────────────────────────────

def _check_path(filename: str, dl_dir: Path) -> Path:
    """Return resolved path or raise HTTP 400 if filename escapes dl_dir."""
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        raise HTTPException(400, "Invalid filename: path traversal not allowed")
    resolved    = (dl_dir / filename).resolve()
    dl_resolved = dl_dir.resolve()
    try:
        resolved.relative_to(dl_resolved)
    except ValueError:
        raise HTTPException(400, "Invalid filename: path traversal not allowed")
    return resolved


# ── Security guard 2: file size ───────────────────────────────────────────────

def _check_size(src: Path) -> None:
    """Raise HTTP 413 if file exceeds MAX_CONVERT_SIZE_MB."""
    size_mb = src.stat().st_size / (1024 * 1024)
    if size_mb > MAX_CONVERT_SIZE_MB:
        raise HTTPException(
            413,
            f"File too large: {size_mb:.1f} MB (max {MAX_CONVERT_SIZE_MB} MB)",
        )


# ── Security guard 3: MIME / magic-byte validation ────────────────────────────

_MAGIC: dict[str, list[bytes]] = {
    ".pdf":  [b"%PDF"],
    ".docx": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    ".webm": [b"\x1a\x45\xdf\xa3"],
    ".mkv":  [b"\x1a\x45\xdf\xa3"],
    ".flv":  [b"FLV"],
    ".avi":  [b"RIFF"],
    # txt, md, html, mp4, mov — no reliable single magic; skip check
}


def _check_mime(src: Path) -> None:
    """Raise HTTP 415 if file magic bytes don't match the declared extension."""
    allowed = _MAGIC.get(src.suffix.lower())
    if not allowed:
        return  # no signature defined for this extension — skip
    header = src.read_bytes()[:16]
    if not any(header.startswith(sig) for sig in allowed):
        raise HTTPException(
            415,
            f"File content does not match declared extension '{src.suffix}'. "
            "Possible content-type mismatch.",
        )


# ── Security guard 4: timeout wrapper ────────────────────────────────────────

def _timeout_call(fn):
    """Run fn() in a thread; raise HTTP 504 if it exceeds CONVERT_TIMEOUT seconds."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exe:
        future = exe.submit(fn)
        try:
            return future.result(timeout=CONVERT_TIMEOUT)
        except concurrent.futures.TimeoutError:
            raise HTTPException(504, f"Conversion timed out after {CONVERT_TIMEOUT} s")


# ── ffmpeg runner with kill-on-timeout ────────────────────────────────────────

def _run_ffmpeg(cmd: list) -> None:
    """Run an ffmpeg command with timeout; kill the subprocess and raise 504 on timeout."""
    proc_ref: list[subprocess.Popen] = []

    def _do():
        p = subprocess.Popen(cmd, capture_output=True, text=True)
        proc_ref.append(p)
        stdout, stderr = p.communicate()
        return p.returncode, stderr

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exe:
        future = exe.submit(_do)
        try:
            returncode, stderr = future.result(timeout=CONVERT_TIMEOUT)
        except concurrent.futures.TimeoutError:
            if proc_ref:
                proc_ref[0].kill()
            raise HTTPException(504, f"Conversion timed out after {CONVERT_TIMEOUT} s")
    if returncode != 0:
        raise HTTPException(500, stderr[-400:])


# ── Document → HTML helpers ───────────────────────────────────────────────────

def _doc_to_html(src: Path) -> str:
    ext = src.suffix.lower()
    if ext in (".html", ".htm"):
        return src.read_text(encoding="utf-8")
    if ext == ".md":
        try:
            import markdown as md_lib
            return md_lib.markdown(src.read_text(encoding="utf-8"),
                                   extensions=["tables", "fenced_code"])
        except ImportError:
            raise HTTPException(400, "markdown not installed — run: pip install markdown")
    if ext == ".txt":
        import html as html_lib
        return f"<pre>{html_lib.escape(src.read_text(encoding='utf-8'))}</pre>"
    if ext == ".docx":
        try:
            import mammoth
            return mammoth.convert_to_html(open(str(src), "rb")).value
        except ImportError:
            raise HTTPException(400, "mammoth not installed — run: pip install mammoth")
    raise HTTPException(400, f"Cannot read {ext} as source document")


def _html_to_dest(html_str: str, dest: Path) -> None:
    to = dest.suffix.lower()
    if to in (".html", ".htm"):
        dest.write_text(html_str, encoding="utf-8")
        return
    if to in (".txt", ".md"):
        try:
            import html2text as h2t
        except ImportError:
            raise HTTPException(400, "html2text not installed — run: pip install html2text")
        h              = h2t.HTML2Text()
        h.body_width   = 0
        h.ignore_links = (to == ".txt")
        dest.write_text(h.handle(html_str), encoding="utf-8")
        return
    if to == ".pdf":
        try:
            from xhtml2pdf import pisa
        except ImportError:
            raise HTTPException(400, "xhtml2pdf not installed — run: pip install xhtml2pdf")
        with open(dest, "wb") as f:
            res = pisa.CreatePDF(html_str, dest=f)
        if res.err:
            raise HTTPException(500, "xhtml2pdf: PDF creation failed")
        return
    if to == ".docx":
        try:
            from docx import Document
            import html2text as h2t
        except ImportError:
            raise HTTPException(400, "python-docx / html2text not installed")
        h            = h2t.HTML2Text()
        h.body_width = 0
        text         = h.handle(html_str)
        doc          = Document()
        for para in text.split("\n\n"):
            p = para.strip()
            if p:
                doc.add_paragraph(p)
        doc.save(str(dest))
        return
    raise HTTPException(400, f"Unsupported output format: {to}")


# ── Main entry point ──────────────────────────────────────────────────────────

def do_convert(filename: str, to_fmt: str, dl_dir: Path) -> str:
    """Validate, sandbox, convert, and return the output filename in dl_dir."""
    # Guard 1: path traversal
    src = _check_path(filename, dl_dir)
    if not src.exists():
        raise HTTPException(404, f"File not found: {filename}")

    # Guard 2 & 3: size and MIME
    _check_size(src)
    _check_mime(src)

    ext = src.suffix.lower()
    to  = to_fmt.lower().lstrip(".")

    VIDEO_EXTS   = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv"}
    AUDIO_CODECS = {"wav": "pcm_s16le", "aac": "aac", "ogg": "libvorbis", "flac": "flac"}
    DOC_EXTS     = {".docx", ".html", ".htm", ".md", ".txt"}

    # Guard 4 & 5: temp-dir isolation + timeout on all conversion paths
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        tmp_src  = tmp_path / src.name
        shutil.copy2(src, tmp_src)
        tmp_dest = tmp_path / f"{src.stem}_converted.{to}"

        if ext in VIDEO_EXTS and to in ("mp3", "wav", "aac", "ogg", "flac"):
            if not ffmpeg_available():
                raise HTTPException(400, "ffmpeg not available — install ffmpeg")
            codec = "libmp3lame" if to == "mp3" else AUDIO_CODECS[to]
            extra = ["-ab", "192k"] if to == "mp3" else []
            _run_ffmpeg([ffmpeg_exe(), "-y", "-i", str(tmp_src),
                         "-vn", "-acodec", codec] + extra + [str(tmp_dest)])

        elif ext in VIDEO_EXTS and to in ("mp4", "webm", "avi", "mkv", "mov"):
            if not ffmpeg_available():
                raise HTTPException(400, "ffmpeg not available — install ffmpeg")
            _run_ffmpeg([ffmpeg_exe(), "-y", "-i", str(tmp_src), str(tmp_dest)])

        elif ext == ".pdf" and to == "docx":
            tmp_src_str  = str(tmp_src)
            tmp_dest_str = str(tmp_dest)

            def _do_pdf_docx():
                try:
                    from pdf2docx import Converter
                except ImportError:
                    raise HTTPException(400,
                        "pdf2docx not installed — run: pip install pdf2docx")
                cv = Converter(tmp_src_str)
                cv.convert(tmp_dest_str)
                cv.close()

            _timeout_call(_do_pdf_docx)

        elif ext == ".pdf" and to in ("txt", "html"):
            tmp_src_str = str(tmp_src)
            _to         = to  # capture for closure

            def _do_pdf_text():
                try:
                    import pypdf
                    import html as html_lib
                except ImportError:
                    raise HTTPException(400,
                        "pypdf not installed — run: pip install pypdf")
                reader = pypdf.PdfReader(tmp_src_str)
                text   = "\n\n".join(page.extract_text() or "" for page in reader.pages)
                if _to == "txt":
                    tmp_dest.write_text(text, encoding="utf-8")
                else:
                    tmp_dest.write_text(
                        f"<pre>{html_lib.escape(text)}</pre>", encoding="utf-8"
                    )

            _timeout_call(_do_pdf_text)

        elif ext in DOC_EXTS and to in ("html", "htm", "txt", "md", "pdf", "docx"):
            _tmp_src  = tmp_src
            _tmp_dest = tmp_dest

            def _do_doc():
                html_str = _doc_to_html(_tmp_src)
                _html_to_dest(html_str, _tmp_dest)

            _timeout_call(_do_doc)

        else:
            raise HTTPException(400,
                f"Conversion {ext}→.{to} not supported. "
                "Supported: video→mp3/wav, pdf→docx/txt/html, "
                "docx/md/html/txt↔pdf/docx/md/html/txt")

        if not tmp_dest.exists():
            raise HTTPException(500, "Conversion produced no output file")

        final_dest = dl_dir / tmp_dest.name
        shutil.copy2(tmp_dest, final_dest)

    return final_dest.name
