"""File conversion service — helpers and main conversion logic."""
import shutil
import subprocess
from pathlib import Path

from fastapi import HTTPException


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def ffmpeg_exe() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def pandoc_available() -> bool:
    return shutil.which("pandoc") is not None


def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


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


def _html_to_dest(html_str: str, dest: Path):
    to = dest.suffix.lower()
    if to in (".html", ".htm"):
        dest.write_text(html_str, encoding="utf-8")
        return
    if to in (".txt", ".md"):
        try:
            import html2text as h2t
        except ImportError:
            raise HTTPException(400, "html2text not installed — run: pip install html2text")
        h             = h2t.HTML2Text()
        h.body_width  = 0
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


def do_convert(filename: str, to_fmt: str, dl_dir: Path) -> str:
    """Convert a file and return the output filename."""
    src = dl_dir / filename
    if not src.exists():
        raise HTTPException(404, f"File not found: {filename}")

    ext  = src.suffix.lower()
    to   = to_fmt.lower().lstrip(".")
    dest = dl_dir / f"{src.stem}_converted.{to}"

    VIDEO_EXTS   = {".mp4", ".webm", ".avi", ".mov", ".mkv", ".flv"}
    AUDIO_CODECS = {"wav": "pcm_s16le", "aac": "aac", "ogg": "libvorbis", "flac": "flac"}
    DOC_EXTS     = {".docx", ".html", ".htm", ".md", ".txt"}

    if ext in VIDEO_EXTS and to in ("mp3", "wav", "aac", "ogg", "flac"):
        if not ffmpeg_available():
            raise HTTPException(400, "ffmpeg not available — install ffmpeg")
        codec = "libmp3lame" if to == "mp3" else AUDIO_CODECS[to]
        extra = ["-ab", "192k"] if to == "mp3" else []
        r = _run([ffmpeg_exe(), "-y", "-i", str(src), "-vn", "-acodec", codec] + extra + [str(dest)])
        if r.returncode != 0:
            raise HTTPException(500, r.stderr[-400:])

    elif ext in VIDEO_EXTS and to in ("mp4", "webm", "avi", "mkv", "mov"):
        if not ffmpeg_available():
            raise HTTPException(400, "ffmpeg not available — install ffmpeg")
        r = _run([ffmpeg_exe(), "-y", "-i", str(src), str(dest)])
        if r.returncode != 0:
            raise HTTPException(500, r.stderr[-400:])

    elif ext == ".pdf" and to == "docx":
        try:
            from pdf2docx import Converter
        except ImportError:
            raise HTTPException(400, "pdf2docx not installed — run: pip install pdf2docx")
        cv = Converter(str(src))
        cv.convert(str(dest))
        cv.close()

    elif ext == ".pdf" and to in ("txt", "html"):
        try:
            import pypdf
            import html as html_lib
        except ImportError:
            raise HTTPException(400, "pypdf not installed — run: pip install pypdf")
        reader = pypdf.PdfReader(str(src))
        text   = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if to == "txt":
            dest.write_text(text, encoding="utf-8")
        else:
            dest.write_text(f"<pre>{html_lib.escape(text)}</pre>", encoding="utf-8")

    elif ext in DOC_EXTS and to in ("html", "htm", "txt", "md", "pdf", "docx"):
        html_str = _doc_to_html(src)
        _html_to_dest(html_str, dest)

    else:
        raise HTTPException(400,
            f"Conversion {ext}→.{to} not supported. "
            "Supported: video→mp3/wav, pdf→docx/txt/html, docx/md/html/txt↔pdf/docx/md/html/txt")

    return dest.name
