import ollama
import json
import re
import logging
from exceptions.JSONDecodeError import JSONDecodeError
from methods.invoice_scrapper import NOMBRE_SOC


logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MODEL = "llama3.2"


prompt = f"""
Eres un asistente de auditoria cuyo proposito es ayudar a extraer información previamente definida de documentos comerciales recibidos o emitidos por la empresa auditada.

Se te proporciona:

1. Texto de un documento comercial (puede ser una factura, nota de crédito, recibo de cobranza)
2. Un JSON parcialmente completo generado por un sistema previo
3. Nombre de la entidad auditada: {NOMBRE_SOC}

Tu tarea:
- COMPLETAR los campos que estén en null
- No modifiques ningún valor no nulo bajo ninguna circunstancia, excepto si una operación matemática lo invalida.

Reglas:
- Respetar valores existentes si parecen correctos
- Solo inferir campos faltantes
- No inventar datos
- Mantener formato numérico correcto
- NO inferir IVA si no aparece explícitamente en el documento.
- Si Subtotal y Total existen:
    - Si Total < Subtotal → están invertidos → intercambiarlos.
    - Si Total >= Subtotal → IVA = Total - Subtotal.
- Si no podés verificar la relación exacta → dejar campos en null.
- NO realizar cálculos complejos ni asumir tasas de IVA.
- El campo tipo requiere que especifiques si se trata de una Factura (o Invoice), Nota de Credito, e-Ticket o Boleta. 
- El numero de documento suele estar precedido por la letra "A" mayúscula, o en ocasiones la B.
- "Empresa" es la contraparte del documento (proveedor o cliente).
- NUNCA puede ser igual a la entidad auditada.
- Si coincide con la entidad auditada, devolver null.
- Los documentos podrían estár en inglés u otro idioma, quiero que intentes darme las respuestas en español.
- Formato de los números que incluyas en el JSON: 1000,00

Devuelve EXACTAMENTE este JSON:

(
  "Tipo": string|null,
  "Numero": string|null,
  "Empresa": string|null,
  "Fecha_Documento": string|null,
  "Moneda": string|null,
  "Concepto": string|null,
  "Subtotal": number|null,
  "IVA_minimo_10": number|null,
  "IVA_basico_22": number|null,
  "Total": number|null
)

"""

def extract_json(llm_response: str):
    match = re.search(r"```json\s*([\s\S]*?)\s*```", llm_response)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except:
        return None
    

def llm_processing(text: str, name: str, partial_data: dict) -> dict | None:
    logger.info(f"Enviando texto al LLM ({len(text)} caracteres)")
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", 
            "content": f"""{prompt}
            JSON parcial:
            {json.dumps(partial_data, default=str,ensure_ascii=False)}
            Factura:
            {text}
            Path:
            {name}"""}],
        options={"temperature": 0.1 })

    content = response["message"]["content"]
    print("RESPUESTA RAW:", repr(content))

    try:
        return extract_json(content)
    except:
        JSONDecodeError("JSON inválido recibido del LLM")
        return None

"""def multiple_processing(text: str, name: str,partial_data: dict,max_attempts=2):
    for attempt in range(max_attempts):
        result = llm_processing(text, name, partial_data)
        print(result)

        if result is not None:
            return result

    return None"""