import ollama
import json
import re
import logging
from exceptions.JSONDecodeError import JSONDecodeError


logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

MODEL = "llama3.2"


prompt = f"""
Eres un modelo de inteligencia artificial cuyo propósito es interpretar la información de la siguiente factura y devolver los campos requeridos a continuación.

Devuelve SOLO un JSON válido, sin texto adicional.

Campos requeridos:
    -Tipo_Documento
    -Numero_documento
    -Fecha_emision
    -Proveedor/emisor
    -Cliente/receptor
    -Moneda
    -Concepto/Descripción
    -Subtotal
    -IVA_10%
    -IVA_22%
    -Total

Reglas:
    - No inventar datos
    - Si un campo falta → null
    - Mantener números como enteros o floats (sin separador de miles, y los decimales con ",")
    - Las facturas suelen tener el siguiente formato de columnas en lo que concierne a su concepto/descripcion: Primero un Codigo, luego un Precio Unitario, luego la Cantidad y el Importe, que es el precio unitario multiplicado por la cantidad. Interpreta estos valores y quedate solo con los que se asemeje a una descripcion de articulo o servicio prestado
    - Al momento de extraer el concepto/descripcion quiero que interpretes el contexto, debería ser la descripción de un producto o un servicio prestado, si consideras que no podría serlo, no lo incluyas.
    - Si interpretas que hay multiples productos o servicios facturados → concatenar con "|", sin saltos de línea ni comillas.
    - Total debe coincidir con Subtotal + IVA_10% + IVA_22%, si no → null
    - El campo tipo requiere que especifiques si se trata de una Factura (o Invoice), Nota de Credito, e-Ticket o Boleta. Esta palabra deberia encontrarse en las primeras lineas del documento puede estar contenida o no ser exacta, apenas identifiques estas palabras, almacena el dato.
    - El numero de documento suele estar precedido por la letra "A" mayúscula, o en ocasiones la B. Por lo que si encuentras alguna de estas letras aislada, el numero de factura puede estar despuest de un/os espacios o puede estar pegada a la letra.
    - Si no encontraste el numero_documento, intenta extraerlo en el path de la factura ya que el mismo suele estar contenido en este.
    - Si la factura está en inglés → solo extraer:
        numero_documento, fecha_emision, proveedor/emisor, cliente/receptor, Moneda, Concepto/Descripción, Total
    - Si el el concepto/descripcion fuera en inglés, no realices traducciones

Ejemplos:

Documento 1: 
Factura 1: "RUT EMISOR | 210002780011
E-FACTURA
SERIE | NUMERO | FORMA DE PAGO
A | 145076 | CRÉDITO
RUT COMPRADOR
RUT - UY - 214048690018
UNIVERSAL SOC. DE PRODUCCIONSANITARIA -
MILLAN 3588 - MONTEVIDEO - MO - UY
FECHA DEL COMPROBANTE | MONEDA | CAMBIO
03/09/2025 | UYU
DESCRIPCIÓN | U.M. | CANTIDAD | VALOR UNIT | MONTO ITEM
TRELEGY ELLIPTA 92/55/22MCG 1X30DReiEA mp5r,000 eso1.400,00 7.140,00
por
Receptor | EA | 5,000 | 1.400,00 | 7.140,00
BASEAMOUNT10 | 7.000,00
TOTALCPU | 140,00
TOTALIMNRATE | 7.854,00
MONTO IVA T MÍNIMA | 7.140,00
BASEAMOUNT22 | 0,00
TOTALPERCEPTIONIRAE | 0,00
TOTALBASICRATE | 0,00
IVA TASA MÍNIMA | 10,00
TOTALIMESI | 0,00
TOTALPERCEPTIONIVA | 0,00
IVA TASA BÁSICA | 22,00
SUBTOTAL IVA T MÍNIMA | 714,00
MONTO TOTAL | 7.854,00
[TEXT]
RUT EMISOR 210002780011
E-FACTURA
SERIE NUMERO FORMA DE PAGO
A 145076 CRÉDITO
RUT COMPRADOR
GLAXOSMITHKLINE URUGUAY S.A. -
GLAXOSMITHKLINE URUGUAY S.A. - RUT - UY - 214048690018
GLAXOSMITHKLINE URUGUAY S.ASALTO
UNIVERSAL SOC. DE PRODUCCIONSANITARIA -
1105MONTEVIDEO URUGUAY - MONTEVIDEO
MILLAN 3588 - MONTEVIDEO - MO - UY
TELÉFONO: 5982-4198333
FECHA DEL COMPROBANTE MONEDA CAMBIO
03/09/2025 UYU
DESCRIPCIÓN U.M. CANTIDAD VALOR UNIT MONTO ITEM
TRELEGY ELLIPTA 92/55/22MCG 1X30DReiEA mp5r,000 eso1.400,00 7.140,00
por
Receptor
BASEAMOUNT10 7.000,00 BASEAMOUNT22 0,00 TOTALIMESI 0,00
TOTALCPU 140,00 TOTALPERCEPTIONIRAE 0,00 TOTALPERCEPTIONIVA 0,00
TOTALIMNRATE 7.854,00 TOTALBASICRATE 0,00 IVA TASA BÁSICA 22,00
MONTO IVA T MÍNIMA 7.140,00 IVA TASA MÍNIMA 10,00 SUBTOTAL IVA T MÍNIMA 714,00
MONTO TOTAL 7.854,00
FECHA DE VENCIMIENTO01/11/2026
PUEDE VERIFICAR COMPROBANTE EN:
HTTP://WWW.DGI.GUB.UY/
I.V.A. AL DÍA
CAE Nº 90242571811
SERIE A - 140001 AL 170000
Código de seguridad
mO8FnG"

-Tipo_Documento = Factura
-Numero_documento = 145076
-Fecha_emision = 03/09/2025
-Proveedor/emisor = GLAXOSMITHKLINE URUGUAY S.A.
-Cliente/receptor = UNIVERSAL SOC. DE PRODUCCIONSANITARIA
-Moneda = UYU
-Concepto/Descripción = TRELEGY ELLIPTA 92/55/22MCG
-Subtotal = 7140,00
-IVA_10% = 714,00
-IVA_22% = 0,00
-Total = 7854,00


Ejemplo 2:
Documento 2: "--- Page 1 ---
[TABLE]
RUC EMISOR | TIPO DE DOCUMENTO
217318710010 | e-Factura
SERIE | NÚMERO | FORMA DE PAGO | VENCIMIENTO
A | 147 | Crédito | 11/08/2025
RUC COMPRADOR | IDENTIFICADOR DE COMPRA
216228530015
NOMBRE | DOMICILIO
LUNAMEN S.A | Paraguay 2141, MONTEVIDEO,
Montevideo
FECHA DE DOCUMENTO | MONEDA
11/08/2025 | USD
Descripción | Uni | * | P. Unitario US$ | Desc | Rec | Cantidad | Importe US$
Realización de tendido de Fibra en cliente Hogart U 1 2.280,00 0,00 0,00 1 2.280,00
ADENDA:
[TEXT]
RUC EMISOR TIPO DE DOCUMENTO
217318710010 e-Factura
SERIE NÚMERO FORMA DE PAGO VENCIMIENTO
A 147 Crédito 11/08/2025
RUC COMPRADOR IDENTIFICADOR DE COMPRA
216228530015
Opnitel S.A NOMBRE DOMICILIO
Oxygen Fiber
LUNAMEN S.A Paraguay 2141, MONTEVIDEO,
RUTA 1 KM 49.500
Montevideo
Zona Franca Libertad
FECHA DE DOCUMENTO MONEDA
Tel.:
opnitelfacturas@gmail.com 11/08/2025 USD
Descripción Uni * P. Unitario US$ Desc Rec Cantidad Importe US$
Realización de tendido de Fibra en cliente Hogart U 1 2.280,00 0,00 0,00 1 2.280,00
Monto retenido: 0,00
Exp. y asimiladas: 0,00
Subtotal no grv.: 2.280,00
Total IVA (0%): 0,00
Total IVA (0%): 0,00
TOTAL A PAGAR: 2.280,00
Res. Nro.
Puede verificar comprobante en:
www.dgi.gub.uy
Fecha de vencimiento:
22/08/2025
Código de seguridad: yTbXfk
I.V.A al día
Nro. de CAE 90231525732, rango: serie A Nº 101 al 200
ADENDA:
Notas: Solicitado por Sr. Joaquin Sellanes
* 1- No gravado"

-Tipo_Documento = Factura
-Numero_documento = 147
-Fecha_emision = 11/08/2025
-Proveedor/emisor = Opnitel S.A 
-Cliente/receptor = LUNAMEN S.A
-Moneda = USD
-Concepto/Descripción = Realización de tendido de Fibra en cliente Hogart
-Subtotal = 2280,00
-IVA_10% = 0,00
-IVA_22% = 0,00
-Total = 2280,00

Ejemplo 3:
Documento 3: "--- Page 1 ---
[TABLE]
RUT EMISOR | 210002780011
NOTA DE CRÉDITO DE E-FACTURA
SERIE | NUMERO | FORMA DE PAGO
A | 73786 | CRÉDITO
RUT COMPRADOR
RUT - UY - 214048690018
UNIVERSAL SOC. DE PRODUCCIONSANITARIA -
MILLAN 3588 - MONTEVIDEO - MO - UY
FECHA DEL COMPROBANTE | MONEDA | CAMBIO
22/09/2025 | UYU
DESCRIPCIÓN | U.M. | CANTIDAD | VALOR UNIT | MONTO ITEM
DARAPRIM X 30 COMP ReiEA mp13r,000 eso4.326,81 57.373,50
por
Receptor | EA | 13,000 | 4.326,81 | 57.373,50
BASEAMOUNT10 | 56.248,53
TOTALCPU | 1.124,97
TOTALIMNRATE | 63.110,85
MONTO IVA T MÍNIMA | 57.373,50
BASEAMOUNT22 | 0,00
TOTALPERCEPTIONIRAE | 0,00
TOTALBASICRATE | 0,00
IVA TASA MÍNIMA | 10,00
TOTALIMESI | 0,00
TOTALPERCEPTIONIVA | 0,00
IVA TASA BÁSICA | 22,00
SUBTOTAL IVA T MÍNIMA | 5.737,35
MONTO TOTAL | 63.110,85
REFERENCIAS
TIPO DE CFE | SERIE | NUMERO | FECHA
E-FACTURA | A | 117259 | 30/01/2024
[TEXT]
RUT EMISOR 210002780011
NOTA DE CRÉDITO DE E-FACTURA
SERIE NUMERO FORMA DE PAGO
A 73786 CRÉDITO
RUT COMPRADOR
GLAXOSMITHKLINE URUGUAY S.A. -
GLAXOSMITHKLINE URUGUAY S.A. - RUT - UY - 214048690018
GLAXOSMITHKLINE URUGUAY S.ASALTO
UNIVERSAL SOC. DE PRODUCCIONSANITARIA -
1105MONTEVIDEO URUGUAY - MONTEVIDEO
MILLAN 3588 - MONTEVIDEO - MO - UY
TELÉFONO: 5982-4198333
FECHA DEL COMPROBANTE MONEDA CAMBIO
22/09/2025 UYU
DESCRIPCIÓN U.M. CANTIDAD VALOR UNIT MONTO ITEM
DARAPRIM X 30 COMP ReiEA mp13r,000 eso4.326,81 57.373,50
por
Receptor
BASEAMOUNT10 56.248,53 BASEAMOUNT22 0,00 TOTALIMESI 0,00
TOTALCPU 1.124,97 TOTALPERCEPTIONIRAE 0,00 TOTALPERCEPTIONIVA 0,00
TOTALIMNRATE 63.110,85 TOTALBASICRATE 0,00 IVA TASA BÁSICA 22,00
MONTO IVA T MÍNIMA 57.373,50 IVA TASA MÍNIMA 10,00 SUBTOTAL IVA T MÍNIMA 5.737,35
MONTO TOTAL 63.110,85
REFERENCIAS
TIPO DE CFE SERIE NUMERO FECHA
E-FACTURA A 117259 30/01/2024
FECHA DE VENCIMIENTO25/09/2026
PUEDE VERIFICAR COMPROBANTE EN:
HTTP://WWW.DGI.GUB.UY/
I.V.A. AL DÍA
CAE Nº 90242187892
SERIE A - 73001 AL 88000
Código de seguridad
b2NrB1"

-Tipo_Documento = Nota de crédito
-Numero_documento = 73786
-Fecha_emision = 30/01/2024
-Proveedor/emisor = GLAXOSMITHKLINE URUGUAY S.A.
-Cliente/receptor = UNIVERSAL SOC. DE PRODUCCIONSANITARIA
-Moneda = UYU
-Concepto/Descripción = DARAPRIM X 30 COMP
-Subtotal = 57373,50
-IVA_10% = 0,00
-IVA_22% = 5737,35
-Total = 63110,85
"""


def parse_llm_response(content: str):
    # Quitar bloque de ```json ... ```
    content = re.sub(r"^```json\s*|\s*```$", "", content.strip(), flags=re.DOTALL)
    
    try:
        return json.loads(content)
    except:
        JSONDecodeError("JSON inválido recibido del LLM")
        return None

def llm_processing(text: str, name: str) -> dict | None:
    logger.info(f"Enviando texto al LLM ({len(text)} caracteres)")
    response = ollama.chat(
        model=MODEL,
        messages=[{"role": "user", "content": f"{prompt}\n\nFactura:\n{text}\nPath:{name}"}],
        options={
            "temperature": 0.1 
        }
    )

    content = response["message"]["content"]
    print("RESPUESTA RAW:", repr(content))

    try:
        return parse_llm_response(content)
    except:
        JSONDecodeError("JSON inválido recibido del LLM")
        return None

def multiple_processing(text: str, name: str, max_attempts=2):
    for attempt in range(max_attempts):
        result = llm_processing(text, name)
        print(result)

        if result is not None:
            return result

    return None