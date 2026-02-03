# 📄 PDF Filler — Excel/CSV → Fillable PDF

**Privacy-first, no-login PDF form filler with automatic text resizing.**

Upload a fillable PDF and an Excel/CSV file, map columns to PDF fields, preview field locations, and generate filled PDFs as a ZIP — all in your browser.

✔️ No accounts &nbsp; ✔️ No data stored &nbsp; ✔️ No tracking &nbsp; ✔️ Automatic text resizing

---

### 🔗 Live Demo
👉 https://shaipai-pdf-filler.streamlit.app/

---

## 🔍 What It Does

This tool helps you fill PDF forms accurately and safely without relying on paid or data-retaining SaaS tools.

### Key Capabilities

| Feature | Description |
|---|---|
| 📤 Upload a fillable PDF | Drag & drop or browse to upload any AcroForm-based PDF |
| 📊 Upload Excel / CSV data | Bring your data in the format you already use |
| 🗺️ Map columns to PDF fields | Match spreadsheet columns to form fields manually |
| 👁️ Preview & highlight field locations | Multi-select supported — see exactly where each field lives |
| 🔤 Automatic text resizing | Text shrinks to fit field boundaries — no overflow, no cut-off |
| 📦 Generate filled PDFs as a ZIP | Bulk-ready output, downloaded instantly |
| 💾 Export / Import mapping JSON | Save and reload your column-to-field mappings locally |

### Important Behaviors

- The **"Clear all shown fields"** button works across pagination and pages — internally clears all `showtoggle::*` keys so no stale highlights remain.
- **No auto-fill, no AI, no project saving** — intentionally removed for safety.

---

## 🚀 How to Run Locally

### 1️⃣ Prerequisites

- Python 3.11+
- `pip` or `uv`
- Recommended: virtual environment

### 2️⃣ Clone the Repository

```bash
git clone https://github.com/<your-org-or-username>/pdf-filler.git
cd pdf-filler
```

### 3️⃣ Install Dependencies

Using pip:
```bash
pip install -r requirements.txt
```

Or using uv:
```bash
uv sync
```

Or install as a package:
```bash
pip install .
```

### 4️⃣ Run the App

```bash
streamlit run app.py
```

### 5️⃣ Open in Browser

```
http://localhost:8501
```

---

## 🔐 Privacy Statement

This tool is **privacy-first by design**.

- ❌ No accounts or logins
- ❌ No analytics
- ❌ No cookies
- ❌ No server-side storage of uploaded files or form data
- ❌ No AI auto-fill or inference
- ❌ No project saving or history

> **Your data never leaves your browser session.**

This makes the tool suitable for:

- Sensitive documents
- Client data
- One-off or repeat form filling
- Environments where data retention is a risk

---

## 👥 Who Is This For?

### 1️⃣ Operations & Admin Teams *(largest group)*

HR, finance, legal, back-office, startup ops — teams that fill PDFs daily (onboarding, KYC, contracts, vendor forms) but don't want Adobe Acrobat pricing, logins, or data stored anywhere.

**Why this tool wins:** No account. No data saved. Automatic text resizing — the major pain point, solved.

---

### 2️⃣ Freelancers & Consultants

Tax preparers, insurance agents, loan processors, immigration consultants — professionals who receive blank PDFs from clients and fill similar forms repeatedly.

**Why this tool:** Upload → fill → download → done. No subscription. No "project history" risk.

---

### 3️⃣ Small Businesses & Startups

Founders, HR generalists, ops managers handling low-volume but high-sensitivity documents — without the complexity of DocuSign or Acrobat.

---

### 4️⃣ Developers & Automation Builders

n8n, Make, Zapier users, and internal tools teams who need a lightweight frontend PDF filler they can embed, fork, or self-host.

This helps with GitHub stars, forks, visibility, and future API or hosted extensions.

---

### 5️⃣ NGOs, Students & Researchers

Grant applications, academic or ethics forms — budget-constrained and privacy-sensitive use cases where free, trustworthy tooling matters.

---

## ⭐ Why This Tool Is Actually Useful

PDF fillers already exist. This one focuses on **what users actually complain about**:

### ✅ Automatic Text Resizing *(core differentiator)*
- Prevents overflow
- Prevents cut-off text
- Produces submission-ready PDFs out of the box

### ✅ Zero Data Retention
- No server storage
- No hidden logging
- Safer than most online PDF tools

### ✅ No Account, No Login, No Tracking
People don't want accounts, emails, or subscriptions. They want: *"Just fill the PDF and download it."*

### ✅ Safe for Public Use
Intentionally removed:
- **AI auto-fill** — hallucination risk
- **Project save / restore** — data leakage risk

---

## 🏷️ License

This project is licensed under the **MIT License**.

---

## 🏗️ Built By

**Shaip**
🌐 [https://www.shaip.com/](https://www.shaip.com/)
