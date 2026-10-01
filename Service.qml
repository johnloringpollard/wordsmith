import QtQuick
import Quickshell
import Quickshell.Io

Item {
    id: root
    property var shell: null
    property var manifest: null
    property bool ready: false
    property string source: ""
    property string sourceApp: ""
    property bool canReplace: false
    property string result: ""
    property string prompt: "Reword for clarity and keep it concise. No em dashes."
    property string attemptedPrompt: ""
    property var savedInstructions: []
    property bool instructionsReady: false
    property bool instructionBusy: false
    property bool promptDirty: false
    property int promptRevision: 0
    property int lastPromptWriteId: 0
    property int lastPromptWriteRevision: 0
    property string phase: "idle"
    property string error: ""
    property int copyRequestId: 0
    readonly property bool copyConfirmed: copyFeedback.running
    property var config: ({provider: "openai", providers: {}})
    property int sequence: 0
    property int generationId: 0
    signal captured(int requestId)
    signal replacementFinished(bool failed)
    signal settingsSaved()
    signal promptSaved(string text)
    signal rewriteFinished()
    signal copyFinished(bool failed)

    function send(type, fields) {
        var message = Object.assign({}, fields || {}, {type: type, id: ++sequence})
        if (!ready) { error = "The editor is starting. Try again in a moment."; return 0 }
        backend.write(JSON.stringify(message) + "\n")
        return sequence
    }
    function capture() {
        if (phase === "capturing" || phase === "replacing") return 0
        copyFeedback.stop(); copyRequestId = 0
        result = ""; error = ""; source = ""; canReplace = false; attemptedPrompt = ""
        persistInstruction("instruction_remember")
        generationId = 0
        var id = send("capture")
        if (id) phase = "capturing"
        return id
    }
    function generate() {
        persistInstruction("instruction_remember")
        copyFeedback.stop(); copyRequestId = 0
        error = ""; result = ""
        generationId = send("generate", {prompt: prompt})
        if (generationId) { attemptedPrompt = prompt; phase = "generating" }
    }
    function updatePrompt(value) {
        if (prompt === value) return
        prompt = value
        promptRevision++
        promptDirty = true
        rememberDelay.restart()
    }
    function persistInstruction(type) {
        rememberDelay.stop()
        if (!ready || !instructionsReady) return
        if (type === "instruction_remember" && !promptDirty) return
        if (type === "instruction_save") error = ""
        var id = send(type, {text: prompt})
        if (id) {
            lastPromptWriteId = id
            lastPromptWriteRevision = promptRevision
            if (type === "instruction_save") instructionBusy = true
        }
    }
    function removeInstruction(text) {
        error = ""
        if (send("instruction_remove", {text: text})) instructionBusy = true
    }
    function cancel() { send("cancel"); generationId = 0; phase = "idle" }
    function copyResult() {
        error = ""
        copyFeedback.stop()
        copyRequestId = send("copy")
        return copyRequestId
    }
    function replace() {
        error = ""
        if (send("replace")) phase = "replacing"
        else { phase = "idle"; replacementFinished(true) }
    }
    function save(provider, model, key, clearKey) {
        error = ""
        send("save", {provider: provider, model: model, key: key, clearKey: clearKey})
    }
    function receive(message) {
        if (message.type === "ready") { ready = true; config = message.data; return }
        if (["instructions", "instruction_remember", "instruction_save", "instruction_remove"].indexOf(message.type) !== -1) {
            if (message.type === "instruction_save" || message.type === "instruction_remove") instructionBusy = false
            if (message.error) {
                error = message.error
                if (message.type === "instructions") instructionsReady = true
                return
            }
            savedInstructions = message.data.saved
            if (message.type === "instructions") {
                if (!promptDirty) prompt = message.data.last
                instructionsReady = true
                if (promptDirty) persistInstruction("instruction_remember")
            } else if ((message.type === "instruction_remember" || message.type === "instruction_save")
                       && message.id === lastPromptWriteId && promptRevision === lastPromptWriteRevision) {
                promptDirty = false
            }
            if (message.type === "instruction_save") promptSaved(message.data.last)
            return
        }
        if (message.type === "generate" && message.id !== generationId) return
        if (message.type === "copy") {
            if (!copyRequestId || message.id !== copyRequestId) return
            copyRequestId = 0
        }
        if (message.error) {
            error = message.error
            phase = "idle"
            if (message.type === "capture") captured(message.id)
            if (message.type === "replace") replacementFinished(true)
            if (message.type === "copy") copyFinished(true)
            return
        }
        if (message.type === "capture") {
            source = message.data.text; sourceApp = message.data.app
            canReplace = message.data.canReplace; phase = "idle"
            captured(message.id)
        } else if (message.type === "generate") {
            result = message.data.text; phase = "idle"
            rewriteFinished()
        } else if (message.type === "settings" || message.type === "save") {
            config = message.data
            if (message.type === "save") settingsSaved()
        } else if (message.type === "copy") {
            copyFeedback.restart()
            copyFinished(false)
        } else if (message.type === "replace") {
            phase = "idle"
            replacementFinished(false)
        }
    }
    Process {
        id: backend
        command: ["python3", "-B", "-u", Qt.resolvedUrl("backend.py").toString().replace("file://", "")]
        running: true
        stdinEnabled: true
        stdout: SplitParser {
            onRead: data => {
                try { root.receive(JSON.parse(data)) }
                catch (e) { root.error = "The editor returned an invalid response." }
            }
        }
        onExited: {
            var replacing = root.phase === "replacing"
            root.ready = false; root.phase = "idle"
            root.instructionsReady = false; root.instructionBusy = false
            root.source = ""; root.result = ""; root.canReplace = false; root.attemptedPrompt = ""
            copyFeedback.stop(); root.copyRequestId = 0
            root.error = "The editor disconnected. Reopen the panel to try again."
            if (replacing) root.replacementFinished(true)
            restart.restart()
        }
    }
    Timer { id: copyFeedback; interval: 5000 }
    Timer { id: rememberDelay; interval: 250; onTriggered: root.persistInstruction("instruction_remember") }
    Timer { id: restart; interval: 1500; onTriggered: backend.running = true }
}
