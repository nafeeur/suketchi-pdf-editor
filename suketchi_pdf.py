from __future__ import annotations

import html
import json
import os
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import pymupdf as fitz
except ImportError:
    import fitz

import random

from PyQt6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QFontDatabase,
    QImage,
    QIcon,
    QPainter,
    QBrush,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QProxyStyle,
    QStyle,
    QStyleOptionMenuItem,
    QStyleOptionToolButton,
    QStyleOptionViewItem,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def rgb_from_qcolor(color: QColor) -> Tuple[float, float, float]:
    return color.redF(), color.greenF(), color.blueF()


def qcolor_from_pdf_int(value: int) -> QColor:
    """PyMuPDF spans return color as 0xRRGGBB integer."""
    r = (value >> 16) & 255
    g = (value >> 8) & 255
    b = value & 255
    return QColor(r, g, b)


def safe_filename(text: str, fallback: str = "export") -> str:
    cleaned = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in text.strip())
    return cleaned or fallback


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def page_range_from_user(parent: QWidget, page_count: int) -> Optional[Tuple[int, int]]:
    text, ok = QInputDialog.getText(
        parent,
        "Page Range",
        f"Enter page range, for example 1-{page_count} or 3-7:",
    )
    if not ok or not text.strip():
        return None

    value = text.strip().replace(" ", "")
    try:
        if "-" in value:
            a, b = value.split("-", 1)
            start = int(a)
            end = int(b)
        else:
            start = end = int(value)
    except ValueError:
        QMessageBox.warning(parent, "Invalid Range", "Please enter a valid page range.")
        return None

    if start < 1 or end < start or end > page_count:
        QMessageBox.warning(parent, "Invalid Range", f"Range must be between 1 and {page_count}.")
        return None

    return start - 1, end - 1


INK = QColor(0, 0, 0)
PAPER = QColor(255, 255, 255)

APP_FONT_FAMILY = "Segoe UI"

GREY_MUTED = QColor(120, 120, 120)
GREY_FAINT = QColor(175, 175, 175)


def sketch_path(rect: QRectF, seed: int, jitter: float = 1.3, segments: int = 5) -> QPainterPath:
    """A wobbly rectangle that looks drawn by hand.

    Each edge becomes a short polyline whose points are nudged by a seeded
    random offset, then smoothed with quadratic curves so the line reads as a
    pen stroke rather than a jagged zigzag. The seed is derived from the widget
    and its geometry, so a control keeps the *same* wobble across repaints
    instead of shimmering every frame.
    """
    rnd = random.Random(seed)
    corners = [
        (rect.left(), rect.top()),
        (rect.right(), rect.top()),
        (rect.right(), rect.bottom()),
        (rect.left(), rect.bottom()),
    ]
    points = []
    for index in range(4):
        x0, y0 = corners[index]
        x1, y1 = corners[(index + 1) % 4]
        # Segment count scales with edge length. With a fixed count, long
        length = max(abs(x1 - x0), abs(y1 - y0))
        edge_segments = max(segments, int(length / 26))
        for step in range(edge_segments):
            t = step / edge_segments
            points.append((
                x0 + (x1 - x0) * t + rnd.uniform(-jitter, jitter),
                y0 + (y1 - y0) * t + rnd.uniform(-jitter, jitter),
            ))

    path = QPainterPath()
    path.moveTo(*points[0])
    for index in range(1, len(points)):
        px, py = points[index - 1]
        x, y = points[index]
        path.quadTo(px, py, (px + x) / 2, (py + y) / 2)
    path.closeSubpath()
    return path


def sketch_line(p1: QPointF, p2: QPointF, seed: int, jitter: float = 1.0) -> QPainterPath:
    """A single wobbly stroke between two points."""
    rnd = random.Random(seed)
    path = QPainterPath()
    path.moveTo(p1)
    steps = 6
    for step in range(1, steps + 1):
        t = step / steps
        x = p1.x() + (p2.x() - p1.x()) * t + rnd.uniform(-jitter, jitter)
        y = p1.y() + (p2.y() - p1.y()) * t + rnd.uniform(-jitter, jitter)
        path.lineTo(x, y)
    return path


def stable_seed(*parts) -> int:
    """Deterministic seed so a control's wobble never changes between frames."""
    return abs(hash(parts)) % (2 ** 31)


def draw_sketch_box(
    painter: QPainter,
    rect: QRectF,
    seed: int,
    fill: Optional[QColor] = None,
    width: float = 2.0,
    shadow: bool = False,
    shadow_offset: float = 4.0,
    jitter: float = 1.3,
):
    """Paint one hand-drawn box, optionally with the hard offset shadow."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if shadow:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(INK)
        painter.drawPath(sketch_path(rect.translated(shadow_offset, shadow_offset), seed, jitter))

    painter.setBrush(fill if fill is not None else Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(INK, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.drawPath(sketch_path(rect, seed, jitter))
    painter.restore()


class SketchMenu(QMenu):
    """A QMenu that paints its own panel and hand-drawn selection.

    QStyleSheetStyle draws CE_MenuItem itself whenever a stylesheet is active
    anywhere in the widget's ancestry, and never delegates to the application
    style. So instead of styling the item, we paint the panel and the highlight
    box underneath, and let the base implementation draw only the text on top
    (the stylesheet keeps item backgrounds transparent).
    """

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        painter.fillRect(self.rect(), PAPER)
        draw_sketch_box(painter, rect, stable_seed("menu", self.width(), self.height()),
                        fill=PAPER, width=2.0, jitter=1.0)

        action = self.activeAction()
        if action is not None and action.isEnabled() and not action.isSeparator():
            geo = QRectF(self.actionGeometry(action)).adjusted(3, 1, -3, -1)
            if geo.width() > 4 and geo.height() > 4:
                draw_sketch_box(painter, geo,
                                stable_seed("menusel", int(geo.width()), int(geo.y())),
                                fill=None, width=1.8, jitter=0.9)
        painter.end()
        super().paintEvent(event)


class SketchStyle(QProxyStyle):
    """Paints Qt's standard controls as hand-drawn boxes.

    Qt stylesheets cannot draw a wobbly border, so borders and backgrounds are
    deliberately left out of the stylesheet and painted here instead. The
    stylesheet still handles colour, font and padding.
    """

    def _seed_for(self, widget, rect) -> int:
        return stable_seed(id(widget) if widget is not None else 0,
                           rect.width(), rect.height())

    def drawPrimitive(self, element, option, painter, widget=None):
        rect = QRectF(option.rect).adjusted(1.5, 1.5, -1.5, -1.5)
        seed = self._seed_for(widget, option.rect)

        if element in (
            QStyle.PrimitiveElement.PE_PanelButtonCommand,
            QStyle.PrimitiveElement.PE_PanelButtonTool,
        ):
            if rect.width() <= 2 or rect.height() <= 2:
                return
            state = option.state
            on = bool(state & QStyle.StateFlag.State_On)
            sunken = bool(state & QStyle.StateFlag.State_Sunken)
            hovered = bool(state & QStyle.StateFlag.State_MouseOver)
            enabled = bool(state & QStyle.StateFlag.State_Enabled)

            if on or sunken:
                fill = INK
            elif hovered and enabled:
                fill = QColor(238, 238, 238)
            else:
                fill = PAPER

            shadow = enabled and not (on or sunken)
            offset = 0.0 if (on or sunken) else 3.5
            target = rect.translated(1.5, 1.5) if (on or sunken) else rect
            draw_sketch_box(painter, target, seed, fill=fill,
                            width=2.0 if enabled else 1.2,
                            shadow=shadow, shadow_offset=offset)
            return

        if element in (
            QStyle.PrimitiveElement.PE_FrameLineEdit,
            QStyle.PrimitiveElement.PE_PanelLineEdit,
        ):
            if element == QStyle.PrimitiveElement.PE_PanelLineEdit:
                draw_sketch_box(painter, rect, seed, fill=PAPER, width=1.8)
            return

        if element in (
            QStyle.PrimitiveElement.PE_Frame,
            QStyle.PrimitiveElement.PE_FrameGroupBox,
            QStyle.PrimitiveElement.PE_FrameTabWidget,
        ):
            draw_sketch_box(painter, rect, seed, fill=None, width=1.6, jitter=1.0)
            return

        if element in (
            QStyle.PrimitiveElement.PE_PanelMenu,
            QStyle.PrimitiveElement.PE_FrameMenu,
        ):
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.fillRect(option.rect, PAPER)
            painter.restore()
            draw_sketch_box(painter, QRectF(option.rect).adjusted(1.5, 1.5, -1.5, -1.5),
                            seed, fill=None, width=2.0, jitter=1.0)
            return

        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            draw_sketch_box(painter, rect, seed, fill=PAPER, width=1.8, jitter=0.9)
            if option.state & QStyle.StateFlag.State_On:
                painter.save()
                painter.setPen(QPen(INK, 2.0, Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                painter.drawPath(sketch_line(
                    QPointF(rect.left() + rect.width() * 0.22, rect.top() + rect.height() * 0.52),
                    QPointF(rect.left() + rect.width() * 0.45, rect.top() + rect.height() * 0.78),
                    seed + 1, 0.6))
                painter.drawPath(sketch_line(
                    QPointF(rect.left() + rect.width() * 0.45, rect.top() + rect.height() * 0.78),
                    QPointF(rect.left() + rect.width() * 0.82, rect.top() + rect.height() * 0.22),
                    seed + 2, 0.6))
                painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)

    def drawControl(self, element, option, painter, widget=None):
        # Qt reuses these control elements with different option structs (a
        if element == QStyle.ControlElement.CE_MenuItem and isinstance(option, QStyleOptionMenuItem):
            menu_option = QStyleOptionMenuItem(option)

            if menu_option.menuItemType == QStyleOptionMenuItem.MenuItemType.Separator:
                rect = QRectF(option.rect)
                painter.save()
                painter.setPen(QPen(INK, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                y = rect.center().y()
                painter.drawPath(sketch_line(
                    QPointF(rect.left() + 10, y), QPointF(rect.right() - 10, y),
                    stable_seed("sep", int(rect.width()), int(rect.y())), 0.7))
                painter.restore()
                return

            selected = bool(option.state & QStyle.StateFlag.State_Selected) and \
                bool(option.state & QStyle.StateFlag.State_Enabled)
            if selected:
                rect = QRectF(option.rect).adjusted(3, 1.5, -3, -1.5)
                draw_sketch_box(
                    painter, rect,
                    stable_seed("menuitem", int(rect.width()), int(rect.y())),
                    fill=PAPER, width=1.8, jitter=1.0,
                )
                menu_option.state &= ~QStyle.StateFlag.State_Selected
                menu_option.palette.setColor(QPalette.ColorRole.HighlightedText, INK)
            super().drawControl(element, menu_option, painter, widget)
            return

        if element == QStyle.ControlElement.CE_ItemViewItem and isinstance(option, QStyleOptionViewItem):
            view_option = QStyleOptionViewItem(option)
            selected = bool(option.state & QStyle.StateFlag.State_Selected)
            if selected:
                rect = QRectF(option.rect).adjusted(5, 2, -9, -2)
                if rect.width() > 4 and rect.height() > 4:
                    draw_sketch_box(
                        painter, rect,
                        stable_seed("item", int(rect.width()), int(rect.y())),
                        fill=PAPER, width=1.8, jitter=1.0,
                        shadow=True, shadow_offset=2.5,
                    )
                view_option.state &= ~QStyle.StateFlag.State_Selected
                view_option.palette.setColor(QPalette.ColorRole.HighlightedText, INK)
                view_option.palette.setColor(QPalette.ColorRole.Highlight, Qt.GlobalColor.transparent)
            super().drawControl(element, view_option, painter, widget)
            return

        super().drawControl(element, option, painter, widget)

    def drawComplexControl(self, control, option, painter, widget=None):
        if control == QStyle.ComplexControl.CC_ToolButton and isinstance(option, QStyleOptionToolButton):
            # Toolbar buttons are auto-raise: Qt only paints their panel on
            rect = QRectF(option.rect).adjusted(1.5, 1.5, -1.5, -1.5)
            seed = self._seed_for(widget, option.rect)
            state = option.state
            on = bool(state & QStyle.StateFlag.State_On)
            sunken = bool(state & QStyle.StateFlag.State_Sunken)
            hovered = bool(state & QStyle.StateFlag.State_MouseOver)
            enabled = bool(state & QStyle.StateFlag.State_Enabled)

            if rect.width() > 2 and rect.height() > 2:
                if on or sunken:
                    fill = INK
                elif hovered and enabled:
                    fill = QColor(238, 238, 238)
                else:
                    fill = PAPER
                target = rect.translated(1.5, 1.5) if (on or sunken) else rect
                draw_sketch_box(
                    painter, target, seed, fill=fill,
                    width=2.0 if enabled else 1.2,
                    shadow=enabled and not (on or sunken), shadow_offset=3.5,
                )

            label = QStyleOptionToolButton(option)
            self.drawControl(QStyle.ControlElement.CE_ToolButtonLabel, label, painter, widget)
            return

        if control in (QStyle.ComplexControl.CC_ComboBox, QStyle.ComplexControl.CC_SpinBox):
            rect = QRectF(option.rect).adjusted(1.5, 1.5, -1.5, -1.5)
            seed = self._seed_for(widget, option.rect)
            draw_sketch_box(painter, rect, seed, fill=PAPER, width=1.8)
            if control == QStyle.ComplexControl.CC_ComboBox:
                painter.save()
                painter.setPen(QPen(INK, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                cx = rect.right() - 12
                cy = rect.center().y() - 1
                painter.drawPath(sketch_line(QPointF(cx - 4, cy - 2), QPointF(cx, cy + 3), seed + 3, 0.5))
                painter.drawPath(sketch_line(QPointF(cx, cy + 3), QPointF(cx + 4, cy - 2), seed + 4, 0.5))
                painter.restore()
            return
        super().drawComplexControl(control, option, painter, widget)


class Tool:
    SELECT = "Select"
    TEXT_BOX = "Add Text Box"
    EDIT_TEXT = "Edit Text Span"
    EDIT_BLOCK = "Edit Text Block"
    MOVE_TEXT = "Reposition Text"
    NOTE = "Add Comment"
    HIGHLIGHT = "Highlight"
    UNDERLINE = "Underline"
    STRIKEOUT = "Strikethrough"
    RECTANGLE = "Draw Rectangle"
    LINE = "Draw Line"
    INK = "Freehand Draw"
    REDACT = "Redact (Blackout)"
    CROP = "Crop Page"
    LINK = "Insert Hyperlink"
    IMAGE = "Insert Image"


DRAG_RECT_TOOLS = {
    Tool.TEXT_BOX,
    Tool.HIGHLIGHT,
    Tool.UNDERLINE,
    Tool.STRIKEOUT,
    Tool.RECTANGLE,
    Tool.REDACT,
    Tool.CROP,
    Tool.LINK,
}

CLICK_TOOLS = {
    Tool.EDIT_TEXT,
    Tool.EDIT_BLOCK,
    Tool.NOTE,
    Tool.IMAGE,
}

LINE_TOOLS = {Tool.LINE}


@dataclass
class TextSpanHit:
    text: str
    bbox: fitz.Rect
    size: float
    color: QColor
    font: str


@dataclass
class TextBlockHit:
    text: str
    bbox: fitz.Rect


class TextBoxDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, initial_text: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(520, 360)

        layout = QVBoxLayout(self)
        self.editor = QTextEdit()
        self.editor.setPlainText(initial_text)
        self.editor.setPlaceholderText("Type the text that should appear inside the selected PDF box...")
        layout.addWidget(self.editor)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def text(self) -> str:
        return self.editor.toPlainText()


class SearchReplaceDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("Search and Replace Text")
        self.resize(520, 220)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.find_input = QLineEdit()
        self.replace_input = QLineEdit()
        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["Current Page", "Whole Document"])
        self.case_sensitive = QCheckBox("Case sensitive")

        form.addRow("Find:", self.find_input)
        form.addRow("Replace with:", self.replace_input)
        form.addRow("Scope:", self.scope_combo)
        form.addRow("", self.case_sensitive)

        note = QLabel(
            "This replaces visible text by redacting the old match area and drawing the replacement text. "
            "It is best for simple, horizontal text."
        )
        note.setWordWrap(True)
        note.setObjectName("SmallNote")

        layout.addLayout(form)
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> Tuple[str, str, str, bool]:
        return (
            self.find_input.text(),
            self.replace_input.text(),
            self.scope_combo.currentText(),
            self.case_sensitive.isChecked(),
        )


class DocumentInfoDialog(QDialog):
    def __init__(self, parent: QWidget, info: Dict[str, str], page_count: int):
        super().__init__(parent)
        self.setWindowTitle("Document Information")
        self.resize(620, 460)

        layout = QVBoxLayout(self)
        self.info_box = QTextEdit()
        self.info_box.setReadOnly(True)

        data = {"page_count": page_count, **(info or {})}
        self.info_box.setPlainText(json.dumps(data, indent=2, ensure_ascii=False))
        layout.addWidget(self.info_box)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class MetadataEditDialog(QDialog):
    def __init__(self, parent: QWidget, info: Dict[str, str]):
        super().__init__(parent)
        self.setWindowTitle("Edit PDF Metadata")
        self.resize(520, 340)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.fields: Dict[str, QLineEdit] = {}
        for key in ["title", "author", "subject", "keywords", "creator", "producer"]:
            line = QLineEdit()
            line.setText(str((info or {}).get(key, "") or ""))
            self.fields[key] = line
            form.addRow(key.title() + ":", line)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def metadata(self) -> Dict[str, str]:
        return {k: v.text() for k, v in self.fields.items()}


class PasswordDialog(QDialog):
    def __init__(self, parent: QWidget, title: str = "Password Required"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(360, 130)

        layout = QVBoxLayout(self)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Enter PDF password")
        layout.addWidget(QLabel("This PDF is encrypted."))
        layout.addWidget(self.password)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> str:
        return self.password.text()


class PageCanvas(QWidget):
    """Interactive PDF page preview. Coordinates passed to parent are image pixels."""

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.pixmap: Optional[QPixmap] = None
        self.zoom = 1.0
        self.tool = Tool.SELECT
        self.search_rects: List[QRectF] = []
        self.edit_rects: List[QRectF] = []
        self.crop_preview_rect: Optional[QRectF] = None
        self._brand: Optional[QPixmap] = None
        self.xray_enabled = False
        self.xray_text: List[QRectF] = []
        self.xray_image: List[QRectF] = []
        self.xray_vector: List[QRectF] = []
        self.stroke_color = QColor("#257A6C")
        self.fill_color = QColor("#e7f0ee")
        self.text_color = QColor("#1c1a17")
        self.line_width = 2

        self._margin = 14
        self._drag_start: Optional[QPointF] = None
        self._drag_current: Optional[QPointF] = None
        self._ink_points: List[QPointF] = []
        self._pan_last: Optional[QPointF] = None

        self.setMouseTracking(True)
        self.setMinimumSize(850, 1000)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_page(
        self,
        pixmap: QPixmap,
        zoom: float,
        search_rects: Optional[List[QRectF]] = None,
        edit_rects: Optional[List[QRectF]] = None,
        crop_preview_rect: Optional[QRectF] = None,
        xray: Optional[Dict[str, List[QRectF]]] = None,
    ):
        self.pixmap = pixmap
        self.zoom = zoom
        self.search_rects = search_rects or []
        self.edit_rects = edit_rects or []
        self.crop_preview_rect = crop_preview_rect
        xray = xray or {}
        self.xray_text = xray.get("text", [])
        self.xray_image = xray.get("image", [])
        self.xray_vector = xray.get("vector", [])
        self._drag_start = None
        self._drag_current = None
        self._ink_points = []
        self.resize(self.sizeHint())
        self.updateGeometry()
        self.update()

    def set_tool(self, tool: str):
        self.tool = tool
        self._drag_start = None
        self._drag_current = None
        self._ink_points = []
        self.update()

    def set_xray_enabled(self, enabled: bool):
        self.xray_enabled = bool(enabled)
        self.update()

    def set_style(self, stroke_color: QColor, fill_color: QColor, text_color: QColor, line_width: int):
        self.stroke_color = QColor(stroke_color)
        self.fill_color = QColor(fill_color)
        self.text_color = QColor(text_color)
        self.line_width = max(1, int(line_width))
        self.update()

    def sizeHint(self) -> QSize:
        if self.pixmap is None:
            return QSize(920, 1120)
        return QSize(self.pixmap.width() + self._margin * 2, self.pixmap.height() + self._margin * 2)

    def _page_rect(self) -> QRectF:
        if self.pixmap is None:
            return QRectF()
        x = max((self.width() - self.pixmap.width()) / 2, self._margin)
        y = self._margin
        return QRectF(x, y, self.pixmap.width(), self.pixmap.height())

    def _event_to_image_point(self, event) -> Optional[QPointF]:
        rect = self._page_rect()
        point = QPointF(event.position().x() - rect.x(), event.position().y() - rect.y())
        if 0 <= point.x() <= rect.width() and 0 <= point.y() <= rect.height():
            return point
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), PAPER)

        if self.pixmap is None:
            center = QRectF(self.rect())
            if self._brand is None:
                self._brand = load_brand_pixmap(128) or QPixmap()
            if not self._brand.isNull():
                painter.drawPixmap(
                    int(center.center().x() - self._brand.width() / 2),
                    int(center.center().y() - self._brand.height() - 34),
                    self._brand,
                )
            painter.setPen(GREY_MUTED)
            painter.setFont(QFont(APP_FONT_FAMILY, 20))
            painter.drawText(center.adjusted(0, 44, 0, 0), Qt.AlignmentFlag.AlignCenter, "Open a PDF to get started")
            painter.setPen(GREY_FAINT)
            painter.setFont(QFont(APP_FONT_FAMILY, 13))
            painter.drawText(center.adjusted(0, 108, 0, 0), Qt.AlignmentFlag.AlignCenter,
                             "Click here, drop a PDF, or press Ctrl+O")
            return

        page_rect = self._page_rect()

        page_seed = stable_seed("page", int(page_rect.width()), int(page_rect.height()))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(INK)
        painter.drawPath(sketch_path(page_rect.translated(6, 6), page_seed, 1.1))
        painter.setBrush(PAPER)
        painter.drawPath(sketch_path(page_rect, page_seed, 1.1))
        painter.drawPixmap(int(page_rect.x()), int(page_rect.y()), self.pixmap)
        # Outline goes on top: the page bitmap is opaque and would otherwise
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(INK, 2.0, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(sketch_path(page_rect, page_seed, 1.1))

        painter.save()
        painter.translate(page_rect.x(), page_rect.y())

        if self.xray_enabled:
            painter.fillRect(QRectF(0, 0, page_rect.width(), page_rect.height()),
                             QColor(255, 255, 255, 205))

            painter.setPen(QPen(INK, 1))
            painter.setBrush(QColor(0, 0, 0, 42))
            for rect in self.xray_text:
                painter.drawRect(rect)

            painter.setPen(QPen(INK, 1, Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(INK, Qt.BrushStyle.BDiagPattern))
            for rect in self.xray_image:
                painter.drawRect(rect)

            painter.setPen(QPen(INK, 1.2, Qt.PenStyle.DotLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for rect in self.xray_vector:
                painter.drawRect(rect)

            self._paint_xray_legend(painter)

        if self.search_rects:
            painter.setPen(QPen(INK, 2))
            painter.setBrush(QColor(0, 0, 0, 38))
            for rect in self.search_rects:
                painter.drawPath(sketch_path(rect, stable_seed("find", rect.x(), rect.y()), 0.8))

        if self.tool in {Tool.EDIT_TEXT, Tool.EDIT_BLOCK, Tool.MOVE_TEXT} and self.edit_rects:
            painter.setPen(QPen(INK, 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 0, 0, 16))
            for rect in self.edit_rects:
                painter.drawRect(rect)

        if self.crop_preview_rect:
            painter.setPen(QPen(INK, 2, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(0, 0, 0, 18))
            painter.drawRect(self.crop_preview_rect)

        if self._drag_start and self._drag_current:
            temp = QRectF(self._drag_start, self._drag_current).normalized()
            if self.tool == Tool.REDACT:
                painter.setPen(QPen(INK, 2.4, Qt.PenStyle.SolidLine))
                painter.setBrush(QBrush(INK, Qt.BrushStyle.FDiagPattern))
            else:
                painter.setPen(QPen(INK, 2, Qt.PenStyle.DashLine))
                painter.setBrush(QColor(0, 0, 0, 26))
            painter.drawPath(sketch_path(temp, stable_seed("drag", int(temp.width()), int(temp.height())), 1.0))

        if self._drag_start and self._drag_current and self.tool == Tool.LINE:
            painter.setPen(QPen(self.stroke_color, max(1.0, float(self.line_width))))
            painter.drawLine(self._drag_start, self._drag_current)

        if self._drag_start and self._drag_current and self.tool == Tool.MOVE_TEXT:
            painter.setPen(QPen(INK, 2.2, Qt.PenStyle.DashLine))
            painter.drawLine(self._drag_start, self._drag_current)
            painter.drawEllipse(self._drag_current, 5, 5)

        if len(self._ink_points) > 1:
            painter.setPen(QPen(self.stroke_color, max(1.0, float(self.line_width)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            for a, b in zip(self._ink_points, self._ink_points[1:]):
                painter.drawLine(a, b)

        painter.restore()

    def _paint_xray_legend(self, painter: QPainter):
        """Small legend so the tints are self-explanatory."""
        entries = [
            ("solid", f"Editable text · {len(self.xray_text)}"),
            ("hatch", f"Image · {len(self.xray_image)}"),
            ("dotted", f"Vector · {len(self.xray_vector)}"),
        ]
        pad, swatch, row_h = 11, 11, 20
        painter.setFont(QFont(APP_FONT_FAMILY, 10))
        metrics = painter.fontMetrics()
        width = max(metrics.horizontalAdvance(label) for _, label in entries) + swatch + pad * 3
        height = row_h * len(entries) + pad

        box = QRectF(14, 14, width, height)
        draw_sketch_box(painter, box, stable_seed("legend", int(width), int(height)),
                        fill=PAPER, width=1.8)

        y = box.y() + pad / 2 + 4
        for texture, label in entries:
            marker = QRectF(box.x() + pad, y + 3, swatch, swatch)
            painter.setPen(QPen(INK, 1))
            if texture == "solid":
                painter.setBrush(QColor(0, 0, 0, 60))
            elif texture == "hatch":
                painter.setBrush(QBrush(INK, Qt.BrushStyle.BDiagPattern))
            else:
                painter.setPen(QPen(INK, 1.2, Qt.PenStyle.DotLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(marker)
            painter.setPen(INK)
            painter.drawText(QRectF(box.x() + pad * 2 + swatch, y, width, row_h),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            y += row_h

    def wheelEvent(self, event):
        """Ctrl/Cmd + wheel zooms. Normal wheel still scrolls via QScrollArea."""
        modifiers = event.modifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
            self.callback("__zoom_delta__", event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.pixmap is not None and event.button() == Qt.MouseButton.LeftButton:
            self.callback("__fit_width__", None)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if self.pixmap is None:
            if event.button() == Qt.MouseButton.LeftButton:
                self.callback("__open_pdf__", None)
                event.accept()
            return

        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan_last = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        p = self._event_to_image_point(event)
        if p is None:
            return

        if self.tool == Tool.MOVE_TEXT:
            ok = bool(self.callback("__move_text_start__", p))
            if ok:
                self._drag_start = p
                self._drag_current = p
                self.update()
            return

        if self.tool in CLICK_TOOLS:
            self.callback(self.tool, p)
            return

        if self.tool in DRAG_RECT_TOOLS or self.tool in LINE_TOOLS:
            self._drag_start = p
            self._drag_current = p
            self.update()
            return

        if self.tool == Tool.INK:
            self._ink_points = [p]
            self.update()
            return

    def mouseMoveEvent(self, event):
        if self.pixmap is None:
            return

        if self._pan_last is not None:
            current = event.position()
            delta = current - self._pan_last
            self._pan_last = current
            self.callback("__pan__", delta)
            event.accept()
            return

        p = self._event_to_image_point(event)
        if p is None:
            return

        if self._drag_start and (self.tool in DRAG_RECT_TOOLS or self.tool in LINE_TOOLS or self.tool == Tool.MOVE_TEXT):
            self._drag_current = p
            self.update()
            return

        if self.tool == Tool.INK and self._ink_points:
            self._ink_points.append(p)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.pixmap is None:
            return

        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._pan_last = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.button() != Qt.MouseButton.LeftButton:
            return

        p = self._event_to_image_point(event)
        if p is None:
            return

        if self._drag_start and self.tool == Tool.MOVE_TEXT:
            start = self._drag_start
            self._drag_start = None
            self._drag_current = None
            self.update()
            if (start - p).manhattanLength() > 4:
                self.callback("__move_text_end__", (start, p))
            return

        if self._drag_start and self.tool in DRAG_RECT_TOOLS:
            rect = QRectF(self._drag_start, p).normalized()
            self._drag_start = None
            self._drag_current = None
            self.update()
            if rect.width() >= 8 and rect.height() >= 8:
                self.callback(self.tool, rect)
            return

        if self._drag_start and self.tool in LINE_TOOLS:
            start = self._drag_start
            self._drag_start = None
            self._drag_current = None
            self.update()
            if (start - p).manhattanLength() > 8:
                self.callback(self.tool, (start, p))
            return

        if self.tool == Tool.INK and len(self._ink_points) > 1:
            points = list(self._ink_points)
            self._ink_points = []
            self.update()
            self.callback(self.tool, points)


def _open_worker_doc(source: Dict[str, object]):
    """Open an independent PyMuPDF document inside a worker thread."""
    if source.get("type") == "path":
        doc = fitz.open(str(source["path"]))
    else:
        doc = fitz.open(stream=source["data"], filetype="pdf")

    password = str(source.get("password") or "")
    if doc.needs_pass and password:
        doc.authenticate(password)
    return doc


class ThumbnailWorker(QObject):
    thumbnail_ready = pyqtSignal(int, int, bytes)
    progress = pyqtSignal(int, int, int)
    error = pyqtSignal(int, str)
    finished = pyqtSignal(int)

    def __init__(self, job_id: int, source: Dict[str, object], thumb_zoom: float = 0.17):
        super().__init__()
        self.job_id = job_id
        self.source = source
        self.thumb_zoom = thumb_zoom
        self.cancelled = False

    @pyqtSlot()
    def run(self):
        doc = None
        try:
            doc = _open_worker_doc(self.source)
            total = doc.page_count
            for page_index in range(total):
                if self.cancelled:
                    break
                page = doc[page_index]
                pix = page.get_pixmap(matrix=fitz.Matrix(self.thumb_zoom, self.thumb_zoom), alpha=False)
                self.thumbnail_ready.emit(self.job_id, page_index, pix.tobytes("png"))
                self.progress.emit(self.job_id, page_index + 1, total)
        except Exception as exc:
            self.error.emit(self.job_id, str(exc))
        finally:
            if doc:
                doc.close()
            self.finished.emit(self.job_id)


class SearchWorker(QObject):
    finished_results = pyqtSignal(int, str, object)
    progress = pyqtSignal(int, int, int)
    error = pyqtSignal(int, str)
    finished = pyqtSignal(int)

    def __init__(self, job_id: int, source: Dict[str, object], query: str):
        super().__init__()
        self.job_id = job_id
        self.source = source
        self.query = query
        self.cancelled = False

    @pyqtSlot()
    def run(self):
        doc = None
        results = []
        try:
            doc = _open_worker_doc(self.source)
            total = doc.page_count
            for page_index in range(total):
                if self.cancelled:
                    break
                for rect in doc[page_index].search_for(self.query):
                    results.append((page_index, rect.x0, rect.y0, rect.x1, rect.y1))
                self.progress.emit(self.job_id, page_index + 1, total)
            self.finished_results.emit(self.job_id, self.query, results)
        except Exception as exc:
            self.error.emit(self.job_id, str(exc))
        finally:
            if doc:
                doc.close()
            self.finished.emit(self.job_id)


class ImageExportWorker(QObject):
    progress = pyqtSignal(int, int, int)
    error = pyqtSignal(int, str)
    done = pyqtSignal(int, str, int)
    finished = pyqtSignal(int)

    def __init__(self, job_id: int, source: Dict[str, object], folder: str, base_name: str, ext: str, scale: float = 2.0):
        super().__init__()
        self.job_id = job_id
        self.source = source
        self.folder = folder
        self.base_name = base_name
        self.ext = ext
        self.scale = scale
        self.cancelled = False

    @pyqtSlot()
    def run(self):
        doc = None
        count = 0
        try:
            doc = _open_worker_doc(self.source)
            total = doc.page_count
            output_dir = Path(self.folder)
            output_dir.mkdir(parents=True, exist_ok=True)
            for page_index in range(total):
                if self.cancelled:
                    break
                pix = doc[page_index].get_pixmap(matrix=fitz.Matrix(self.scale, self.scale), alpha=False)
                out = output_dir / f"{self.base_name}_page_{page_index + 1:03d}.{self.ext}"
                pix.save(str(out))
                count += 1
                self.progress.emit(self.job_id, page_index + 1, total)
            self.done.emit(self.job_id, self.folder, count)
        except Exception as exc:
            self.error.emit(self.job_id, str(exc))
        finally:
            if doc:
                doc.close()
            self.finished.emit(self.job_id)


class PdfStudioOverhaulPro(QMainWindow):
    def __init__(self):
        super().__init__()

        self.doc: Optional[fitz.Document] = None
        self.file_path: Optional[str] = None
        self.current_page_index = 0
        self.zoom = 1.25
        self.current_tool = Tool.SELECT
        self.annotation_color = QColor("#000000")
        self.fill_color = QColor("#ffffff")
        self.text_color = QColor("#000000")
        self.line_width = 2
        self.opacity_percent = 35
        self.is_dirty = False

        self.search_results: List[Tuple[int, fitz.Rect]] = []
        self.search_index = -1
        self.pending_image_path: Optional[str] = None
        self.undo_stack: List[bytes] = []
        self.redo_stack: List[bytes] = []
        self.max_history = 10
        self._pdf_password = ""
        self._workers: List[Tuple[QThread, QObject]] = []
        self._thumbnail_job_id = 0
        self._search_job_id = 0
        self._export_job_id = 0
        self._page_structure_changed = False

        self._doc_version = 0
        self._render_cache: Dict[Tuple[int, float, int], QPixmap] = {}
        self._render_cache_order: List[Tuple[int, float, int]] = []
        self.xray_enabled = False
        self._xray_cache: Dict[Tuple[int, int, int], Dict[str, List[QRectF]]] = {}

        self.setWindowTitle("Suketchi PDF Reader")
        self.resize(1540, 950)

        self.setAcceptDrops(True)

        self._build_ui()
        self._apply_theme()
        self._update_contextual_panel()
        self._set_document_controls(False)

    def _build_ui(self):
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(190)
        self.progress_bar.setVisible(False)
        self.status.addPermanentWidget(self.progress_bar)

        self._build_top_bar()

        self.page_list = QListWidget()
        self.page_list.setIconSize(QSize(96, 130))
        self.page_list.currentRowChanged.connect(self.on_page_selected)

        self.outline_list = QListWidget()
        self.outline_list.itemClicked.connect(self.go_to_outline_item)

        search_panel = self._build_search_panel()

        self.comments_list = QListWidget()
        self.comments_list.itemClicked.connect(self.go_to_comment_item)

        self.sidebar = QTabWidget()
        self.sidebar.setObjectName("SidebarTabs")
        self.sidebar.setMinimumWidth(238)
        self.sidebar.setMaximumWidth(320)
        self.sidebar.setUsesScrollButtons(False)
        self.sidebar.tabBar().setExpanding(True)
        self.sidebar.addTab(self.page_list, "Pages")
        self.sidebar.addTab(self.outline_list, "Outline")
        self.sidebar.addTab(search_panel, "Find")
        self.sidebar.addTab(self.comments_list, "Notes")

        self.canvas = PageCanvas(self.handle_canvas_action)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.canvas)

        self.properties = self._build_properties_panel()
        self.properties.setMinimumWidth(210)
        self.properties.setMaximumWidth(250)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.addWidget(self.sidebar)
        body.addWidget(self.scroll)
        body.addWidget(self.properties)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 7)
        body.setStretchFactor(2, 1)
        body.setSizes([260, 980, 255])

        self.setCentralWidget(body)

    def _build_top_bar(self):
        top = QToolBar("Ribbon")
        top.setMovable(False)
        top.setObjectName("Ribbon")
        top.setIconSize(QSize(16, 16))
        top.setContentsMargins(6, 4, 6, 4)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, top)

        brand_pixmap = load_seal_pixmap(24)
        if brand_pixmap is not None:
            brand_icon = QLabel()
            brand_icon.setPixmap(brand_pixmap)
            brand_icon.setContentsMargins(2, 0, 6, 0)
            top.addWidget(brand_icon)
        brand_text = QLabel("Suketchi")
        brand_text.setObjectName("BrandText")
        top.addWidget(brand_text)
        top.addSeparator()

        self.open_action = self._add_action(top, "Open", self.open_pdf, "Ctrl+O")
        self.save_action = self._add_action(top, "Save", self.save_as_pdf, "Ctrl+S")
        for action in (self.open_action, self.save_action):
            button = top.widgetForAction(action)
            if button is not None:
                button.setObjectName("Primary")
        top.addSeparator()

        self.undo_action = self._add_action(top, "Undo", self.undo, "Ctrl+Z")
        self.redo_action = self._add_action(top, "Redo", self.redo, "Ctrl+Y")
        top.addSeparator()

        self.file_menu_button = self._menu_button("File", [
            ("Save Encrypted Copy…", self.save_encrypted_copy),
            None,
            ("Document Properties…", self.show_document_info),
            ("Edit Metadata…", self.edit_metadata),
        ])
        top.addWidget(self.file_menu_button)

        self.edit_menu_button = self._menu_button("Edit", [
            ("Find and Replace…", self.search_and_replace),
            None,
            ("Reflow Current Page", self.reflow_current_page_to_new_page),
            ("Reflow Whole Document…", self.reflow_document_to_new_pdf),
        ])
        top.addWidget(self.edit_menu_button)

        self.insert_menu_button = self._menu_button("Insert", [
            ("Image or Signature…", self.prepare_insert_image),
            ("Watermark…", self.add_watermark),
            ("Stamp…", self.add_stamp),
            None,
            ("Blank Page", self.insert_blank_page),
            ("Merge PDF After This Page…", self.insert_pdf_after_current),
        ])
        top.addWidget(self.insert_menu_button)

        self.pages_menu_button = self._menu_button("Pages", [
            ("Rotate Clockwise", self.rotate_current_page_clockwise),
            ("Rotate Counter-clockwise", self.rotate_current_page_counterclockwise),
            None,
            ("Move Page Up", self.move_page_up),
            ("Move Page Down", self.move_page_down),
            None,
            ("Duplicate Page", self.duplicate_current_page),
            ("Delete Page", self.delete_current_page),
            None,
            ("Extract Page Range…", self.extract_page_range),
            ("Split Into Single Pages…", self.split_every_page),
        ])
        top.addWidget(self.pages_menu_button)

        self.export_menu_button = self._menu_button("Export", [
            ("Current Page as Image…", [
                ("PNG…", lambda: self.export_page_image("png")),
                ("JPEG…", lambda: self.export_page_image("jpg")),
            ]),
            ("All Pages as Images…", [
                ("PNG Folder…", lambda: self.export_all_pages_images("png")),
                ("JPEG Folder…", lambda: self.export_all_pages_images("jpg")),
            ]),
            None,
            ("Text", [
                ("Current Page…", self.export_current_page_text),
                ("Whole Document…", self.export_full_document_text),
            ]),
            ("Document As", [
                ("HTML…", self.export_full_document_html),
                ("Markdown…", self.export_full_document_markdown),
                ("Word DOCX…", self.export_full_document_docx),
            ]),
            None,
            ("Metadata as JSON…", self.export_metadata_json),
        ])
        top.addWidget(self.export_menu_button)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top.addWidget(spacer)

        self.xray_button = QToolButton()
        self.xray_button.setObjectName("ToolButton")
        self.xray_button.setText("X-ray")
        self.xray_button.setCheckable(True)
        self.xray_button.setToolTip(
            "Reveal what this page is really made of: editable text, images and vector art"
        )
        self.xray_button.toggled.connect(self.toggle_xray)
        top.addWidget(self.xray_button)
        top.addSeparator()

        self.zoom_out_action = self._add_action(top, "−", self.zoom_out, "Ctrl+-")
        self.zoom_combo = QComboBox()
        self.zoom_combo.setFixedWidth(104)
        self.zoom_combo.setToolTip("Zoom level")
        self.zoom_combo.addItems(["50%", "75%", "100%", "125%", "150%", "175%", "200%", "300%", "Fit Width", "Fit Page"])
        self.zoom_combo.setCurrentText("125%")
        self.zoom_combo.currentTextChanged.connect(self.handle_zoom_combo)
        top.addWidget(self.zoom_combo)
        self.zoom_in_action = self._add_action(top, "+", self.zoom_in, "Ctrl++")

    def _menu_button(self, label: str, items) -> QToolButton:
        """Build a ribbon dropdown.

        Item forms, shared by every menu so they all behave identically:
            None                     -> separator
            (text, callable)         -> action
            (text, [sub-items...])   -> submenu
        """
        button = QToolButton()
        button.setText(f"{label} \u25be")
        button.setMinimumWidth(64)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(self._build_menu(button, items))
        return button

    def _build_menu(self, parent: QWidget, items) -> QMenu:
        menu = SketchMenu(parent)
        for item in items:
            if item is None:
                menu.addSeparator()
                continue
            item_label, target = item
            if isinstance(target, (list, tuple)):
                submenu = self._build_menu(menu, target)
                submenu.setTitle(item_label)
                menu.addMenu(submenu)
            else:
                action = QAction(item_label, self)
                action.triggered.connect(target)
                menu.addAction(action)
        return menu

    def _add_action(self, toolbar: QToolBar, text: str, callback, shortcut: Optional[str] = None) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(callback)
        if shortcut:
            action.setShortcut(shortcut)
        toolbar.addAction(action)
        return action

    def _build_search_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)

        self.search_input = QLineEdit()
        self.search_input.setFixedHeight(31)
        self.search_input.setPlaceholderText("Find text...")
        self.search_input.returnPressed.connect(self.search_text)

        search_row = QHBoxLayout()
        search_row.setContentsMargins(0, 0, 0, 0)
        search_row.setSpacing(6)
        self.search_button = QPushButton("Find")
        self.search_button.setFixedHeight(31)
        self.search_button.clicked.connect(self.search_text)
        self.next_search_button = QPushButton("Next ▸")
        self.next_search_button.setFixedHeight(31)
        self.next_search_button.clicked.connect(self.go_to_next_search_result)
        search_row.addWidget(self.search_button)
        search_row.addWidget(self.next_search_button)

        self.search_results_list = QListWidget()
        self.search_results_list.itemClicked.connect(self.go_to_search_item)

        layout.addWidget(self.search_input)
        layout.addLayout(search_row)
        layout.addWidget(QLabel("Results"))
        layout.addWidget(self.search_results_list)
        return panel

    TOOL_SHORT_LABELS = {
        Tool.SELECT: "Select",
        Tool.TEXT_BOX: "Text Box",
        Tool.EDIT_TEXT: "Edit Span",
        Tool.EDIT_BLOCK: "Edit Block",
        Tool.MOVE_TEXT: "Move",
        Tool.NOTE: "Note",
        Tool.HIGHLIGHT: "Highlight",
        Tool.UNDERLINE: "Underline",
        Tool.STRIKEOUT: "Strike",
        Tool.RECTANGLE: "Rectangle",
        Tool.LINE: "Line",
        Tool.INK: "Freehand",
        Tool.REDACT: "Redact",
        Tool.CROP: "Crop",
        Tool.LINK: "Link",
    }

    TOOL_FIELDS = {
        Tool.TEXT_BOX: {"font", "text", "stroke"},
        Tool.EDIT_BLOCK: {"font", "text"},
        Tool.EDIT_TEXT: set(),
        Tool.MOVE_TEXT: set(),
        Tool.NOTE: set(),
        Tool.HIGHLIGHT: set(),
        Tool.UNDERLINE: {"stroke"},
        Tool.STRIKEOUT: {"stroke"},
        Tool.RECTANGLE: {"line", "opacity", "stroke", "fill"},
        Tool.LINE: {"line", "stroke"},
        Tool.INK: {"line", "stroke"},
        Tool.REDACT: set(),
        Tool.CROP: set(),
        Tool.LINK: set(),
        Tool.SELECT: set(),
        Tool.IMAGE: set(),
    }

    TOOL_HINTS = {
        Tool.SELECT: "Drag with the right or middle mouse button to pan. Ctrl+wheel zooms.",
        Tool.TEXT_BOX: "Drag a box, then type the text to draw inside it.",
        Tool.EDIT_TEXT: "Click a word to replace it. Its original size and colour are reused.",
        Tool.EDIT_BLOCK: "Click a paragraph to replace the whole block.",
        Tool.MOVE_TEXT: "Drag existing text to a new position on the page.",
        Tool.NOTE: "Click to drop a sticky note comment.",
        Tool.HIGHLIGHT: "Drag across text to highlight it.",
        Tool.UNDERLINE: "Drag across text to underline it.",
        Tool.STRIKEOUT: "Drag across text to strike it through.",
        Tool.RECTANGLE: "Drag to draw a rectangle.",
        Tool.LINE: "Drag from start to end to draw a line.",
        Tool.INK: "Draw freehand with the left mouse button.",
        Tool.REDACT: "Drag an area to permanently remove its content.",
        Tool.CROP: "Drag the area to keep, then confirm the crop.",
        Tool.LINK: "Drag an area, then enter the URL it should open.",
        Tool.IMAGE: "Click where the chosen image should be placed.",
    }

    def _update_contextual_panel(self):
        """Show only the appearance rows the active tool uses."""
        fields = self.TOOL_FIELDS.get(self.current_tool, set())
        rows = {
            "font": self.font_size_spin,
            "line": self.line_width_spin,
            "opacity": self.opacity_spin,
            "text": self.text_color_button,
            "stroke": self.stroke_color_button,
            "fill": self.fill_color_button,
        }
        for name, widget in rows.items():
            index, _ = self.style_form.getWidgetPosition(widget)
            if index >= 0:
                self.style_form.setRowVisible(index, name in fields)
        self.style_group.setVisible(bool(fields))
        self.tool_hint.setText(self.TOOL_HINTS.get(self.current_tool, ""))

    def _make_tool_button(self, tool: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("ToolButton")
        button.setText(self.TOOL_SHORT_LABELS.get(tool, tool))
        button.setToolTip(tool)
        button.setCheckable(True)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda _checked=False, t=tool: self.set_tool(t))
        self.tool_buttons[tool] = button
        return button

    def _build_properties_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("PropertiesPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Tools")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)

        self.tool_buttons: Dict[str, QToolButton] = {}
        self._tool_group = QActionGroup(self)
        self._tool_group.setExclusive(True)

        for group_name, tools in (
            ("Text", [Tool.EDIT_TEXT, Tool.EDIT_BLOCK, Tool.MOVE_TEXT, Tool.TEXT_BOX]),
            ("Markup", [Tool.HIGHLIGHT, Tool.UNDERLINE, Tool.STRIKEOUT, Tool.NOTE]),
            ("Draw", [Tool.RECTANGLE, Tool.LINE, Tool.INK]),
            ("Page", [Tool.REDACT, Tool.CROP, Tool.LINK]),
        ):
            group_box = QGroupBox(group_name)
            grid = QGridLayout(group_box)
            grid.setContentsMargins(8, 10, 8, 8)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(6)
            for index, tool in enumerate(tools):
                grid.addWidget(self._make_tool_button(tool), index // 2, index % 2)
            layout.addWidget(group_box)

        select_button = self._make_tool_button(Tool.SELECT)
        select_button.setChecked(True)
        layout.insertWidget(1, select_button)

        self.tool_hint = QLabel()
        self.tool_hint.setObjectName("ToolHint")
        self.tool_hint.setWordWrap(True)
        layout.addWidget(self.tool_hint)

        self.style_group = QGroupBox("Appearance")
        style_group = self.style_group
        style_form = QFormLayout(style_group)
        self.style_form = style_form
        style_form.setContentsMargins(8, 10, 8, 8)
        style_form.setHorizontalSpacing(8)
        style_form.setVerticalSpacing(7)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 120)
        self.font_size_spin.setValue(14)

        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 20)
        self.line_width_spin.setValue(2)
        self.line_width_spin.valueChanged.connect(lambda value: setattr(self, "line_width", value))

        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(5, 100)
        self.opacity_spin.setValue(35)
        self.opacity_spin.valueChanged.connect(lambda value: setattr(self, "opacity_percent", value))

        self.text_color_button = QPushButton("Text")
        self.text_color_button.clicked.connect(lambda: self.choose_color("text"))

        self.stroke_color_button = QPushButton("Stroke")
        self.stroke_color_button.clicked.connect(lambda: self.choose_color("stroke"))

        self.fill_color_button = QPushButton("Fill")
        self.fill_color_button.clicked.connect(lambda: self.choose_color("fill"))

        style_form.addRow("Font size:", self.font_size_spin)
        style_form.addRow("Line width:", self.line_width_spin)
        style_form.addRow("Opacity %:", self.opacity_spin)
        style_form.addRow("Text color:", self.text_color_button)
        style_form.addRow("Stroke color:", self.stroke_color_button)
        style_form.addRow("Fill color:", self.fill_color_button)
        layout.addWidget(style_group)


        layout.addStretch()
        self._refresh_color_buttons()
        return panel

    def _apply_theme(self):
        self.setStyleSheet("""
            /* ============================================================
               Suketchi PDF Reader — hand-drawn, pure black on white
               Only ink (#000), paper (#fff) and two greys for text that would
               otherwise be unreadable. Weight stays regular throughout.
               ============================================================ */

            QMainWindow, QWidget {
                background: #ffffff;
                color: #000000;
                font-size: 14px;
                font-weight: 400;
            }

            QToolBar#Ribbon {
                background: #ffffff;
                border: none;
                padding: 10px 14px;
                spacing: 6px;
            }
            QToolBar#Ribbon::separator { background: transparent; width: 10px; }

            /* Buttons: colour + spacing only. Outline comes from SketchStyle. */
            QToolButton, QPushButton {
                color: #000000;
                padding: 7px 14px;
                min-height: 20px;
            }
            QToolButton:disabled, QPushButton:disabled { color: #afafaf; }
            QToolButton:checked, QPushButton:checked { color: #ffffff; }
            QToolButton::menu-indicator { image: none; width: 0px; }

            QToolButton#Primary, QPushButton#Primary { padding: 7px 18px; }
            QToolButton#ToolButton { padding: 7px 8px; }

            /* QComboBox is deliberately absent: any rule here would hand the
               widget to Qt's stylesheet engine and lose the hand-drawn box. */
            QSpinBox, QLineEdit {
                color: #000000;
                padding: 6px 14px;
                min-height: 20px;
                selection-background-color: #000000;
                selection-color: #ffffff;
            }
            QLineEdit::placeholder { color: #a0a0a0; }
            QSpinBox::up-button, QSpinBox::down-button { border: none; background: transparent; width: 0px; }

            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #000000;
                border: 2px solid #000000;
                padding: 4px;
                outline: 0;
            }

            /* SketchMenu paints the panel and the selection box itself, so
               item backgrounds stay transparent and text stays ink-coloured
               even when the row is active. */
            QMenu { background: transparent; border: none; padding: 7px; }
            QMenu::item {
                background: transparent;
                color: #000000;
                padding: 8px 30px 8px 16px;
                margin: 1px 2px;
            }
            QMenu::item:selected { background: transparent; color: #000000; }
            QMenu::item:disabled { color: #b4b4b4; }
            QMenu::separator { height: 1px; background: #c8c8c8; margin: 6px 12px; }

            QTabWidget#SidebarTabs { background: #ffffff; }
            QTabWidget::pane { background: #ffffff; border: none; }
            QTabBar::tab {
                background: transparent;
                color: #787878;
                border: none;
                padding: 8px 7px;
                margin-right: 2px;
            }
            QTabBar::tab:selected { color: #000000; }
            QTabBar::tab:hover:!selected { color: #303030; }

            QListWidget { background: #ffffff; color: #000000; border: none; outline: 0; }
            /* Spacing only — the selection box itself is drawn by SketchStyle. */
            QListWidget::item { padding: 7px 8px; margin: 3px 6px; }

            QTextEdit {
                background: #ffffff;
                color: #000000;
                border: 2px solid #000000;
                padding: 7px;
                selection-background-color: #000000;
                selection-color: #ffffff;
            }

            QGroupBox {
                background: transparent;
                border: none;
                margin-top: 15px;
                padding: 10px 8px 8px 8px;
                color: #000000;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #000000;
                font-size: 13px;
            }

            QLabel#PanelTitle {
                font-size: 20px;
                font-weight: 400;
                color: #000000;
                padding: 2px 2px 4px 2px;
            }
            QLabel#ToolHint { color: #787878; font-size: 13px; padding: 0 3px 6px 3px; }
            QLabel#BrandText { color: #000000; font-size: 19px; padding: 0 6px 0 0; }
            QLabel#SmallNote { color: #787878; font-size: 13px; }

            QWidget#PropertiesPanel { background: #ffffff; }

            QSplitter::handle { background: #ffffff; }
            QSplitter::handle:horizontal { width: 2px; background: #000000; }

            QScrollArea { background: #ffffff; border: none; }
            QScrollBar:vertical, QScrollBar:horizontal {
                background: transparent; border: none; margin: 2px;
                width: 12px; height: 12px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                background: #000000; border-radius: 6px; min-height: 34px; min-width: 34px;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #4a4a4a; }
            QScrollBar::add-line, QScrollBar::sub-line,
            QScrollBar::add-page, QScrollBar::sub-page {
                width: 0px; height: 0px; background: none;
            }

            QStatusBar { background: #ffffff; color: #787878; border: none; font-size: 13px; }
            QStatusBar::item { border: none; }

            QProgressBar {
                background: #ffffff; color: #000000;
                border: 2px solid #000000; text-align: center;
                font-size: 12px; min-height: 16px;
            }
            QProgressBar::chunk { background: #000000; }

            QDialog { background: #ffffff; color: #000000; }
            QDialogButtonBox QPushButton { min-width: 88px; padding: 8px 18px; }

            QCheckBox { color: #000000; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; background: transparent; border: none; }

            QFormLayout QLabel { color: #000000; font-size: 13px; }

            QMessageBox { background: #ffffff; color: #000000; }
            QMessageBox QPushButton { min-width: 80px; }

            QToolTip {
                background: #ffffff; color: #000000;
                border: 2px solid #000000; padding: 6px 9px;
            }
        """)

    def _set_document_controls(self, enabled: bool):
        widgets = [
            self.save_action,
            self.undo_action,
            self.redo_action,
            self.zoom_out_action,
            self.zoom_in_action,
            self.file_menu_button,
            self.edit_menu_button,
            self.insert_menu_button,
            self.pages_menu_button,
            self.export_menu_button,
            self.zoom_combo,
            self.search_input,
            self.search_button,
            self.next_search_button,
            self.font_size_spin,
            self.line_width_spin,
            self.opacity_spin,
            self.text_color_button,
            self.stroke_color_button,
            self.fill_color_button,
        ]
        widgets.append(self.xray_button)
        widgets.extend(self.tool_buttons.values())
        for widget in widgets:
            widget.setEnabled(enabled)

        self.open_action.setEnabled(True)
        self._refresh_history_actions()

    def open_pdf(self):
        if self.is_dirty and not self._confirm_discard():
            return

        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if not path:
            return
        self.load_pdf(path)

    def load_pdf(self, path: str):
        """Open a PDF from a known path (file dialog, drag-and-drop, CLI)."""
        try:
            doc = fitz.open(path)
            opened_password = ""

            if doc.needs_pass:
                dialog = PasswordDialog(self)
                if dialog.exec() != QDialog.DialogCode.Accepted:
                    doc.close()
                    return
                opened_password = dialog.value()
                if not doc.authenticate(opened_password):
                    doc.close()
                    QMessageBox.warning(self, "Wrong Password", "The password was not accepted.")
                    return

            if doc.page_count == 0:
                raise ValueError("The selected PDF has no pages.")

            if self.doc:
                self.doc.close()

            self.doc = doc
            self.file_path = path
            self._pdf_password = opened_password
            self.current_page_index = 0
            self.zoom = 1.25
            self.is_dirty = False
            self.undo_stack.clear()
            self.redo_stack.clear()
            self.search_results.clear()
            self.search_results_list.clear()
            self._doc_version = 0
            if not hasattr(self, "_render_cache"):
                self._render_cache = {}
            if not hasattr(self, "_render_cache_order"):
                self._render_cache_order = []
            self._render_cache.clear()
            self._render_cache_order.clear()

            self._set_document_controls(True)
            self.refresh_sidebars()
            self.render_current_page()
            self._update_window_title()
            self.status.showMessage(f"Opened {path}")

        except Exception as exc:
            QMessageBox.critical(self, "Open Error", f"Could not open PDF:\n{exc}")

    def save_as_pdf(self):
        if self.doc is None:
            return

        default = "edited.pdf"
        if self.file_path:
            src = Path(self.file_path)
            default = str(src.with_name(f"{src.stem}_edited.pdf"))

        out, _ = QFileDialog.getSaveFileName(self, "Save Optimized PDF As", default, "PDF Files (*.pdf)")
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        try:
            if self.file_path and os.path.abspath(out) == os.path.abspath(self.file_path):
                QMessageBox.warning(self, "Use Different Name", "Choose a different output file name.")
                return
            self.doc.save(out, garbage=4, deflate=True, clean=True)
            self.file_path = out
            self.is_dirty = False
            self._update_window_title()
            self.status.showMessage(f"Saved {out}")
            QMessageBox.information(self, "Saved", f"PDF saved:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Save Error", f"Could not save PDF:\n{exc}")

    def save_encrypted_copy(self):
        if self.doc is None:
            return

        user_pw, ok = QInputDialog.getText(self, "User Password", "Password required to open PDF:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        owner_pw, ok = QInputDialog.getText(self, "Owner Password", "Owner password for permissions:", QLineEdit.EchoMode.Password)
        if not ok:
            return

        out, _ = QFileDialog.getSaveFileName(self, "Save Encrypted PDF", "encrypted.pdf", "PDF Files (*.pdf)")
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        try:
            self.doc.save(
                out,
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=user_pw,
                owner_pw=owner_pw or user_pw,
                garbage=4,
                deflate=True,
            )
            QMessageBox.information(self, "Saved", f"Encrypted PDF saved:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Encryption Error", f"Could not save encrypted copy:\n{exc}")

    def _document_worker_source(self) -> Optional[Dict[str, object]]:
        """Create a thread-safe document source for background workers.

        A PyMuPDF Document must not be shared across threads. Workers either reopen the
        original file path or open a byte snapshot when the document has unsaved edits.
        """
        if self.doc is None:
            return None
        if self.file_path and not self.is_dirty:
            return {"type": "path", "path": self.file_path, "password": self._pdf_password}
        try:
            return {"type": "bytes", "data": self.doc.tobytes(garbage=1, deflate=True), "password": self._pdf_password}
        except Exception as exc:
            QMessageBox.critical(self, "Worker Error", f"Could not prepare PDF for background task:\n{exc}")
            return None

    def _start_worker(self, worker: QObject):
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        thread.finished.connect(thread.deleteLater)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        self._workers.append((thread, worker))

        def cleanup():
            self._workers[:] = [(t, w) for t, w in self._workers if t is not thread]
            if not self._workers:
                self.progress_bar.setVisible(False)

        thread.finished.connect(cleanup)
        thread.start()

    def _worker_progress(self, job_id: int, done: int, total: int, label: str):
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(done)
        self.status.showMessage(f"{label}: {done}/{total}")

    def _worker_finished(self, job_id: int, message: str):
        self.status.showMessage(message)

    def _apply_thumbnail_from_worker(self, job_id: int, page_index: int, image_bytes: bytes):
        if job_id != self._thumbnail_job_id or self.doc is None:
            return
        if page_index < 0 or page_index >= self.page_list.count():
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(image_bytes):
            self.page_list.item(page_index).setIcon(QIcon(pixmap))

    def _search_finished_from_worker(self, job_id: int, query: str, raw_results: object):
        if job_id != self._search_job_id or self.doc is None:
            return

        self.search_results.clear()
        self.search_results_list.clear()
        for page_index, x0, y0, x1, y1 in raw_results:
            self.search_results.append((int(page_index), fitz.Rect(x0, y0, x1, y1)))
            item = QListWidgetItem(f"Page {int(page_index) + 1}: {query}")
            item.setData(Qt.ItemDataRole.UserRole, len(self.search_results) - 1)
            self.search_results_list.addItem(item)

        if not self.search_results:
            self.render_current_page()
            QMessageBox.information(self, "Search", "No matches found.")
            return

        self.go_to_search_result(0)
        self.status.showMessage(f"Found {len(self.search_results)} result(s) for '{query}'")

    def _image_export_finished_from_worker(self, job_id: int, folder: str, count: int):
        if job_id != self._export_job_id:
            return
        QMessageBox.information(self, "Exported", f"Exported {count} page image(s) to:\n{folder}")

    def _compute_xray(self, page) -> Dict[str, List[QRectF]]:
        """Classify page content into text / image / vector regions.

        Cached per (document version, page, zoom) because get_drawings() is
        expensive on vector-heavy pages.
        """
        key = (self._doc_version, self.current_page_index, int(self.zoom * 1000))
        cached = self._xray_cache.get(key)
        if cached is not None:
            return cached

        text_rects: List[QRectF] = []
        image_rects: List[QRectF] = []
        vector_rects: List[QRectF] = []

        try:
            info = page.get_text("dict")
            for block in info.get("blocks", []):
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if span.get("text", "").strip():
                                text_rects.append(self._pdf_rect_to_image_rect(fitz.Rect(span["bbox"])))
                elif block.get("bbox"):
                    image_rects.append(self._pdf_rect_to_image_rect(fitz.Rect(block["bbox"])))
        except Exception:
            pass

        try:
            for drawing in page.get_drawings():
                rect = drawing.get("rect")
                if rect is None or (rect.width < 2 and rect.height < 2):
                    continue
                if rect.width >= page.rect.width * 0.98 and rect.height >= page.rect.height * 0.98:
                    continue
                vector_rects.append(self._pdf_rect_to_image_rect(rect))
        except Exception:
            pass

        result = {"text": text_rects, "image": image_rects, "vector": vector_rects}
        self._xray_cache[key] = result
        if len(self._xray_cache) > 8:
            self._xray_cache.pop(next(iter(self._xray_cache)))
        return result

    def toggle_xray(self, enabled: bool):
        self.xray_enabled = bool(enabled)
        self.canvas.set_xray_enabled(self.xray_enabled)
        if self.doc is not None:
            self.render_current_page()
        if self.xray_enabled:
            self.status.showMessage("X-ray on — showing what this page actually contains")
        else:
            self.status.showMessage("X-ray off")

    def render_current_page(self):
        if self.doc is None:
            return

        try:
            page = self.doc[self.current_page_index]
            cache_key = (self._doc_version, self.current_page_index, int(self.zoom * 1000))
            qpix = self._render_cache.get(cache_key)
            if qpix is None:
                pix = page.get_pixmap(matrix=fitz.Matrix(self.zoom, self.zoom), alpha=False)
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
                qpix = QPixmap.fromImage(image)
                self._render_cache[cache_key] = qpix
                self._render_cache_order.append(cache_key)
                while len(self._render_cache_order) > 8:
                    old_key = self._render_cache_order.pop(0)
                    self._render_cache.pop(old_key, None)

            search_rects = [
                QRectF(r.x0 * self.zoom, r.y0 * self.zoom, r.width * self.zoom, r.height * self.zoom)
                for p, r in self.search_results
                if p == self.current_page_index
            ]

            edit_rects: List[QRectF] = []
            if self.current_tool in {Tool.EDIT_TEXT, Tool.MOVE_TEXT}:
                for span in self._iter_text_spans(page):
                    edit_rects.append(self._pdf_rect_to_image_rect(span.bbox))
            elif self.current_tool == Tool.EDIT_BLOCK:
                for block in self._iter_text_blocks(page):
                    edit_rects.append(self._pdf_rect_to_image_rect(block.bbox))

            crop_preview = None
            if page.cropbox != page.mediabox:
                crop_preview = self._pdf_rect_to_image_rect(page.cropbox)

            xray = self._compute_xray(page) if self.xray_enabled else None

            self.canvas.set_style(self.annotation_color, self.fill_color, self.text_color, self.line_width)
            self.canvas.set_page(qpix, self.zoom, search_rects, edit_rects, crop_preview, xray)

            self.page_list.blockSignals(True)
            self.page_list.setCurrentRow(self.current_page_index)
            self.page_list.blockSignals(False)

            self._update_zoom_combo_text()
            self.status.showMessage(
                f"Page {self.current_page_index + 1}/{self.doc.page_count} | "
                f"Zoom {int(self.zoom * 100)}% | Tool: {self.current_tool}"
            )
        except Exception as exc:
            QMessageBox.critical(self, "Render Error", f"Could not render page:\n{exc}")

    def refresh_sidebars(self):
        self.refresh_page_thumbnails()
        self.refresh_outline()
        self.refresh_comments()

    def _refresh_light_sidebars(self):
        """Refresh cheap sidebars only. Do not restart the thumbnail worker."""
        self.refresh_outline()
        self.refresh_comments()

    def _update_current_thumbnail_inline(self):
        """Refresh only the visible current-page thumbnail after an annotation/edit."""
        if self.doc is None or self.current_page_index < 0 or self.current_page_index >= self.page_list.count():
            return
        try:
            page = self.doc[self.current_page_index]
            pix = page.get_pixmap(matrix=fitz.Matrix(0.17, 0.17), alpha=False)
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
            self.page_list.item(self.current_page_index).setIcon(QIcon(QPixmap.fromImage(image)))
        except Exception:
            pass

    def _mark_page_structure_changed(self):
        self._page_structure_changed = True

    def refresh_page_thumbnails(self):
        """Load thumbnails in a worker thread so large PDFs do not freeze the UI."""
        if self.doc is None:
            return

        self._thumbnail_job_id += 1
        job_id = self._thumbnail_job_id

        self.page_list.blockSignals(True)
        self.page_list.clear()
        for i in range(self.doc.page_count):
            item = QListWidgetItem(f"Page {i + 1}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            self.page_list.addItem(item)
        self.page_list.setCurrentRow(self.current_page_index)
        self.page_list.blockSignals(False)

        source = self._document_worker_source()
        if not source:
            return

        worker = ThumbnailWorker(job_id, source, thumb_zoom=0.17)
        worker.thumbnail_ready.connect(self._apply_thumbnail_from_worker)
        worker.progress.connect(lambda jid, done, total: self._worker_progress(jid, done, total, "Loading thumbnails"))
        worker.error.connect(lambda jid, msg: self.status.showMessage(f"Thumbnail loading failed: {msg}"))
        worker.finished.connect(lambda jid: self._worker_finished(jid, "Thumbnails loaded"))
        self._start_worker(worker)

    def refresh_outline(self):
        self.outline_list.clear()
        if self.doc is None:
            return
        try:
            toc = self.doc.get_toc()
            if not toc:
                self.outline_list.addItem("No outline/bookmarks found.")
                return
            for level, title, page_num in toc:
                item = QListWidgetItem(("  " * max(level - 1, 0)) + title)
                item.setData(Qt.ItemDataRole.UserRole, max(page_num - 1, 0))
                self.outline_list.addItem(item)
        except Exception:
            self.outline_list.addItem("Could not read outline.")

    def refresh_comments(self):
        self.comments_list.clear()
        if self.doc is None:
            return

        found = 0
        for page_index in range(self.doc.page_count):
            page = self.doc[page_index]
            annot = page.first_annot
            while annot:
                found += 1
                text = f"Page {page_index + 1}: {annot.type[1]}"
                info = annot.info or {}
                content = info.get("content") or info.get("title") or ""
                if content:
                    text += f" — {content[:60]}"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, page_index)
                self.comments_list.addItem(item)
                annot = annot.next
        if found == 0:
            self.comments_list.addItem("No comments or annotations found.")

    def on_page_selected(self, row: int):
        if self.doc is None or row < 0 or row >= self.doc.page_count:
            return
        self.current_page_index = row
        self.render_current_page()

    def go_to_outline_item(self, item: QListWidgetItem):
        if self.doc is None:
            return
        page_index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(page_index, int):
            self.current_page_index = clamp(page_index, 0, self.doc.page_count - 1)
            self.render_current_page()

    def go_to_comment_item(self, item: QListWidgetItem):
        if self.doc is None:
            return
        page_index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(page_index, int):
            self.current_page_index = page_index
            self.render_current_page()

    def set_tool(self, tool: str):
        self.current_tool = tool
        self.canvas.set_tool(tool)
        for name, button in self.tool_buttons.items():
            button.blockSignals(True)
            button.setChecked(name == tool)
            button.blockSignals(False)
        self._update_contextual_panel()
        self.render_current_page()
        self.status.showMessage(f"{tool} selected")

    def choose_color(self, target: str):
        current = self.text_color if target == "text" else self.annotation_color if target == "stroke" else self.fill_color
        color = QColorDialog.getColor(current, self, f"Choose {target.title()} Color")
        if not color.isValid():
            return
        if target == "text":
            self.text_color = color
        elif target == "stroke":
            self.annotation_color = color
        else:
            self.fill_color = color
        self._refresh_color_buttons()

    @staticmethod
    def _swatch_style(color: QColor) -> str:
        """Swatch button style with a readable, contrast-aware label color."""
        luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        fg = "#1f2733" if luminance > 150 else "#ffffff"
        return (
            f"background:{color.name()}; color:{fg};"
            "border:2px solid #000000; padding:6px 12px; font-weight:400;"
        )

    def _refresh_color_buttons(self):
        self.text_color_button.setStyleSheet(self._swatch_style(self.text_color))
        self.stroke_color_button.setStyleSheet(self._swatch_style(self.annotation_color))
        self.fill_color_button.setStyleSheet(self._swatch_style(self.fill_color))

    def handle_canvas_action(self, tool: str, payload):
        if tool == "__open_pdf__":
            self.open_pdf()
            return True
        if self.doc is None:
            return False

        try:
            if tool == "__zoom_delta__":
                self.zoom_by_wheel(int(payload))
                return True
            if tool == "__pan__":
                self.pan_view(payload)
                return True
            if tool == "__fit_width__":
                self.fit_width()
                return True
            if tool == "__move_text_start__":
                return self.begin_move_text(payload)
            if tool == "__move_text_end__":
                self.end_move_text(payload)
                return True

            if tool == Tool.TEXT_BOX:
                self.add_text_box(payload)
            elif tool == Tool.EDIT_TEXT:
                self.edit_existing_text_span(payload)
            elif tool == Tool.EDIT_BLOCK:
                self.edit_existing_text_block(payload)
            elif tool == Tool.NOTE:
                self.add_note(payload)
            elif tool == Tool.HIGHLIGHT:
                self.add_markup_annotation(payload, "highlight")
            elif tool == Tool.UNDERLINE:
                self.add_markup_annotation(payload, "underline")
            elif tool == Tool.STRIKEOUT:
                self.add_markup_annotation(payload, "strikeout")
            elif tool == Tool.RECTANGLE:
                self.add_rectangle(payload)
            elif tool == Tool.LINE:
                self.add_line(payload)
            elif tool == Tool.INK:
                self.add_ink(payload)
            elif tool == Tool.REDACT:
                self.apply_redaction(payload)
            elif tool == Tool.CROP:
                self.crop_page(payload)
            elif tool == Tool.LINK:
                self.add_url_link(payload)
            elif tool == Tool.IMAGE:
                self.insert_image_at(payload)
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Tool Error", f"{tool} failed:\n{exc}")
            return False

    def zoom_by_wheel(self, delta: int):
        if self.doc is None:
            return
        factor = 1.10 if delta > 0 else 1 / 1.10
        self.zoom = clamp(self.zoom * factor, 0.25, 5.0)
        self.render_current_page()

    def pan_view(self, delta: QPointF):
        self.scroll.horizontalScrollBar().setValue(self.scroll.horizontalScrollBar().value() - int(delta.x()))
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().value() - int(delta.y()))

    def begin_move_text(self, image_point: QPointF) -> bool:
        page = self.doc[self.current_page_index]
        pdf_point = fitz.Point(image_point.x() / self.zoom, image_point.y() / self.zoom)
        hit = self._find_span_at_point(page, pdf_point)
        if not hit:
            self._moving_text_hit = None
            self.status.showMessage("Move Text: click directly on selectable text.")
            return False
        self._moving_text_hit = hit
        self.status.showMessage(f"Move Text: dragging '{hit.text[:40]}'")
        return True

    def end_move_text(self, image_points: Tuple[QPointF, QPointF]):
        if not self._moving_text_hit:
            return
        start, end = image_points
        dx = (end.x() - start.x()) / self.zoom
        dy = (end.y() - start.y()) / self.zoom
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            self._moving_text_hit = None
            return

        page = self.doc[self.current_page_index]
        hit = self._moving_text_hit
        self._moving_text_hit = None
        old_rect = hit.bbox + (-1, -1, 1, 1)
        new_rect = fitz.Rect(hit.bbox.x0 + dx, hit.bbox.y0 + dy, hit.bbox.x1 + dx, hit.bbox.y1 + dy) + (-1, -1, 8, 4)

        self._push_undo()
        page.add_redact_annot(old_rect, fill=(1, 1, 1))
        page.apply_redactions()
        self._safe_insert_textbox(page, new_rect, hit.text, max(6, hit.size), hit.color, align=0)
        self._mark_dirty("Text moved")

    def edit_existing_text_span(self, image_point: QPointF):
        page = self.doc[self.current_page_index]
        pdf_point = fitz.Point(image_point.x() / self.zoom, image_point.y() / self.zoom)

        hit = self._find_span_at_point(page, pdf_point)
        if not hit:
            QMessageBox.information(self, "No Text Found", "No editable text span found at this point.")
            return

        dialog = TextBoxDialog(self, "Replace Text Span", hit.text)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        replacement = dialog.text()
        if replacement == hit.text:
            return

        self._push_undo()
        font_size = max(6, hit.size)
        erase_rect = hit.bbox + (-1, -1, 1, 1)
        draw_rect = self._expanded_text_rect(page, erase_rect, replacement, font_size)
        self._replace_rect_with_text(
            page=page,
            rect=erase_rect,
            text=replacement,
            fontsize=font_size,
            color=hit.color if hit.color.isValid() else self.text_color,
            fill=(1, 1, 1),
            align=0,
            draw_rect=draw_rect,
        )
        self._mark_dirty("Text span replaced")

    def edit_existing_text_block(self, image_point: QPointF):
        page = self.doc[self.current_page_index]
        pdf_point = fitz.Point(image_point.x() / self.zoom, image_point.y() / self.zoom)

        hit = self._find_block_at_point(page, pdf_point)
        if not hit:
            QMessageBox.information(self, "No Text Block Found", "No editable text block found at this point.")
            return

        dialog = TextBoxDialog(self, "Replace Text Block", hit.text)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        replacement = dialog.text()
        if replacement == hit.text:
            return

        self._push_undo()
        font_size = self.font_size_spin.value()
        erase_rect = hit.bbox + (-2, -2, 2, 2)
        draw_rect = self._expanded_text_rect(page, erase_rect, replacement, font_size)
        self._replace_rect_with_text(
            page=page,
            rect=erase_rect,
            text=replacement,
            fontsize=font_size,
            color=self.text_color,
            fill=(1, 1, 1),
            align=0,
            draw_rect=draw_rect,
        )
        self._mark_dirty("Text block replaced")

    def search_and_replace(self):
        if self.doc is None:
            return

        dialog = SearchReplaceDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        find_text, replace_text, scope, case_sensitive = dialog.values()
        if not find_text:
            return

        pages = [self.current_page_index] if scope == "Current Page" else list(range(self.doc.page_count))
        total = 0

        self._push_undo()
        for page_index in pages:
            page = self.doc[page_index]
            rects = page.search_for(find_text)
            if case_sensitive and rects:
                exact = []
                for rect in rects:
                    try:
                        found = page.get_textbox(rect)
                    except Exception:
                        found = ""
                    if find_text in found:
                        exact.append(rect)
                rects = exact
            if not rects:
                continue

            for rect in rects:
                page.add_redact_annot(rect + (-1, -1, 1, 1), fill=(1, 1, 1))
            page.apply_redactions()

            for rect in rects:
                size = clamp(rect.height * 0.72, 6, 24)
                draw_rect = self._expanded_text_rect(page, rect + (0, -1, max(80, rect.width * 2), 5), replace_text, size)
                self._safe_insert_textbox(page, draw_rect, replace_text, size, self.text_color, align=0)
                total += 1

        if total == 0:
            self.undo_stack.pop() if self.undo_stack else None
            QMessageBox.information(self, "Search and Replace", "No matches found.")
            self._refresh_history_actions()
            return

        self._mark_dirty(f"Replaced {total} text match(es)", refresh_sidebars=True)

    def reflow_current_page_to_new_page(self):
        if self.doc is None:
            return

        page = self.doc[self.current_page_index]
        text = page.get_text("text", sort=True).strip()
        if not text:
            QMessageBox.information(self, "Reflow", "No selectable text found on this page.")
            return

        self._push_undo()
        self._insert_reflowed_text_pages(
            text=text,
            start_at=self.current_page_index + 1,
            page_size=(page.rect.width, page.rect.height),
            title=f"Reflowed copy of page {self.current_page_index + 1}",
        )
        self.current_page_index += 1
        self._mark_dirty("Reflowed page inserted after current page", refresh_sidebars=True)

    def reflow_document_to_new_pdf(self):
        if self.doc is None:
            return

        out, _ = QFileDialog.getSaveFileName(self, "Save Reflowed Text PDF", "reflowed_document.pdf", "PDF Files (*.pdf)")
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        try:
            new_doc = fitz.open()
            for i, page in enumerate(self.doc):
                text = page.get_text("text", sort=True).strip()
                if not text:
                    text = f"[Page {i + 1}: no selectable text found]"
                self._insert_reflowed_text_pages_into_doc(
                    doc=new_doc,
                    text=text,
                    page_size=(page.rect.width, page.rect.height),
                    title=f"Page {i + 1}",
                )
            new_doc.save(out, garbage=4, deflate=True)
            new_doc.close()
            QMessageBox.information(self, "Reflow Complete", f"Reflowed PDF saved:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Reflow Error", f"Could not create reflowed PDF:\n{exc}")

    def _replace_rect_with_text(
        self,
        page,
        rect: fitz.Rect,
        text: str,
        fontsize: float,
        color: QColor,
        fill: Tuple[float, float, float] = (1, 1, 1),
        align: int = 0,
        draw_rect: Optional[fitz.Rect] = None,
    ):
        """Erase old visible PDF text and redraw replacement text safely.

        The erase rectangle and draw rectangle are intentionally separate. Text
        spans in PDFs are often too small for replacement text; using the same
        rectangle can make PyMuPDF draw nothing.
        """
        erase_rect = fitz.Rect(rect)
        page.add_redact_annot(erase_rect, fill=fill)
        page.apply_redactions()

        if not text or not str(text).strip():
            return

        final_draw_rect = draw_rect or self._expanded_text_rect(page, erase_rect, text, fontsize)
        self._safe_insert_textbox(page, final_draw_rect, text, fontsize, color, align=align)

    def _expanded_text_rect(self, page, rect: fitz.Rect, text: str, fontsize: float) -> fitz.Rect:
        """Return a draw box large enough that replacement text does not vanish.

        PyMuPDF's insert_textbox returns a negative value when the text does not
        fit. This method estimates a safe width/height before drawing.
        """
        font_size = float(clamp(fontsize, 6, 72))
        source = str(text or "")
        lines = source.splitlines() or [source]
        non_empty = [line if line else " " for line in lines]

        try:
            max_line_width = max(fitz.get_text_length(line, fontname="helv", fontsize=font_size) for line in non_empty)
        except Exception:
            max_line_width = max(len(line) for line in non_empty) * font_size * 0.56

        needed_w = max(rect.width, max_line_width + font_size * 0.8 + 6)
        needed_h = max(rect.height, len(non_empty) * font_size * 1.45 + 6)

        page_rect = page.rect
        x0 = clamp(rect.x0, page_rect.x0, page_rect.x1 - 8)
        y0 = clamp(rect.y0 - font_size * 0.15, page_rect.y0, page_rect.y1 - 8)
        x1 = min(max(rect.x1, x0 + needed_w), page_rect.x1 - 2)
        y1 = min(max(rect.y1 + font_size * 0.45, y0 + needed_h), page_rect.y1 - 2)

        if x1 - x0 < min(needed_w, page_rect.width - 4):
            x0 = max(page_rect.x0 + 2, x1 - min(needed_w, page_rect.width - 4))

        return fitz.Rect(x0, y0, x1, y1)

    def _safe_insert_textbox(self, page, rect: fitz.Rect, text: str, fontsize: float, color: QColor, align: int = 0):
        """Insert text safely and never treat negative insert_textbox return as success.

        insert_textbox does not always raise an exception. When text does not
        fit, it returns a negative number and draws nothing. That was the cause
        of the disappearing text bug.
        """
        if not text or not str(text).strip():
            return 0

        font_size = float(clamp(fontsize, 6, 72))
        rgb = rgb_from_qcolor(color if color and color.isValid() else QColor(17, 24, 39))
        text_value = str(text)
        draw_rect = self._expanded_text_rect(page, fitz.Rect(rect), text_value, font_size)
        last_error = None

        for candidate_rect in (draw_rect, fitz.Rect(rect)):
            for fontname in ("helv", "Helvetica", None):
                try:
                    kwargs = dict(
                        fontsize=font_size,
                        color=rgb,
                        align=align,
                        overlay=True,
                    )
                    if fontname:
                        kwargs["fontname"] = fontname
                    rc = page.insert_textbox(candidate_rect, text_value, **kwargs)
                    if rc is None or rc >= 0:
                        return rc
                    last_error = RuntimeError(f"insert_textbox returned {rc}; text did not fit")
                except Exception as exc:
                    last_error = exc

        try:
            x = draw_rect.x0
            y = draw_rect.y0 + font_size
            line_gap = font_size * 1.25
            for raw_line in text_value.splitlines() or [text_value]:
                line = raw_line if raw_line else " "
                if y > page.rect.y1 - 2:
                    break
                inserted = False
                for fontname in ("helv", "Helvetica", None):
                    try:
                        kwargs = dict(fontsize=font_size, color=rgb, overlay=True)
                        if fontname:
                            kwargs["fontname"] = fontname
                        page.insert_text(fitz.Point(x, y), line, **kwargs)
                        inserted = True
                        break
                    except Exception as exc:
                        last_error = exc
                if not inserted:
                    raise last_error or RuntimeError("insert_text fallback failed")
                y += line_gap
            return 0
        except Exception as exc:
            raise RuntimeError(f"Could not draw text. First error: {last_error}; fallback error: {exc}")

    def _iter_text_spans(self, page) -> Iterable[TextSpanHit]:
        info = page.get_text("dict")
        for block in info.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text.strip():
                        continue
                    yield TextSpanHit(
                        text=text,
                        bbox=fitz.Rect(span["bbox"]),
                        size=float(span.get("size", 11)),
                        color=qcolor_from_pdf_int(int(span.get("color", 0))),
                        font=span.get("font", "helv"),
                    )

    def _iter_text_blocks(self, page) -> Iterable[TextBlockHit]:
        blocks = page.get_text("blocks", sort=True)
        for block in blocks:
            if len(block) < 5:
                continue
            x0, y0, x1, y1, text = block[:5]
            if str(text).strip():
                yield TextBlockHit(text=str(text).strip(), bbox=fitz.Rect(x0, y0, x1, y1))

    def _find_span_at_point(self, page, point: fitz.Point) -> Optional[TextSpanHit]:
        candidates = [span for span in self._iter_text_spans(page) if span.bbox.contains(point)]
        if not candidates:
            tolerance = fitz.Rect(point.x - 3, point.y - 3, point.x + 3, point.y + 3)
            candidates = [span for span in self._iter_text_spans(page) if span.bbox.intersects(tolerance)]
        if not candidates:
            return None
        return min(candidates, key=lambda s: s.bbox.get_area())

    def _find_block_at_point(self, page, point: fitz.Point) -> Optional[TextBlockHit]:
        candidates = [block for block in self._iter_text_blocks(page) if block.bbox.contains(point)]
        if not candidates:
            tolerance = fitz.Rect(point.x - 4, point.y - 4, point.x + 4, point.y + 4)
            candidates = [block for block in self._iter_text_blocks(page) if block.bbox.intersects(tolerance)]
        if not candidates:
            return None
        return min(candidates, key=lambda b: b.bbox.get_area())

    def _insert_reflowed_text_pages(
        self,
        text: str,
        start_at: int,
        page_size: Tuple[float, float],
        title: str,
    ):
        width, height = page_size
        chunks = self._paginate_text_for_reflow(text, width, height)
        for offset, chunk in enumerate(chunks):
            page = self.doc.new_page(pno=start_at + offset, width=width, height=height)
            self._draw_reflow_page(page, chunk, title if offset == 0 else f"{title} continued")

    def _insert_reflowed_text_pages_into_doc(
        self,
        doc,
        text: str,
        page_size: Tuple[float, float],
        title: str,
    ):
        width, height = page_size
        chunks = self._paginate_text_for_reflow(text, width, height)
        for offset, chunk in enumerate(chunks):
            page = doc.new_page(width=width, height=height)
            self._draw_reflow_page(page, chunk, title if offset == 0 else f"{title} continued")

    def _paginate_text_for_reflow(self, text: str, width: float, height: float) -> List[str]:
        margin = 54
        usable_width = max(width - margin * 2, 250)
        chars_per_line = max(50, int(usable_width / 5.4))
        lines_per_page = max(28, int((height - margin * 2 - 34) / 15))

        lines: List[str] = []
        for para in text.splitlines():
            para = para.strip()
            if not para:
                lines.append("")
                continue
            lines.extend(textwrap.wrap(para, width=chars_per_line) or [""])

        chunks = []
        for i in range(0, len(lines), lines_per_page):
            chunks.append("\n".join(lines[i:i + lines_per_page]))
        return chunks or [""]

    def _draw_reflow_page(self, page, text: str, title: str):
        rect = page.rect
        margin = 54
        page.insert_text(
            fitz.Point(margin, margin - 18),
            title,
            fontsize=13,
            fontname="helv",
            color=(0.10, 0.20, 0.45),
        )
        page.draw_line(
            fitz.Point(margin, margin - 8),
            fitz.Point(rect.width - margin, margin - 8),
            color=(0.70, 0.75, 0.82),
            width=0.8,
        )
        page.insert_textbox(
            fitz.Rect(margin, margin + 8, rect.width - margin, rect.height - margin),
            text,
            fontsize=11,
            fontname="helv",
            color=(0.05, 0.05, 0.05),
            align=0,
        )

    def add_text_box(self, image_rect: QRectF):
        dialog = TextBoxDialog(self, "Add Text Box")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        text = dialog.text().strip()
        if not text:
            return

        self._push_undo()
        page = self.doc[self.current_page_index]
        rect = self._image_rect_to_pdf_rect(image_rect)
        page.insert_textbox(
            rect,
            text,
            fontsize=self.font_size_spin.value(),
            fontname="helv",
            color=rgb_from_qcolor(self.text_color),
            align=0,
            overlay=True,
        )
        page.draw_rect(rect, color=rgb_from_qcolor(self.annotation_color), width=0.6, overlay=True)
        self._mark_dirty("Text box added", refresh_sidebars=True)

    def add_note(self, image_point: QPointF):
        text, ok = QInputDialog.getMultiLineText(self, "Sticky Note", "Note:")
        if not ok or not text.strip():
            return

        self._push_undo()
        page = self.doc[self.current_page_index]
        x, y = self._image_point_to_pdf_xy(image_point)
        annot = page.add_text_annot(fitz.Point(x, y), text.strip())
        annot.set_info(title="PDF Studio Note", content=text.strip())
        annot.update()
        self._mark_dirty("Sticky note added", refresh_sidebars=True)

    def add_markup_annotation(self, image_rect: QRectF, kind: str):
        self._push_undo()
        page = self.doc[self.current_page_index]
        rect = self._image_rect_to_pdf_rect(image_rect)

        if kind == "highlight":
            annot = page.add_highlight_annot(rect)
            annot.set_colors(stroke=rgb_from_qcolor(QColor("#b4b4b4")))
        elif kind == "underline":
            annot = page.add_underline_annot(rect)
            annot.set_colors(stroke=rgb_from_qcolor(self.annotation_color))
        else:
            annot = page.add_strikeout_annot(rect)
            annot.set_colors(stroke=rgb_from_qcolor(self.annotation_color))
        annot.update()
        self._mark_dirty(f"{kind.title()} added", refresh_sidebars=True)

    def add_rectangle(self, image_rect: QRectF):
        self._push_undo()
        page = self.doc[self.current_page_index]
        rect = self._image_rect_to_pdf_rect(image_rect)
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=rgb_from_qcolor(self.annotation_color), fill=rgb_from_qcolor(self.fill_color))
        annot.set_border(width=self.line_width)
        annot.set_opacity(self.opacity_percent / 100)
        annot.update()
        self._mark_dirty("Rectangle added", refresh_sidebars=True)

    def add_line(self, image_points: Tuple[QPointF, QPointF]):
        self._push_undo()
        page = self.doc[self.current_page_index]
        p1, p2 = image_points
        annot = page.add_line_annot(
            fitz.Point(p1.x() / self.zoom, p1.y() / self.zoom),
            fitz.Point(p2.x() / self.zoom, p2.y() / self.zoom),
        )
        annot.set_colors(stroke=rgb_from_qcolor(self.annotation_color))
        annot.set_border(width=self.line_width)
        annot.update()
        self._mark_dirty("Line added", refresh_sidebars=True)

    def add_ink(self, image_points: List[QPointF]):
        """Add freehand ink.

        PyMuPDF expects ink paths as a sequence of strokes, where each stroke is
        a sequence of plain float coordinate pairs: [[(x, y), (x, y), ...]].
        Passing fitz.Point objects can crash on newer PyMuPDF builds with:
        "arg must be seq of seq of float pairs".
        """
        if not image_points or len(image_points) < 2:
            return

        self._push_undo()
        page = self.doc[self.current_page_index]

        stroke = [
            (float(p.x() / self.zoom), float(p.y() / self.zoom))
            for p in image_points
        ]

        compact_stroke = []
        last = None
        for point in stroke:
            rounded = (round(point[0], 2), round(point[1], 2))
            if rounded != last:
                compact_stroke.append(point)
                last = rounded

        if len(compact_stroke) < 2:
            return

        try:
            annot = page.add_ink_annot([compact_stroke])
            annot.set_colors(stroke=rgb_from_qcolor(self.annotation_color))
            annot.set_border(width=self.line_width)
            annot.update()
        except Exception:
            color = rgb_from_qcolor(self.annotation_color)
            for start, end in zip(compact_stroke, compact_stroke[1:]):
                page.draw_line(
                    fitz.Point(start[0], start[1]),
                    fitz.Point(end[0], end[1]),
                    color=color,
                    width=self.line_width,
                    overlay=True,
                )

        self._mark_dirty("Ink added", refresh_sidebars=True)

    def apply_redaction(self, image_rect: QRectF):
        response = QMessageBox.warning(
            self,
            "Apply Redaction",
            "This permanently removes visible content inside the selected area in the edited copy. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        self._push_undo()
        page = self.doc[self.current_page_index]
        rect = self._image_rect_to_pdf_rect(image_rect)
        page.add_redact_annot(rect, fill=(0, 0, 0))
        page.apply_redactions()
        self._mark_dirty("Redaction applied", refresh_sidebars=True)

    def crop_page(self, image_rect: QRectF):
        response = QMessageBox.question(
            self,
            "Crop Page",
            "Crop the current page to the selected area?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return

        self._push_undo()
        page = self.doc[self.current_page_index]
        rect = self._image_rect_to_pdf_rect(image_rect)
        page.set_cropbox(rect)
        self._mark_dirty("Page cropped", refresh_sidebars=True)

    def add_url_link(self, image_rect: QRectF):
        url, ok = QInputDialog.getText(self, "Add URL Link", "URL:")
        if not ok or not url.strip():
            return
        url = url.strip()
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("mailto:")):
            url = "https://" + url

        self._push_undo()
        page = self.doc[self.current_page_index]
        rect = self._image_rect_to_pdf_rect(image_rect)
        page.insert_link({"kind": fitz.LINK_URI, "from": rect, "uri": url})
        page.draw_rect(rect, color=(0.1, 0.25, 0.9), width=0.8, overlay=True)
        self._mark_dirty("URL link area added")

    def prepare_insert_image(self):
        if self.doc is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        self.pending_image_path = path
        self.set_tool(Tool.IMAGE)
        self.status.showMessage("Click where you want to place the image.")

    def insert_image_at(self, image_point: QPointF):
        if not self.pending_image_path:
            return

        self._push_undo()
        page = self.doc[self.current_page_index]
        x, y = self._image_point_to_pdf_xy(image_point)
        img = QImage(self.pending_image_path)
        if img.isNull():
            raise ValueError("Could not read selected image.")

        width = min(240, page.rect.width * 0.45)
        height = width * img.height() / max(img.width(), 1)
        rect = fitz.Rect(x, y, x + width, y + height)
        page.insert_image(rect, filename=self.pending_image_path, overlay=True)

        self.pending_image_path = None
        self.set_tool(Tool.SELECT)
        self._mark_dirty("Image inserted", refresh_sidebars=True)

    def add_stamp(self):
        presets = ["DRAFT", "APPROVED", "CONFIDENTIAL", "REVIEWED", "PAID", "VOID", "FINAL"]
        text, ok = QInputDialog.getItem(self, "Add Stamp", "Stamp:", presets, 0, True)
        if not ok or not text.strip():
            return

        self._push_undo()
        page = self.doc[self.current_page_index]
        rect = page.rect
        stamp_rect = fitz.Rect(rect.width * 0.20, rect.height * 0.38, rect.width * 0.80, rect.height * 0.52)
        page.draw_rect(stamp_rect, color=rgb_from_qcolor(self.annotation_color), width=2.5, overlay=True)
        page.insert_textbox(
            stamp_rect,
            text.strip(),
            fontsize=34,
            fontname="helv",
            color=rgb_from_qcolor(self.annotation_color),
            align=1,
            overlay=True,
        )
        self._mark_dirty("Stamp added")

    def add_watermark(self):
        text, ok = QInputDialog.getText(self, "Watermark", "Watermark text:")
        if not ok or not text.strip():
            return

        # ValueError: bad rotate value. This version uses a large centered
        self._push_undo()
        for page in self.doc:
            rect = page.rect
            font_size = max(28, min(rect.width, rect.height) / 9)
            box = fitz.Rect(rect.width * 0.08, rect.height * 0.43, rect.width * 0.92, rect.height * 0.57)
            self._safe_insert_textbox(
                page,
                box,
                text.strip(),
                fontsize=font_size,
                color=QColor(155, 163, 175),
                align=1,
            )
        self._mark_dirty("Watermark added to all pages")

    def rotate_current_page_clockwise(self):
        self._rotate_current_page(90)

    def rotate_current_page_counterclockwise(self):
        self._rotate_current_page(-90)

    def _rotate_current_page(self, delta: int):
        if self.doc is None:
            return
        self._push_undo()
        page = self.doc[self.current_page_index]
        page.set_rotation((page.rotation + delta) % 360)
        self._mark_dirty("Page rotated")

    def delete_current_page(self):
        if self.doc is None or self.doc.page_count <= 1:
            return
        response = QMessageBox.question(
            self,
            "Delete Page",
            f"Delete page {self.current_page_index + 1}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if response != QMessageBox.StandardButton.Yes:
            return
        self._push_undo()
        self.doc.delete_page(self.current_page_index)
        self.current_page_index = min(self.current_page_index, self.doc.page_count - 1)
        self._mark_page_structure_changed()
        self._mark_dirty("Page deleted", refresh_sidebars=True)

    def duplicate_current_page(self):
        if self.doc is None:
            return

        try:
            self._push_undo()

            # PyMuPDF cannot insert pages from the same open document object
            temp_doc = fitz.open()
            temp_doc.insert_pdf(
                self.doc,
                from_page=self.current_page_index,
                to_page=self.current_page_index,
            )
            self.doc.insert_pdf(
                temp_doc,
                from_page=0,
                to_page=0,
                start_at=self.current_page_index + 1,
            )
            temp_doc.close()

            self.current_page_index += 1
            self._mark_page_structure_changed()
            self._mark_dirty("Page duplicated", refresh_sidebars=True)
        except Exception as exc:
            QMessageBox.critical(self, "Duplicate Page Error", f"Could not duplicate page:\n{exc}")

    def move_page_up(self):
        if self.doc is None or self.current_page_index <= 0:
            return
        self._push_undo()
        self.doc.move_page(self.current_page_index, self.current_page_index - 1)
        self.current_page_index -= 1
        self._mark_page_structure_changed()
        self._mark_dirty("Page moved up", refresh_sidebars=True)

    def move_page_down(self):
        if self.doc is None or self.current_page_index >= self.doc.page_count - 1:
            return
        self._push_undo()
        # no-op because the page is already right before index+1.
        target = self.current_page_index + 2
        if target >= self.doc.page_count:
            self.doc.move_page(self.current_page_index, -1)
        else:
            self.doc.move_page(self.current_page_index, target)
        self.current_page_index += 1
        self._mark_page_structure_changed()
        self._mark_dirty("Page moved down", refresh_sidebars=True)

    def insert_blank_page(self):
        if self.doc is None:
            return
        self._push_undo()
        current = self.doc[self.current_page_index]
        self.doc.new_page(pno=self.current_page_index + 1, width=current.rect.width, height=current.rect.height)
        self.current_page_index += 1
        self._mark_page_structure_changed()
        self._mark_dirty("Blank page inserted", refresh_sidebars=True)

    def insert_pdf_after_current(self):
        if self.doc is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Merge PDF After Current Page", "", "PDF Files (*.pdf)")
        if not path:
            return
        try:
            src = fitz.open(path)
            if src.page_count == 0:
                raise ValueError("Selected PDF has no pages.")
            self._push_undo()
            self.doc.insert_pdf(src, start_at=self.current_page_index + 1)
            src.close()
            self._mark_page_structure_changed()
            self._mark_dirty("PDF merged", refresh_sidebars=True)
        except Exception as exc:
            QMessageBox.critical(self, "Merge Error", f"Could not merge PDF:\n{exc}")

    def extract_page_range(self):
        if self.doc is None:
            return
        rng = page_range_from_user(self, self.doc.page_count)
        if not rng:
            return
        start, end = rng

        out, _ = QFileDialog.getSaveFileName(self, "Extract Page Range", f"pages_{start+1}_{end+1}.pdf", "PDF Files (*.pdf)")
        if not out:
            return
        if not out.lower().endswith(".pdf"):
            out += ".pdf"

        try:
            new_doc = fitz.open()
            new_doc.insert_pdf(self.doc, from_page=start, to_page=end)
            new_doc.save(out, garbage=4, deflate=True)
            new_doc.close()
            QMessageBox.information(self, "Extracted", f"Saved:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Extract Error", f"Could not extract pages:\n{exc}")

    def split_every_page(self):
        if self.doc is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose Folder for Split Pages")
        if not folder:
            return
        try:
            base = safe_filename(Path(self.file_path).stem if self.file_path else "document")
            for i in range(self.doc.page_count):
                new_doc = fitz.open()
                new_doc.insert_pdf(self.doc, from_page=i, to_page=i)
                out = Path(folder) / f"{base}_page_{i + 1:03d}.pdf"
                new_doc.save(str(out), garbage=4, deflate=True)
                new_doc.close()
            QMessageBox.information(self, "Split Complete", f"Saved {self.doc.page_count} PDF files.")
        except Exception as exc:
            QMessageBox.critical(self, "Split Error", f"Could not split document:\n{exc}")

    def search_text(self):
        """Search in a worker thread so big documents stay responsive."""
        if self.doc is None:
            return
        query = self.search_input.text().strip()
        if not query:
            return

        self._search_job_id += 1
        job_id = self._search_job_id
        self.search_results.clear()
        self.search_results_list.clear()
        self.search_index = -1
        self.render_current_page()

        source = self._document_worker_source()
        if not source:
            return

        worker = SearchWorker(job_id, source, query)
        worker.progress.connect(lambda jid, done, total: self._worker_progress(jid, done, total, "Searching"))
        worker.finished_results.connect(self._search_finished_from_worker)
        worker.error.connect(lambda jid, msg: QMessageBox.critical(self, "Search Error", f"Search failed:\n{msg}"))
        worker.finished.connect(lambda jid: self._worker_finished(jid, "Search complete"))
        self._start_worker(worker)
        self.sidebar.setCurrentIndex(2)
        self.status.showMessage(f"Searching for '{query}'...")

    def go_to_search_result(self, index: int):
        if not self.search_results or self.doc is None:
            return
        self.search_index = index % len(self.search_results)
        page_index, _ = self.search_results[self.search_index]
        self.current_page_index = page_index
        self.search_results_list.setCurrentRow(self.search_index)
        self.render_current_page()

    def go_to_next_search_result(self):
        if not self.search_results:
            self.search_text()
            return
        self.go_to_search_result(self.search_index + 1)

    def go_to_search_item(self, item: QListWidgetItem):
        index = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(index, int):
            self.go_to_search_result(index)

    def export_page_image(self, fmt: str):
        if self.doc is None:
            return
        ext = "jpg" if fmt.lower() in {"jpg", "jpeg"} else "png"
        out, _ = QFileDialog.getSaveFileName(self, f"Export Current Page as {ext.upper()}", f"page_{self.current_page_index+1}.{ext}", f"{ext.upper()} Image (*.{ext})")
        if not out:
            return
        if not out.lower().endswith("." + ext):
            out += "." + ext
        try:
            pix = self.doc[self.current_page_index].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pix.save(out)
            QMessageBox.information(self, "Exported", f"Saved:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Could not export image:\n{exc}")

    def export_all_pages_images(self, fmt: str):
        """Export all pages in a worker thread to avoid locking the app."""
        if self.doc is None:
            return
        folder = QFileDialog.getExistingDirectory(self, f"Choose Folder for {fmt.upper()} Export")
        if not folder:
            return
        ext = "jpg" if fmt.lower() in {"jpg", "jpeg"} else "png"
        base = safe_filename(Path(self.file_path).stem if self.file_path else "document")
        source = self._document_worker_source()
        if not source:
            return

        self._export_job_id += 1
        job_id = self._export_job_id
        worker = ImageExportWorker(job_id, source, folder, base, ext, scale=2.0)
        worker.progress.connect(lambda jid, done, total: self._worker_progress(jid, done, total, f"Exporting {ext.upper()}"))
        worker.done.connect(self._image_export_finished_from_worker)
        worker.error.connect(lambda jid, msg: QMessageBox.critical(self, "Export Error", f"Could not export images:\n{msg}"))
        worker.finished.connect(lambda jid: self._worker_finished(jid, "Export complete"))
        self._start_worker(worker)
        self.status.showMessage(f"Exporting all pages as {ext.upper()}...")

    def export_current_page_text(self):
        if self.doc is None:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Export Current Page Text", f"page_{self.current_page_index+1}.txt", "Text Files (*.txt)")
        if not out:
            return
        text = self.doc[self.current_page_index].get_text("text", sort=True)
        self._write_text_file(out, text)

    def export_full_document_text(self):
        if self.doc is None:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Export Full Text", "document_text.txt", "Text Files (*.txt)")
        if not out:
            return
        text = "\n\n".join(f"--- Page {i+1} ---\n{p.get_text('text', sort=True)}" for i, p in enumerate(self.doc))
        self._write_text_file(out, text)

    def export_full_document_html(self):
        if self.doc is None:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Export HTML", "document.html", "HTML Files (*.html)")
        if not out:
            return
        if not out.lower().endswith(".html"):
            out += ".html"
        body = []
        for i, page in enumerate(self.doc):
            text = html.escape(page.get_text("text", sort=True))
            body.append(f"<h2>Page {i+1}</h2><pre>{text}</pre>")
        content = "<!doctype html><html><head><meta charset='utf-8'><title>PDF Export</title></head><body>" + "\n".join(body) + "</body></html>"
        self._write_text_file(out, content)

    def export_full_document_markdown(self):
        if self.doc is None:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Export Markdown", "document.md", "Markdown Files (*.md)")
        if not out:
            return
        if not out.lower().endswith(".md"):
            out += ".md"
        text = "\n\n".join(f"## Page {i+1}\n\n{p.get_text('text', sort=True)}" for i, p in enumerate(self.doc))
        self._write_text_file(out, text)

    def export_full_document_docx(self):
        if self.doc is None:
            return
        try:
            from docx import Document
        except ImportError:
            QMessageBox.warning(self, "Missing Dependency", "Install DOCX export support with:\n\npip install python-docx")
            return

        out, _ = QFileDialog.getSaveFileName(self, "Export DOCX", "document.docx", "Word Document (*.docx)")
        if not out:
            return
        if not out.lower().endswith(".docx"):
            out += ".docx"

        try:
            docx = Document()
            docx.add_heading(Path(self.file_path).name if self.file_path else "PDF Export", 0)
            for i, page in enumerate(self.doc):
                docx.add_heading(f"Page {i+1}", level=1)
                for para in page.get_text("text", sort=True).splitlines():
                    if para.strip():
                        docx.add_paragraph(para.strip())
                if i != self.doc.page_count - 1:
                    docx.add_page_break()
            docx.save(out)
            QMessageBox.information(self, "Exported", f"DOCX saved:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "DOCX Export Error", f"Could not export DOCX:\n{exc}")

    def export_metadata_json(self):
        if self.doc is None:
            return
        out, _ = QFileDialog.getSaveFileName(self, "Export Metadata JSON", "metadata.json", "JSON Files (*.json)")
        if not out:
            return
        if not out.lower().endswith(".json"):
            out += ".json"
        data = {"page_count": self.doc.page_count, "metadata": self.doc.metadata}
        self._write_text_file(out, json.dumps(data, indent=2, ensure_ascii=False))

    def _write_text_file(self, out: str, text: str):
        try:
            Path(out).write_text(text, encoding="utf-8")
            QMessageBox.information(self, "Exported", f"Saved:\n{out}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Could not save file:\n{exc}")

    def show_document_info(self):
        if self.doc is None:
            return
        DocumentInfoDialog(self, self.doc.metadata or {}, self.doc.page_count).exec()

    def edit_metadata(self):
        if self.doc is None:
            return
        dialog = MetadataEditDialog(self, self.doc.metadata or {})
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._push_undo()
        self.doc.set_metadata(dialog.metadata())
        self._mark_dirty("Metadata updated")

    def zoom_in(self):
        if self.doc is None:
            return
        self.zoom = min(5.0, self.zoom + 0.15)
        self.render_current_page()

    def zoom_out(self):
        if self.doc is None:
            return
        self.zoom = max(0.25, self.zoom - 0.15)
        self.render_current_page()

    def fit_width(self):
        if self.doc is None:
            return
        page = self.doc[self.current_page_index]
        available = max(self.scroll.viewport().width() - 90, 200)
        self.zoom = clamp(available / page.rect.width, 0.25, 5.0)
        self.render_current_page()

    def fit_page(self):
        if self.doc is None:
            return
        page = self.doc[self.current_page_index]
        available_w = max(self.scroll.viewport().width() - 90, 200)
        available_h = max(self.scroll.viewport().height() - 90, 200)
        self.zoom = clamp(min(available_w / page.rect.width, available_h / page.rect.height), 0.25, 5.0)
        self.render_current_page()

    def handle_zoom_combo(self, text: str):
        if self.doc is None:
            return
        if text == "Fit Width":
            self.fit_width()
        elif text == "Fit Page":
            self.fit_page()
        elif text.endswith("%"):
            try:
                self.zoom = clamp(int(text[:-1]) / 100, 0.25, 5.0)
                self.render_current_page()
            except ValueError:
                pass

    def _update_zoom_combo_text(self):
        text = f"{int(round(self.zoom * 100))}%"
        presets = {
            "50%", "75%", "100%", "125%", "150%",
            "175%", "200%", "300%", "Fit Width", "Fit Page",
        }
        self.zoom_combo.blockSignals(True)
        # dropdown does not fill up with fractional percentages on wheel zoom.
        for i in range(self.zoom_combo.count() - 1, -1, -1):
            if self.zoom_combo.itemText(i) not in presets:
                self.zoom_combo.removeItem(i)
        if self.zoom_combo.findText(text) < 0:
            self.zoom_combo.insertItem(0, text)
        self.zoom_combo.setCurrentText(text)
        self.zoom_combo.blockSignals(False)

    def _push_undo(self):
        if self.doc is None:
            return
        try:
            self.undo_stack.append(self.doc.tobytes(garbage=4, deflate=True))
            if len(self.undo_stack) > self.max_history:
                self.undo_stack.pop(0)
            self.redo_stack.clear()
            self._refresh_history_actions()
        except Exception:
            pass

    def undo(self):
        if self.doc is None or not self.undo_stack:
            return
        try:
            self.redo_stack.append(self.doc.tobytes(garbage=4, deflate=True))
            data = self.undo_stack.pop()
            self.doc.close()
            self.doc = fitz.open(stream=data, filetype="pdf")
            self._doc_version += 1
            self._render_cache.clear()
            self._render_cache_order.clear()
            self.current_page_index = min(self.current_page_index, self.doc.page_count - 1)
            self.is_dirty = True
            self.refresh_sidebars()
            self.render_current_page()
            self._update_window_title()
            self._refresh_history_actions()
        except Exception as exc:
            QMessageBox.critical(self, "Undo Error", f"Could not undo:\n{exc}")

    def redo(self):
        if self.doc is None or not self.redo_stack:
            return
        try:
            self.undo_stack.append(self.doc.tobytes(garbage=4, deflate=True))
            data = self.redo_stack.pop()
            self.doc.close()
            self.doc = fitz.open(stream=data, filetype="pdf")
            self._doc_version += 1
            self._render_cache.clear()
            self._render_cache_order.clear()
            self.current_page_index = min(self.current_page_index, self.doc.page_count - 1)
            self.is_dirty = True
            self.refresh_sidebars()
            self.render_current_page()
            self._update_window_title()
            self._refresh_history_actions()
        except Exception as exc:
            QMessageBox.critical(self, "Redo Error", f"Could not redo:\n{exc}")

    def _refresh_history_actions(self):
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(bool(self.undo_stack) and self.doc is not None)
        if hasattr(self, "redo_action"):
            self.redo_action.setEnabled(bool(self.redo_stack) and self.doc is not None)

    def _mark_dirty(self, message: str, refresh_sidebars: bool = False):
        self.is_dirty = True
        self._doc_version += 1
        self._render_cache.clear()
        self._render_cache_order.clear()
        self._xray_cache.clear()

        if self._page_structure_changed:
            self.refresh_sidebars()
            self._page_structure_changed = False
        else:
            self._refresh_light_sidebars()
            self._update_current_thumbnail_inline()

        self.render_current_page()
        self._update_window_title()
        self._refresh_history_actions()
        self.status.showMessage(message)

    def _update_window_title(self):
        name = Path(self.file_path).name if self.file_path else "Untitled"
        mark = " •" if self.is_dirty else ""
        self.setWindowTitle(f"Suketchi — {name}{mark}")

    def _confirm_discard(self) -> bool:
        response = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Continue without saving?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return response == QMessageBox.StandardButton.Yes

    def _image_point_to_pdf_xy(self, point: QPointF) -> Tuple[float, float]:
        return point.x() / self.zoom, point.y() / self.zoom

    def _image_rect_to_pdf_rect(self, rect: QRectF) -> fitz.Rect:
        x0 = rect.left() / self.zoom
        y0 = rect.top() / self.zoom
        x1 = rect.right() / self.zoom
        y1 = rect.bottom() / self.zoom
        return fitz.Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def _pdf_rect_to_image_rect(self, rect: fitz.Rect) -> QRectF:
        return QRectF(rect.x0 * self.zoom, rect.y0 * self.zoom, rect.width * self.zoom, rect.height * self.zoom)

    @staticmethod
    def _pdf_from_mime(mime) -> Optional[str]:
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".pdf"):
                return url.toLocalFile()
        return None

    def dragEnterEvent(self, event):
        if self._pdf_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._pdf_from_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._pdf_from_mime(event.mimeData())
        if not path:
            event.ignore()
            return
        event.acceptProposedAction()
        if self.is_dirty and not self._confirm_discard():
            return
        self.load_pdf(path)

    def closeEvent(self, event):
        if self.is_dirty and not self._confirm_discard():
            event.ignore()
            return
        for thread, worker in list(self._workers):
            try:
                worker.cancelled = True
            except Exception:
                pass
            thread.quit()
            thread.wait(2000)
        self._workers.clear()
        if self.doc:
            self.doc.close()
        event.accept()


def load_hand_font() -> str:
    """Load the bundled handwriting font, else fall back gracefully.

    Looks for PatrickHand-Regular.ttf next to this script (or in ./assets).
    If it is missing, tries handwriting faces that ship with common systems,
    and finally settles for a normal sans so the app still runs everywhere.
    """
    global APP_FONT_FAMILY

    here = Path(__file__).resolve().parent
    for candidate in (
        here / "PatrickHand-Regular.ttf",
        here / "assets" / "PatrickHand-Regular.ttf",
    ):
        if candidate.exists():
            font_id = QFontDatabase.addApplicationFont(str(candidate))
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                APP_FONT_FAMILY = families[0]
                return APP_FONT_FAMILY

    available = set(QFontDatabase.families())
    for name in ("Patrick Hand", "Comic Neue", "Segoe Print", "Bradley Hand",
                 "Chalkboard SE", "Comic Sans MS", "Ink Free"):
        if name in available:
            APP_FONT_FAMILY = name
            return APP_FONT_FAMILY

    APP_FONT_FAMILY = "Segoe UI"
    return APP_FONT_FAMILY


def asset_path(*candidates) -> Optional[Path]:
    """Find a bundled asset next to the script, tolerating a few layouts."""
    here = Path(__file__).resolve().parent
    for rel in candidates:
        for base in (here, here / "logo", here / "assets"):
            path = base / rel
            if path.exists():
                return path
    return None


def render_svg(path: Path, size: int) -> Optional[QPixmap]:
    """Render an SVG crisply at an exact pixel size."""
    try:
        from PyQt6.QtSvg import QSvgRenderer
    except ImportError:
        return None
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return None
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    renderer.render(painter)
    painter.end()
    return pixmap


def load_app_icon() -> QIcon:
    """Window / taskbar / launcher icon: the page mark.

    Uses the pre-rendered PNG set when present (its 16-32px sizes use the
    simplified mark, which survives where fine detail blurs). Otherwise renders
    the SVG at each size. Returns an empty icon if no assets exist at all, so
    the app still runs.
    """
    icon = QIcon()
    found = False
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        png = asset_path(f"png/icon_{size}.png", f"icon_{size}.png")
        if png:
            icon.addFile(str(png), QSize(size, size))
            found = True
    if found:
        return icon

    detailed = asset_path("suketchi_mark.svg")
    simplified = asset_path("suketchi_mark_small.svg")
    for size in (16, 24, 32, 48, 64, 128, 256, 512):
        source = simplified if (size <= 32 and simplified) else detailed
        if source:
            pixmap = render_svg(source, size)
            if pixmap:
                icon.addPixmap(pixmap)
    return icon


def load_seal_pixmap(size: int) -> Optional[QPixmap]:
    """The hanko seal, used as the small brand badge in the toolbar.

    The seal is a solid stamped square, so it stays legible at 20-30px where
    the detailed page mark would turn to grey mush.
    """
    svg = asset_path("suketchi_seal.svg")
    if svg:
        pixmap = render_svg(svg, size)
        if pixmap:
            return pixmap
    return load_brand_pixmap(size)


def load_brand_pixmap(size: int) -> Optional[QPixmap]:
    """The page mark, used large (empty state, about box)."""
    svg = None
    if size <= 40:
        svg = asset_path("suketchi_mark_small.svg")
    if svg is None:
        svg = asset_path("suketchi_mark.svg")
    if svg:
        pixmap = render_svg(svg, size)
        if pixmap:
            return pixmap
    png = asset_path("png/icon_256.png", "icon_256.png")
    if png:
        pixmap = QPixmap(str(png))
        if not pixmap.isNull():
            return pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
    return None


def _apply_bw_palette(app: QApplication):
    """Pure black-on-white palette, so native dialogs match the sketch look."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, PAPER)
    p.setColor(QPalette.ColorRole.WindowText, INK)
    p.setColor(QPalette.ColorRole.Base, PAPER)
    p.setColor(QPalette.ColorRole.AlternateBase, PAPER)
    p.setColor(QPalette.ColorRole.Text, INK)
    p.setColor(QPalette.ColorRole.Button, PAPER)
    p.setColor(QPalette.ColorRole.ButtonText, INK)
    p.setColor(QPalette.ColorRole.ToolTipBase, PAPER)
    p.setColor(QPalette.ColorRole.ToolTipText, INK)
    p.setColor(QPalette.ColorRole.Highlight, INK)
    p.setColor(QPalette.ColorRole.HighlightedText, PAPER)
    p.setColor(QPalette.ColorRole.PlaceholderText, GREY_FAINT)
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, GREY_FAINT)
    app.setPalette(p)


_apply_light_palette = _apply_bw_palette


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Suketchi PDF Reader")
    app.setStyle(SketchStyle("Fusion"))
    family = load_hand_font()
    app.setFont(QFont(family, 11))
    _apply_bw_palette(app)
    icon = load_app_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = PdfStudioOverhaulPro()
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

