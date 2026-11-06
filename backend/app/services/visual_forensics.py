
import io
from pathlib import Path

import cv2
import numpy as np
import pymupdf

from PIL import Image, ImageChops, ImageEnhance


class VisualForensics:

    def load_image(self, file_path, page_index=0):

        path = Path(file_path)

        if path.suffix.lower() == ".pdf":

            doc = pymupdf.open(path)

            try:

                page = doc[page_index]

                pix = page.get_pixmap(
                    matrix=pymupdf.Matrix(2, 2),
                    alpha=False
                )

                image = Image.open(
                    io.BytesIO(pix.tobytes("png"))
                ).convert("RGB")

                return cv2.cvtColor(
                    np.array(image),
                    cv2.COLOR_RGB2BGR
                )

            finally:
                doc.close()

        image = cv2.imread(str(path))

        if image is None:
            raise ValueError("Unable to load image")

        return image

    def check_brightness(self, image, page_number):

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )

        height, width = gray.shape

        rows = 4
        cols = 4

        values = []

        for row in range(rows):

            for col in range(cols):

                y1 = row * height // rows
                y2 = (row + 1) * height // rows

                x1 = col * width // cols
                x2 = (col + 1) * width // cols

                mean = float(
                    np.mean(gray[y1:y2, x1:x2])
                )

                values.append(
                    (row, col, mean)
                )

        med = np.median(
            [value[2] for value in values]
        )

        mad = np.median(
            [
                abs(value[2] - med)
                for value in values
            ]
        )

        threshold = max(
            35,
            3.5 * mad
        )

        observations = []

        for row, col, mean in values:

            if abs(mean - med) > threshold:

                x1 = col * width // cols
                x2 = (col + 1) * width // cols

                y1 = row * height // rows
                y2 = (row + 1) * height // rows

                observations.append({

                    "type": "brightness_inconsistency",

                    "page_number": page_number,

                    "bbox": {
                        "x": int(x1),
                        "y": int(y1),
                        "width": int(x2 - x1),
                        "height": int(y2 - y1)
                    },

                    "severity": "low",

                    "status": "potential_anomaly",

                    "description": (
                        "Unusual local brightness variation detected."
                    )
                })

        return observations

    def detect_rectangular_regions(
        self,
        image,
        page_number
    ):

        gray = cv2.cvtColor(
            image,
            cv2.COLOR_BGR2GRAY
        )

        edges = cv2.Canny(
            gray,
            60,
            160
        )

        contours, _ = cv2.findContours(
            edges,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        height, width = gray.shape
        image_area = height * width

        observations = []

        for contour in contours:

            x, y, w, h = cv2.boundingRect(contour)

            area = (w * h) / image_area

            if (
                0.015 <= area <= 0.30
                and w > 80
                and w > 3 * h
            ):

                observations.append({

                    "type": "rectangular_region",

                    "page_number": page_number,

                    "bbox": {
                        "x": int(x),
                        "y": int(y),
                        "width": int(w),
                        "height": int(h)
                    },

                    "severity": "low",

                    "status": "potential_anomaly",

                    "description": (
                        "Prominent rectangular region detected. "
                        "It may be a normal table, field, stamp "
                        "or inserted region."
                    )
                })

                if len(observations) >= 10:
                    break

        return observations

    def perform_ela(self, file_path, quality=90):

        path = Path(file_path)

        if path.suffix.lower() not in [
            ".jpg", ".jpeg"
        ]:

            return {
                "available": False,
                "message": (
                    "ELA screening is only enabled for JPEG images."
                )
            }

        original = Image.open(path).convert("RGB")

        buffer = io.BytesIO()

        original.save(
            buffer,
            format="JPEG",
            quality=quality
        )

        buffer.seek(0)

        recompressed = Image.open(buffer).convert("RGB")

        difference = ImageChops.difference(
            original,
            recompressed
        )

        difference = ImageEnhance.Contrast(
            difference
        ).enhance(10)

        return {
            "available": True,
            "ela_image": difference,
            "note": (
                "ELA differences are screening observations, "
                "not proof of manipulation."
            )
        }

    def analyze_page(self, image, page_number):

        observations = []

        observations.extend(
            self.check_brightness(
                image,
                page_number
            )
        )

        observations.extend(
            self.detect_rectangular_regions(
                image,
                page_number
            )
        )

        return {
            "page_number": page_number,
            "image_width": int(image.shape[1]),
            "image_height": int(image.shape[0]),
            "observations": observations
        }

    def analyze_document(self, file_path):

        path = Path(file_path)

        if path.suffix.lower() == ".pdf":

            doc = pymupdf.open(path)
            page_count = len(doc)
            doc.close()

        else:
            page_count = 1

        pages = []

        for index in range(page_count):

            image = self.load_image(
                path,
                index
            )

            result = self.analyze_page(
                image,
                index + 1
            )

            pages.append(result)

        return {
            "filename": path.name,
            "page_count": page_count,
            "pages": pages,
            "total_observations": sum(
                len(page["observations"])
                for page in pages
            )
        }
