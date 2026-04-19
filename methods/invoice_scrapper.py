import pdfplumber
import os
import re
from tkinter import Tk, filedialog, simpledialog
import sys
from datetime import datetime
import unicodedata
from itertools import combinations, permutations



sys.path.append("./")

#RUT_RE = re.compile(r"\b\d{12}\b")

SOCIEDAD_RE = re.compile(
    r"""
    \b(
        s\.?a\.?|
        s\.?r\.?l\.?|
        s\.?a\.?s\.?|
        l\.?t\.?d\.?a\.?|
        l\.?t\.?d\.?|
        l\.?l\.?c\.?|
        s\.?c\.?|
        sociedad\s+an[oó]nima
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

"""PFISICA_RE = re.compile(
    r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+\b"
)"""

FECHA_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")

TOTAL_RE = re.compile(
    r"\d{1,3}(?:\.\d{3})+,\d{2}"   # Latin WITH thousands:    2.937,60
    r"|"
    r"\d+,\d{2}(?!\d)"              # Latin WITHOUT thousands: 237,60
    r"|"
    r"\d{1,3}(?:,\d{3})+\.\d{2}"   # English WITH thousands:  36,600.00
    r"|"
    r"\d+\.\d{2}(?!\d)"             # English WITHOUT thousands: 0.00
)

_LATIN_THOUSANDS_RE  = re.compile(r"\d{1,3}(?:\.\d{3})+,\d{2}")
_LATIN_SIMPLE_RE     = re.compile(r"^\d+,\d{2}$")
_ENGLISH_THOUSANDS_RE = re.compile(r"\d{1,3}(?:,\d{3})+\.\d{2}")
_ENGLISH_SIMPLE_RE   = re.compile(r"^\d+\.\d{2}$")


def get_company_name() -> str:
    root = Tk()
    root.withdraw()
    nombre = simpledialog.askstring(
        "Empresa auditada",
        "Ingrese la razón social de la empresa auditada:",
    )
    root.destroy()
    if not nombre:
        raise ValueError("Debe ingresar un nombre de empresa.")
    return nombre.strip()



def normalize_text(s: str) -> str:
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = re.sub(r"[^\w\s%]", "", s)
    return s


NOMBRE_SOC = normalize_text(get_company_name())

def parse_number(value) -> float | None:
    if value is None:
        return None
    value = str(value).strip()

    if _LATIN_THOUSANDS_RE.search(value):
        return float(value.replace(".", "").replace(",", "."))

    if _LATIN_SIMPLE_RE.search(value):
        return float(value.replace(",", "."))

    if _ENGLISH_THOUSANDS_RE.search(value):
        return float(value.replace(",", ""))

    if _ENGLISH_SIMPLE_RE.search(value):
        return float(value)

    return None

#metodo utilizado en la extracción de importes:
def find_amount_from_line(line: list) -> str | None:

    for w in reversed(line):
        m = TOTAL_RE.search(w["text"])
        if m:
            return m.group()

    # Fallback: join adjacent token pairs to handle split numbers like
    # "126,302" + ".60" being two separate PDF words.
    for i in range(len(line) - 2, -1, -1):
        combined = line[i]["text"] + line[i + 1]["text"]
        m = TOTAL_RE.search(combined)
        if m:
            return m.group()

    return None

def extract_amounts_from_line(line: list) -> list[float]:

    values = []

    # 1. detectar valores individuales
    for w in line:
        text = w["text"]

        matches = TOTAL_RE.findall(text)
        for m in matches:
            val = parse_number(m)
            if val is not None:
                values.append(val)

    # 2. fallback: números partidos en tokens (ej: "126,302" + ".60")
    for i in range(len(line) - 1):
        combined = line[i]["text"] + line[i + 1]["text"]

        matches = TOTAL_RE.findall(combined)
        for m in matches:
            val = parse_number(m)
            if val is not None:
                values.append(val)

    return values


def extract_type(lines, max_lines: int = 15) -> str | None:
    keywords = {"factura": "Factura", "boleta": "Boleta", "nota": "Nota de Crédito", "efactura": "Factura", "recibo": "Recibo", "ecobranza": "Recibo", "invoice": "Factura"}
    for line in lines[:max_lines]:
        text_line = " ".join(normalize_text(w["text"]) for w in line).lower()
        for word in text_line.split():
            if word in keywords:
                return keywords[word]
    return None


def extract_nbr(lines) -> str | None:
    for line in lines:
        text_line = " ".join(w["text"] for w in line)

        match = re.search(r"\b[ABC]\s*[-/]?\s*(\d{3,})\b", text_line)
        if match:
            digits = match.group(1)
            if len(digits) != 12:
                return digits

    return None


"""def extract_rut(x_margin: int = 15) -> dict:
    # CHANGE 6: Early-exit once both RUTs are found.
    # The original code kept scanning even after finding the emisor RUT.
    # Now we break out of the outer loop as soon as both slots are filled.
    result = {"Rut_Emisor": None, "Rut_Receptor": None}
    all_ruts = []

    for line in lines:
        for w in line:
            m = RUT_RE.search(w["text"])
            if m:
                all_ruts.append(m.group())

            if "emisor" in w["text"].lower() and result["Rut_Emisor"] is None:
                candidates = [
                    (abs(ww["x0"] - w["x0"]), rm.group())
                    for ww in line
                    if (rm := RUT_RE.search(ww["text"]))
                ]
                if candidates:
                    result["Rut_Emisor"] = min(candidates)[1]

        # Early-exit: receptor can only be found after emisor is known
        if result["Rut_Emisor"] and result["Rut_Receptor"] is None:
            for rut in all_ruts:
                if rut != result["Rut_Emisor"]:
                    result["Rut_Receptor"] = rut
                    break

        if result["Rut_Emisor"] and result["Rut_Receptor"]:
            break

    return result"""


def extract_company_name(lines,max_gap: int = 12) -> str | None:
    audited_norm = normalize_text(NOMBRE_SOC)

    for idx, line in enumerate(lines):
        text = " ".join(normalize_text(w["text"]) for w in line).strip()
        m = SOCIEDAD_RE.search(text)

        if not m:
            continue
    
        suffix_text = m.group(0).strip().lower().split()
        suffix_words = []
        k, j = len(line) - 1, len(suffix_text) - 1

        while k >= 0 and j >= 0:
            if normalize_text(line[k]["text"]) == suffix_text[j]:
                suffix_words.append(line[k])
                j -= 1
            k -= 1

        if j >= 0:
            continue

        suffix_words = list(reversed(suffix_words))
        suffix_word  = suffix_words[-1]
        start_idx    = line.index(suffix_words[0])
        name_words   = []
        prev_x0      = suffix_words[0]["x0"]

        for p in range(start_idx - 1, -1, -1):
            w = line[p]
            if prev_x0 - w["x1"] > max_gap:
                break
            name_words.append(w)
            prev_x0 = w["x0"]

        name_words = list(reversed(name_words)) + suffix_words

        if len(name_words) == len(suffix_words) and idx > 0:
            prev_line  = lines[idx - 1]
            width      = suffix_word["x1"] - suffix_word["x0"]
            margin     = max(10, width * 0.30)
            candidates = sorted(
                [
                    w for w in prev_line
                    if not (
                        w["x1"] < suffix_word["x0"] - margin
                        or w["x0"] > suffix_word["x1"] + margin
                    )
                ],
                key=lambda x: x["x0"],
            )
            if candidates:
                name_words = candidates + suffix_words

        company_name = " ".join(w["text"] for w in name_words).strip()
        if not company_name or len(company_name) < 3:
            return None
        #eliminar casos basura (solo símbolos)
        if not any(c.isalpha() for c in company_name):
            return None
        if company_name and normalize_text(company_name) != audited_norm:
            return company_name

    # Fallback: physical person
    """for line in lines:
        text = " ".join(w["text"] for w in line)
        m = PFISICA_RE.search(text)
        if m:
            candidate = m.group().strip()
            if normalize_text(candidate) != audited_norm:
                return candidate"""

    return None


def extract_currency(lines) -> str | None:
    VALID = {"usd", "uyu", "eur"}
    for line in lines:
        for w in line:
            if normalize_text(w["text"]) in VALID:
                return normalize_text(w["text"]).upper()
    return None


def extract_dates(lines,max_vertical_gap: int = 20): #utilizar modelo para sacarla si es en inglés
    fechas = []

    for line in lines:
        text_line = " ".join(w["text"] for w in line)

        for match in FECHA_RE.findall(text_line):
            try:
                d, m, y = re.split(r"[/-]", match)
                if len(y) == 2:
                    y = "20" + y

                fecha = datetime(int(y), int(m), int(d))

                # tomar referencia vertical (primer word de la línea)
                y_pos = line[0]["top"] if "top" in line[0] else line[0]["y0"]

                fechas.append({
                    "fecha": fecha,
                    "y": y_pos
                })

            except:
                continue

    if not fechas:
        return None

    #ordenar por posición vertical (arriba → abajo)
    fechas.sort(key=lambda x: x["y"])

    #tomar la primera como referencia
    y_ref = fechas[0]["y"]

    #filtrar por distancia vertical
    fechas_filtradas = [
        f for f in fechas
        if abs(f["y"] - y_ref) <= max_vertical_gap
    ]

    if not fechas_filtradas:
        return None

    #dentro de las filtradas → ordenar por antigüedad
    fechas_filtradas.sort(key=lambda x: x["fecha"])
    #este procedimiento se aplica porque en las Notas de Credito puede haber referencias a otras facturas que tienene fechas anteriores a la de emision, y sin este mecanismo traería esas fechas
    return fechas_filtradas[0]["fecha"]


def extract_concept(lines,vertical_tolerance: int = 30) -> dict:
    x1 = x2 = y_reference = None
    descriptions = []
    collecting   = False
    
    header_terms = ["descripcion", "concepto", "detalle", "producto", "description", "concept", "items"]
    
    for idx, line in enumerate(lines):
        line = sorted(line, key=lambda w: w["x0"])
        norm_text = [normalize_text(w["text"]) for w in line]

        if any(term in "".join(norm_text) for term in header_terms):
            collecting  = True
            objective_word = None
            
            for w in line:
                if normalize_text(w["text"]) in header_terms and objective_word is None:
                    objective_word = w
                    #almacenamos el extremo izquierdo de la palabra inmediatamente a la derecha de la palabra objetivo
                    idx_w = line.index(w)
                    next_word = normalize_text(line[idx_w + 1]["text"])

                    if next_word not in header_terms:
                        x2 = line[idx_w + 1]["x0"]
                    else: 
                        x2 = line[idx_w + 2]["x0"]

            if not objective_word:
                continue

            objective_index = line.index(objective_word)

            #caso1 - es la primera palabra de la fila
            if objective_index == 0:
                candidates = []

                # mirar varias filas siguientes (no solo una para cubrirme de OCR desalineado)
                for next_line in lines[idx + 1: idx + 6]:
                    next_line = sorted(next_line, key=lambda w: w["x0"])
                    if next_line:
                        candidates.append(next_line[0]["x0"])

                if candidates:
                    x1 = min(candidates)  # más robusto que tomar solo una fila
                else:
                    x1 = objective_word["x0"]

            #caso2 - hay palabras previas en la fila
            else:
                prev_word = line[objective_index - 1]
                x1 = objective_word["x0"]
                
                ref_x = prev_word["x1"] 
                ref_y = objective_word["top"]
            #se busca el limite derecho de la columna previa iterando desde el header hasta el último de los conceptos (limitado en base a vertical_tolerance)
                for next_line in lines[idx + 1:]:
                    next_line = sorted(next_line, key=lambda w: w["x0"])

                    #frento para que no siga iterando si se pasó de la tolerancia vertical
                    if not next_line or abs(next_line[0]["top"] - ref_y) > vertical_tolerance:
                        break

                    updated_margin = [
                        w for w in next_line
                        if w["x0"] <= ref_x <= w["x1"]] and abs(w["top"] - ref_y) 
                    
                    if updated_margin:
                        ref_x = updated_margin[0]["x1"]
                
                x1 = ref_x +1

            y_reference = None
            continue

        if collecting and x1 is not None:
            words_in_col = [w for w in line if w["x0"] >= x1 and (x2 is None or w["x1"] < x2)]
            if not words_in_col:
                continue
            current_y = words_in_col[0]["top"]

            row_text  = " ".join(w["text"] for w in words_in_col)

            if y_reference is None:
                descriptions.append(row_text)
                y_reference = current_y
            elif abs(current_y - y_reference) <= vertical_tolerance:
                descriptions.append(row_text)
                y_reference = current_y
            else:
                collecting = False

    return {"descripcion_texto": " | ".join(descriptions), "y_reference": y_reference}


"""def extract_importes_v1(lines,y_reference) -> dict:
    total_general = iva_minimo_10 = iva_basico_22 = None

    if y_reference is None:
        return {"total_general": None, "iva_minimo_10": None, "iva_basico_22": None}

    #Utilizo y_reference, extraido de extract_concept para partir la búsqueda debajo del concepto de la factura y optimizar tiempos de procesamiento
    for line in lines:
        line      = sorted(line, key=lambda w: w["x0"])
        y         = line[0]["top"]
        if y <= y_reference:
            continue

        line_text = " ".join(normalize_text(w["text"]) for w in line)

        # Total general (exclude "Total IVA")
        for i, w in enumerate(line):
            if normalize_text(w["text"]).startswith("total"):
                context = " ".join(normalize_text(x["text"]) for x in line[i:i + 3])
                if "iva" in context:
                    continue
                amount = find_amount_from_line(line[i + 1:])
                if amount:
                    total_general = amount
                    break

        # IVA 10% → Mínima
        if (
            "iva" in line_text
            and "neto" not in line_text
            and "subtotal" not in line_text
            and any(t in line_text for t in ["10%", "10 %", "minima", "tm"])
            and any(t in line_text for t in ["total","monto"])
        ):
            amount = find_amount_from_line(line)
            if amount:
                iva_minimo_10 = amount

        # IVA 22% → Básica
        if (
            "iva" in line_text
            and "neto" not in line_text
            and "subtotal" not in line_text
            and any(t in line_text for t in ["22%", "22 %", "basica", "tb"])
            and any(t in line_text for t in ["total","monto"])
        ):
            amount = find_amount_from_line(line)
            if amount:
                iva_basico_22 = amount

    return {
        "total_general": parse_number(total_general),
        "iva_minimo_10": parse_number(iva_minimo_10),
        "iva_basico_22": parse_number(iva_basico_22),
    }"""

def extract_importes_v2(lines, y_reference) -> dict:
    empty = {
        "total_general":    None,
        "subtotal_no_grav": None,
        "subtotal_minima":  None,
        "subtotal_basica":  None,
        "iva_minimo_10":    None,
        "iva_basico_22":    None,
    }

    if y_reference is None:
        return empty

    # ── 1. Filtrar líneas por y_reference ────────────────────────────────────
    indexed_lines = []
    for line in lines:
        line_sorted = sorted(line, key=lambda w: w["x0"])
        if line_sorted[0]["top"] > y_reference:
            indexed_lines.append(line_sorted)

    # ── 2. Líneas que contienen "total" ───────────────────────────────────────
    total_line_indices = []
    for idx, line in enumerate(indexed_lines):
        line_text = " ".join(normalize_text(w["text"]) for w in line)
        if "total" in line_text:
            total_line_indices.append(idx)

    if not total_line_indices:
        return empty

    # ── 3. Candidatos numéricos en ventana ±2 de cada línea "total" ──────────
    seen_raw   = set()
    candidates = []

    for t_idx in total_line_indices:
        window_start = max(0, t_idx - 2)
        window_end   = min(len(indexed_lines) - 1, t_idx + 2)

        for line_idx in range(window_start, window_end + 1):
            for raw in _collect_all_amounts(indexed_lines[line_idx]):
                if raw not in seen_raw:
                    parsed = parse_number(raw)
                    if parsed is not None:
                        candidates.append(parsed)
                        seen_raw.add(raw)

    if not candidates:
        return empty

    # ── 4. Mayor candidato → total general ───────────────────────────────────
    total_general = max(candidates)
    remaining     = [c for c in candidates if c != total_general]

    # ── 5. Subconjunto que suma total_general ─────────────────────────────────
    TOLERANCE     = 0.01
    matched_subset = None

    for size in range(1, len(remaining) + 1):
        for subset in combinations(remaining, size):
            if abs(sum(subset) - total_general) <= TOLERANCE:
                matched_subset = list(subset)
                break
        if matched_subset:
            break

    if not matched_subset:
        return {**empty, "total_general": total_general}

    # ── 6. Clasificar subset según paridad ────────────────────────────────────
    #
    #   Par   → pares (subtotal, iva): todos los valores tienen IVA asignable
    #   Impar → un valor es no gravado (sin IVA), el resto son pares (sub, iva)
    #
    RATES = {"basica": 0.22, "minima": 0.10}

    subtotal_no_grav = None
    subtotal_minima  = None
    subtotal_basica  = None
    iva_minimo_10    = None
    iva_basico_22    = None

    def try_pair_match(values: list) -> list[tuple] | None:
        """
        Dado un conjunto de valores de tamaño par, intenta emparejar cada
        elemento con otro tal que  sub * tasa == iva  (22% o 10%).
        Devuelve lista de (subtotal, iva, tasa_nombre) o None si no cierra.
        """
        if len(values) % 2 != 0:
            return None

        # Intentamos todas las permutaciones de la primera mitad como subtotales
        half = len(values) // 2
        for perm in permutations(values, len(values)):
            subs = list(perm[:half])
            ivas = list(perm[half:])
            pairs = []
            used_ivas = []
            success = True

            for sub in subs:
                matched = False
                for rate_name, rate in RATES.items():
                    expected_iva = round(sub * rate, 2)
                    for iva_candidate in ivas:
                        if iva_candidate not in used_ivas and abs(iva_candidate - expected_iva) <= TOLERANCE:
                            pairs.append((sub, iva_candidate, rate_name))
                            used_ivas.append(iva_candidate)
                            matched = True
                            break
                    if matched:
                        break
                if not matched:
                    success = False
                    break

            if success and len(pairs) == half:
                return pairs

        return None

    n = len(matched_subset)

    if n % 2 == 0:
        # ── Caso par: todos los valores tienen IVA ───────────────────────────
        pairs = try_pair_match(matched_subset)

        if pairs:
            for sub, iva, rate_name in pairs:
                if rate_name == "basica":
                    subtotal_basica = sub
                    iva_basico_22   = iva
                elif rate_name == "minima":
                    subtotal_minima = sub
                    iva_minimo_10   = iva

    else:
        # ── Caso impar: un valor es no gravado, el resto son pares ───────────
        for i, candidate_no_grav in enumerate(matched_subset):
            rest = [v for j, v in enumerate(matched_subset) if j != i]

            if len(rest) % 2 != 0:
                continue

            pairs = try_pair_match(rest)
            if pairs:
                subtotal_no_grav = candidate_no_grav
                for sub, iva, rate_name in pairs:
                    if rate_name == "basica":
                        subtotal_basica = sub
                        iva_basico_22   = iva
                    elif rate_name == "minima":
                        subtotal_minima = sub
                        iva_minimo_10   = iva
                break

    return {
        "total_general":    total_general,
        "subtotal_no_grav": subtotal_no_grav,
        "subtotal_minima":  subtotal_minima,
        "subtotal_basica":  subtotal_basica,
        "iva_minimo_10":    iva_minimo_10,
        "iva_basico_22":    iva_basico_22,
    }

def _collect_all_amounts(line: list) -> list[str]:
    """Extrae todos los strings numéricos que matchean TOTAL_RE en una línea."""
    found = []

    for w in line:
        for m in TOTAL_RE.finditer(w["text"]):
            found.append(m.group())

    # Pares adyacentes para números partidos como "126,302" + ".60"
    for i in range(len(line) - 1):
        combined = line[i]["text"] + line[i + 1]["text"]
        for m in TOTAL_RE.finditer(combined):
            found.append(m.group())

    return found


def safe_extract(func, default=None):
    try:
        return func()
    except Exception:
        return default

"""def save_excel(df: pd.DataFrame) -> None:
    output_file = Path.home() / "Downloads" / "facturas_procesadas.xlsx"
    try:
        df.to_excel(output_file, index=False)
    except PermissionError:
        print("Cierre el archivo Excel antes de continuar.")
    print(f"Archivo guardado en: {output_file}")
    os.startfile(output_file)"""


"""def export_pdf_coordinates(pdf_path: str, output_txt: str = "debug_factura.txt") -> None:
    with pdfplumber.open(pdf_path) as pdf, open(output_txt, "w", encoding="utf-8") as f:
        for page_num, page in enumerate(pdf.pages):
            f.write(f"\n===== PAGE {page_num + 1} =====\n")
            for w in page.extract_words():
                f.write(f"[{round(w['x0'], 2)}, {round(w['top'], 2)}] {w['text']}\n")"""


