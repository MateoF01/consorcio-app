# PDF Parser

Parser de liquidaciones de expensas en PDF, pensado para correr en AWS Lambda y también probarse localmente.

## Estructura

- `pdf_parser/index.py`: parser principal
- `pdf_parser/__init__.py`: marca el directorio como paquete importable
- `pdf_parser/vendor/`: dependencias embebidas para el parser

## Requisitos

- Python 3.10+ recomendado
- El parser usa `pdfplumber`
- La dependencia ya quedó instalada dentro de `pdf_parser/vendor`, no hace falta crear un entorno aparte para probar este repo

## Probar local

Desde la raíz del repo:

```bash
python3 pdf_parser/index.py 'Liq_CUCH_CUCHA_CUCHA_1588_CAP__FED__04_2026.Pdf'
```

Eso imprime el JSON parseado por `stdout`.

## Estructura del JSON

Las claves principales hoy son:

- `administracion`
- `consorcio`
- `emisor`
- `remuneraciones al personal y cargas sociales`
- `pagos del período por suministros, servicios, abonos y seguros`
- `estado de cuentas`
- `estado de cuentas totales`
- `formas de pago`
- `resumen financiero`

La sección más importante, `estado de cuentas`, sale como una lista de objetos; cada uno representa una unidad/departamento con campos como:

- `unidad`
- `piso_dpto`
- `propietario`
- `saldo_anterior`
- `pagos`
- `deuda`
- `intereses`
- `expensas_a_porcentaje`
- `expensas_a_monto`
- `redondeo`
- `total`

Si querés validar que el archivo compila:

```bash
python3 -m py_compile pdf_parser/index.py
```

## Usarlo como módulo

```python
from pathlib import Path

from pdf_parser.index import parse_pdf_to_json

pdf_bytes = Path("Liq_CUCH_CUCHA_CUCHA_1588_CAP__FED__04_2026.Pdf").read_bytes()
data = parse_pdf_to_json(pdf_bytes)
```

## Usarlo en AWS Lambda

El handler es:

```text
pdf_parser.index.lambda_handler
```

El evento puede incluir una de estas dos opciones:

```json
{
  "pdf_base64": "JVBERi0xLjIK..."
}
```

o:

```json
{
  "pdf_path": "/var/task/archivo.pdf"
}
```

## Notas

- Este parser está ajustado al layout del PDF actual de expensas.
- Usa `pdfplumber` para extraer layout, texto y columnas.
- Si cambia mucho el formato del emisor, puede hacer falta recalibrar reglas de columnas o regex.
- Si el PDF futuro viene escaneado como imagen, este parser no alcanza por sí solo y habría que sumar OCR.
