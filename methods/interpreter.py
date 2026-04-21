import ollama
import json
import re
import logging
from exceptions.JSONDecodeError import JSONDecodeError
from methods.invoice_scrapper import NOMBRE_SOC
import subprocess

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MODEL = "llama3.2"


prompt = f"""
Eres un asistente de auditoría cuyo propósito es extraer y validar información de documentos comerciales (facturas, notas de crédito, e-tickets, recibos).

Se te proporciona:

Texto completo de un documento comercial (puede estar en español, inglés u otro idioma)
Un JSON parcialmente completo generado por un sistema previo
Nombre de la entidad auditada: {NOMBRE_SOC}

Tu tarea:

Completar únicamente los campos que estén en null o sean claramente incorrectos
Validar coherencia de los datos existentes
Corregir valores SOLO si puedes respaldarlos con evidencia explícita del documento

REGLAS GENERALES:

NO inventar datos, todo dato devuelto debe estar contenido en el texto brindado.
NO asumir información implícita
NO utilizar conocimiento externo
Priorizar siempre datos explícitos del documento
Responder SIEMPRE en español (excepto el campo "Concepto")
Mantener formato numérico: 1000,00
Responder SOLO con un JSON válido, sin texto adicional
PROHIBIDO modificar campos que no sean null salvo que te lo permita explicitamente

IDIOMA Y NORMALIZACIÓN:

El documento puede estar en inglés u otro idioma
Debes interpretar correctamente los campos independientemente del idioma

Tipo de documento:

"Invoice" → "Factura"
"Credit Note" / "Credit Memo" → "Nota de Crédito"
"Receipt" → "Recibo"
"Ticket" / "eTicket" → "e-Ticket"

Fechas:

Si el documento está en inglés, asumir formato MM/DD/YYYY 
Si está en español, asumir formato DD/MM/YYYY
Convertir SIEMPRE a formato ISO: YYYY-MM-DD

Concepto:

Extraer el texto descriptivo principal del documento
NO traducir el contenido
Mantener el idioma original

IDENTIFICACIÓN DE LA EMPRESA (CRÍTICO):

"Empresa" es la contraparte del documento (proveedor o cliente), NUNCA la entidad auditada. Tu objetivo es identificar a la contraparte.
Debes EXCLUIR cualquier nombre que sea igual o similar a: {NOMBRE_SOC}

Se considera "similar" si:

Comparte palabras clave 
Es una razón social extendida o abreviada de la misma entidad
Tiene alta coincidencia textual aunque no sea idéntico

Ejemplo:

"UNIVERSAL S.P.S" ≈ "UNIVERSAL SOC.PROD.SANITARIA" → INVALIDO

UBICACIÓN Y PRIORIDAD:

Priorizar candidatos ubicados en la parte superior del documento
Especialmente cerca de:
Logo
Encabezado
Datos fiscales (RUT / Tax ID)

CRITERIOS DE SELECCIÓN (deben cumplirse en su mayoría):

Un nombre de empresa válido típicamente:

Es una cadena de texto relativamente corta (no una frase larga)
Contiene palabras en mayúscula o formato de razón social
Puede incluir sufijos como:
S.A., S.R.L., Ltd., Inc., Corp., etc.
Puede tratarse de una persona física, en cuyo caso será uno o varios nombres y uno o varios apellidos.
NO contiene descripciones operativas (ej: “detalle”, “concepto”, “cantidad”)
NO es una dirección completa
NO es una ciudad o país
NO es un teléfono ni email

Reglas adicionales:

Si detectas múltiples nombres:
Priorizar el que:
NO sea la entidad auditada
Si un candidato contiene números (dirección, teléfono) → descartarlo
IMPORTANTE: Si identificás el nombre de la empresa, DEBES incluirlo en el campo "Empresa" del JSON.
════════════════════════════════════════
IMPORTES — PROCEDIMIENTO ESTRICTO
════════════════════════════════════════

Los campos de importes son:
  Subtotal_no_grav, Subtotal_minima, Subtotal_basica,
  IVA_minimo_10, IVA_basico_22, Total

PASO 0 — VERIFICAR SI YA ESTÁN RESUELTOS:
  Calcular:
    suma_subtotales = suma de todos los Subtotal_* que no sean null
    suma_ivas       = suma de todos los IVA_* que no sean null

  Si Total no es null Y (suma_subtotales + suma_ivas) ≈ Total (diferencia ≤ 0.01):
    → Los importes son coherentes. No hacer nada con importes. Pasar a campos no monetarios.

  Si la ecuación NO se cumple o hay campos null:
    → Ejecutar PASO 1 en adelante

PASO 1 — EXTRAER CANDIDATOS NUMÉRICOS:
  Recorrer el texto desde la mitad hacia el final del documento
  Extraer TODOS los números con formato monetario:
    Formatos válidos: 1.234,56 | 1234,56 | 1,234.56 | 1234.56
  Ignorar completamente:
    - Porcentajes: 10%, 22%
    - Números sueltos que representen tasas: 10, 22, 10,00, 22,00

PASO 2 — IDENTIFICAR EL TOTAL:
  El Total es el candidato más grande asociado a etiquetas como:
    "Total", "Importe Total", "Total a Pagar", "Amount Due"
  Si no hay etiqueta clara → usar el candidato más grande

PASO 3 — BUSCAR SUBCONJUNTO QUE SUME EL TOTAL (LÓGICA COMBINATORIA):
  Con los candidatos restantes (excluyendo el Total), probar subconjuntos
  de tamaño 1, 2, 3… hasta encontrar uno donde:
    sum(subconjunto) ≈ Total (diferencia ≤ 0.01)

  Si ningún subconjunto cumple la ecuación:
    → Devolver todos los importes como null (excepto Total si fue identificado)

PASO 4 — CLASIFICAR EL SUBCONJUNTO POR PARIDAD:

  Si el subconjunto tiene tamaño PAR:
    → Todos los valores tienen IVA asignable
    → Iterar pares (A, B) del subconjunto buscando:
        A * 0.22 ≈ B  →  A = Subtotal_basica,  B = IVA_basico_22
        A * 0.10 ≈ B  →  A = Subtotal_minima,  B = IVA_minimo_10

  Si el subconjunto tiene tamaño IMPAR:
    → Un valor es no gravado (sin IVA)
    → Probar cada elemento como candidato no gravado:
        Restar ese elemento del subconjunto → queda un grupo de tamaño par
        Aplicar lógica PAR sobre ese grupo
        Si se cierran todos los pares:
          → El elemento removido es Subtotal_no_grav
          → Asignar el resto según la lógica PAR

PASO 5 — REGLA CRÍTICA DE CLASIFICACIÓN IVA:
  Un candidato NO puede ser IVA si su valor supera el 30% del Total
  En ese caso reclasificarlo como subtotal

PASO 6 — SÓLO COMPLETAR CAMPOS NULL:
  Aplicar los valores encontrados ÚNICAMENTE sobre campos que sean null en el JSON parcial
  PROHIBIDO sobreescribir campos ya existentes

════════════════════════════════════════
FORMATO DE NÚMEROS (OBLIGATORIO)
════════════════════════════════════════
  Todos los importes → decimal con punto, sin separador de miles
  Válido:   1234.56 | 62795.00
  Inválido: 1.234,56 | 62.795 | 1,234.56

════════════════════════════════════════
FORMATO DE SALIDA
════════════════════════════════════════
```json
{{
  "Tipo":             string|null,
  "Numero":           string|null,
  "Empresa":          string|null,
  "Fecha_Documento":  string|null,
  "Moneda":           string|null,
  "Concepto":         string|null,
  "Subtotal_no_grav": number|null,
  "Subtotal_minima":  number|null,
  "Subtotal_basica":  number|null,
  "IVA_minimo_10":    number|null,
  "IVA_basico_22":    number|null,
  "Total":            number|null
}}
```
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
    # Campos monetarios — verificar coherencia antes de enviar
    subtotales = [
        partial_data.get("Subtotal_no_grav"),
        partial_data.get("Subtotal_minima"),
        partial_data.get("Subtotal_basica"),
    ]
    ivas = [
        partial_data.get("IVA_minimo_10"),
        partial_data.get("IVA_basico_22"),
    ]
    total = partial_data.get("Total")

    suma = sum(v for v in subtotales + ivas if v is not None)
    importes_coherentes = (
        total is not None
        and suma > 0
        and abs(suma - total) <= 0.01
    )

    # Si los importes ya cierran, los eliminamos del partial para que el LLM
    # no los toque — solo trabajará los campos remanentes
    data_para_llm = dict(partial_data)
    print(data_para_llm)
    if importes_coherentes:
        for campo in ["Subtotal_no_grav","Subtotal_minima","Subtotal_basica",
                      "IVA_minimo_10","IVA_basico_22","Total"]:
            data_para_llm.pop(campo, None)

    null_fields = [k for k, v in data_para_llm.items() if v is None]
    if not null_fields:
        logger.info("JSON ya completo, omitiendo LLM")
        return partial_data

    logger.info(f"Enviando texto al LLM ({len(text)} caracteres)")

    subprocess.Popen(["ollama", "serve"])

    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user",
            "content": f"""{prompt}
            JSON parcial:
            {json.dumps(data_para_llm, default=str, ensure_ascii=False)}
            Documento:
            {text}
            Path:
            {name}"""}],
        options={"temperature": 0.1}
    )

    content = response["message"]["content"]
    print("RESPUESTA RAW:", repr(content))

    try:
        llm_result = extract_json(content)
        if llm_result is None:
            JSONDecodeError("JSON inválido recibido del LLM")
            return None

        # Merge: el LLM solo puede completar nulls, nunca sobreescribir
        merged = dict(partial_data)
        for k, v in llm_result.items():
            if merged.get(k) is None and v is not None and v != "":
                merged[k] = v

        return merged

    except Exception:
        JSONDecodeError("JSON inválido recibido del LLM")
        return None

"""def multiple_processing(text: str, name: str,partial_data: dict,max_attempts=2):
    for attempt in range(max_attempts):
        result = llm_processing(text, name, partial_data)
        print(result)

        if result is not None:
            return result

    return None"""