#!/usr/bin/env python3
"""Exercise the current preview QML with offscreen mouse and keyboard events."""
import argparse
import json
import os
from pathlib import Path
import re

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QUICK_BACKEND"] = "software"

from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--panel", type=Path, default=Path(__file__).with_name("Panel.qml"))
args = parser.parse_args()
source = args.panel.read_text()
start = source.index("                            FocusScope {\n                                id: selectionPreview")
stop = source.index('                            Label { text: "PROMPT"', start)
preview = source[start:stop]
preview = re.sub(r'(\bid: (\w+))', r'\1; objectName: "\2"', preview)
selected = ("<b>Literal source</b>\n  second line\t spaced  " + " long source text " * 40 + "\n") * 10
qml = '''import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
Window {
    id: root
    width: 500; height: 300; visible: true
    property color ink: "black"
    property color muted: "gray"
    property bool previewExpanded: false
    property QtObject editor: QtObject { property string source: SOURCE_TEXT }
    component Label: Text {
        color: root.ink
        font.pixelSize: 13
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
    Rectangle {
        anchors.fill: parent
        color: "white"
        MouseArea { anchors.fill: parent }
    }
    ColumnLayout { x: 20; y: 20; width: 400;
'''.replace("SOURCE_TEXT", json.dumps(selected)) + preview + "\n    }\n}"
app = QGuiApplication([])
engine = QQmlApplicationEngine()
engine.loadData(qml.encode(), QUrl("file:///tmp/rewerd-preview-pointer-review.qml"))
assert engine.rootObjects(), "Preview QML failed to load"
window = engine.rootObjects()[0]
QTest.qWait(150)
window.requestActivate()
QTest.qWait(30)
collapsed = window.findChild(QObject, "collapsedSelection")
full = window.findChild(QObject, "selectionText")
scroll = window.findChild(QObject, "selectionScroll")
preview_item = window.findChild(QObject, "selectionPreview")
assert collapsed.property("text") == re.sub(r"\s+", " ", selected).strip()
assert collapsed.property("truncated")
assert full.property("text") == selected

states = []
for _ in range(3):
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 25))
    QTest.qWait(150)
    states.append(window.property("previewExpanded"))
print("Mouse click expansion states:", states, flush=True)
assert states == [True, False, True], "A click must collapse the expanded preview"
assert preview_item.property("height") == 112

QTest.mousePress(window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 115))
QTest.qWait(25)
for y in range(115, 35, -8):
    QTest.mouseMove(window, QPoint(60, y))
    QTest.qWait(25)
QTest.mouseRelease(window, Qt.LeftButton, Qt.NoModifier, QPoint(60, 35))
QTest.qWait(200)
scroll_y = scroll.property("contentY")
print("Scroll position after drag:", round(scroll_y, 2), flush=True)
assert scroll_y > 0, "Expanded preview must remain draggable"
assert window.property("previewExpanded"), "Dragging must not collapse the preview"
QTest.qWait(500)

QTest.keyClick(window, Qt.Key_Space)
QTest.qWait(50)
assert not window.property("previewExpanded"), "Space must collapse the preview"
QTest.keyClick(window, Qt.Key_Return)
QTest.qWait(50)
assert window.property("previewExpanded"), "Return must expand the preview"
QTest.keyClick(window, Qt.Key_Enter)
QTest.qWait(50)
assert not window.property("previewExpanded"), "Enter must collapse the preview"
print("PASS: repeated mouse toggles, drag scrolling, and keyboard toggles", flush=True)
window.close()
