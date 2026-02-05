"""PDF sanitization — scrubs metadata, annotations, embedded files, and history.

Legal-grade sanitization removes all non-content data that could leak
redacted information. This includes:
- Standard metadata (author, title, etc.)
- XMP metadata (XML-based, not cleared by set_metadata alone)
- Annotations (comments, highlights, sticky notes)
- Embedded files / attachments
- Form fields (AcroForm)
- JavaScript actions
- Incremental update history (collapsed via garbage collection)
"""

from __future__ import annotations

import logging
import os
import pathlib
import tempfile

import fitz

logger = logging.getLogger(__name__)


def sanitize_pdf(input_path: pathlib.Path, output_path: pathlib.Path) -> None:
    """Sanitize a PDF by removing non-content data.

    Args:
        input_path: Source PDF path.
        output_path: Destination path (may be same as input_path).
    """
    doc = fitz.open(str(input_path))

    # Clear standard metadata fields
    doc.set_metadata({
        "author": "",
        "title": "",
        "subject": "",
        "keywords": "",
        "creator": "",
        "producer": "",
    })

    # Clear XMP metadata (XML-based, separate from standard metadata)
    try:
        doc.del_xml_metadata()
    except Exception:
        logger.debug("No XMP metadata to remove or removal failed")

    # Remove all annotations
    for page in doc:
        annots = list(page.annots() or [])
        for annot in annots:
            page.delete_annot(annot)

    # Remove embedded files / attachments
    while doc.embfile_count() > 0:
        doc.embfile_del(0)

    # Remove form fields (AcroForm)
    for page in doc:
        widgets = list(page.widgets() or [])
        for widget in widgets:
            page.delete_widget(widget)

    # Remove JavaScript actions from the document catalog
    try:
        cat = doc.pdf_catalog()
        xref = doc.xref_get_key(cat, "Names")
        if xref[0] != "null":
            names_xref = int(xref[1].split()[0])
            js_key = doc.xref_get_key(names_xref, "JavaScript")
            if js_key[0] != "null":
                doc.xref_set_key(names_xref, "JavaScript", "null")
                logger.info("Removed JavaScript actions from PDF catalog")
    except Exception:
        logger.debug("No JavaScript actions to remove or removal failed")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=output_path.parent, suffix=".pdf.tmp"
    )
    try:
        os.close(tmp_fd)
        doc.save(tmp_path, garbage=4, clean=True)
        doc.close()
        pathlib.Path(tmp_path).replace(output_path)
    except Exception:
        doc.close()
        pathlib.Path(tmp_path).unlink(missing_ok=True)
        raise