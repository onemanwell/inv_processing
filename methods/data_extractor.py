import sys
import os
import logging
from pathlib import Path
from tkinter import Tk, filedialog
import numpy as np
import pdfplumber
import fitz
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
from paddleocr import PaddleOCR
from PIL import Image
from methods.invoice_scrapper import extract_nbr
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

VALID_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}

_ocr = None

def get_ocr() -> PaddleOCR:
    global _ocr
    if _ocr is None:
        _ocr = PaddleOCR(
            # use local detection model (language-agnostic)
            text_detection_model_dir=r'ocrmodels\Multilingual_PP-OCRv3_det_infer',
            # use multilingual recognition model (supports English + Spanish)
            text_recognition_model_dir=r'ocrmodels\latin_PP-OCRv3_rec_infer',
            use_angle_cls=True,
            cls_model_dir=r'ocrmodels\ch_ppocr_mobile_v2.0_cls_infer'    
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

def split_file(pages): #method for splitting  files by document number (in case there is multiple documents in a single file)
    indep_docs = []
    current_doc = []
    current_number = None

    for page in pages:
        lines = page["lines"]
        page_number = extract_nbr(lines)

        if not current_doc:
            current_doc.append(page)
            current_number = page_number
            continue

        if page_number is None or page_number == current_number:
            current_doc.append(page)
        else:
            indep_docs.append(current_doc)
            current_doc = [page]
            current_number = page_number

    if current_doc:
        indep_docs.append(current_doc)


    return indep_docs

# extract text from digital PDF
def scrape_pdfs(pdf_path: str, y_tolerance: int = 3) -> list:
    words = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_index, page in enumerate(pdf.pages):
            page_words = page.extract_words(
                use_text_flow=True, keep_blank_chars=False
            )
            for w in page_words:
                w["_page"] = page_index
                words.append(w)

    words.sort(key=lambda w: (w["_page"], w["top"]))

    line_map: dict = {}
    for w in words:
        key = (w["_page"], round(w["top"] / y_tolerance))
        line_map.setdefault(key, []).append(w)

    result = sorted(line_map.values(), key=lambda ln: (ln[0]["_page"], ln[0]["top"]))
    for ln in result:
        ln.sort(key=lambda w: w["x0"])
    
    return result

def lines_to_text(lines: list) -> str:
    result = []
    for line in lines:
        text_line = " ".join(w["text"] for w in line)
        result.append(text_line)
    return "\n".join(result)

#for scanned PDFS, which don't have embedded text, convert each page to an image and run OCR on it
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
    words = []

    for page_idx, img in enumerate(images):
        result = ocr.ocr(np.array(img), cls=True)

        if not result or not result[0]:
            continue

        for line in result[0]:
            bbox = line[0]
            text = line[1][0]
            confidence = line[1][1]

            if confidence < 0.6 or not text.strip():
                continue

            # extraer coordenadas tipo pdfplumber
            x0 = min(p[0] for p in bbox)
            x1 = max(p[0] for p in bbox)
            top = min(p[1] for p in bbox)

            words.append({
                "text": text.strip(),
                "x0": x0,
                "x1": x1,
                "top": top,
                "_page": page_idx
            })

    # reconstrucción de líneas con coordenadas
    words.sort(key=lambda w: (w["_page"], w["top"]))

    lines = []
    current_line = []
    current_y = None
    y_tolerance = 12

    for w in words:
        if not current_line:
            current_line = [w]
            current_y = w["top"]
            continue

        same_page = w["_page"] == current_line[0]["_page"]

        if same_page and abs(w["top"] - current_y) <= y_tolerance:
            current_line.append(w)
            current_y = (current_y + w["top"]) / 2
        else:
            lines.append(sorted(current_line, key=lambda x: x["x0"]))
            current_line = [w]
            current_y = w["top"]

    if current_line:
        normalized_y = min(w["top"] for w in current_line)

        for item in current_line:
            item["top"] = normalized_y

        lines.append(sorted(current_line, key=lambda x: x["x0"]))

    return lines

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

    if suffix in VALID_EXTENSIONS and suffix != ".pdf":
        lines = _extract_with_paddleocr([Image.open(path)])
        return [(lines, "paddleocr")]

    if suffix == ".pdf":
        pages = []

        if _pdf_has_text(path):
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    page_words = page.extract_words(
                        use_text_flow=True,
                        keep_blank_chars=False
                    )

                    words = []

                    for w in page_words:
                        words.append({
                            "text": w["text"],
                            "x0": w["x0"],
                            "x1": w["x1"],
                            "top": w["top"],
                            "_page": 0
                        })

                    words.sort(key=lambda w: w["top"])

                    line_map = {}
                    y_tolerance = 3

                    for w in words:
                        key = round(w["top"] / y_tolerance)
                        line_map.setdefault(key, []).append(w)

                    lines = sorted(
                        line_map.values(),
                        key=lambda ln: ln[0]["top"]
                    )

                    for ln in lines:
                        ln.sort(key=lambda w: w["x0"])

                    pages.append({
                        "lines": lines,
                        "method": "pdfplumber"
                    })

        else:
            images = _pdf_to_images(path)

            for img in images:
                lines = _extract_with_paddleocr([img])

                pages.append({
                    "lines": lines,
                    "method": "paddleocr"
                })

        grouped_docs = split_file(pages)

        result = []

        for idx,doc in enumerate(grouped_docs, start=1):
            merged_lines = []

            for page in doc:
                merged_lines.extend(page["lines"])

            method = doc[0]["method"]
            result.append((merged_lines, method))

            save_lines_debug(merged_lines, f"{path.stem}_doc{idx}.txt")
        return result

    raise ValueError(f"Unsupported filetype for selected file: {suffix}")

def save_lines_debug(lines, filename="ocr_debug.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        for line_idx, line in enumerate(lines, 1):
            f.write(f"===== LINEA {line_idx} =====\n")

            for w in line:
                text = w["text"]
                x0 = round(w["x0"], 2)
                x1 = round(w["x1"], 2)
                top = round(w["top"], 2)
                page = w.get("_page", 0)

                f.write(
                    f"[page={page}] "
                    f"[x0={x0}] "
                    f"[x1={x1}] "
                    f"[top={top}] "
                    f"{text}\n"
                )

            f.write("\n")

# document container
class Document:
    def __init__(self, path: Path, text: str, method: str, error: str | None = None):
        self.path = path
        self.name = path.name
        self.text = text
        self.method = method
        self.error = error
        self.ok = error is None 

def save_text(text, filename):
    base_dir = os.path.dirname(os.path.abspath(__file__))  # directorio del script
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
            extracted_docs = extract_text(path)

            for idx, (text, method) in enumerate(extracted_docs, start=1):

                if len(extracted_docs) == 1:
                    doc_path = path
                else:
                    doc_path = Path(f"{path.stem}_{idx}{path.suffix}")

                doc = Document(doc_path, text, method)
                documents.append(doc)

        except Exception as e:
            logger.error(f"Error processing {path.name}: {e}")
            documents.append(
                Document(path, "", "error", error=str(e))
            )

    logger.info(
        f"Extraction completed: {sum(d.ok for d in documents)}/{len(documents)} OK"
    )

    return documents



def save_lines_debug(lines: list, output_file: str = "ocr_debug.txt") -> None:
    """
    Guarda todas las líneas detectadas con coordenadas x/y por palabra.
    Útil para revisar OCR en documentos escaneados.
    """

    output_path = Path(output_file)

    with open(output_path, "w", encoding="utf-8") as f:
        current_page = None

        for line_idx, line in enumerate(lines, start=1):

            if not line:
                continue

            page = line[0].get("_page", 0)

            if page != current_page:
                current_page = page
                f.write(f"\n================ PAGE {page + 1} ================\n")

            f.write(f"\n----- LINE {line_idx} -----\n")

            for word in line:
                text = word.get("text", "")
                x0 = round(word.get("x0", 0), 2)
                x1 = round(word.get("x1", 0), 2)
                y = round(word.get("top", 0), 2)

                f.write(
                    f"[x0={x0}] [x1={x1}] [y={y}] {text}\n"
                )