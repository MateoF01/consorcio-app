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

## Actualizar el parser más adelante

Si después querés cambiar lógica de parseo, campos del JSON o la forma de guardar en S3, el flujo recomendado es este.

### 1. Editar el código

Normalmente vas a tocar alguno de estos archivos:

- [pdf_parser/index.py](/Users/mateo/Documents/GitHub/consorcio-app/pdf_parser/index.py): lógica del parser y upload a S3
- [pdf_parser/requirements.txt](/Users/mateo/Documents/GitHub/consorcio-app/pdf_parser/requirements.txt): dependencias Python
- [pdf_parser/Dockerfile](/Users/mateo/Documents/GitHub/consorcio-app/pdf_parser/Dockerfile): imagen de Lambda, solo si necesitás cambiar cómo se construye el contenedor

### 2. Probar localmente el cambio

Si querés probar el parser directo:

```bash
python3 -m pip install -r pdf_parser/requirements.txt
python3 pdf_parser/index.py 'Liq_CUCH_CUCHA_CUCHA_1588_CAP__FED__04_2026.Pdf'
```

Si querés validar sintaxis:

```bash
python3 -m py_compile pdf_parser/index.py
```

### 3. Probar la Lambda local como contenedor

Reconstruí la imagen:

```bash
docker build -t pdf-parser-lambda -f pdf_parser/Dockerfile .
```

Levantala:

```bash
docker run --rm -p 9000:8080 -v "$PWD:/workspace" pdf-parser-lambda
```

Invocala:

```bash
curl -XPOST 'http://localhost:9000/2015-03-31/functions/function/invocations' \
  -H 'Content-Type: application/json' \
  -d @pdf_parser/event.local.json
```

### 4. Volver a buildar la imagen para AWS

Cuando el cambio ya está bien:

```bash
docker build -t pdf-parser-lambda -f pdf_parser/Dockerfile .
```

### 5. Etiquetar la imagen para ECR

Ejemplo con tu cuenta y repo:

```bash
docker tag pdf-parser-lambda:latest 623859664918.dkr.ecr.sa-east-1.amazonaws.com/pdf-parser-lambda:latest
```

Mejor práctica: además del `latest`, podés usar tags versionados:

```bash
docker tag pdf-parser-lambda:latest 623859664918.dkr.ecr.sa-east-1.amazonaws.com/pdf-parser-lambda:v2
```

### 6. Push a ECR

Si todavía no hiciste login en ECR:

```bash
aws ecr get-login-password --region sa-east-1 | docker login --username AWS --password-stdin 623859664918.dkr.ecr.sa-east-1.amazonaws.com
```

Después:

```bash
docker push 623859664918.dkr.ecr.sa-east-1.amazonaws.com/pdf-parser-lambda:latest
```

o si versionaste:

```bash
docker push 623859664918.dkr.ecr.sa-east-1.amazonaws.com/pdf-parser-lambda:v2
```

### 7. Actualizar la Lambda desde la consola de AWS

En AWS Console:

1. Entrá a **Lambda**
2. Abrí tu función
3. Andá a la pestaña o sección de **Code**
4. En funciones basadas en imagen, usá **Deploy new image** o **Edit image URI**
5. Seleccioná la nueva imagen/tag de ECR
6. Guardá / Deploy

Si usás siempre el tag `latest`, igual conviene hacer el deploy explícito desde la consola para que Lambda tome la nueva imagen.

### 8. Probar la función actualizada

Después del deploy:

1. Andá a la pestaña **Test**
2. Usá un evento de prueba
3. Revisá el resultado
4. Si falla, mirá **CloudWatch Logs**

## Flujo corto de mantenimiento

Cada vez que cambies algo, el ciclo normal es:

```bash
python3 pdf_parser/index.py 'Liq_CUCH_CUCHA_CUCHA_1588_CAP__FED__04_2026.Pdf'
docker build -t pdf-parser-lambda -f pdf_parser/Dockerfile .
docker tag pdf-parser-lambda:latest 623859664918.dkr.ecr.sa-east-1.amazonaws.com/pdf-parser-lambda:latest
docker push 623859664918.dkr.ecr.sa-east-1.amazonaws.com/pdf-parser-lambda:latest
```

Y después actualizás la Lambda desde la consola.

## Notas

- Este parser está ajustado al layout del PDF actual de expensas.
- Usa `pdfplumber` para extraer layout, texto y columnas.
- El contenedor instala dependencias desde `pdf_parser/requirements.txt`.
- Si cambia mucho el formato del emisor, puede hacer falta recalibrar reglas de columnas o regex.
- Si el PDF futuro viene escaneado como imagen, este parser no alcanza por sí solo y habría que sumar OCR.
