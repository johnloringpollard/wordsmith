#!/usr/bin/env python3
"""Render the real panel with sample data, without a desktop or provider request."""
import argparse
import os
from pathlib import Path
import tempfile
import sys
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from providers import DEFAULT_INSTRUCTIONS

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['QT_QUICK_BACKEND'] = 'software'
os.environ['QT_SCALE_FACTOR'] = '2'

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

ROOT = Path(__file__).resolve().parents[1]
STUBS = {
    'qs/Commons/qmldir': 'module qs.Commons\nsingleton Color 1.0 Color.qml\nsingleton Style 1.0 Style.qml\n',
    'qs/Commons/Color.qml': '''pragma Singleton
import QtQuick
QtObject {
 property color foreground: "#20242a"
 property color background: "#fafbfc"
 property color muted: "#757c84"
 property color accent: "#3375be"
 property color urgent: "#c23535"
 property QtObject popups: QtObject { property color text: "#20242a" }
}''',
    'qs/Commons/Style.qml': '''pragma Singleton
import QtQuick
QtObject { property QtObject font: QtObject { property string family: "Inter" } }''',
    'qs/Ui/qmldir': 'module qs.Ui\nPanel 1.0 Panel.qml\nBarIconButton 1.0 WidgetButton.qml\nKeyboardPanel 1.0 KeyboardPanel.qml\n',
    'qs/Ui/Panel.qml': '''import QtQuick
Item {
 property string moduleName: ""
 property bool manageIpc: false
 property var bar: null
 property bool opened: true
 property QtObject controller: QtObject { function show() {} }
 function close() { opened = false }
 function toggle() { opened = !opened }
}''',
    'qs/Ui/WidgetButton.qml': '''import QtQuick
Item {
 property var bar
 property string text: ""
 property string tooltipText: ""
 property Component iconComponent: null
 property bool active: false
 property bool useActiveColor: false
 property color activeColor: "#3375be"
 property color foreground: "#20242a"
 implicitWidth: 20; implicitHeight: 20
 signal pressed(int button)
}''',
    'qs/Ui/KeyboardPanel.qml': '''import QtQuick
Rectangle {
 objectName: "previewCard"
 property var anchorItem
 property var owner
 property var bar
 property bool open: true
 property var focusTarget
 property int contentWidth: 500
 property int contentHeight: 400
 property int padding: 20
 function fittedContentWidth(n) { return n }
 function fittedContentHeight(n) { return n }
 function cappedContentHeight(n) { return n }
 default property alias contentItem: holder.data
 x: 20; y: 20
 width: contentWidth + padding * 2
 height: contentHeight + padding * 2
 radius: 12; color: "#fafbfc"
 border.color: "#dfe3e8"; border.width: 1
 Item { id: holder; x: parent.padding; y: parent.padding; width: parent.contentWidth; height: parent.contentHeight }
}''',
}
SCENE = '''import QtQuick
Window {
 id: window
 visible: true; width: 580; height: 700; color: "#edf0f4"
 QtObject {
  id: sample
  property bool settingsBusy: false
  property bool ready: true
  property bool instructionsReady: true
  property bool instructionBusy: false
  property bool copyConfirmed: false
  property string phase: "idle"
  property string source: "We wanted to give everyone a quick update that the new dashboard is now ready for you to try."
  property string result: "The new dashboard is ready. Try it today and let us know what you think."
  property string prompt: "Reword for clarity and keep it concise."
  property string attemptedPrompt: prompt
  property string error: ""
  property bool canReplace: true
  property var savedInstructions: [prompt]
  property var config: ({provider: "openai", defaultInstructions: DEFAULTS_PLACEHOLDER, providers: {openai: {model: "gpt-6-astra", hasKey: false}}})
  signal captured(int requestId)
  signal replacementFinished(bool failed)
  signal settingsSaved()
  signal promptSaved(string text)
  signal rewriteFinished()
  signal copyFinished(bool failed)
 }
 QtObject { id: sampleBar; property QtObject shell: QtObject { function serviceFor(id) { return sample } } }
 WordsmithPanel {
  objectName: "previewPanel"
  anchors.fill: parent
  bar: sampleBar
 }
}'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', action='store_true')
    parser.add_argument('--settings-page', choices=['index', 'provider', 'defaults'])
    parser.add_argument('--dark', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'preview.png')
    args = parser.parse_args()
    app = QGuiApplication([])
    engine = QQmlApplicationEngine()
    engine.warnings.connect(lambda errors: print('\n'.join(e.toString() for e in errors)))
    with tempfile.TemporaryDirectory(prefix='rewerd-preview-') as directory:
        folder = Path(directory)
        for name, text in STUBS.items():
            if args.dark:
                for light, dark in [('#20242a', '#d7e1e5'), ('#fafbfc', '#121e24'), ('#757c84', '#91a0a7'), ('#dfe3e8', '#3b4b53')]:
                    text = text.replace(light, dark)
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        panel = (ROOT / 'Panel.qml').read_text().replace('import Quickshell\n', '')
        (folder / 'WordsmithPanel.qml').write_text(panel)
        (folder / 'Preview.qml').write_text(SCENE.replace('DEFAULTS_PLACEHOLDER', json.dumps(DEFAULT_INSTRUCTIONS)))
        engine.addImportPath(str(folder))
        engine.load(QUrl.fromLocalFile(str(folder / 'Preview.qml')))
        QTest.qWait(500)
        if not engine.rootObjects():
            raise RuntimeError('Preview QML failed to load')
        window = engine.rootObjects()[0]
        QTest.qWait(300)
        panel_item = window.findChild(QObject, 'previewPanel')
        card = panel_item.findChild(QObject, 'previewCard') if panel_item else None
        if card is None:
            raise RuntimeError('Panel did not load')
        if args.dark:
            window.setProperty('color', '#0b1419')
        if args.settings or args.settings_page:
            panel_item.setProperty('showSettings', True)
            panel_item.loadSettings()
            if args.settings_page == "provider":
                panel_item.editProvider()
            elif args.settings_page == "defaults":
                panel_item.editDefaults()
            QTest.qWait(100)
        window.setHeight(int(card.property('height')) + 40)
        QTest.qWait(100)
        if not window.grabWindow().save(str(args.output)):
            raise RuntimeError(f'Could not save {args.output}')
        window.close()
    print(f'Rendered {args.output} from Panel.qml with sample text.')


if __name__ == '__main__':
    main()
