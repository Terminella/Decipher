import io
import json
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


INK = colors.HexColor("#241913")
MUTED = colors.HexColor("#6C625C")
ACCENT = colors.HexColor("#A95732")
PALE = colors.HexColor("#F6F1ED")
LINE = colors.HexColor("#E4D9D0")
PAGE_WIDTH = A4[0] - 36 * mm


def _font_family() -> str:
    if "Dossier" in pdfmetrics.getRegisteredFontNames():
        return "Dossier"
    font_dir = Path(reportlab.__file__).parent / "fonts"
    font_files = {
        "Dossier": font_dir / "Vera.ttf",
        "Dossier-Bold": font_dir / "VeraBd.ttf",
        "Dossier-Italic": font_dir / "VeraIt.ttf",
        "Dossier-BoldItalic": font_dir / "VeraBI.ttf",
    }
    if all(path.is_file() for path in font_files.values()):
        for name, path in font_files.items():
            pdfmetrics.registerFont(TTFont(name, str(path)))
        pdfmetrics.registerFontFamily(
            "Dossier",
            normal="Dossier",
            bold="Dossier-Bold",
            italic="Dossier-Italic",
            boldItalic="Dossier-BoldItalic",
        )
        return "Dossier"
    return "Helvetica"


def _styles():
    font = _font_family()
    bold = "Dossier-Bold" if font == "Dossier" else "Helvetica-Bold"
    italic = "Dossier-Italic" if font == "Dossier" else "Helvetica-Oblique"
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Title"],
            fontName=bold,
            fontSize=24,
            leading=29,
            alignment=TA_CENTER,
            textColor=INK,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            leading=14,
            alignment=TA_CENTER,
            textColor=MUTED,
            spaceAfter=14,
        ),
        "section": ParagraphStyle(
            "ReportSection",
            parent=base["Heading2"],
            fontName=bold,
            fontSize=13,
            leading=17,
            textColor=ACCENT,
            spaceBefore=13,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "ReportBody",
            parent=base["BodyText"],
            fontName=font,
            fontSize=9,
            leading=13,
            textColor=INK,
            spaceAfter=5,
            splitLongWords=1,
        ),
        "small": ParagraphStyle(
            "ReportSmall",
            parent=base["BodyText"],
            fontName=font,
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
            splitLongWords=1,
        ),
        "table": ParagraphStyle(
            "ReportTable",
            parent=base["BodyText"],
            fontName=font,
            fontSize=7.5,
            leading=10,
            textColor=INK,
            splitLongWords=1,
        ),
        "finding": ParagraphStyle(
            "ReportFinding",
            parent=base["Heading3"],
            fontName=bold,
            fontSize=10,
            leading=14,
            textColor=INK,
            spaceAfter=4,
            keepWithNext=True,
        ),
        "quote": ParagraphStyle(
            "ReportQuote",
            parent=base["BodyText"],
            fontName=italic,
            fontSize=8,
            leading=11,
            leftIndent=8,
            textColor=MUTED,
            borderColor=LINE,
            borderWidth=0.5,
            borderPadding=6,
            spaceBefore=3,
            spaceAfter=8,
            splitLongWords=1,
        ),
        "toc": ParagraphStyle(
            "ReportTOC",
            parent=base["Normal"],
            fontName=font,
            fontSize=9,
            leading=15,
            leftIndent=8,
            firstLineIndent=-8,
        ),
        "toc_heading": ParagraphStyle(
            "ReportTOCHeading",
            parent=base["Heading1"],
            fontName=bold,
            fontSize=18,
            leading=23,
            textColor=INK,
            spaceAfter=10,
        ),
    }


def _text(value, fallback="Not provided"):
    if value is None or value == "":
        return fallback
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return escape(str(value)).replace("\r\n", "\n").replace("\n", "<br/>")


def _section(title, styles, story):
    story.append(Paragraph(_text(title), styles["section"]))
    story.append(HRFlowable(
        width="100%",
        thickness=0.7,
        color=LINE,
        spaceAfter=8,
    ))


def _bullet(text, styles):
    return Paragraph(f"• {_text(text)}", styles["small"])


def _table(rows, widths, header=True):
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PALE) if header else
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


class _DossierDocument(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._section_number = 0

    def beforeDocument(self):
        self._section_number = 0

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph) or flowable.style.name != "ReportSection":
            return
        title = flowable.getPlainText()
        self._section_number += 1
        key = f"dossier-section-{self._section_number}"
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level=0, closed=False)
        self.notify("TOCEntry", (0, title, self.page, key))


def _on_page(canvas, document):
    canvas.saveState()
    page_width, _ = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, 15 * mm, page_width - 18 * mm, 15 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, 10 * mm, "DECIPHER  |  INVESTIGATION DOSSIER")
    canvas.drawRightString(page_width - 18 * mm, 10 * mm, f"Page {document.page}")
    canvas.restoreState()


def _create_document(buffer, title):
    return _DossierDocument(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=21 * mm,
        title=str(title or "Investigation Dossier"),
        author="Decipher",
        pageCompression=1,
    )


def _add_contents(styles, story):
    story.extend([
        Paragraph("Contents", styles["toc_heading"]),
        HRFlowable(width="100%", thickness=0.7, color=LINE, spaceAfter=9),
    ])
    contents = TableOfContents()
    contents.levelStyles = [styles["toc"]]
    contents.dotsMinLevel = 0
    story.extend([contents, PageBreak()])


def _add_metrics(styles, story, metrics):
    cells = [
        Paragraph(f"<b>{_text(value, '0')}</b><br/>{_text(label)}", styles["body"])
        for label, value in metrics
    ]
    table = Table([cells], colWidths=[PAGE_WIDTH / len(cells)] * len(cells))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("BOX", (0, 0), (-1, -1), 0.6, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend([table, Spacer(1, 5 * mm)])


def _build_pdf(title, generated_at, metrics, sections, *, include_contents=True):
    buffer = io.BytesIO()
    document = _create_document(buffer, title)
    styles = _styles()
    story = [
        Spacer(1, 9 * mm),
        Paragraph(_text(title), styles["title"]),
        Paragraph(f"Generated {_text(generated_at)}", styles["subtitle"]),
    ]
    _add_metrics(styles, story, metrics)
    if include_contents:
        _add_contents(styles, story)
    for section in sections:
        section(styles, story)
    document.multiBuild(story)
    return buffer.getvalue()


def _standard_sections(report_data):
    investigation = report_data.get("investigation") or {}
    summary = report_data.get("summary") or {}
    sections = report_data.get("sections") or {}
    documents = sections.get("document_overview") or []
    field_groups = sections.get("extracted_information") or []
    findings = (
        report_data.get("findings")
        or sections.get("contextual_analysis")
        or []
    )
    visual_findings = sections.get("visual_forensic_findings") or []
    traceability = sections.get("evidence_and_traceability") or []
    limitations = report_data.get("limitations") or []

    def executive(styles, story):
        _section("Executive summary", styles, story)
        story.append(Paragraph(
            f"<b>Investigation:</b> {_text(investigation.get('title'))}<br/>"
            f"<b>Reference:</b> {_text(investigation.get('id'))} &nbsp; "
            f"<b>Status:</b> {_text(investigation.get('status'))}<br/>"
            f"<b>Created:</b> {_text(investigation.get('created_at'))}<br/>"
            f"<b>Scope:</b> {_text(investigation.get('description'))}",
            styles["body"],
        ))
        severity_counts = summary.get("severity_counts") or {}
        distribution = [
            [Paragraph("<b>Severity</b>", styles["table"]),
             Paragraph("<b>Count</b>", styles["table"])],
        ]
        for severity in ("high", "medium", "low", "info"):
            distribution.append([
                Paragraph(_text(severity.title()), styles["table"]),
                Paragraph(_text(severity_counts.get(severity), "0"), styles["table"]),
            ])
        story.append(_table(distribution, [PAGE_WIDTH * 0.68, PAGE_WIDTH * 0.32]))
        story.append(Spacer(1, 4 * mm))

    def inventory(styles, story):
        _section("Document inventory and integrity", styles, story)
        if not documents:
            story.append(Paragraph("No documents were included.", styles["body"]))
            return
        rows = [[
            Paragraph("<b>Document</b>", styles["table"]),
            Paragraph("<b>Type / status</b>", styles["table"]),
            Paragraph("<b>SHA-256</b>", styles["table"]),
            Paragraph("<b>Uploaded</b>", styles["table"]),
        ]]
        for item in documents:
            rows.append([
                Paragraph(_text(item.get("filename")), styles["table"]),
                Paragraph(
                    f"{_text(item.get('document_type'))}<br/>"
                    f"{_text(item.get('processing_status'))}",
                    styles["table"],
                ),
                Paragraph(_text(item.get("sha256")), styles["table"]),
                Paragraph(_text(item.get("uploaded_at")), styles["table"]),
            ])
        story.append(_table(rows, [45 * mm, 32 * mm, 61 * mm, 36 * mm]))

    def extracted(styles, story):
        _section("Extracted information", styles, story)
        if not field_groups:
            story.append(Paragraph("No extracted fields were reported.", styles["body"]))
            return
        for group in field_groups:
            story.append(Paragraph(
                f"<b>{_text(group.get('filename'))}</b>",
                styles["body"],
            ))
            fields = group.get("fields") or []
            if not fields:
                story.append(Paragraph("No named fields were extracted.", styles["small"]))
                continue
            rows = [[
                Paragraph("<b>Field</b>", styles["table"]),
                Paragraph("<b>Extracted value</b>", styles["table"]),
                Paragraph("<b>Page</b>", styles["table"]),
                Paragraph("<b>Confidence</b>", styles["table"]),
            ]]
            for field in fields:
                confidence = field.get("confidence")
                confidence_label = (
                    f"{confidence:.0%}" if isinstance(confidence, (int, float))
                    else "—"
                )
                rows.append([
                    Paragraph(_text(field.get("field_name")), styles["table"]),
                    Paragraph(_text(field.get("field_value")), styles["table"]),
                    Paragraph(_text(field.get("page_number"), "—"), styles["table"]),
                    Paragraph(confidence_label, styles["table"]),
                ])
            story.append(_table(rows, [35 * mm, 95 * mm, 19 * mm, 25 * mm]))
            story.append(Spacer(1, 3 * mm))

    def findings_section(styles, story):
        _section("Contextual analysis findings", styles, story)
        if not findings:
            story.append(Paragraph("No contextual findings were reported.", styles["body"]))
        for index, finding in enumerate(findings, start=1):
            story.append(Paragraph(
                f"{index}. {_text(finding.get('title'))} "
                f"<font color='#A95732'>"
                f"[{_text(finding.get('severity'), 'unrated').upper()}]</font>",
                styles["finding"],
            ))
            story.append(Paragraph(
                f"<b>Type:</b> {_text(finding.get('anomaly_type'))} &nbsp; "
                f"<b>Classification:</b> {_text(finding.get('classification'))}"
                + (
                    f" &nbsp; <b>Priority:</b> {_text(finding.get('priority_score'))}"
                    if finding.get("priority_score") is not None else ""
                ),
                styles["small"],
            ))
            if finding.get("field_name"):
                story.append(Paragraph(
                    f"<b>Field:</b> {_text(finding.get('field_name'))}",
                    styles["small"],
                ))
            story.append(Paragraph(_text(finding.get("explanation")), styles["body"]))
            evidence = finding.get("evidence")
            if evidence:
                for item in evidence if isinstance(evidence, list) else [evidence]:
                    story.append(Paragraph(
                        f"<b>Evidence:</b> {_text(item)}",
                        styles["quote"],
                    ))
            story.append(Spacer(1, 2 * mm))

    def visual(styles, story):
        _section("Visual forensic observations", styles, story)
        if not visual_findings:
            story.append(Paragraph("No visual forensic observations were reported.", styles["body"]))
            return
        for item in visual_findings:
            story.append(Paragraph(
                f"<b>{_text(item.get('filename'))} · Page "
                f"{_text(item.get('page'), '—')}</b>",
                styles["body"],
            ))
            for observation in item.get("observations") or []:
                story.append(_bullet(observation, styles))

    def evidence_map(styles, story):
        _section("Evidence and traceability", styles, story)
        if not traceability:
            story.append(Paragraph("No finding-to-evidence links were reported.", styles["body"]))
            return
        rows = [[
            Paragraph("<b>Finding</b>", styles["table"]),
            Paragraph("<b>Document</b>", styles["table"]),
            Paragraph("<b>Page</b>", styles["table"]),
            Paragraph("<b>Field</b>", styles["table"]),
            Paragraph("<b>Source evidence</b>", styles["table"]),
        ]]
        for item in traceability:
            values = item.get("evidence")
            if not isinstance(values, list):
                values = [values] if values else []
            if not values:
                values = [{}]
            for value in values:
                if not isinstance(value, dict):
                    value = {"quote": value}
                document_name = (
                    value.get("filename")
                    or value.get("document_name")
                    or value.get("document_id")
                )
                page = value.get("page", value.get("page_number"))
                field = value.get("label") or value.get("field_name")
                quote = (
                    value.get("value")
                    or value.get("note")
                    or value.get("quote")
                    or value
                )
                rows.append([
                    Paragraph(_text(item.get("finding_id")), styles["table"]),
                    Paragraph(_text(document_name), styles["table"]),
                    Paragraph(_text(page, "—"), styles["table"]),
                    Paragraph(_text(field), styles["table"]),
                    Paragraph(_text(quote), styles["table"]),
                ])
        story.append(_table(rows, [16 * mm, 28 * mm, 12 * mm, 28 * mm, 90 * mm]))

    def limitations_section(styles, story):
        _section("Limitations and review notice", styles, story)
        if not limitations:
            story.append(Paragraph("No additional processing limitations were reported.", styles["small"]))
        for limitation in limitations:
            story.append(_bullet(limitation, styles))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(
            f"<b>{_text(report_data.get('disclaimer'))}</b>",
            styles["body"],
        ))

    return [
        executive,
        inventory,
        extracted,
        findings_section,
        visual,
        evidence_map,
        limitations_section,
    ]


def generate_investigation_pdf(report_data: dict) -> bytes:
    investigation = report_data.get("investigation") or {}
    summary = report_data.get("summary") or {}
    severities = summary.get("severity_counts") or {}
    title = report_data.get("report_title") or "Investigation Dossier"
    if investigation.get("title"):
        title = f"{title} · {investigation['title']}"
    metrics = [
        ("Documents", summary.get("document_count", 0)),
        ("Findings", summary.get("finding_count", 0)),
        ("High severity", severities.get("high", 0)),
        ("Status", investigation.get("status", "unknown")),
    ]
    return _build_pdf(
        title,
        report_data.get("generated_at"),
        metrics,
        _standard_sections(report_data),
    )


def _ai_sections(report_data):
    investigation = report_data.get("investigation") or {}
    run = report_data.get("run") or {}
    findings = report_data.get("findings") or []
    documents = report_data.get("documents") or []
    result = run.get("result") or {}

    def overview(styles, story):
        _section("Investigation overview", styles, story)
        story.append(Paragraph(
            f"<b>Investigation:</b> {_text(investigation.get('title'))}<br/>"
            f"<b>Investigation ID:</b> {_text(investigation.get('id'))}<br/>"
            f"<b>Description:</b> {_text(investigation.get('description'))}<br/>"
            f"<b>Analysis depth:</b> {_text(investigation.get('analysis_depth'))}<br/>"
            f"<b>Run:</b> #{_text(run.get('id'))} &nbsp; "
            f"<b>Status:</b> {_text(run.get('status'))}<br/>"
            f"<b>Model:</b> {_text(run.get('model'))} "
            f"({_text(run.get('model_version'))})<br/>"
            f"<b>Completed:</b> {_text(run.get('completed_at'))}",
            styles["body"],
        ))
        finding_counts = result.get("structured_findings") or {}
        rejected_count = finding_counts.get("rejected_count", 0)
        if not findings and rejected_count:
            outcome = (
                f"No candidate passed source-quote verification. "
                f"{rejected_count} candidate(s) were excluded and are not "
                "presented as verified findings."
            )
        elif not findings:
            outcome = (
                "The model completed its review but produced no "
                "source-verified findings."
            )
        else:
            outcome = (
                f"{len(findings)} finding(s) passed source-quote verification "
                "and are listed below."
            )
        story.append(Paragraph(
            f"<b>Outcome:</b> {_text(outcome)}",
            styles["body"],
        ))

        _section("Evidence reviewed", styles, story)
        if not documents:
            story.append(Paragraph("No documents were attached to this run.", styles["body"]))
            return
        rows = [[
            Paragraph("<b>Document</b>", styles["table"]),
            Paragraph("<b>Source</b>", styles["table"]),
            Paragraph("<b>SHA-256 prefix</b>", styles["table"]),
        ]]
        for document in documents:
            source = (
                "AI-only upload"
                if document.get("source_type") == "ai_upload"
                else "Linked source"
            )
            digest = document.get("sha256") or ""
            rows.append([
                Paragraph(_text(document.get("filename")), styles["table"]),
                Paragraph(_text(source), styles["table"]),
                Paragraph(_text(digest[:16] if digest else "Not recorded"), styles["table"]),
            ])
        story.append(_table(rows, [60 * mm, 38 * mm, 76 * mm]))

    def finding_section(styles, story):
        _section("AI findings and source evidence", styles, story)
        if not findings:
            finding_counts = result.get("structured_findings") or {}
            rejected_count = finding_counts.get("rejected_count", 0)
            if rejected_count:
                message = (
                    f"{rejected_count} candidate(s) were excluded because their "
                    "citations could not be verified against source text."
                )
            else:
                message = (
                    "This analysis run produced no source-verified findings."
                )
            story.append(Paragraph(_text(message), styles["body"]))
        for index, finding in enumerate(findings, start=1):
            story.append(Paragraph(
                f"{index}. {_text(finding.get('title'))} "
                f"<font color='#A95732'>"
                f"[{_text(finding.get('severity'), 'unrated').upper()}]</font>",
                styles["finding"],
            ))
            confidence = finding.get("confidence")
            confidence_text = (
                f"{confidence:.0%}" if isinstance(confidence, (int, float))
                else "Not rated"
            )
            story.append(Paragraph(
                f"<b>Category:</b> {_text(finding.get('category'))} &nbsp; "
                f"<b>Confidence:</b> {confidence_text} &nbsp; "
                f"<b>Review:</b> {_text(finding.get('review_status'))}",
                styles["small"],
            ))
            story.append(Paragraph(_text(finding.get("description")), styles["body"]))
            if finding.get("reasoning"):
                story.append(Paragraph(
                    f"<b>Reasoning:</b> {_text(finding.get('reasoning'))}",
                    styles["small"],
                ))
            if finding.get("recommended_action"):
                story.append(Paragraph(
                    f"<b>Suggested follow-up:</b> "
                    f"{_text(finding.get('recommended_action'))}",
                    styles["body"],
                ))
            for evidence in finding.get("evidence") or []:
                source_label = _text(evidence.get("filename"), "Linked finding")
                page = _text(evidence.get("page_number"), "—")
                field = evidence.get("field_name")
                if field:
                    source_label += f" · {_text(field)}"
                story.append(Paragraph(
                    f"<b>{source_label} · Page {page} · "
                    f"{_text(evidence.get('verification_status'))}</b><br/>"
                    f"{_text(evidence.get('quote'))}",
                    styles["quote"],
                ))
            alternatives = finding.get("alternative_explanations") or []
            if alternatives:
                story.append(Paragraph("<b>Alternative explanations</b>", styles["small"]))
                for alternative in alternatives:
                    story.append(_bullet(alternative, styles))
            reviews = finding.get("reviews") or []
            if reviews:
                story.append(Paragraph("<b>Human review history</b>", styles["small"]))
                for review in reviews:
                    review_text = (
                        f"{_text(review.get('created_at'))} · "
                        f"{_text(review.get('review_status'))} · "
                        f"{_text(review.get('reviewer'), 'Reviewer not named')}"
                    )
                    if review.get("comment"):
                        review_text += f" · {_text(review.get('comment'))}"
                    story.append(_bullet(review_text, styles))
            story.append(Spacer(1, 3 * mm))

    def methodology(styles, story):
        _section("Method and limitations", styles, story)
        story.append(Paragraph(
            "This report contains output from a local model and source references "
            "recorded by the analysis run. Model confidence is an analytical score, "
            "not a probability that misconduct occurred.",
            styles["body"],
        ))
        result = run.get("result") or {}
        retrieval = result.get("evidence_retrieval") or {}
        story.append(Paragraph(
            f"<b>Source hash checks passed:</b> "
            f"{_text(retrieval.get('sha256_verified'), 'Not reported')}<br/>"
            f"<b>Analysis completed:</b> {_text(run.get('completed_at'))}",
            styles["small"],
        ))
        story.append(Paragraph(
            "<b>All findings require review by a qualified human. "
            "A model output is not proof of fraud, misconduct, or document alteration.</b>",
            styles["body"],
        ))

    return [overview, finding_section, methodology]


def generate_ai_investigation_pdf(report_data: dict) -> bytes:
    investigation = report_data.get("investigation") or {}
    run = report_data.get("run") or {}
    findings = report_data.get("findings") or []
    severity_counts = {
        severity: sum(
            1 for finding in findings
            if str(finding.get("severity") or "").casefold() == severity
        )
        for severity in ("high", "medium", "low")
    }
    metrics = [
        ("Evidence", len(report_data.get("documents") or [])),
        ("Verified findings", len(findings)),
        ("High severity", severity_counts["high"]),
        ("Run", f"#{run.get('id', '—')}"),
    ]
    title = f"AI Investigation Report · {investigation.get('title') or 'Investigation'}"
    return _build_pdf(
        title,
        report_data.get("generated_at"),
        metrics,
        _ai_sections(report_data),
        include_contents=False,
    )
