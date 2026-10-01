#!/usr/bin/env python3
"""Exercise Settings navigation and keyboard focus with the real QML, without provider requests."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preview', root / 'scripts/render_preview.py')
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)
from PySide6.QtCore import QObject, QUrl, QPoint, QPointF, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtTest import QTest

app = QGuiApplication([])
engine = QQmlApplicationEngine()
errors = []
engine.warnings.connect(lambda values: errors.extend(error.toString() for error in values))
with tempfile.TemporaryDirectory(prefix='wordsmith-ui-check-') as directory:
    folder = Path(directory)
    for name, value in preview.STUBS.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
    (folder/'WordsmithPanel.qml').write_text((root/'Panel.qml').read_text().replace('import Quickshell\n',''))
    scene = preview.SCENE.replace("DEFAULTS_PLACEHOLDER", json.dumps(preview.DEFAULT_INSTRUCTIONS))
    scene = scene.replace('id: sample\n', '''id: sample
  objectName: "sampleService"
  property bool testFail: false
  property string receivedDefaults: ""
  property string receivedProvider: ""
  property string receivedModel: ""
  property string receivedKey: ""
  property bool testDelay: false
  property var pendingConfig: null
  function persistInstruction(kind) {}
  function saveDefaults(text) {
    receivedDefaults = text
    settingsBusy = true
    pendingConfig = Object.assign({}, config, {defaultInstructions: text})
    if (!testDelay) Qt.callLater(finishSave)
  }
  function save(provider, model, key, clearKey) {
    receivedProvider = provider; receivedModel = model; receivedKey = key
    settingsBusy = true
    var providers = Object.assign({}, config.providers)
    providers[provider] = {model: model, hasKey: !clearKey}
    pendingConfig = Object.assign({}, config, {provider: provider, providers: providers})
    if (!testDelay) Qt.callLater(finishSave)
  }
  function finishSave() {
    settingsBusy = false
    if (testFail) { error = "Could not save settings."; return }
    config = pendingConfig
    settingsSaved()
  }
''')
    (folder/'Preview.qml').write_text(scene)
    engine.addImportPath(str(folder))
    engine.load(QUrl.fromLocalFile(str(folder/'Preview.qml')))
    QTest.qWait(500)
    assert engine.rootObjects(), errors
    window=engine.rootObjects()[0]
    window.requestActivate()
    QTest.qWait(50)
    panel=window.findChild(QObject,'previewPanel')
    sample=window.findChild(QObject,'sampleService')
    def find(name):
        result=window.findChild(QObject,name)
        assert result is not None, name
        return result
    def click(name):
        target=find(name)
        assert target.property('visible') and target.property('enabled'), name+' hidden/disabled'
        point=target.mapToScene(QPointF(target.width()/2,target.height()/2))
        assert 0 <= point.x() < window.width() and 0 <= point.y() < window.height(), (name,point)
        QTest.mouseClick(window,Qt.LeftButton,Qt.NoModifier,QPoint(round(point.x()),round(point.y())))
        QTest.qWait(100)
    click('settingsButton')
    assert panel.property('showSettings') and panel.property('settingsPage')=='index'
    click('defaultsEditButton')
    assert panel.property('settingsPage')=='defaults'
    defaults=find('defaultsInput')
    assert defaults.property('activeFocus'), 'Defaults must focus on entry'
    stock=defaults.property('text')
    QTest.keyClick(window, Qt.Key_X, Qt.ShiftModifier)
    assert defaults.property('text') != stock, 'Typing must enter defaults textarea'
    defaults.setProperty('text',stock)
    assert 'No em dashes' in stock and 'natural' in stock
    defaults.setProperty('text','Use a relaxed voice. Keep technical terms.')
    click('settingsButton')
    assert panel.property('settingsPage')=='index'
    click('defaultsEditButton')
    assert defaults.property('text')==stock, 'Back must discard unsaved draft'
    defaults.setProperty('text','Use a relaxed voice. Keep technical terms.')
    sample.setProperty('testFail', True)
    click('defaultsSaveButton')
    assert panel.property('settingsPage')=='defaults'
    assert defaults.property('text')=='Use a relaxed voice. Keep technical terms.'
    assert sample.property('error')=='Could not save settings.'
    sample.setProperty('testFail', False)
    sample.setProperty('testDelay', True)
    click('defaultsSaveButton')
    assert not find('defaultsSaveButton').property('enabled')
    assert not find('settingsButton').property('enabled')
    sample.finishSave()
    QTest.qWait(100)
    sample.setProperty('testDelay', False)
    assert panel.property('showSettings') and panel.property('settingsPage')=='index', 'Save must return Settings'
    assert find('settingsButton').property('activeFocus'), 'Save must focus visible Settings control'
    click('defaultsEditButton')
    assert defaults.property('text')=='Use a relaxed voice. Keep technical terms.', 'Saved defaults must reload'
    click('settingsButton')
    click('providerEditButton')
    assert panel.property('settingsPage')=='provider'
    assert find('provider').property('activeFocus'), 'Provider editor must focus dropdown'
    find('modelInput').setProperty('text','test-model')
    click('providerSaveButton')
    assert panel.property('showSettings') and panel.property('settingsPage')=='index'
    click('providerEditButton')
    assert find('modelInput').property('text')=='test-model'
    click('settingsButton')
    click('settingsButton')
    assert not panel.property('showSettings')
    assert not [e for e in errors if 'recursive rearrange' not in e], errors
    window.close()
print('Real QML UI: index, provider/defaults edit, cancel, save, reopen verified.')
