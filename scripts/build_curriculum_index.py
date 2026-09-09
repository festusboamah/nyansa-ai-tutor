"""Build the bundled reference index from an explicitly supplied local ZIP.

Usage: python scripts/build_curriculum_index.py PATH_TO_RESOURCE_PACK.zip
No archive paths are extracted to the filesystem. This is an offline maintainer
command, not a web upload endpoint; review any replacement index before release.
"""
import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from pypdf import PdfReader


def build(archive):
    records = []
    with ZipFile(archive) as pack:
        pdfs = [entry for entry in pack.infolist() if entry.filename.lower().endswith(".pdf")]
        if len(pdfs) > 50 or sum(e.file_size for e in pdfs) > 100_000_000:
            raise ValueError("Resource pack exceeds the offline importer limits.")
        for entry in pdfs:
            raw = pack.read(entry)
            reader = PdfReader(BytesIO(raw))
            if len(reader.pages) > 500:
                raise ValueError("Curriculum PDF exceeds the page limit.")
            records.append({
                "filename": Path(entry.filename).name,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "pages": [{"page": i + 1, "text": page.extract_text()} for i, page in enumerate(reader.pages)],
            })
    destination = Path(__file__).resolve().parents[1] / "dashboard" / "data" / "nacca_resources.json"
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    print(build(parser.parse_args().archive))
