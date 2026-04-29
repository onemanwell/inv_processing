from methods.data_extractor import Document
from methods.invoice_scrapper import extract_type, extract_nbr, extract_company_name, extract_concept, extract_currency, extract_dates, extract_importes_v2
import pandas as pd
from methods.interpreter import llm_processing

#Modelo de procesos lógicos basado en la identificación de palabras claves, la utilización de coordenadas, y ecuaciones matemáticas
def logic_processor(documents: list[Document]) -> list[dict]:
    results = []

    for doc in documents:
        if not doc.ok:
            continue
        
        lines = doc.text
        
        concepto_data = extract_concept(lines)
        importes = extract_importes_v2(lines,concepto_data["y_reference"])
        
        subtotal_no_grav = importes.get("subtotal_no_grav")
        subtotal_minima = importes.get("subtotal_minima")
        subtotal_basica = importes.get("subtotal_basica")
        total_general = importes.get("total_general")
        iva_minimo    = importes.get("iva_minimo_10")
        iva_basico    = importes.get("iva_basico_22")

        if iva_minimo == 10 or iva_minimo == 22: iva_minimo= None
        if iva_basico == 10 or iva_basico == 22: iva_basico= None


        subtotal = (
            None
            if total_general is None
            else total_general - (iva_minimo or 0) - (iva_basico or 0)
        )

        results.append({
            "Path":              doc.path,
            "text":              doc.text,
            "data":{
                "Tipo":              extract_type(lines),
                "Numero":            extract_nbr(lines),
                "Empresa":           extract_company_name(lines),
                "Fecha_Documento":   extract_dates(lines),
                "Moneda":            extract_currency(lines),
                "Concepto":          concepto_data["descripcion_texto"],
                "Subtotal_no_grav":  subtotal_no_grav,
                "Subtotal_basica":   subtotal_basica,
                "Subtotal_minima":   subtotal_minima,
                "IVA_minimo_10":     iva_minimo,
                "IVA_basico_22":     iva_basico,
                "Total":             total_general,
            }
        })
 
    return results

def has_nulls(data: dict) -> bool:
    return any(v is None for v in data.values())

def lines_to_text(lines: list) -> str:
    text = []
    for line in lines:
        text_line = " ".join(w["text"] for w in line)
        text.append(text_line)
    return "\n".join(text)

#Empleo de llama3.2 para la extracción de los campos remanentes
def inference_processor(results: list[dict]) -> list[dict]:
    
    final_results = []
    for r in results:
        data = r["data"]
        doc_text = lines_to_text(r["text"])
        
        if not has_nulls(data):
            final_results.append({
                "file": r["Path"],
                "data": data
            })
            continue
        
        llm_result = llm_processing(text=doc_text,name=r["Path"], partial_data=data)
        
        if llm_result is None:
            final_data = data

        else:
            # merge: LLM completa solo nulls
            final_data = data.copy()
            for k, v in llm_result.items():
                if final_data.get(k) is None and v is not None:
                    final_data[k] = v
        

        final_results.append({
            "file": r["Path"],
            "data": final_data
        })
     
    return final_results

#Combinación de ambos métodos
def hibrid_processor(documents) -> list[dict]:
    preliminary_data = logic_processor(documents)
    final_data = inference_processor(preliminary_data)

    return final_data