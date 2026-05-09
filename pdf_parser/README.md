# PDF Parser

Parser de liquidaciones de expensas en PDF, pensado para correr en AWS Lambda y también probarse localmente.

## Estructura

- `pdf_parser/index.py`: parser principal
- `pdf_parser/__init__.py`: marca el directorio como paquete importable
- `pdf_parser/requirements.txt`: dependencias usadas por el contenedor

## Requisitos

- Python 3.10+ recomendado
- El parser usa `pdfplumber`
- Si querés correrlo fuera del contenedor, instalá dependencias con `pip install -r pdf_parser/requirements.txt`

## Probar local

Desde la raíz del repo:

```bash
python3 -m pip install -r pdf_parser/requirements.txt
```

Después:

```bash
python3 pdf_parser/index.py 'Liq_CUCH_CUCHA_CUCHA_1588_CAP__FED__04_2026.Pdf'
```

Eso imprime el JSON parseado por `stdout`.

## Probar como Lambda Container

### 1. Build de la imagen

Desde la raíz del repo:

```bash
docker build -t pdf-parser-lambda -f pdf_parser/Dockerfile .
```

### 2. Levantar la Lambda local

Este comando monta el repo en `/workspace` para que la Lambda pueda leer el PDF de ejemplo:

```bash
docker run --rm -p 9000:8080 -v "$PWD:/workspace" pdf-parser-lambda
```

### 3. Invocar la Lambda local

En otra terminal:

```bash
curl -XPOST 'http://localhost:9000/2015-03-31/functions/function/invocations' \
  -H 'Content-Type: application/json' \
  -d @pdf_parser/event.local.json
```

El archivo [event.local.json](/Users/mateo/Documents/GitHub/consorcio-app/pdf_parser/event.local.json) usa:

- `pdf_path`: apunta al PDF montado en `/workspace`
- `skip_s3_upload: true`: para poder probar el parser sin credenciales AWS ni bucket

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

El evento puede incluir una de estas dos opciones para el PDF:

```json
{
  "pdf_base64": "JVBERi0xLjIK...",
  "s3_bucket": "mi-bucket"
}
```

o:

```json
{
  "pdf_path": "/var/task/archivo.pdf",
  "s3_bucket": "mi-bucket"
}
```

Para desactivar la subida a S3 en pruebas locales:

```json
{
  "pdf_path": "/workspace/Liq_CUCH_CUCHA_CUCHA_1588_CAP__FED__04_2026.Pdf",
  "skip_s3_upload": true
}
```

También podés pasar el bucket por variable de entorno:

```text
S3_BUCKET=mi-bucket
```

Opcionalmente podés overridear el prefijo base:

```text
S3_PREFIX=expensas-dashboard-data
```

## Estructura en S3

El `lambda_handler` guarda siempre dos archivos:

- el PDF original
- el JSON parseado

La estructura queda así:

```text
expensas-dashboard-data/
  cucha-cucha-1588-cap-fed/
    2026-04/
      original.pdf
      parsed.json
```

El nombre del edificio se arma a partir de `consorcio.nombre`, normalizado a slug.
La carpeta de período se arma a partir de `consorcio.periodo`.

## Respuesta de Lambda

La respuesta devuelve:

- `data`: el JSON parseado
- `storage`: bucket y keys usadas en S3

## Notas

- Este parser está ajustado al layout del PDF actual de expensas.
- Usa `pdfplumber` para extraer layout, texto y columnas.
- El contenedor instala dependencias desde `pdf_parser/requirements.txt`.
- Si cambia mucho el formato del emisor, puede hacer falta recalibrar reglas de columnas o regex.
- Si el PDF futuro viene escaneado como imagen, este parser no alcanza por sí solo y habría que sumar OCR.
