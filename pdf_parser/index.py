from __future__ import annotations

import base64
import io
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


CURRENT_DIR = Path(__file__).resolve().parent
VENDOR_DIR = CURRENT_DIR / "vendor"
if str(VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(VENDOR_DIR))

import pdfplumber


SECTION_NAME_MAP = {
    2: "servicios públicos",
    3: "abonos de servicios",
    4: "mantenimiento de partes comunes",
    5: "trabajos de reparaciones en unidades",
    6: "gastos bancarios",
    7: "gastos de limpieza",
    8: "gastos de administración",
    9: "pagos del período por seguros",
    10: "otros",
}

ACCOUNT_COLUMN_RANGES = {
    "unidad": (20, 220),
    "saldo_anterior": (220, 276),
    "pagos": (276, 323),
    "deuda": (323, 370),
    "intereses": (370, 416),
    "expensas_a_porcentaje": (416, 456),
    "expensas_a_monto": (456, 503),
    "expensas_b_porcentaje": (503, 542),
    "expensas_b_monto": (542, 588),
    "gastos_c_porcentaje": (588, 628),
    "gastos_c_monto": (628, 674),
    "redondeo": (674, 710),
    "total": (710, 761),
}


def clean_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_amount(value: str | None) -> float | None:
    if value is None:
        return None
    normalized = value.strip().replace(".", "").replace(",", ".")
    if not normalized:
        return None
    return float(normalized)


def parse_percent(value: str | None) -> float | None:
    if value is None:
        return None
    return parse_amount(value.replace("%", ""))


def extract_last_money(line: str | None) -> float | None:
    if not line:
        return None
    match = re.search(r"(-?[\d.]+,\d{2})$", line)
    return parse_amount(match.group(1)) if match else None


def extract_page_lines(page: pdfplumber.page.Page) -> list[str]:
    text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
    return [clean_space(line) for line in text.splitlines() if clean_space(line)]


def row_words(page: pdfplumber.page.Page, tolerance: float = 2.0) -> list[list[dict[str, Any]]]:
    grouped: list[dict[str, Any]] = []
    for word in page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False):
        row = next((item for item in grouped if abs(item["top"] - word["top"]) <= tolerance), None)
        if row is None:
            row = {"top": word["top"], "words": []}
            grouped.append(row)
        row["words"].append(word)

    rows: list[list[dict[str, Any]]] = []
    for row in sorted(grouped, key=lambda item: item["top"]):
        rows.append(sorted(row["words"], key=lambda item: item["x0"]))
    return rows


def words_in_range(words: list[dict[str, Any]], x_min: float, x_max: float) -> str | None:
    selected = [word["text"] for word in words if x_min <= word["x0"] < x_max]
    if not selected:
        return None
    return clean_space(" ".join(selected))


def parse_header(page_1_lines: list[str], page_3_lines: list[str], page_4_lines: list[str]) -> dict[str, Any]:
    page_1_text = "\n".join(page_1_lines)
    page_3_text = "\n".join(page_3_lines)
    page_4_text = "\n".join(page_4_lines)

    liquidation_match = re.search(r"Liquidación de mes:\s*(.+)", page_1_text)
    admin_name_match = re.search(r"Nombre:\s*(GALARDON|.+?)\s+Nombre:", page_1_text)
    admin_address_match = re.search(r"Domicilio:\s*(.+?)\s+ED\.", page_1_text)
    admin_contact_match = re.search(r"Mail:\s*(.+?)\s+Te\.\:\s*(\S+)\s+CUIT:\s*(\S+)", page_1_text)
    admin_line_match = re.search(r"Administración:\s*(.+?)\s+Nº RPA:\s*(\S+)\s+CUIT:\s*(\S+)", page_4_text)
    admin_rpa_match = re.search(r"Inscripción R\.P\.A\.\:\s*(\S+)", page_1_text)
    admin_tax_match = re.search(r"Situación Fiscal:\s*(.+)", page_1_text)
    consortium_cuit_match = re.search(r"Clave SUTERH:\s*(\S+)", page_1_text)
    consortium_address_match = re.search(r"Domicilio del Consorcio:\s*(.+?)\s+CUIT:\s*(\S+)", page_4_text)
    due_date_match = re.search(r"DIA DE VENCIMIENTO DE LA PRESENTE LIQUIDACION:\s*(\S+)", page_3_text)
    building_match = re.search(r"Edificio:\s*(.+)", page_1_text)
    issuer_name = page_1_lines[0] if page_1_lines else None

    admin_email = None
    admin_phone = None
    admin_cuit = None
    if admin_contact_match:
        admin_email = admin_contact_match.group(1).strip()
        admin_phone = admin_contact_match.group(2).strip()
    if admin_line_match:
        admin_cuit = admin_line_match.group(3).strip()

    consortium_name = None
    consortium_cuit = None
    if consortium_address_match:
        consortium_name = consortium_address_match.group(1).strip()
        consortium_cuit = consortium_address_match.group(2).strip()

    return {
        "administracion": {
            "nombre": admin_name_match.group(1).strip() if admin_name_match else None,
            "domicilio": admin_address_match.group(1).strip() if admin_address_match else None,
            "mail": admin_email,
            "telefono": admin_phone,
            "cuit": admin_cuit,
            "inscripcion_rpa": admin_rpa_match.group(1).strip() if admin_rpa_match else None,
            "situacion_fiscal": admin_tax_match.group(1).strip() if admin_tax_match else None,
        },
        "consorcio": {
            "nombre": consortium_name,
            "domicilio": consortium_name,
            "cuit": consortium_cuit,
            "clave_suterh": consortium_cuit_match.group(1).strip() if consortium_cuit_match else None,
            "edificio": building_match.group(1).strip() if building_match else None,
            "periodo": liquidation_match.group(1).strip() if liquidation_match else None,
            "vencimiento": due_date_match.group(1).strip() if due_date_match else None,
        },
        "emisor": {
            "nombre": issuer_name,
            "roles": [
                line
                for line in page_1_lines
                if line in {
                    "Administrador de Consorcios.",
                    "Martillero Publico, Corredor y Tasador. CUCHA CUCHA 1588-CAP. FED. - Buenos Aires",
                    "RPA 15797 / CUCICBA 5757",
                }
            ],
        },
    }


def parse_table_block(lines: list[str], start_line: str, end_line: str) -> list[str]:
    start_index = lines.index(start_line)
    end_index = lines.index(end_line, start_index)
    return lines[start_index + 1 : end_index]


def parse_simple_item_lines(lines: list[str]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    buffer: list[str] = []

    for line in lines:
        if re.match(r"^\d+\.", line):
            if buffer:
                items.append(parse_single_item(" ".join(buffer)))
            buffer = [line]
        else:
            buffer.append(line)

    if buffer:
        items.append(parse_single_item(" ".join(buffer)))

    return items


def parse_single_item(line: str) -> dict[str, Any]:
    normalized = clean_space(line)
    item_number_match = re.match(r"^(\d+)\.(.+)$", normalized)
    if not item_number_match:
        return {"descripcion": normalized}

    item_number = int(item_number_match.group(1))
    content = clean_space(item_number_match.group(2))
    amounts = re.findall(r"-?[\d.]+,\d{2}", content)
    description = clean_space(re.sub(r"(?:\s+-?[\d.]+,\d{2})+$", "", content).strip())

    if "SIN MOVIMIENTOS" in content:
        description = "SIN MOVIMIENTOS"

    return {
        "item": item_number,
        "descripcion": description,
        "montos": [parse_amount(amount) for amount in amounts],
    }


def parse_expense_sections(page_1_lines: list[str], page_2_lines: list[str]) -> dict[str, Any]:
    lines = page_1_lines + page_2_lines
    start_index = lines.index("RUBROS - CONCEPTO - DETALLE DE PROVEEDORES") + 1
    end_index = lines.index("TOTAL DE GASTOS (100,000%) 1.739.021,29 1.739.021,29")
    section_lines = lines[start_index:end_index]

    parsed: dict[str, Any] = {}
    current_number: int | None = None
    current_title: str | None = None
    current_lines: list[str] = []

    for line in section_lines:
        header_match = re.match(r"^(\d{1,2})\s+(.+)$", line)
        total_match = re.match(r"^TOTAL RUBRO (\d{1,2})\s+([\d.,]+%)\s+(-?[\d.]+,\d{2})$", line)

        if total_match and current_number is not None and current_title is not None:
            parsed[current_title] = {
                "items": parse_simple_item_lines(current_lines),
                "total": {
                    "porcentaje": parse_percent(total_match.group(2)),
                    "monto": parse_amount(total_match.group(3)),
                },
            }
            current_number = None
            current_title = None
            current_lines = []
            continue

        if header_match and line.startswith(tuple(str(number) for number in range(2, 11))):
            current_number = int(header_match.group(1))
            current_title = SECTION_NAME_MAP.get(current_number, clean_space(header_match.group(2)).lower())
            current_lines = []
            continue

        if current_number is not None:
            current_lines.append(line)

    grand_total_line = lines[end_index]
    grand_total_match = re.search(r"\(([\d.,]+%)\)\s+(-?[\d.]+,\d{2})\s+(-?[\d.]+,\d{2})$", grand_total_line)
    parsed["total_de_gastos"] = {
        "porcentaje": parse_percent(grand_total_match.group(1)) if grand_total_match else None,
        "monto": parse_amount(grand_total_match.group(2)) if grand_total_match else None,
    }
    return parsed


def parse_remuneraciones(page_1_lines: list[str]) -> dict[str, Any]:
    detail_items = [{"descripcion": "SIN MOVIMIENTOS", "monto": 0.0}]
    detail_total = {"porcentaje": 0.0, "monto": 0.0}
    contributions_items = [{"descripcion": "SIN MOVIMIENTOS", "monto": 0.0}]
    contributions_total = {"porcentaje": 0.0, "monto": 0.0}
    rubro_total = {"porcentaje": 0.0, "monto": 0.0}

    for line in page_1_lines:
        if line == "1.SIN MOVIMIENTOS 0,00":
            continue
        if line == "TOTAL 0,000% 0,00" and detail_total["monto"] == 0.0:
            detail_total = {"porcentaje": 0.0, "monto": 0.0}
        elif line == "TOTAL 0,000% 0,00":
            contributions_total = {"porcentaje": 0.0, "monto": 0.0}
        elif line == "TOTAL RUBRO 1 0,000% 0,00":
            rubro_total = {"porcentaje": 0.0, "monto": 0.0}

    return {
        "detalle_de_sueldo_y_cargas_sociales": {
            "items": detail_items,
            "total": detail_total,
        },
        "aportes_y_contribuciones": {
            "items": contributions_items,
            "total": contributions_total,
        },
        "total_rubro": rubro_total,
    }


def parse_estado_de_cuentas(page_4: pdfplumber.page.Page) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    items: list[dict[str, Any]] = []
    totals: dict[str, Any] | None = None
    payment_info: dict[str, Any] = {}

    for words in row_words(page_4):
        first_cell = words_in_range(words, *ACCOUNT_COLUMN_RANGES["unidad"])
        if not first_cell:
            continue

        if re.match(r"^\d+\s+", first_cell):
            unit_number, unit_label = first_cell.split(" ", 1)
            piso_dpto, propietario = (unit_label.split(" ", 1) + [""])[:2]
            items.append(
                {
                    "unidad": int(unit_number),
                    "piso_dpto": piso_dpto.strip(),
                    "propietario": propietario.strip() or None,
                    "saldo_anterior": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["saldo_anterior"])),
                    "pagos": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["pagos"])),
                    "deuda": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["deuda"])),
                    "intereses": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["intereses"])),
                    "expensas_a_porcentaje": parse_percent(words_in_range(words, *ACCOUNT_COLUMN_RANGES["expensas_a_porcentaje"])),
                    "expensas_a_monto": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["expensas_a_monto"])),
                    "expensas_b_porcentaje": parse_percent(words_in_range(words, *ACCOUNT_COLUMN_RANGES["expensas_b_porcentaje"])),
                    "expensas_b_monto": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["expensas_b_monto"])),
                    "gastos_c_porcentaje": parse_percent(words_in_range(words, *ACCOUNT_COLUMN_RANGES["gastos_c_porcentaje"])),
                    "gastos_c_monto": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["gastos_c_monto"])),
                    "redondeo": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["redondeo"])),
                    "total": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["total"])),
                }
            )
        elif first_cell == "TOTAL":
            totals = {
                "saldo_anterior": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["saldo_anterior"])),
                "pagos": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["pagos"])),
                "deuda": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["deuda"])),
                "intereses": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["intereses"])),
                "expensas_a_porcentaje": parse_percent(words_in_range(words, *ACCOUNT_COLUMN_RANGES["expensas_a_porcentaje"])),
                "expensas_a_monto": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["expensas_a_monto"])),
                "expensas_b_porcentaje": parse_percent(words_in_range(words, *ACCOUNT_COLUMN_RANGES["expensas_b_porcentaje"])),
                "expensas_b_monto": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["expensas_b_monto"])),
                "gastos_c_porcentaje": parse_percent(words_in_range(words, *ACCOUNT_COLUMN_RANGES["gastos_c_porcentaje"])),
                "gastos_c_monto": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["gastos_c_monto"])),
                "redondeo": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["redondeo"])),
                "total": parse_amount(words_in_range(words, *ACCOUNT_COLUMN_RANGES["total"])),
            }
        elif first_cell.startswith("Titular:"):
            first_line = clean_space(" ".join(word["text"] for word in words))
            payment_info["titular"] = clean_space(first_line.replace("Titular:", "").split("Banco:")[0])
            if "Banco:" in first_line:
                payment_info["banco"] = clean_space(first_line.split("Banco:", 1)[1])
        elif first_cell.startswith("CBU:"):
            first_line = clean_space(" ".join(word["text"] for word in words))
            cbu_match = re.search(r"CBU:\s*(\S+)", first_line)
            branch_match = re.search(r"Sucursal:\s*(\S+)", first_line)
            payment_info["cbu"] = cbu_match.group(1) if cbu_match else None
            payment_info["sucursal"] = branch_match.group(1) if branch_match else None

    if totals is None:
        totals = {}

    return items, totals, payment_info


def parse_resumen_financiero(page_2_lines: list[str]) -> dict[str, Any]:
    return {
        "concepto": next((line.replace("CONCEPTO:", "").strip() for line in page_2_lines if line.startswith("CONCEPTO:")), None),
        "saldo_anterior": extract_last_money(next((line for line in page_2_lines if line.startswith("SALDO ANTERIOR")), None)),
        "ingresos_del_mes": extract_last_money(next((line for line in page_2_lines if line.startswith("Ingresos de éste mes")), None)),
        "egresos_del_periodo": extract_last_money(next((line for line in page_2_lines if line.startswith("Egresos realizados en este período")), None)),
        "ingreso_efectivo_recibido": extract_last_money(next((line for line in page_2_lines if line.startswith("Ingreso efectivo recibido adm BAÑOS")), None)),
        "saldo_al_cierre": extract_last_money(next((line for line in page_2_lines if line == "SALDO AL CIERRE $ 6.202.583,01"), None)),
    }


def parse_pdf_to_json(pdf_bytes: bytes) -> dict[str, Any]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        page_1 = pdf.pages[0]
        page_2 = pdf.pages[1]
        page_3 = pdf.pages[2]
        page_4 = pdf.pages[3]

        page_1_lines = extract_page_lines(page_1)
        page_2_lines = extract_page_lines(page_2)
        page_3_lines = extract_page_lines(page_3)
        page_4_lines = extract_page_lines(page_4)

        header = parse_header(page_1_lines, page_3_lines, page_4_lines)
        estado_de_cuentas, estado_totales, formas_de_pago = parse_estado_de_cuentas(page_4)

        return {
            "administracion": header["administracion"],
            "consorcio": header["consorcio"],
            "emisor": header["emisor"],
            "remuneraciones al personal y cargas sociales": parse_remuneraciones(page_1_lines),
            "pagos del período por suministros, servicios, abonos y seguros": parse_expense_sections(page_1_lines, page_2_lines),
            "estado de cuentas": estado_de_cuentas,
            "estado de cuentas totales": estado_totales,
            "formas de pago": formas_de_pago,
            "resumen financiero": parse_resumen_financiero(page_2_lines),
        }


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    if "pdf_base64" in event:
        pdf_bytes = base64.b64decode(event["pdf_base64"])
    elif "pdf_path" in event:
        pdf_bytes = Path(event["pdf_path"]).read_bytes()
    else:
        raise ValueError("El evento debe incluir 'pdf_base64' o 'pdf_path'.")

    return parse_pdf_to_json(pdf_bytes)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python3 pdf_parser/index.py <archivo.pdf>", file=sys.stderr)
        return 1

    payload = parse_pdf_to_json(Path(argv[1]).read_bytes())
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
