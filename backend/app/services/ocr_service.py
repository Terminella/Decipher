
import importlib
import io
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image


class OCRService:

    def __init__(self, languages=None, gpu=False):

        self.languages = languages or ["en"]
        self.gpu = gpu
        self.reader = None

    def get_reader(self):

        if self.reader is None:
            try:
                easyocr = importlib.import_module("easyocr")
            except ModuleNotFoundError as exc:
                if exc.name != "easyocr":
                    raise
                raise RuntimeError(
                    "EasyOCR is required for image and scanned-PDF OCR. "
                    "Install it with: pip install -r backend/requirements.txt"
                ) from exc

            self.reader = easyocr.Reader(
                self.languages,
                gpu=self.gpu
            )

        return self.reader

    def extract_image(self, image, page_number=1):

        image = image.convert("RGB")
        array = np.array(image)

        results = self.get_reader().readtext(
            array,
            detail=1,
            paragraph=False
        )

        blocks = []

        for bbox, text, confidence in results:

            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]

            blocks.append({
                "text": text,
                "confidence": float(confidence),
                "bbox": {
                    "x": int(min(xs)),
                    "y": int(min(ys)),
                    "width": int(max(xs) - min(xs)),
                    "height": int(max(ys) - min(ys))
                },
                "page_number": page_number,
                "source": "ocr"
            })

        return {
            "page_number": page_number,
            "width": image.width,
            "height": image.height,
            "text": "\n".join(
                block["text"] for block in blocks
            ),
            "blocks": blocks,
            "extraction_method": "easyocr"
        }

    def extract_pdf(self, file_path, force_ocr=False):

        document = pymupdf.open(file_path)
        pages = []

        try:
            for index, page in enumerate(document):

                page_number = index + 1
                text = page.get_text("text").strip()

                if text and not force_ocr:

                    words = page.get_text("words")
                    blocks = []

                    for word in words:

                        x0, y0, x1, y1, value = word[:5]

                        blocks.append({
                            "text": value,
                            "confidence": None,
                            "bbox": {
                                "x": x0,
                                "y": y0,
                                "width": x1 - x0,
                                "height": y1 - y0
                            },
                            "page_number": page_number,
                            "source": "native_pdf"
                        })

                    pages.append({
                        "page_number": page_number,
                        "width": page.rect.width,
                        "height": page.rect.height,
                        "text": text,
                        "blocks": blocks,
                        "extraction_method": "native_pdf"
                    })

                else:

                    pix = page.get_pixmap(
                        matrix=pymupdf.Matrix(2, 2),
                        alpha=False
                    )

                    image = Image.open(
                        io.BytesIO(pix.tobytes("png"))
                    )

                    result = self.extract_image(
                        image,
                        page_number
                    )

                    result["extraction_method"] = (
                        "scanned_pdf_ocr"
                    )

                    pages.append(result)

        finally:
            document.close()

        return {
            "filename": Path(file_path).name,
            "page_count": len(pages),
            "pages": pages,
            "full_text": "\n\n".join(
                page["text"] for page in pages
            )
        }

    def extract(self, file_path, force_ocr=False):

        path = Path(file_path)
        extension = path.suffix.lower()

        if extension == ".pdf":

            return self.extract_pdf(
                path,
                force_ocr
            )

        if extension in [
            ".jpg", ".jpeg", ".png",
            ".bmp", ".tiff", ".tif", ".webp"
        ]:

            with Image.open(path) as image:

                result = self.extract_image(
                    image,
                    1
                )

            return {
                "filename": path.name,
                "page_count": 1,
                "pages": [result],
                "full_text": result["text"]
            }

        raise ValueError(
            f"Unsupported document format: {extension}"
        )
