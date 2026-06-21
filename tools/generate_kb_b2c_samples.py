from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from openpyxl import load_workbook
except ModuleNotFoundError:
    load_workbook = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend" / "src" / "app" / "openapi-test" / "samples.generated.json"
WORKBOOK_PATTERN = "KB_B2C_OpenAPI*.xlsx"
XML_DIR = ROOT / "KB_B2C"
LEGACY_XML_DIR = ROOT / "trx_b2c"
B2C_INDEX_FILE = "B2C.txt"

INPUT_TEXT = "\uc785\ub825"
OUTPUT_TEXT = "\ucd9c\ub825"

DATA_HEADER = {
    "udId": "UDID",
    "subChannel": "subChannel",
    "deviceModel": "Android",
    "deviceOs": "Android",
    "carrier": "KT",
    "connectionType": "..",
    "appName": "..",
    "appVersion": "..",
    "scrNo": "0000",
}


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def normalize_tr_code(raw_code: str, sheet_name: str = "") -> str:
    source = raw_code or sheet_name
    source = re.sub(r"\([^)]*\)", "", source)
    source = re.sub(r"[^0-9A-Za-z]", "", source)
    return source.upper()


def is_field_name(value: str) -> bool:
    if not value:
        return False
    upper = value.upper()
    if upper in {"\uc601\ubb38\uba85", "INPUT", "OUTPUT", "IN", "OUT", "RQ", "RP"}:
        return False
    return bool(re.search(r"[A-Za-z]", value))


def field_from_standard_row(row: tuple[Any, ...]) -> dict[str, str] | None:
    korean = clean(row[2] if len(row) > 2 else "")
    english = clean(row[3] if len(row) > 3 else "")
    if not is_field_name(english):
        return None
    return {
        "korean": korean,
        "name": english,
        "type": clean(row[4] if len(row) > 4 else ""),
        "length": clean(row[5] if len(row) > 5 else ""),
        "decimal": clean(row[6] if len(row) > 6 else ""),
        "note": clean(row[7] if len(row) > 7 else ""),
    }


def field_from_realtime_row(row: tuple[Any, ...]) -> dict[str, str] | None:
    korean = clean(row[1] if len(row) > 1 else "")
    english = clean(row[6] if len(row) > 6 else "")
    if not is_field_name(english):
        return None
    return {
        "korean": korean,
        "name": english,
        "type": "",
        "length": "",
        "decimal": "",
        "note": "",
    }


def has_marker(row: tuple[Any, ...], marker: str) -> bool:
    return any(clean(cell).upper() == marker for cell in row)


def has_text(row: tuple[Any, ...], text: str) -> bool:
    return any(text in clean(cell) for cell in row)


def parse_block_fields(rows: list[tuple[Any, ...]]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []

    for index, row in enumerate(rows):
        if not has_marker(row, "BLOCK") or not has_text(row, INPUT_TEXT):
            continue

        for field_row in rows[index + 2 :]:
            if has_marker(field_row, "BLOCK"):
                break
            if not any(clean(cell) for cell in field_row):
                break
            field = field_from_standard_row(field_row)
            if field:
                fields.append(field)

    return fields


def parse_rq_fields(rows: list[tuple[Any, ...]]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    collecting = False
    started_with = ""

    for row in rows:
        marker = clean(row[1] if len(row) > 1 else "").upper()
        if marker in {"RQ", "IN"}:
            if fields:
                break
            collecting = True
            started_with = marker
            continue

        if collecting and marker in {"RP", "OUT"}:
            break
        if collecting and has_text(row, OUTPUT_TEXT):
            break

        if not collecting:
            continue

        if not any(clean(cell) for cell in row):
            if fields:
                break
            continue

        field = field_from_standard_row(row)
        if field:
            fields.append(field)

    return fields if started_with else []


def parse_realtime_key_fields(rows: list[tuple[Any, ...]]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    collecting = False

    for row in rows:
        row_text = " ".join(clean(cell) for cell in row)
        if INPUT_TEXT in row_text and "input" in row_text.lower():
            collecting = True
            continue
        if collecting and (OUTPUT_TEXT in row_text or "output" in row_text.lower()):
            break
        if not collecting:
            continue

        field = field_from_realtime_row(row)
        if field:
            fields.append(field)

    return fields


def parse_input_fields(ws) -> tuple[str, list[dict[str, str]]]:
    rows = list(ws.iter_rows(values_only=True))

    block_fields = parse_block_fields(rows)
    if block_fields:
        return "block", block_fields

    rq_fields = parse_rq_fields(rows)
    if rq_fields:
        return "rq", rq_fields

    realtime_fields = parse_realtime_key_fields(rows)
    if realtime_fields:
        return "realtime", realtime_fields

    return "unknown", []


def extract_description(ws, fallback: str) -> str:
    rows = list(ws.iter_rows(min_row=1, max_row=15, values_only=True))
    for row in rows:
        cells = [clean(cell) for cell in row]
        for index, cell in enumerate(cells):
            if cell == "\uc124\uba85":
                for value in cells[index + 1 :]:
                    if value:
                        return value
    return fallback


def default_value(field: dict[str, str]) -> str:
    name = field["name"]
    upper = name.upper()
    lower = name.lower()
    korean = field.get("korean", "")
    note = field.get("note", "")
    configured_default = clean(field.get("default", ""))
    text = f"{upper} {korean} {note}"
    compact_text = compact(text)

    if configured_default:
        return configured_default
    if upper.startswith("ATTR_"):
        return ""
    if upper in {"FILLER", "CONTKEY"} or "CONTKEY" in upper:
        return ""
    if upper in {"GNL_AC_NO", "AC_NO", "ACNO"} or upper.endswith("_AC_NO"):
        return "{{gnlAcNo}}"
    if upper == "GDS_NO":
        return "{{gdsNo}}"
    if upper in {"PWD", "AC_PWD"} or upper.endswith("_PWD"):
        return "{{pwd}}"
    if upper in {"CI_NO", "CINO"}:
        return "{{ciNo}}"
    if upper == "CONTIF":
        return "0"
    if upper in {"RL_TM_KEY", "TR_KEY"}:
        if "\ud574\uc678" in text or "KRX_CD" in text or "\uac70\ub798\uc18c" in text:
            return "NASAAPL"
        return "005930"
    if upper in {"IS_CD", "PDNO", "STK_CD", "STCK_SHRN_ISCD"} or "IS_CD" in upper:
        return "005930"
    if upper in {"KRX_CD", "EXCH_CD"}:
        return "NAS"
    if upper == "NTN_CD":
        return "USA"
    if upper == "N_MINUTE":
        return "1"
    if upper in {"INQ_CNT", "RCRD_C"} or upper.endswith("_CNT") or "COUNT" in upper:
        return "10"
    if "STRT_DT" in upper or "START_DT" in upper or "\uc2dc\uc791\uc77c\uc790" in compact_text:
        return "20250101"
    if "END_DT" in upper or "\uc885\ub8cc\uc77c\uc790" in compact_text:
        return "20251231"
    if upper in {"DT", "BSNSS_DT", "KOR_DT"} or upper.endswith("_DT"):
        return "20250617"
    if upper in {"TM", "KOR_TM"} or upper.endswith("_TM"):
        return "090000"
    if upper.endswith("_YN"):
        return "N"
    if any(token in upper for token in ("CLSF", "CCD", "DVSN", "GB", "TYPE")):
        return "1"
    if upper.endswith("_Q") or "QTY" in upper:
        return "1"
    if upper.endswith("_C") or "CNT" in upper:
        return "10"
    if upper.startswith("N_") and lower != "n_minute":
        return "1"

    return ""


def build_data_body(fields: list[dict[str, str]]) -> dict[str, str]:
    body: dict[str, str] = {}
    for field in fields:
        key = field["name"]
        if key not in body:
            body[key] = default_value(field)
    return body


def load_b2c_catalog(workbook_path: Path) -> dict[str, Any]:
    if load_workbook is None:
        raise RuntimeError("openpyxl is required to load the KB B2C workbook.")

    wb = load_workbook(workbook_path, read_only=True, data_only=True)
    index = wb.worksheets[0]
    b2c: list[dict[str, Any]] = []
    layout_counts: dict[str, int] = {}

    for row in index.iter_rows(min_row=3, values_only=True):
        raw_code = clean(row[1] if len(row) > 1 else "")
        service_name = clean(row[2] if len(row) > 2 else "")
        sheet_name = clean(row[3] if len(row) > 3 else "") or raw_code
        if not raw_code:
            continue
        if sheet_name not in wb.sheetnames:
            continue

        ws = wb[sheet_name]
        tr_code = normalize_tr_code(raw_code, sheet_name)
        layout, fields = parse_input_fields(ws)
        description = extract_description(ws, service_name)
        layout_counts[layout] = layout_counts.get(layout, 0) + 1

        body = {
            "dataHeader": dict(DATA_HEADER),
            "dataBody": build_data_body(fields),
        }

        label_prefix = "\uc2e4\uc2dc\uac04 " if layout in {"realtime", "unknown"} and tr_code.startswith("KBRS") else ""
        b2c.append(
            {
                "id": f"Tkb_{tr_code}_B2C",
                "label": f"{tr_code} {label_prefix}{service_name}".strip(),
                "method": "POST",
                "endpoint": f"/excel-b2c/{tr_code.lower()}",
                "description": f"B2C \ud22c\uc790\uc815\ubcf4: {description}",
                "headers": {"Content-Type": "application/json"},
                "body": body,
                "query": {},
                "fileName": workbook_path.name,
                "source": "kb-b2c-excel",
                "layout": layout,
                "sheetName": sheet_name,
            }
        )

    return {"b2c": b2c, "layoutCounts": layout_counts}


def read_xml_text(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def load_b2c_index(xml_dir: Path) -> list[dict[str, Any]]:
    index_path = xml_dir / B2C_INDEX_FILE
    if not index_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    current_category = ""
    duplicate_counts: dict[str, int] = {}

    for line in read_text_file(index_path).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            current_category = stripped.strip("[]").strip()
            continue
        if "-" not in stripped:
            continue

        raw_code, raw_label = stripped.split("-", 1)
        tr_code = normalize_tr_code(raw_code)
        if not tr_code:
            continue

        duplicate_counts[tr_code] = duplicate_counts.get(tr_code, 0) + 1
        entries.append(
            {
                "trCode": tr_code,
                "label": clean(raw_label) or tr_code,
                "category": current_category,
                "order": len(entries),
                "duplicateIndex": duplicate_counts[tr_code],
            }
        )

    return entries


def parse_xml_root(path: Path) -> tuple[ET.Element, str]:
    text, encoding = read_xml_text(path)
    xml_body = re.sub(r"<\?xml[^>]*\?>", "", text, count=1).lstrip()
    return ET.fromstring(xml_body), encoding


def field_from_xml_node(node: ET.Element) -> dict[str, str] | None:
    name = clean(node.attrib.get("Name"))
    if not name or name.startswith("_"):
        return None

    io_type = clean(node.attrib.get("IOType")).lower()
    spec = clean(node.attrib.get("Spec") or node.attrib.get("format"))
    if io_type == "record" or spec.lower() == "struct":
        return None

    return {
        "korean": clean(node.attrib.get("Desc")),
        "name": name,
        "type": clean(node.attrib.get("format") or node.attrib.get("Spec")),
        "length": clean(node.attrib.get("Size") or node.attrib.get("SizeEN") or node.attrib.get("SizeKR")),
        "decimal": clean(node.attrib.get("portion")),
        "note": clean(node.attrib.get("IOType")),
        "default": clean(node.attrib.get("Default")),
    }


def parse_xml_input_fields(root: ET.Element) -> list[dict[str, str]]:
    input_node = root.find("Input")
    if input_node is None:
        return []

    fields: list[dict[str, str]] = []
    for node in input_node.iter():
        if node is input_node:
            continue
        field = field_from_xml_node(node)
        if field:
            fields.append(field)
    return fields


def build_b2c_xml_item(
    xml_path: Path,
    root: ET.Element,
    encoding: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    tr_code = normalize_tr_code(
        clean(root.findtext("Name")) or clean(root.findtext("Route")) or clean(metadata.get("trCode")) or xml_path.stem
    )
    description = clean(metadata.get("label")) or clean(root.findtext("Desc")) or tr_code
    category = clean(metadata.get("category"))
    duplicate_index = int(metadata.get("duplicateIndex") or 1)
    fields = parse_xml_input_fields(root)
    body = {
        "dataHeader": dict(DATA_HEADER),
        "dataBody": build_data_body(fields),
    }
    item_id = xml_path.stem if duplicate_index <= 1 else f"{xml_path.stem}__{duplicate_index}"
    description_prefix = f"{category}: " if category else ""

    return {
        "id": item_id,
        "label": f"{tr_code} {description}".strip(),
        "method": "POST",
        "endpoint": f"/api/v1/{tr_code.lower()}",
        "transactionCode": tr_code,
        "description": f"B2C XML 전문: {description_prefix}{description}",
        "headers": {"Content-Type": "application/json"},
        "body": body,
        "query": {},
        "fileName": xml_path.name,
        "source": "kb-b2c-xml",
        "layout": "xml",
        "inputFieldCount": len(fields),
        "menu": category,
        "sourceEncoding": encoding,
    }


def load_b2c_xml_catalog(xml_dir: Path) -> dict[str, Any]:
    b2c: list[dict[str, Any]] = []
    encodings: dict[str, int] = {}
    index_entries = load_b2c_index(xml_dir)
    xml_entries: dict[str, tuple[Path, ET.Element, str]] = {}

    for xml_path in sorted(xml_dir.glob("*.xml")):
        root, encoding = parse_xml_root(xml_path)
        encodings[encoding] = encodings.get(encoding, 0) + 1
        tr_code = normalize_tr_code(clean(root.findtext("Name")) or clean(root.findtext("Route")) or xml_path.stem)
        xml_entries[tr_code] = (xml_path, root, encoding)

    consumed_codes: set[str] = set()
    for entry in index_entries:
        tr_code = clean(entry.get("trCode"))
        xml_entry = xml_entries.get(tr_code)
        if not xml_entry:
            continue
        xml_path, root, encoding = xml_entry
        b2c.append(build_b2c_xml_item(xml_path, root, encoding, entry))
        consumed_codes.add(tr_code)

    for tr_code, (xml_path, root, encoding) in sorted(xml_entries.items()):
        if tr_code in consumed_codes:
            continue
        b2c.append(build_b2c_xml_item(xml_path, root, encoding))

    return {"b2c": b2c, "encodings": encodings, "indexCount": len(index_entries)}


def merge_b2c_catalogs(excel_items: list[dict[str, Any]], xml_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    excel_by_id = {clean(item.get("id")): item for item in excel_items}
    merged: list[dict[str, Any]] = []

    for xml_item in xml_items:
        existing = excel_by_id.get(clean(xml_item.get("id")))
        if existing:
            next_item = dict(existing)
            next_item["source"] = "kb-b2c-excel+xml"
            next_item["sourceXmlFile"] = xml_item.get("fileName")
            next_item["xmlInputFieldCount"] = xml_item.get("inputFieldCount")
            merged.append(next_item)
        else:
            merged.append(xml_item)

    return merged


def main() -> None:
    xml_dir = XML_DIR if XML_DIR.exists() else LEGACY_XML_DIR
    xml_loaded = load_b2c_xml_catalog(xml_dir) if xml_dir.exists() else {"b2c": [], "encodings": {}, "indexCount": 0}
    workbook_path: Path | None = None
    loaded: dict[str, Any] = {"b2c": [], "layoutCounts": {}}

    if xml_loaded["b2c"]:
        b2c_catalog = xml_loaded["b2c"]
    else:
        matches = sorted(ROOT.glob(WORKBOOK_PATTERN))
        if not matches:
            raise SystemExit(f"KB B2C source was not found: {XML_DIR} or {WORKBOOK_PATTERN}")
        workbook_path = matches[0]
        loaded = load_b2c_catalog(workbook_path)
        b2c_catalog = loaded["b2c"]

    catalog = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sourceWorkbook": str(workbook_path) if workbook_path else "",
        "sourceXmlDirectory": str(xml_dir) if xml_loaded["b2c"] else "",
        "b2c": b2c_catalog,
    }

    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(f"B2C: {len(catalog['b2c'])}")
    if loaded["layoutCounts"]:
        print("Layouts:", loaded["layoutCounts"])
    if xml_loaded["b2c"]:
        print(f"XML samples: {len(xml_loaded['b2c'])}, index entries: {xml_loaded.get('indexCount', 0)}, encodings: {xml_loaded['encodings']}")


if __name__ == "__main__":
    main()
