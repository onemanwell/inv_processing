import sys
import os
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "False"
import logging
from pathlib import Path
from tkinter import Tk, filedialog
import numpy as np
import pdfplumber
import fitz
from paddleocr import PaddleOCR
from PIL import Image


logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

VALID_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

_ocr = None

def get_ocr() -> PaddleOCR:
    global _ocr
    if _ocr is None:
        _ocr = PaddleOCR(
            # use local detection model (language-agnostic)
            det_model_dir='ocrmodels/Multilingual_PP-OCRv3_det_infer',
            # use multilingual recognition model (supports English + Spanish)
            rec_model_dir='ocrmodels/latin_PP-OCRv3_rec_infer',
            # use angle classifier for rotated text
            cls_model_dir='ocrmodels/ch_ppocr_mobile_v2.0_cls_infer',
            use_angle_cls=True,
            use_gpu=False,
            show_log=False
        )
    return _ocr
def __repr__(self): 
    status = "OK" if self.ok else f"ERROR: {self.error}" 
    return f"Document('{self.name}', method='{self.method}', status='{status}')" 

# file selection dialog
def select_files() -> list[Path]:
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    paths = filedialog.askopenfilenames(
        title="Seleccione los archivos",
        filetypes=[
            ("Supported files", "*.pdf *.jpg *.jpeg *.png *.tiff *.tif *.bmp *.webp"),
            ("All files", "*.*"),
        ],
    )
    root.destroy()

    files = [Path(p) for p in paths]
    return [f for f in files if f.suffix.lower() in VALID_EXTENSIONS]

# check if PDF contains embedded text
def _pdf_has_text(path: Path) -> bool:
    try:
        with pdfplumber.open(path) as pdf:
            text = "".join((p.extract_text() or "") for p in pdf.pages[:3])
            return len(text.split()) >= 10
    except Exception:
        return False

# extract text from digital PDF
def _extract_with_pdfplumber(path: Path) -> str:
    parts = []

    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            tables = page.extract_tables()
            table_text = ""

            if tables:
                for table in tables:
                    for row in table:
                        clean_row = [str(c).strip() for c in row if c and str(c).strip()]
                        if clean_row:
                            table_text += " | ".join(clean_row) + "\n"

            free_text = page.extract_text() or ""

            content = ""
            if table_text:
                content += f"[TABLE]\n{table_text}\n"
            if free_text:
                content += f"[TEXT]\n{free_text}\n"

            if content.strip():
                parts.append(f"--- Page {i + 1} ---\n{content.strip()}")

    return "\n\n".join(parts)

# convert PDF pages to images using PyMuPDF
def _pdf_to_images(path: Path):
    doc = fitz.open(path)
    images = []

    for page in doc:
        pix = page.get_pixmap(dpi=300)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)

    return images

# run OCR on images
def _extract_with_paddleocr(images: list[Image.Image]) -> str:
    ocr = get_ocr()
    parts = []

    for i, img in enumerate(images):
        result = ocr.ocr(np.array(img), cls=True)

        if not result or not result[0]:
            continue

        # sort lines top-to-bottom, then left-to-right
        lines = sorted(result[0], key=lambda x: (x[0][0][1], x[0][0][0]))

        page_text = ""
        for line in lines:
            text, confidence = line[1][0], line[1][1]
            if confidence >= 0.6 and text.strip():
                page_text += text.strip() + "\n"

        if page_text.strip():
            parts.append(f"--- Page {i + 1} ---\n{page_text.strip()}")

    return "\n\n".join(parts)

# clean text before sending to LLM
def clean_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        line = line.strip()
        if len(line) < 2:
            continue
        cleaned.append(line)

    return "\n".join(cleaned)

# main extraction logic
def extract_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        if _pdf_has_text(path):
            text = _extract_with_pdfplumber(path)
            return clean_text(text), "pdfplumber"
        else:
            images = _pdf_to_images(path)
            text = _extract_with_paddleocr(images)
            return clean_text(text), "paddleocr"

    elif suffix in VALID_EXTENSIONS:
        text = _extract_with_paddleocr([Image.open(path)])
        return clean_text(text), "paddleocr"

    else:
        raise ValueError(f"Unsupported extension: {suffix}")

# document container
class Document:
    def __init__(self, path: Path, text: str, method: str, error: str | None = None):
        self.path = path
        self.name = path.name
        self.text = text
        self.method = method
        self.error = error
        self.ok = error is None and len(text.strip()) > 20

def save_text(text, filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))  # carpeta del script
    filepath = os.path.join(base_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)

def select_and_extract() -> list[Document]:
    files = select_files()
    if not files:
        return []

    documents = []

    for path in files:
        try:
            text, method = extract_text(path)
            doc = Document(path, text, method)
        except Exception as e:
            logger.error(f"Error processing {path.name}: {e}")
            doc = Document(path, "", "error", error=str(e))

        documents.append(doc)

    logger.info(f"Extraction completed: {sum(d.ok for d in documents)}/{len(documents)} OK")

    return documents
