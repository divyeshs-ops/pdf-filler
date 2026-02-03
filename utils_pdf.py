import os
import io
import zipfile
import re
from typing import Dict, List, Tuple, Any, Optional

import pandas as pd
from pdfrw import PdfReader, PdfWriter, PdfDict, PdfName, PdfString, PdfObject


# -------------------------
# Text auto-fit helpers
#
# V1 relied on viewer-side appearance regeneration (NeedAppearances + clearing /AP)
# which *often* auto-fits text. Some PDFs still clip/occlude if the field's default
# appearance (/DA) has a fixed font size. Setting the font size to 0 in /DA is the
# standard way to enable AutoSize in many PDF viewers.
# -------------------------
def _pdfstr_to_text(v: Any) -> str:
    if v is None:
        return ""
    try:
        # pdfrw PdfString objects support decode
        return PdfString.decode(v)
    except Exception:
        return str(v)


def _set_da_autosize(field: Any) -> None:
    """Force font size to 0 in the field's /DA to enable AutoSize where supported."""
    da = getattr(field, "DA", None)
    if not da:
        return
    da_txt = _pdfstr_to_text(da)

    # Replace the first "<number> Tf" with "0 Tf" (keeps the font resource).
    # Example: "/Helv 10 Tf 0 g" -> "/Helv 0 Tf 0 g"
    new_da = re.sub(r"(\s)(-?\d+(?:\.\d+)?)\s+Tf\b", r"\g<1>0 Tf", da_txt, count=1)
    if new_da != da_txt:
        try:
            field.DA = PdfString.encode(new_da)
        except Exception:
            # If encoding fails, leave as-is.
            pass


# -------------------------
# Excel/CSV loader (multi-sheet)
# -------------------------
def load_table_any(file_bytes: bytes, filename: str) -> Tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".csv":
        df = pd.read_csv(io.BytesIO(file_bytes), dtype=str).fillna("")
        return df, {"__csv__": df}

    if ext in [".xlsx", ".xls", ".xlsm"]:
        sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, dtype=str)
        for k in list(sheets.keys()):
            sheets[k] = sheets[k].fillna("")

        master = None
        for sheet_name, sdf in sheets.items():
            sdf2 = sdf.copy()
            sdf2.columns = [f"{sheet_name}::{c}" for c in sdf2.columns]
            if master is None:
                master = sdf2
            else:
                master = master.join(sdf2, how="outer")

        master = master.fillna("")
        return master, sheets

    raise ValueError("Unsupported file. Please upload .xlsx/.xlsm or .csv")


# -------------------------
# PDF helpers
# -------------------------
def is_xfa_pdf(template) -> bool:
    try:
        acro = template.Root.AcroForm
        if acro and hasattr(acro, "XFA") and acro.XFA is not None:
            return True
    except Exception:
        pass
    return False


def iter_fields(field_list):
    """
    Yield BOTH parent fields and kids.
    Many PDFs store the field name (/T) on the parent,
    and the visible widgets in /Kids.
    """
    if not field_list:
        return
    for f in field_list:
        yield f
        kids = getattr(f, "Kids", None)
        if kids:
            for k in iter_fields(kids):
                yield k


def clean_field_name(tval) -> Optional[str]:
    if tval is None:
        return None
    name = str(tval).strip()
    if name.startswith("(") and name.endswith(")"):
        name = name[1:-1]
    name = name.strip()
    return name if name else None


def rect_to_list(r) -> Optional[List[float]]:
    try:
        return [float(r[0]), float(r[1]), float(r[2]), float(r[3])]
    except Exception:
        return None


# -------------------------
# ✅ CRITICAL FIX: correct checkbox ON value detection
# -------------------------
def get_checkbox_on_value(field) -> PdfName:
    """
    Return the exact ON appearance name from /AP /N keys.
    Many PDFs use custom ON names like /Checkbox_40, /On, /1, etc.
    We must return the key exactly as stored in the PDF (no conversion).
    """

    # 1) Try the field object itself
    try:
        ap = getattr(field, "AP", None)
        n = getattr(ap, "N", None) if ap else None
        if n:
            for k in n.keys():
                if str(k) != "/Off":
                    return k  # ✅ return key as-is
    except Exception:
        pass

    # 2) Try Kids widgets (some PDFs store AP on kids only)
    try:
        kids = getattr(field, "Kids", None)
        if kids:
            for kid in kids:
                ap = getattr(kid, "AP", None)
                n = getattr(ap, "N", None) if ap else None
                if n:
                    for k in n.keys():
                        if str(k) != "/Off":
                            return k  # ✅ return key as-is
    except Exception:
        pass

    # Fallback
    return PdfName.Yes


def should_check(value: str, rule: dict) -> bool:
    v = str(value).strip().lower()
    checked_values = [str(x).strip().lower() for x in rule.get("checked_values", [])]
    unchecked_values = [str(x).strip().lower() for x in rule.get("unchecked_values", [])]
    default = str(rule.get("default", "off")).strip().lower()

    if v in checked_values:
        return True
    if v in unchecked_values:
        return False
    return True if default == "on" else False


# -------------------------
# Field extraction (AcroForm + Page Widgets)
# -------------------------
def extract_pdf_fields_all(pdf_path: str) -> Tuple[List[str], Dict[str, str]]:
    pdf = PdfReader(pdf_path)

    if getattr(pdf.Root, "AcroForm", None) is None:
        raise RuntimeError("PDF has no AcroForm fields (not standard fillable).")
    if is_xfa_pdf(pdf):
        raise RuntimeError("This PDF is XFA. Convert to AcroForm first.")

    fields: List[Tuple[str, str]] = []

    all_fields = getattr(pdf.Root.AcroForm, "Fields", None)
    if all_fields:
        for f in iter_fields(all_fields):
            nm = clean_field_name(getattr(f, "T", None))
            if not nm:
                continue
            ft = getattr(f, "FT", None)
            ftype = "checkbox_or_radio" if ft == PdfName.Btn else "text"
            fields.append((nm, ftype))

    for p in getattr(pdf, "pages", []):
        annots = getattr(p, "Annots", None)
        if not annots:
            continue
        for a in annots:
            try:
                if getattr(a, "Subtype", None) != PdfName.Widget:
                    continue
                nm = clean_field_name(getattr(a, "T", None))
                if not nm:
                    continue
                ft = getattr(a, "FT", None)
                ftype = "checkbox_or_radio" if ft == PdfName.Btn else "text"
                fields.append((nm, ftype))
            except Exception:
                continue

    merged: Dict[str, str] = {}
    order: List[str] = []
    for nm, tp in fields:
        if nm not in merged:
            merged[nm] = tp
            order.append(nm)
        else:
            if merged[nm] != "checkbox_or_radio" and tp == "checkbox_or_radio":
                merged[nm] = tp

    return order, merged


def build_field_rect_index(pdf_path: str) -> Tuple[Dict[str, List[Dict[str, Any]]], int]:
    pdf = PdfReader(pdf_path)
    idx: Dict[str, List[Dict[str, Any]]] = {}

    pages = getattr(pdf, "pages", [])
    for pi, page in enumerate(pages):
        annots = getattr(page, "Annots", None)
        if not annots:
            continue
        for a in annots:
            try:
                if getattr(a, "Subtype", None) != PdfName.Widget:
                    continue
                nm = clean_field_name(getattr(a, "T", None))
                if not nm:
                    continue
                r = rect_to_list(getattr(a, "Rect", None))
                if not r:
                    continue
                idx.setdefault(nm, []).append({"page": pi, "rect": r})
            except Exception:
                continue

    return idx, len(pages)


def get_page_mediabox(pdf_path: str, page_index: int) -> Tuple[float, float, float, float]:
    pdf = PdfReader(pdf_path)
    page = pdf.pages[page_index]
    media = getattr(page, "MediaBox", None)
    if not media:
        return (0.0, 0.0, 612.0, 792.0)
    x0, y0, x1, y1 = float(media[0]), float(media[1]), float(media[2]), float(media[3])
    return (x0, y0, x1, y1)


# -------------------------
# Fill PDF
# -------------------------
def fill_pdf_with_pdfrw(
    template_path: str,
    output_path: str,
    data_row: pd.Series,
    mapping: Dict[str, str],
    rules: Dict[str, dict],
    debug: bool = False,
    force_autosize_text: bool = True,
) -> int:
    template = PdfReader(template_path)

    if getattr(template.Root, "AcroForm", None) is None:
        raise RuntimeError("No AcroForm found in PDF.")
    if is_xfa_pdf(template):
        raise RuntimeError("This PDF is XFA. Convert to AcroForm first.")

    try:
        template.Root.AcroForm.update(PdfDict(NeedAppearances=PdfObject("true")))
    except Exception:
        pass

    filled_count = 0
    all_fields = getattr(template.Root.AcroForm, "Fields", None)
    if not all_fields:
        raise RuntimeError("AcroForm exists, but no fields found in AcroForm.Fields")

    for field in iter_fields(all_fields):
        nm = clean_field_name(getattr(field, "T", None))
        if not nm or nm not in mapping:
            continue

        excel_col = mapping[nm]
        if not excel_col or excel_col not in data_row.index:
            continue

        value = str(data_row.get(excel_col, ""))
        ft = getattr(field, "FT", None)

        # Checkbox / Radio
        if ft == PdfName.Btn:
            rule = rules.get(nm, {
                "checked_values": ["yes", "true", "1", "x", "on", "checked", "male"],
                "unchecked_values": ["no", "false", "0", "off", "unchecked", "", "female"],
                "default": "off"
            })

            on_val = get_checkbox_on_value(field)
            do_check = should_check(value, rule)

            if debug:
                print(f"[DEBUG] '{nm}' value={repr(value)} do_check={do_check} on_val={on_val}")

            # parent /V is logical value
            field.V = on_val if do_check else PdfName.Off

            # kids /AS controls visible checkmark
            kids = getattr(field, "Kids", None)
            if kids:
                for kid in kids:
                    kid.AS = on_val if do_check else PdfName.Off
            else:
                field.AS = on_val if do_check else PdfName.Off

            filled_count += 1
            continue

        # Text
        # Optional: force AutoSize by switching font size in /DA to 0 Tf.
        # This keeps V1 behaviour (viewer regenerates appearances) but also fixes
        # templates that would otherwise clip/occlude long values.
        if force_autosize_text:
            try:
                _set_da_autosize(field)
            except Exception:
                pass

        field.V = PdfString.encode(value)
        try:
            if getattr(field, "AP", None) is not None:
                field.AP = None
        except Exception:
            pass

        filled_count += 1

        # ensure not read-only
        try:
            if hasattr(field, "Ff"):
                field.Ff = None
        except Exception:
            pass

    PdfWriter().write(output_path, template)
    return filled_count


# -------------------------
# ZIP packaging
# -------------------------
def make_zip_bytes(files: List[Tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in files:
            z.writestr(name, data)
    return buf.getvalue()
