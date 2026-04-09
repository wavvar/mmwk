#!/usr/bin/env python3

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


REPO_ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS_ROOT = Path(__file__).resolve().parent
MODULES_ROOT = REPO_ROOT / "modules"
OUTPUT_ROOT = DOWNLOADS_ROOT / "modules"
GITHUB_BLOB_BASE = "https://github.com/wavvar/mmwk/blob/main"
PAGE_WIDTH, PAGE_HEIGHT = A4
LEFT_MARGIN = 18 * mm
RIGHT_MARGIN = 18 * mm
TOP_MARGIN = 18 * mm
BOTTOM_MARGIN = 24 * mm
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
HTML_NS = {"x": "http://www.w3.org/1999/xhtml"}
ADDRESS_EN = (
    "Suite 1101-10, 11th Floor, within 16 suites including Suite 301, 3rd Floor, "
    "Building 2, Zone 1, No. 188 South Fourth Ring West Road, Fengtai District, Beijing"
)
ADDRESS_ZH = (
    "北京市丰台区南四环西路188号一区2号楼3层301室等16套内11层1101-10套间"
)
FOOTER_CONTACT = "www.wavvar.com | support@wavvar.com"
EN_FONT_NAME = "WavvarArialUnicode"
ZH_FONT_NAME = "WavvarSongti"
ZH_FONT_FALLBACK = "WavvarZhCID"


MODULE_DOCS = [
    ("rpx.md", "rpx-en.pdf"),
    ("rpx_cn.md", "rpx-zh-cn.pdf"),
    ("mini.md", "mini-en.pdf"),
    ("mini_cn.md", "mini-zh-cn.pdf"),
    ("pro.md", "pro-en.pdf"),
    ("pro_cn.md", "pro-zh-cn.pdf"),
    ("mdr.md", "mdr-en.pdf"),
    ("mdr_cn.md", "mdr-zh-cn.pdf"),
    ("wdr-m.md", "wdr-m-en.pdf"),
    ("wdr-m_cn.md", "wdr-m-zh-cn.pdf"),
    ("wdr-4g.md", "wdr-4g-en.pdf"),
    ("wdr-4g_cn.md", "wdr-4g-zh-cn.pdf"),
    ("ml6432ax.md", "ml6432ax-en.pdf"),
    ("ml6432ax_cn.md", "ml6432ax-zh-cn.pdf"),
    ("ml6432a_bo.md", "ml6432a-bo-en.pdf"),
    ("ml6432a_bo_cn.md", "ml6432a-bo-zh-cn.pdf"),
    ("ml6432a.md", "ml6432a-en.pdf"),
    ("ml6432a_cn.md", "ml6432a-zh-cn.pdf"),
    ("f9a1.md", "f9a1-en.pdf"),
    ("f9a1_cn.md", "f9a1-zh-cn.pdf"),
]


@dataclass
class TableCellSpec:
    row: int
    column: int
    colspan: int
    rowspan: int
    tag: str
    element: ET.Element


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def escape_text(text: str | None) -> str:
    normalized = (text or "").translate(
        str.maketrans(
            {
                "⎓": " DC ",
                "–": "-",
                "—": "-",
                "−": "-",
                "‑": "-",
                "‒": "-",
            }
        )
    )
    return escape(normalized, {'"': "&quot;"})


def register_fonts(language: str) -> tuple[str, str]:
    if language != "zh-cn":
        if EN_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
            font_candidates = [
                Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
                Path("/Library/Fonts/Arial Unicode.ttf"),
            ]
            for candidate in font_candidates:
                if not candidate.exists():
                    continue
                try:
                    pdfmetrics.registerFont(TTFont(EN_FONT_NAME, str(candidate)))
                    pdfmetrics.registerFontFamily(
                        EN_FONT_NAME,
                        normal=EN_FONT_NAME,
                        bold=EN_FONT_NAME,
                        italic=EN_FONT_NAME,
                        boldItalic=EN_FONT_NAME,
                    )
                    break
                except Exception:
                    continue
        if EN_FONT_NAME in pdfmetrics.getRegisteredFontNames():
            return (EN_FONT_NAME, EN_FONT_NAME)
        return ("Helvetica", "Helvetica-Bold")

    if ZH_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        font_candidates = [
            Path("/System/Library/Fonts/Supplemental/Songti.ttc"),
            Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
            Path("/System/Library/Fonts/STHeiti Light.ttc"),
        ]
        registered = False
        for candidate in font_candidates:
            if not candidate.exists():
                continue
            try:
                pdfmetrics.registerFont(TTFont(ZH_FONT_NAME, str(candidate)))
                registered = True
                break
            except Exception:
                continue
        if registered:
            pdfmetrics.registerFontFamily(
                ZH_FONT_NAME,
                normal=ZH_FONT_NAME,
                bold=ZH_FONT_NAME,
                italic=ZH_FONT_NAME,
                boldItalic=ZH_FONT_NAME,
            )
        elif ZH_FONT_FALLBACK not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            pdfmetrics.registerFontFamily(
                ZH_FONT_FALLBACK,
                normal="STSong-Light",
                bold="STSong-Light",
                italic="STSong-Light",
                boldItalic="STSong-Light",
            )

    if ZH_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return (ZH_FONT_NAME, ZH_FONT_NAME)
    return (ZH_FONT_FALLBACK, ZH_FONT_FALLBACK)


def build_styles(language: str) -> StyleSheet1:
    body_font, bold_font = register_fonts(language)
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DocBody",
            parent=styles["BodyText"],
            fontName=body_font,
            fontSize=10.4,
            leading=14,
            textColor=colors.HexColor("#333333"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DocCaption",
            parent=styles["DocBody"],
            fontSize=8.8,
            leading=11,
            textColor=colors.HexColor("#6b7280"),
            alignment=TA_CENTER,
            spaceBefore=3,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverEyebrow",
            parent=styles["DocBody"],
            alignment=TA_CENTER,
            fontName=bold_font,
            fontSize=10,
            leading=12,
            textColor=colors.HexColor("#0b63ce"),
            spaceAfter=12,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverTitle",
            parent=styles["Heading1"],
            alignment=TA_CENTER,
            fontName=bold_font,
            fontSize=26,
            leading=31,
            spaceBefore=0,
            spaceAfter=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CoverMeta",
            parent=styles["DocBody"],
            alignment=TA_CENTER,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ContentsEntry",
            parent=styles["DocBody"],
            fontSize=9.4,
            leading=12,
            leftIndent=0,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DocBlockQuote",
            parent=styles["DocBody"],
            leftIndent=9,
            borderPadding=6,
            borderLeftColor=colors.HexColor("#d4d8dd"),
            borderLeftWidth=2,
            textColor=colors.HexColor("#4b5563"),
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="DocCode",
            parent=styles["Code"],
            fontName="Courier",
            fontSize=8.5,
            leading=10.2,
            leftIndent=8,
            rightIndent=8,
            borderPadding=8,
            borderWidth=0.5,
            borderColor=colors.HexColor("#d6d9de"),
            backColor=colors.HexColor("#f7f8fa"),
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableBody",
            parent=styles["DocBody"],
            fontSize=8.4,
            leading=10.6,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TableHead",
            parent=styles["TableBody"],
            fontName=bold_font,
            textColor=colors.HexColor("#111111"),
        )
    )
    heading_sizes = {
        "Heading1": (22, 26),
        "Heading2": (16.5, 20),
        "Heading3": (13.4, 17),
        "Heading4": (11.6, 15),
        "Heading5": (10.6, 14),
        "Heading6": (10.0, 13),
    }
    for name, (font_size, leading) in heading_sizes.items():
        styles[name].fontName = bold_font
        styles[name].fontSize = font_size
        styles[name].leading = leading
        styles[name].spaceBefore = 8
        styles[name].spaceAfter = 6
        styles[name].textColor = colors.HexColor("#111111")
    return styles


class ModuleDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str, *, footer_font_name: str, language: str, **kwargs):
        super().__init__(filename, **kwargs)
        self.footer_font_name = footer_font_name
        self.language = language
        self._heading_index = 0
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="content")
        template = PageTemplate(id="content", frames=[frame], onPage=self.draw_footer)
        self.addPageTemplates([template])

    def beforeDocument(self) -> None:
        self._heading_index = 0

    def draw_footer(self, canvas, doc) -> None:
        canvas.saveState()
        line_y = 18 * mm
        base_y = 8.2 * mm
        canvas.setStrokeColor(colors.HexColor("#d8dee8"))
        canvas.setLineWidth(0.6)
        canvas.line(self.leftMargin, line_y, self.pagesize[0] - self.rightMargin, line_y)
        canvas.setFillColor(colors.HexColor("#6b7280"))
        footer_font_size = 7.2
        footer_width = self.pagesize[0] - self.leftMargin - self.rightMargin
        address = ADDRESS_ZH if self.language == "zh-cn" else ADDRESS_EN
        footer_lines = simpleSplit(address, self.footer_font_name, footer_font_size, footer_width)
        footer_lines.append(FOOTER_CONTACT)
        canvas.setFont(self.footer_font_name, footer_font_size)
        for index, line in enumerate(reversed(footer_lines)):
            canvas.drawString(self.leftMargin, base_y + (index * 8.2), line)
        canvas.drawRightString(
            self.pagesize[0] - self.rightMargin,
            base_y,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()

    def afterFlowable(self, flowable) -> None:
        if not isinstance(flowable, Paragraph):
            return
        style_name = getattr(flowable.style, "name", "")
        toc_levels = {
            "Heading2": 0,
            "Heading3": 1,
            "Heading4": 2,
            "Heading5": 3,
            "Heading6": 4,
        }
        if style_name not in toc_levels:
            return
        title = flowable.getPlainText().strip()
        if not title or is_contents_heading(title):
            return
        self._heading_index += 1
        bookmark = f"heading-{self._heading_index}"
        self.canv.bookmarkPage(bookmark)
        self.notify("TOCEntry", (toc_levels[style_name], title, self.page, bookmark))


def sanitize_html_for_xml(html_content: str) -> str:
    return re.sub(
        r"<(img|br|hr|meta|link|input)(\s[^<>]*?)?>",
        lambda match: match.group(0)[:-1] + " />" if not match.group(0).endswith("/>") else match.group(0),
        html_content,
        flags=re.IGNORECASE,
    )


def resolve_link(href: str | None, current_markdown: Path) -> str:
    if not href:
        return ""
    if href.startswith(("http://", "https://", "mailto:", "#")):
        return href
    target, sep, anchor = href.partition("#")
    resolved = (current_markdown.parent / target).resolve()
    try:
        relative = resolved.relative_to(REPO_ROOT)
    except ValueError:
        return href
    github_url = f"{GITHUB_BLOB_BASE}/{relative.as_posix()}"
    if sep:
        github_url = f"{github_url}#{anchor}"
    return github_url


def resolve_image(src: str | None, current_markdown: Path) -> Path | None:
    if not src or src.startswith(("http://", "https://", "data:")):
        return None
    candidate = (current_markdown.parent / src).resolve()
    if candidate.exists():
        return candidate
    return None


def text_only(element: ET.Element) -> str:
    return "".join(element.itertext()).strip()


def inline_markup(element: ET.Element, current_markdown: Path) -> str:
    parts: list[str] = []
    if element.text:
        parts.append(escape_text(element.text))
    for child in element:
        tag = local_name(child.tag)
        inner = inline_markup(child, current_markdown)
        if tag in {"strong", "b"}:
            parts.append(f"<b>{inner}</b>")
        elif tag in {"em", "i"}:
            parts.append(f"<i>{inner}</i>")
        elif tag == "code":
            parts.append(f"<font name=\"Courier\">{inner}</font>")
        elif tag == "a":
            href = resolve_link(child.get("href"), current_markdown)
            label = inner or escape_text(href)
            parts.append(f"<link href=\"{escape_text(href)}\" color=\"#0b63ce\">{label}</link>")
        elif tag == "br":
            parts.append("<br/>")
        elif tag in {"span", "small", "sup", "sub"}:
            parts.append(inner)
        elif tag == "img":
            alt = child.get("alt") or ""
            if alt:
                parts.append(escape_text(alt))
        else:
            parts.append(inner)
        if child.tail:
            parts.append(escape_text(child.tail))
    return "".join(parts).strip()


def image_width_hint(element: ET.Element, max_width: float) -> float:
    width_attr = element.get("width", "").strip()
    if width_attr.endswith("%"):
        try:
            return max_width * (float(width_attr[:-1]) / 100.0)
        except ValueError:
            return max_width
    if width_attr:
        try:
            return min(float(width_attr), max_width)
        except ValueError:
            pass
    style = element.get("style", "")
    match = re.search(r"width:\s*([0-9.]+)%", style)
    if match:
        return max_width * (float(match.group(1)) / 100.0)
    return max_width


def build_image_flowable(element: ET.Element, current_markdown: Path, max_width: float) -> Image | None:
    image_path = resolve_image(element.get("src"), current_markdown)
    if image_path is None:
        return None
    reader = ImageReader(str(image_path))
    source_width, source_height = reader.getSize()
    desired_width = image_width_hint(element, max_width)
    scale = min(desired_width / source_width, (190 * mm) / source_height, 1.0)
    flowable = Image(str(image_path), width=source_width * scale, height=source_height * scale)
    flowable.hAlign = "CENTER"
    return flowable


def simple_paragraph(markup: str, style: ParagraphStyle) -> Paragraph | None:
    cleaned = markup.strip()
    if not cleaned:
        return None
    return Paragraph(cleaned, style)


def render_list(
    element: ET.Element,
    styles: StyleSheet1,
    current_markdown: Path,
    ordered: bool,
    max_width: float,
) -> ListFlowable:
    items: list[ListItem] = []
    for child in element:
        if local_name(child.tag) != "li":
            continue
        children = render_children(child, styles, current_markdown, max_width=max_width - 10)
        if not children:
            paragraph = simple_paragraph(inline_markup(child, current_markdown), styles["DocBody"])
            if paragraph is not None:
                children = [paragraph]
        items.append(ListItem(children or [Spacer(1, 1)]))
    return ListFlowable(
        items,
        bulletType="1" if ordered else "bullet",
        start="1",
        leftIndent=14,
        bulletFontName=styles["DocBody"].fontName,
        bulletFontSize=9,
    )


def estimate_cell_weight(element: ET.Element) -> float:
    text_length = len(text_only(element))
    image_count = sum(1 for node in element.iter() if local_name(node.tag) == "img")
    weight = max(1.0, min(6.0, text_length / 22.0))
    return weight + (image_count * 1.2)


def table_column_widths(specs: list[TableCellSpec], column_count: int) -> list[float]:
    weights = [1.0] * column_count
    for spec in specs:
        per_column_weight = estimate_cell_weight(spec.element) / max(spec.colspan, 1)
        for offset in range(spec.colspan):
            column = spec.column + offset
            weights[column] = max(weights[column], per_column_weight)
    total = sum(weights) or float(column_count)
    return [CONTENT_WIDTH * weight / total for weight in weights]


def render_table_cell(
    element: ET.Element,
    cell_tag: str,
    styles: StyleSheet1,
    current_markdown: Path,
    cell_width: float,
):
    style_name = "TableHead" if cell_tag == "th" else "TableBody"
    child_blocks = render_children(element, styles, current_markdown, max_width=max(cell_width - 10, 32))
    if child_blocks:
        return child_blocks
    paragraph = simple_paragraph(inline_markup(element, current_markdown), styles[style_name])
    return paragraph or ""


def render_table(
    element: ET.Element,
    styles: StyleSheet1,
    current_markdown: Path,
) -> Table:
    rows: list[ET.Element] = []
    header_rows = 0
    for child in element:
        tag = local_name(child.tag)
        if tag == "thead":
            section_rows = [node for node in child if local_name(node.tag) == "tr"]
            header_rows += len(section_rows)
            rows.extend(section_rows)
        elif tag in {"tbody", "tfoot"}:
            rows.extend([node for node in child if local_name(node.tag) == "tr"])
        elif tag == "tr":
            rows.append(child)
    if not rows:
        return Table([[""]])

    specs: list[TableCellSpec] = []
    occupied: set[tuple[int, int]] = set()
    max_columns = 0

    for row_index, row in enumerate(rows):
        column_index = 0
        for cell in row:
            if local_name(cell.tag) not in {"th", "td"}:
                continue
            while (row_index, column_index) in occupied:
                column_index += 1
            colspan = int(cell.get("colspan", "1"))
            rowspan = int(cell.get("rowspan", "1"))
            specs.append(
                TableCellSpec(
                    row=row_index,
                    column=column_index,
                    colspan=colspan,
                    rowspan=rowspan,
                    tag=local_name(cell.tag),
                    element=cell,
                )
            )
            for row_offset in range(rowspan):
                for column_offset in range(colspan):
                    if row_offset == 0 and column_offset == 0:
                        continue
                    occupied.add((row_index + row_offset, column_index + column_offset))
            column_index += colspan
            max_columns = max(max_columns, column_index)

    if header_rows == 0 and rows:
        first_row_cells = [node for node in rows[0] if local_name(node.tag) in {"th", "td"}]
        if first_row_cells and all(local_name(node.tag) == "th" for node in first_row_cells):
            header_rows = 1

    widths = table_column_widths(specs, max_columns)
    data = [["" for _ in range(max_columns)] for _ in rows]
    style_commands = [
        ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#d9dde3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]

    for spec in specs:
        span_width = sum(widths[spec.column : spec.column + spec.colspan])
        data[spec.row][spec.column] = render_table_cell(
            spec.element,
            spec.tag,
            styles,
            current_markdown,
            span_width,
        )
        if spec.colspan > 1 or spec.rowspan > 1:
            style_commands.append(
                (
                    "SPAN",
                    (spec.column, spec.row),
                    (spec.column + spec.colspan - 1, spec.row + spec.rowspan - 1),
                )
            )
        if spec.tag == "th" or spec.row < header_rows:
            style_commands.append(
                (
                    "BACKGROUND",
                    (spec.column, spec.row),
                    (spec.column + spec.colspan - 1, spec.row + spec.rowspan - 1),
                    colors.HexColor("#eef3f8"),
                )
            )

    table = Table(data, colWidths=widths, repeatRows=header_rows)
    table.setStyle(TableStyle(style_commands))
    return table


def document_language(markdown_path: Path) -> str:
    return "zh-cn" if markdown_path.stem.endswith("_cn") else "en"


def is_contents_heading(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"table of contents", "contents", "目录"}


def first_heading(body: ET.Element) -> str:
    for node in body.iter():
        if local_name(node.tag) == "h1":
            title = text_only(node)
            if title:
                return title
    return "Wavvar MMWK Module Document"


def collect_contents_entries(body: ET.Element) -> list[tuple[int, str]]:
    entries: list[tuple[int, str]] = []
    for node in body.iter():
        tag = local_name(node.tag)
        if tag not in {"h2", "h3", "h4", "h5", "h6"}:
            continue
        title = text_only(node)
        if not title or is_contents_heading(title):
            continue
        entries.append((int(tag[1]), title))
    return entries


def filtered_body_children(body: ET.Element) -> list[ET.Element]:
    children = list(body)
    filtered: list[ET.Element] = []
    skipped_title = False
    index = 0
    while index < len(children):
        child = children[index]
        tag = local_name(child.tag)
        title = text_only(child)
        if not skipped_title and tag == "h1":
            skipped_title = True
            index += 1
            continue
        if tag in {"h2", "h3"} and is_contents_heading(title):
            if index + 1 < len(children) and local_name(children[index + 1].tag) in {"ul", "ol"}:
                index += 2
                continue
            index += 1
            continue
        if tag == "p" and title.strip().lower() in {"中文版", "chinese version"}:
            index += 1
            continue
        filtered.append(child)
        index += 1
    return filtered


def build_cover(title: str, language: str, styles: StyleSheet1) -> list:
    if language == "zh-cn":
        eyebrow = "Wavvar MMWK 模组文档"
    else:
        eyebrow = "Wavvar MMWK Module Documentation"
    subtitle = "Wavvar Technologies"
    return [
        Spacer(1, 56 * mm),
        Paragraph(eyebrow, styles["CoverEyebrow"]),
        Paragraph(escape_text(title), styles["CoverTitle"]),
        Paragraph(subtitle, styles["CoverMeta"]),
        Spacer(1, 12 * mm),
        HRFlowable(width="42%", color=colors.HexColor("#d8dee8"), thickness=1.0),
        Spacer(1, 104 * mm),
        PageBreak(),
    ]


def build_contents_page(
    language: str,
    styles: StyleSheet1,
) -> list:
    heading = "目录" if language == "zh-cn" else "Contents"
    toc = TableOfContents()
    toc.dotsMinLevel = 0
    toc.levelStyles = [
        ParagraphStyle(name="TOCLevel0", parent=styles["ContentsEntry"], leftIndent=0, firstLineIndent=0),
        ParagraphStyle(name="TOCLevel1", parent=styles["ContentsEntry"], leftIndent=12, firstLineIndent=0),
        ParagraphStyle(name="TOCLevel2", parent=styles["ContentsEntry"], leftIndent=24, firstLineIndent=0),
        ParagraphStyle(name="TOCLevel3", parent=styles["ContentsEntry"], leftIndent=36, firstLineIndent=0),
        ParagraphStyle(name="TOCLevel4", parent=styles["ContentsEntry"], leftIndent=48, firstLineIndent=0),
    ]
    story: list = [Paragraph(heading, styles["Heading2"]), Spacer(1, 4), toc, PageBreak()]
    return story


def render_children(
    element: ET.Element,
    styles: StyleSheet1,
    current_markdown: Path,
    *,
    max_width: float,
) -> list:
    flowables: list = []
    for child in element:
        flowables.extend(render_element(child, styles, current_markdown, max_width=max_width))
    return flowables


def render_element(
    element: ET.Element,
    styles: StyleSheet1,
    current_markdown: Path,
    *,
    max_width: float,
) -> list:
    tag = local_name(element.tag)
    flowables: list = []

    if tag in {"header", "section", "article", "body", "div"}:
        if tag == "div":
            image_children = [child for child in element if local_name(child.tag) == "img"]
            if image_children:
                for image_element in image_children:
                    image_flowable = build_image_flowable(image_element, current_markdown, max_width=max_width)
                    if image_flowable is not None:
                        flowables.append(image_flowable)
                        flowables.append(Spacer(1, 4))
        for child in element:
            if tag == "div" and local_name(child.tag) == "img":
                continue
            flowables.extend(render_element(child, styles, current_markdown, max_width=max_width))
        return flowables

    if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        level = int(tag[1])
        paragraph = simple_paragraph(inline_markup(element, current_markdown), styles[f"Heading{level}"])
        if paragraph is not None:
            flowables.append(paragraph)
        return flowables

    if tag == "p":
        paragraph = simple_paragraph(inline_markup(element, current_markdown), styles["DocBody"])
        if paragraph is not None:
            flowables.append(paragraph)
        return flowables

    if tag == "blockquote":
        paragraph = simple_paragraph(escape_text(text_only(element)), styles["DocBlockQuote"])
        if paragraph is not None:
            flowables.append(paragraph)
        return flowables

    if tag == "pre":
        flowables.append(Preformatted(text_only(element), styles["DocCode"]))
        return flowables

    if tag == "img":
        image_flowable = build_image_flowable(element, current_markdown, max_width=max_width)
        if image_flowable is not None:
            flowables.append(image_flowable)
        return flowables

    if tag == "figure":
        image = element.find("x:img", HTML_NS)
        if image is not None:
            image_flowable = build_image_flowable(image, current_markdown, max_width=max_width)
            if image_flowable is not None:
                flowables.append(image_flowable)
        caption = element.find("x:figcaption", HTML_NS)
        if caption is not None:
            paragraph = simple_paragraph(inline_markup(caption, current_markdown), styles["DocCaption"])
            if paragraph is not None:
                flowables.append(paragraph)
        return flowables

    if tag in {"ul", "ol"}:
        flowables.append(
            render_list(
                element,
                styles,
                current_markdown,
                ordered=(tag == "ol"),
                max_width=max_width,
            )
        )
        flowables.append(Spacer(1, 4))
        return flowables

    if tag == "table":
        flowables.append(render_table(element, styles, current_markdown))
        flowables.append(Spacer(1, 8))
        return flowables

    if tag == "hr":
        flowables.append(HRFlowable(width="100%", color=colors.HexColor("#d9dde3"), thickness=0.7))
        flowables.append(Spacer(1, 6))
        return flowables

    if tag in {"thead", "tbody", "tfoot", "tr", "td", "th", "li"}:
        return render_children(element, styles, current_markdown, max_width=max_width)

    paragraph = simple_paragraph(inline_markup(element, current_markdown), styles["DocBody"])
    if paragraph is not None:
        flowables.append(paragraph)
    flowables.extend(render_children(element, styles, current_markdown, max_width=max_width))
    return flowables


def render_story(markdown_path: Path, styles: StyleSheet1) -> list:
    with TemporaryDirectory(prefix="mmwk-module-html-") as temporary_dir:
        html_path = Path(temporary_dir) / f"{markdown_path.stem}.html"
        subprocess.run(
            ["pandoc", str(markdown_path), "-s", "-o", str(html_path)],
            check=True,
            cwd=MODULES_ROOT,
        )
        document = ET.ElementTree(ET.fromstring(sanitize_html_for_xml(html_path.read_text(encoding="utf-8"))))
        body = document.getroot().find("x:body", HTML_NS)
        if body is None:
            raise RuntimeError(f"Could not find body in rendered HTML for {markdown_path.name}")
        language = document_language(markdown_path)
        title = first_heading(body)
        story = build_cover(title, language, styles)
        story.extend(build_contents_page(language, styles))
        for child in filtered_body_children(body):
            story.extend(render_element(child, styles, markdown_path, max_width=CONTENT_WIDTH))
        compact_story: list = []
        for flowable in story:
            compact_story.append(flowable)
            if isinstance(flowable, (Paragraph, ListFlowable, Table, Image, Preformatted)):
                compact_story.append(Spacer(1, 4))
        return compact_story


def build_pdf(markdown_name: str, pdf_name: str, styles: StyleSheet1) -> None:
    markdown_path = MODULES_ROOT / markdown_name
    output_path = OUTPUT_ROOT / pdf_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    story = render_story(markdown_path, styles)
    language = document_language(markdown_path)
    title = markdown_path.stem.replace("_", " ")
    document = ModuleDocTemplate(
        str(output_path),
        footer_font_name=styles["DocBody"].fontName,
        language=language,
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=title,
        author="Wavvar",
    )
    document.multiBuild(story)
    print(f"generated {output_path.relative_to(REPO_ROOT)}")


def main() -> None:
    if not REPO_ROOT.exists():
        raise SystemExit(f"Missing repo root: {REPO_ROOT}")
    for markdown_name, pdf_name in MODULE_DOCS:
        styles = build_styles(document_language(MODULES_ROOT / markdown_name))
        build_pdf(markdown_name, pdf_name, styles)


if __name__ == "__main__":
    main()
