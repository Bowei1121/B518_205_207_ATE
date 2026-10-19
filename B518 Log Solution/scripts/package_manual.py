"""Validate offline resources and package the bilingual reader folder."""
import argparse
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

REPO = Path(__file__).resolve().parents[2]


class Reader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sections = []
        self.ids = set()
        self.resources = []
        self.anchors = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            if values["id"] in self.ids:
                raise ValueError("Duplicate ID: " + values["id"])
            self.ids.add(values["id"])
        if tag == "section" and "id" in values:
            self.sections.append(values["id"])
        for attr in ("src", "href"):
            if values.get(attr):
                self.resources.append(values[attr])
        if tag == "img" and (not values.get("alt") or not values.get("data-caption")):
            # The zoom dialog's empty image is populated dynamically.
            if values.get("id") != "dialog-image":
                raise ValueError("Image missing descriptive alt/caption")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=REPO / "B518_Log_Solution_Manual_2026-10-19.zip")
    args = parser.parse_args()
    manual = REPO / "Manual"
    readers = []
    for name in ("index.html", "index-en.html"):
        reader = Reader()
        reader.feed((manual / name).read_text(encoding="utf-8"))
        for resource in reader.resources:
            url = urlsplit(resource)
            if url.scheme or url.netloc:
                raise ValueError("External reader resource: " + resource)
            if url.path and not (manual / unquote(url.path)).is_file():
                raise ValueError("Missing resource: " + resource)
            if not url.path and url.fragment not in reader.ids:
                raise ValueError("Missing anchor: " + resource)
        readers.append(reader)
    if readers[0].sections != readers[1].sections:
        raise ValueError("Bilingual section IDs/order differ")
    manifest = json.loads((manual / "Photo/generated/manifest.json").read_text())
    for asset in manifest["images"]:
        data = (manual / "Photo/generated" / asset["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != asset["sha256"]:
            raise ValueError("Changed screenshot: " + asset["file"])
    files = sorted(path for path in manual.rglob("*") if path.is_file()
                   and not any(part.startswith(".") for part in path.relative_to(manual).parts))
    with ZipFile(args.output, "w", ZIP_DEFLATED) as package:
        for path in files:
            package.write(path, path.relative_to(REPO))
    with ZipFile(args.output) as package:
        if package.testzip():
            raise ValueError("ZIP CRC failure")
        for path in files:
            if package.read(str(path.relative_to(REPO))) != path.read_bytes():
                raise ValueError("ZIP differs from source: " + str(path))
    print("Verified {} bilingual sections, {} screenshots, {} reader files".format(
        len(readers[0].sections), len(manifest["images"]), len(files)))
    print(args.output)


if __name__ == "__main__":
    main()
