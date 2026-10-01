#!/usr/bin/env python3
"""Check reopen timing using the real QML and backend with a local response fixture."""
import importlib.util
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('preview',ROOT/'scripts/render_preview.py')
preview=importlib.util.module_from_spec(spec);spec.loader.exec_module(preview)
with tempfile.TemporaryDirectory(prefix='rewerd-qml-reopen-') as tmp:
    d=Path(tmp)
    for name,content in preview.STUBS.items():
        name=name.removeprefix('qs/')
        if name == 'Ui/KeyboardPanel.qml':
            content = content.replace('property bool open: true', 'property bool open: true; visible: open')
        p=d/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)
    p=d/'Ui/Panel.qml';s=p.read_text().replace('Item {','Item {\n id: panelStub',1).replace('property bool opened: true','property bool opened: false').replace('function show() {}','function show() { panelStub.opened = true }');p.write_text(s)
    for name in ['Service.qml','Panel.qml']:
        content=(ROOT/name).read_text()
        if name=='Panel.qml':
            content=content.replace('visible: root.editor && !!root.editor.result', 'objectName: \"rewriteResult\"; visible: root.editor && !!root.editor.result')
        (d/name.replace('Panel.qml','RewerdPanel.qml')).write_text(content)
    (d/'backend.py').write_text('''import sys,time
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, ROOT)
import backend
from instructions import InstructionStore
backend.ConfigStore=Mock
backend.InstructionStore=lambda:InstructionStore(Path(STATE))
backend.ClipboardSnapshot.capture=lambda:backend.ClipboardSnapshot('text/plain',b'original source')
backend.Selection.capture=lambda previous:backend.Selection('original source','0x123',1,'id','fixture',True)
def generate(*args):
 deadline = time.monotonic() + 8
 while not Path(GATE).exists():
  if time.monotonic() > deadline:
   raise RuntimeError('Test response was not released')
  time.sleep(.02)
 return 'The completed rewrite.'
backend.generate=generate
editor=backend.Backend()
editor.emit('ready',data={'provider':'openai','providers':{}})
editor.handle({'type':'instructions'})
import json
for line in sys.stdin:
 editor.handle(json.loads(line))
'''.replace('ROOT',repr(str(ROOT))).replace('STATE',repr(str(d/'instructions.json'))).replace('GATE',repr(str(d/'release-response'))))
    (d/'shell.qml').write_text('''import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
 Service { id: editor }
 QtObject { id: sampleBar; property QtObject shell: QtObject { function serviceFor(id) { return editor } } }
 Window {
  visible: true; width: 580; height: 720
  RewerdPanel { id: panel; anchors.fill: parent; bar: sampleBar }
 }
 IpcHandler {
  target: "test"
  function open(): void { panel.open() }
  function close(): void { panel.close() }
  function generate(): void { panel.rewrite() }
  function findResult(item): var {
   if (item.objectName === "rewriteResult") return item
   for (var child of item.children || []) { var found = findResult(child); if (found) return found }
   return null
  }
  function state(): string { return JSON.stringify({resultVisible:findResult(panel).visible,opened:panel.opened,phase:editor.phase,source:editor.source,result:editor.result,ready:editor.ready}) }
 }
}
''')
    log=open(d/'quickshell.log','w')
    env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QT_QUICK_BACKEND':'software'}
    process=subprocess.Popen(['qs','-p',str(d)],stdout=log,stderr=log,env=env)
    def call(name):
        p=subprocess.run(['qs','ipc','-p',str(d),'call','test',name],capture_output=True,text=True,env=env,timeout=4)
        if p.returncode: raise RuntimeError(p.stderr)
        return p.stdout.strip()
    try:
        for _ in range(50):
            time.sleep(.1)
            try:
                if json.loads(call('state'))['ready']:break
            except Exception:pass
        else: raise RuntimeError((d/'quickshell.log').read_text())
        call('open')
        time.sleep(.2)
        call('generate')
        time.sleep(.1)
        call('close')
        assert not json.loads(call('state'))['resultVisible']
        call('open')
        time.sleep(.2)
        (d/'release-response').touch()
        time.sleep(.5)
        state=json.loads(call('state'))
        print(json.dumps(state))
        assert state['opened'] and state['resultVisible'] and state['result']=='The completed rewrite.', 'Pending rewrite lost after reopening same input'
        call('close')
        assert not json.loads(call('state'))['resultVisible']
        call('open')
        time.sleep(.2)
        state = json.loads(call('state'))
        assert state['resultVisible'] and state['result'] == 'The completed rewrite.'
        print('PASS: pending response completes after close/reopen; completed response survives another reopen')
    finally:
        process.terminate()
        process.wait(timeout=5)
        log.close()
