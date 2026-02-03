import os
import re
import io
import json
import tempfile
import hashlib
from datetime import datetime
from typing import Dict, List, Tuple

import streamlit as st
import pandas as pd
from pdf2image import convert_from_path
import matplotlib.pyplot as plt
import matplotlib.patches as patches
 


from utils_pdf import (
    load_table_any,
    extract_pdf_fields_all,
    build_field_rect_index,
    get_page_mediabox,
    fill_pdf_with_pdfrw,
    make_zip_bytes,
)

st.set_page_config(page_title="PDF Filler (Excel → Fillable PDF)", layout="wide")

# ==========================================================
# Sticky PDF viewer + UI tweaks
# ==========================================================
st.markdown(
    """
    <style>
    .sticky-viewer {
        position: sticky;
        top: 0.75rem;
        z-index: 999;
        background: white;
        padding: 0.6rem 0.6rem 0.4rem 0.6rem;
        border: 1px solid rgba(49, 51, 63, 0.18);
        border-radius: 0.8rem;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.title("📄 PDF Filler (Excel/CSV → Fillable PDF)")
st.caption(
    "Upload a fillable PDF + Excel/CSV, map columns to fields, preview field locations (multi-select), "
    "then generate filled PDFs as a ZIP. No data is saved on the server."
)

# ==========================================================
# Helpers
# ==========================================================
def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _clean_rule_token(v: str) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = s.strip().strip('"').strip("'").strip()
    return s

def safe_filename(s: str, max_len=70) -> str:
    s = str(s).strip()
    s = re.sub(r"[^\w\-\. ]+", "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    return (s[:max_len].rstrip() if s else "row")

# -------------------------
# Upload section
# -------------------------
colA, colB = st.columns(2)
with colA:
    pdf_file = st.file_uploader("Upload Fillable PDF", type=["pdf"])
with colB:
    data_file = st.file_uploader("Upload Excel/CSV", type=["xlsx", "xls", "xlsm", "csv"])

if not pdf_file or not data_file:
    st.info("Upload both files to continue.")
    st.stop()

# -------------------------
# Save uploads to temp files
# -------------------------
tmp_dir = tempfile.mkdtemp(prefix="pdf_filler_")
pdf_path = os.path.join(tmp_dir, "template.pdf")
data_name = data_file.name

pdf_bytes = pdf_file.getvalue()
excel_bytes = data_file.getvalue()

with open(pdf_path, "wb") as f:
    f.write(pdf_bytes)

# -------------------------
# Load table (multi-sheet)
# -------------------------
try:
    df_master, sheets = load_table_any(excel_bytes, data_name)
except Exception as e:
    st.error(f"Failed to read data file: {e}")
    st.stop()

st.success(f"Loaded data: {len(sheets)} sheet(s), rows={len(df_master)}, columns={len(df_master.columns)}")
if len(sheets) > 1:
    with st.expander("Show sheets summary"):
        for sname, sdf in sheets.items():
            st.write(f"- **{sname}**: {len(sdf)} rows × {len(sdf.columns)} cols")

# -------------------------
# Extract PDF fields + rects
# -------------------------
try:
    pdf_fields, pdf_field_types = extract_pdf_fields_all(pdf_path)
    rect_index, page_count = build_field_rect_index(pdf_path)
except Exception as e:
    st.error(str(e))
    st.stop()

st.write(f"✅ PDF fields detected: **{len(pdf_fields)}** | Pages: **{page_count}**")
st.caption("Tip: Tick multiple ‘Show’ toggles to highlight multiple fields at the same time on the right viewer.")

# -------------------------
# Session state init
# -------------------------
if "mapping" not in st.session_state:
    st.session_state.mapping = {}
if "rules" not in st.session_state:
    st.session_state.rules = {}
if "show_fields" not in st.session_state:
    st.session_state.show_fields = set()
if "show_page" not in st.session_state:
    st.session_state.show_page = 1

# Hash store (used for warnings)
st.session_state["pdf_hash"] = sha256_bytes(pdf_bytes)
st.session_state["excel_hash"] = sha256_bytes(excel_bytes)

# ==========================================================
# Import / Export project.json (backup + QA flow)
# ==========================================================
with st.expander("📦 Export / Import Mapping JSON (local backup)"):
    export_payload = {
        "pdf_hash": st.session_state.get("pdf_hash", ""),
        "excel_hash": st.session_state.get("excel_hash", ""),
        "pdf_name": pdf_file.name,
        "excel_name": data_file.name,
        "mapping": st.session_state.mapping,
        "rules": st.session_state.rules,
        "exported_at": now_ts(),
    }

    st.download_button(
        "⬇️ Export mapping_rules.json",
        data=json.dumps(export_payload, ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="mapping_rules.json",
        mime="application/json",
        use_container_width=True,
    )

    imp = st.file_uploader("Import mapping_rules.json", type=["json"])
    if imp:
        try:
            raw = imp.getvalue()

            # Prevent infinite rerun loops: Streamlit keeps the uploaded file
            # selected across reruns. If we call st.rerun() every time, it will
            # keep re-importing and re-rerunning.
            import hashlib
            import_hash = hashlib.sha1(raw).hexdigest()
            if st.session_state.get("_last_import_hash") == import_hash:
                st.info("Project JSON already imported in this session.")
                obj = None
            else:
                st.session_state["_last_import_hash"] = import_hash
                obj = json.loads(raw.decode("utf-8"))

            if obj is None:
                # Don't re-import; continue running the app normally.
                pass
            else:
                new_mapping, new_rules, warn = normalize_imported_schema(
                    obj=obj,
                    df_columns=list(df_master.columns),
                    pdf_fields=pdf_fields,
                )
                st.session_state.mapping = new_mapping
                st.session_state.rules = new_rules

                # IMPORTANT: clear selectbox widget state so imported mapping shows up.
                # Streamlit widgets with `key=` override `index=` if state already exists.
                for f in pdf_fields:
                    k = f"map::{f}"
                    if k in st.session_state:
                        del st.session_state[k]

                st.success(f"Imported ✅ ({len(new_mapping)} mappings, {len(new_rules)} rule-sets).")
                if warn:
                    with st.expander("⚠️ Import warnings"):
                        for w in warn:
                            st.write(f"- {w}")

                if obj.get("pdf_hash") and obj.get("pdf_hash") != st.session_state.get("pdf_hash"):
                    st.warning("⚠️ Imported project was saved for a DIFFERENT PDF (hash mismatch). Mapping may be wrong.")
                if obj.get("excel_hash") and obj.get("excel_hash") != st.session_state.get("excel_hash"):
                    st.warning("⚠️ Imported project was saved for a DIFFERENT Excel (hash mismatch). Mapping may be wrong.")

                # Force UI refresh so mapping dropdowns immediately reflect imported values
                st.rerun()
        except Exception as e:
            st.error(f"Invalid JSON: {e}")

# ==========================================================
# Reset checkbox widgets button
# ==========================================================
if st.sidebar.button("🧹 Reset all checkbox rule widgets"):
    keys_to_del = [k for k in st.session_state.keys() if k.startswith(("chk::", "unchk::", "def::"))]
    for k in keys_to_del:
        del st.session_state[k]
    st.sidebar.success("Cleared checkbox rule widgets. Re-enter values now.")
    st.rerun()

col_options = [""] + list(df_master.columns)

# ==========================================================
# Main UI: Left fixed-height scroll + Right sticky viewer
# ==========================================================
left, right = st.columns([1.25, 1])

with left:
    st.subheader("🧩 Field Mapping (Fixed scroll panel)")
    search = st.text_input("Search PDF fields", value="")
    page_size = st.selectbox("Fields per page", [15, 25, 50], index=1)

    filtered = [f for f in pdf_fields if search.lower() in f.lower()] if search else pdf_fields
    total = len(filtered)
    max_page = max(1, (total + page_size - 1) // page_size)

    page = st.number_input("Fields list page", min_value=1, max_value=max_page, value=1, step=1)
    start = (page - 1) * page_size
    end = min(total, start + page_size)

    st.write(f"Showing fields **{start+1}–{end}** of **{total}**")

    scroll_box = st.container(height=720, border=True)

    with scroll_box:
        for field_name in filtered[start:end]:
            ftype = pdf_field_types.get(field_name, "text")

            with st.container(border=True):
                c1, c2, c3 = st.columns([2.2, 2.2, 1.1])

                with c1:
                    st.markdown(f"**{field_name}**  \n`{ftype}`")

                with c2:
                    key = f"map::{field_name}"
                    default_val = st.session_state.mapping.get(field_name, "")

                    # FIX: Streamlit widget state can override imported mappings.
                    # If a selectbox key already exists with "" (blank), Streamlit will keep
                    # showing blank even when we set st.session_state.mapping.
                    # Force the widget state to the imported/default value (if valid).
                    if default_val and default_val in col_options:
                        if (key not in st.session_state) or (st.session_state.get(key) not in col_options) or (st.session_state.get(key) == ""):
                            st.session_state[key] = default_val
                    else:
                        # ensure widget state is valid
                        if key in st.session_state and st.session_state.get(key) not in col_options:
                            st.session_state[key] = ""
                    chosen = st.selectbox(
                        "Excel Column",
                        col_options,
                        index=col_options.index(default_val) if default_val in col_options else 0,
                        key=key
                    )

                    # Update mapping.
                    # Only delete mapping if BOTH the dropdown is blank AND there was no
                    # imported/default mapping to begin with. This prevents accidental
                    # deletion on reruns.
                    if chosen:
                        st.session_state.mapping[field_name] = chosen
                    else:
                        if not default_val and field_name in st.session_state.mapping:
                            del st.session_state.mapping[field_name]

                with c3:
                    show_key = f"showtoggle::{field_name}"
                    is_on = field_name in st.session_state.show_fields
                    toggle = st.checkbox("Show", value=is_on, key=show_key)
                    if toggle:
                        st.session_state.show_fields.add(field_name)
                    else:
                        st.session_state.show_fields.discard(field_name)

                # Checkbox rules UI
                if ftype == "checkbox_or_radio":
                    rule = st.session_state.rules.get(field_name, {
                        "checked_values": ["yes", "true", "1", "x", "on", "checked", "male", "y", "YES"],
                        "unchecked_values": ["no", "false", "0", "off", "unchecked", "", "female", "n", "NO"],
                        "default": "off",
                    })

                    r1, r2, r3 = st.columns([2, 2, 1])

                    with r1:
                        checked_str = st.text_input(
                            "Checked values (comma separated)",
                            value=",".join(rule.get("checked_values", [])),
                            key=f"chk::{field_name}"
                        )

                    with r2:
                        unchecked_str = st.text_input(
                            "Unchecked values (comma separated)",
                            value=",".join(rule.get("unchecked_values", [])),
                            key=f"unchk::{field_name}"
                        )

                    with r3:
                        default = st.selectbox(
                            "Default",
                            ["off", "on"],
                            index=0 if rule.get("default", "off") == "off" else 1,
                            key=f"def::{field_name}"
                        )

                    checked_vals = [_clean_rule_token(x) for x in (checked_str or "").split(",")]
                    checked_vals = [x for x in checked_vals if x != ""]

                    unchecked_vals = [_clean_rule_token(x) for x in (unchecked_str or "").split(",")]
                    unchecked_vals = [x for x in unchecked_vals if x != ""]

                    st.session_state.rules[field_name] = {
                        "checked_values": checked_vals,
                        "unchecked_values": unchecked_vals,
                        "default": default
                    }

with right:
    st.markdown('<div class="sticky-viewer">', unsafe_allow_html=True)
    st.subheader("📌 Visual Field Viewer (Sticky + Multi-select)")

    selected = sorted(list(st.session_state.show_fields))
    if not selected:
        st.info("Tick ON 'Show' for any field(s). Viewer stays visible while you scroll the left list.")
    else:
        st.session_state.show_page = st.number_input(
            "Page to view",
            min_value=1,
            max_value=page_count,
            value=int(st.session_state.show_page),
            step=1
        )
        page_i = int(st.session_state.show_page) - 1

        st.write(f"Selected fields: **{len(selected)}**")
        st.write(", ".join(selected[:25]) + (" ..." if len(selected) > 25 else ""))

        if st.button("Clear all shown fields"):
            # Clear both the derived set AND the underlying checkbox widget states.
            # Otherwise Streamlit will remember checkbox=True and re-add fields on rerun.
            for k in list(st.session_state.keys()):
                if str(k).startswith("showtoggle::"):
                    del st.session_state[k]
            st.session_state.show_fields = set()
            st.rerun()

        dpi = 130
        images = convert_from_path(pdf_path, dpi=dpi, first_page=page_i+1, last_page=page_i+1)
        img = images[0]

        x0, y0, x1, y1 = get_page_mediabox(pdf_path, page_i)
        page_w, page_h = (x1 - x0), (y1 - y0)
        img_w, img_h = img.size
        sx, sy = img_w / page_w, img_h / page_h

        fig, ax = plt.subplots(figsize=(6.0, 7.6))
        ax.imshow(img)

        drawn = 0
        for field_name in selected:
            locs = rect_index.get(field_name, [])
            locs_on_page = [x for x in locs if x.get("page") == page_i]
            for loc in locs_on_page:
                rx0, ry0, rx1, ry1 = loc["rect"]
                ix0 = (rx0 - x0) * sx
                ix1 = (rx1 - x0) * sx
                iy0 = img_h - ((ry0 - y0) * sy)
                iy1 = img_h - ((ry1 - y0) * sy)
                w = ix1 - ix0
                h = iy0 - iy1
                ax.add_patch(
                    patches.Rectangle((ix0, iy1), w, h, linewidth=3, edgecolor="red", facecolor="none")
                )
                drawn += 1

        ax.set_title(f"Page {page_i+1} — highlighted boxes: {drawn}")
        ax.axis("off")
        st.pyplot(fig, clear_figure=True)

    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------
# Actions: export mapping, preview row, generate ZIP
# -------------------------
st.divider()

a1, a2, a3 = st.columns([1, 1, 2])

mapping_rules = {"mapping": st.session_state.mapping, "rules": st.session_state.rules}
mapping_json = json.dumps(mapping_rules, ensure_ascii=False, indent=2).encode("utf-8")

with a1:
    st.download_button(
        "💾 Download mapping_rules.json",
        data=mapping_json,
        file_name="mapping_rules.json",
        mime="application/json",
        use_container_width=True
    )

with a2:
    preview_row = st.number_input(
        "Preview row #",
        min_value=1,
        max_value=max(1, len(df_master)),
        value=1,
        step=1
    )

with a3:
    st.write(" ")

with st.expander("🔍 Debug (optional) — see mapped value for a PDF field"):
    dbg_field = st.selectbox("Pick a PDF field to debug", [""] + pdf_fields)
    if dbg_field:
        col = st.session_state.mapping.get(dbg_field, "")
        st.write("Mapped column:", col)
        if col and col in df_master.columns:
            st.write("Row 1 raw value:", repr(df_master.iloc[0].get(col, "")))
        else:
            st.warning("No mapping or column not found in df_master.")

if st.button("👁️ Generate Preview PDF", use_container_width=True):
    if len(st.session_state.mapping) == 0:
        st.warning("Map at least one field first.")
    else:
        try:
            row = df_master.iloc[preview_row - 1]
            preview_path = os.path.join(tmp_dir, "preview.pdf")
            filled = fill_pdf_with_pdfrw(
                pdf_path, preview_path, row,
                st.session_state.mapping, st.session_state.rules
            )
            with open(preview_path, "rb") as f:
                st.download_button(
                    f"⬇️ Download Preview (filled_fields={filled})",
                    data=f.read(),
                    file_name="preview.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        except Exception as e:
            st.error(f"Preview failed: {e}")

st.divider()
st.subheader("🚀 Generate Filled PDFs")

name_hint = st.text_input("Optional filename base column (must match a dropdown column exactly)", value="")

if st.button("Generate ZIP (all rows)", type="primary", use_container_width=True):
    if len(st.session_state.mapping) == 0:
        st.warning("Map at least one field first.")
        st.stop()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_files = []
    report_rows = []

    name_col = None
    if name_hint and name_hint in df_master.columns:
        name_col = name_hint
    else:
        possible = {"File_No", "ID", "Name", "PDF_Name", "filename"}
        for c in df_master.columns:
            if c.split("::")[-1] in possible:
                name_col = c
                break

    used_names = set()

    for i in range(len(df_master)):
        row_no = i + 1
        row = df_master.iloc[i]

        if name_col and str(row.get(name_col, "")).strip():
            base = safe_filename(row.get(name_col))
        else:
            base = f"row_{row_no:03d}"

        fname = base + ".pdf"
        if fname in used_names:
            k = 2
            while f"{base}_{k}.pdf" in used_names:
                k += 1
            fname = f"{base}_{k}.pdf"
        used_names.add(fname)

        out_path = os.path.join(tmp_dir, fname)

        try:
            filled = fill_pdf_with_pdfrw(
                pdf_path, out_path, row,
                st.session_state.mapping, st.session_state.rules
            )
            status = "OK" if filled > 0 else "ZERO_FILLED"
            report_rows.append({"row": row_no, "file": fname, "status": status, "filled_fields": filled, "error": ""})
            with open(out_path, "rb") as f:
                out_files.append((fname, f.read()))
        except Exception as e:
            report_rows.append({"row": row_no, "file": fname, "status": "ERROR", "filled_fields": 0, "error": str(e)})

    report_df = pd.DataFrame(report_rows)
    report_csv = report_df.to_csv(index=False).encode("utf-8")

    out_files.append(("_REPORT.csv", report_csv))
    out_files.append(("mapping_rules.json", mapping_json))

    zip_bytes = make_zip_bytes(out_files)

    st.download_button(
        f"⬇️ Download ZIP (generated at {ts})",
        data=zip_bytes,
        file_name=f"filled_pdfs_{ts}.zip",
        mime="application/zip",
        use_container_width=True
    )



st.markdown(
    """
    <hr style="margin-top:30px;">
    <div style="text-align:center; font-size:13px; color:#6b7280;">
        ✔️ Privacy-first · No data stored<br>
        Built by <a href="https://www.shaip.com/" target="_blank"
        style="text-decoration:none; font-weight:600; color:#2563eb;">
        Shaip
        </a>
    </div>
    """,
    unsafe_allow_html=True
)
