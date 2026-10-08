from pathlib import Path
from pypdf import PdfReader

KB_DIR = Path("data/knowledge_base")

SEARCH_TERMS = [
    "PRB",
    "RRC",
    "E-RAB",
    "handover",
    "throughput",
    "RSRP",
    "SINR",
    "packet loss",
    "latency",
    "availability",
    "alarm",
    "threshold",
    "utilization",
    "call drop"
]

pdf_files = list(KB_DIR.rglob("*.pdf"))

print(f"\nFound {len(pdf_files)} PDF files\n")

for pdf_path in pdf_files:

    print("=" * 80)
    print(f"FILE: {pdf_path.name}")
    print(f"PATH: {pdf_path}")
    print("=" * 80)

    reader = PdfReader(pdf_path)

    full_text = ""

    for page in reader.pages:
        try:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        except Exception:
            pass

    text_lower = full_text.lower()

    print(f"Pages: {len(reader.pages)}")
    print(f"Characters extracted: {len(full_text):,}")
    print("\nTerm occurrences:")

    found_any = False

    for term in SEARCH_TERMS:

        count = text_lower.count(term.lower())

        if count > 0:
            print(f"  {term:<20} : {count}")
            found_any = True

    if not found_any:
        print("  No search terms found.")

    print()