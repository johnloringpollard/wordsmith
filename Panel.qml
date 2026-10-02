import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName: "io.github.johnloringpollard.rewerd"
    manageIpc: false
    readonly property var editor: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
    readonly property bool busy: editor && editor.phase !== "idle"
    readonly property bool useRewordIcon: true
    readonly property color ink: Color.popups.text
    readonly property color muted: Color.muted
    property bool showSettings: false
    property string settingsPage: "index"
    onSettingsPageChanged: Qt.callLater(root.focusSettingsPage)
    property bool showSavedPrompts: false
    property bool previewExpanded: false
    property int captureId: 0
    property bool awaitingReplacement: false
    property bool awaitingCopy: false
    property var providerIds: ["openai", "claude", "google", "cursor"]
    readonly property var providerKeyPages: ({
        openai: "https://platform.openai.com/api-keys",
        claude: "https://platform.claude.com/settings/keys",
        google: "https://aistudio.google.com/api-keys",
        cursor: "https://cursor.com/dashboard/api"
    })
    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    function open() {
        if (!editor || editor.phase === "capturing" || editor.phase === "replacing") return
        captureId = editor.capture()
        if (!captureId) controller.show()
    }
    function resetPreview() {
        previewExpanded = false
        selectionScroll.contentY = 0
    }
    function reconcileSavedPrompts() {
        var prompts = editor ? editor.savedInstructions : []
        for (var i = savedPromptModel.count - 1; i >= 0; --i) {
            if (prompts.indexOf(savedPromptModel.get(i).promptText) < 0) savedPromptModel.remove(i)
        }
        for (var target = 0; target < prompts.length; ++target) {
            var current = target
            while (current < savedPromptModel.count && savedPromptModel.get(current).promptText !== prompts[target]) ++current
            if (current === savedPromptModel.count) savedPromptModel.insert(target, {promptText: prompts[target]})
            else if (current !== target) savedPromptModel.move(current, target, 1)
        }
    }
    ListModel { id: savedPromptModel }
    Component.onCompleted: reconcileSavedPrompts()
    onEditorChanged: reconcileSavedPrompts()
    function resetSavedFeedback() {
        savedFeedbackAnimation.stop()
        savedFeedback.opacity = 0
        savedFeedback.scale = 1
    }
    function rewrite() {
        awaitingCopy = false
        resetSavedFeedback()
        showSavedPrompts = false
        editor.generate()
    }
    function acceptPrompt(event) {
        event.accepted = true
        if (event.isAutoRepeat || !opened || showSettings || !editor || busy || awaitingCopy) return
        if (!editor.ready || !editor.instructionsReady || !editor.source || !editor.prompt.trim()) return
        if (editor.result && editor.prompt === editor.attemptedPrompt) {
            if (editor.canReplace) replaceSelection()
            else {
                awaitingCopy = true
                if (!editor.copyResult()) awaitingCopy = false
            }
        } else rewrite()
    }
    function replaceSelection() {
        if (!editor || !editor.result || !editor.canReplace || busy) return
        awaitingReplacement = true
        editor.phase = "replacing"
        close()
        replaceDelay.restart()
    }
    function selectPrompt(text) {
        editor.updatePrompt(text)
        editor.persistInstruction("instruction_remember")
        showSavedPrompts = false
        instruction.forceActiveFocus()
    }
    function loadSettings() {
        if (!editor) return
        awaitingCopy = false
        editor.error = ""
        settingsPage = "index"
    }
    function focusSettingsPage() {
        if (!opened || !showSettings) return
        if (settingsPage === "defaults") defaultsInput.forceActiveFocus()
        else if (settingsPage === "provider") provider.forceActiveFocus()
        else settingsButton.forceActiveFocus()
    }
    function editProvider() {
        editor.error = ""
        provider.currentIndex = Math.max(0, providerIds.indexOf(editor.config.provider))
        loadProvider()
        settingsPage = "provider"
    }
    function editDefaults() {
        editor.error = ""
        defaultsInput.text = editor.config.defaultInstructions || ""
        settingsPage = "defaults"
    }
    function backSettings() {
        if (editor && editor.settingsBusy) return
        if (editor) editor.error = ""
        keyInput.text = ""
        defaultsInput.text = ""
        if (settingsPage === "index") showSettings = false
        else settingsPage = "index"
    }
    function loadProvider() {
        var entry = editor ? editor.config.providers[providerIds[provider.currentIndex]] : null
        modelInput.text = entry ? entry.model : ""
        keyInput.text = ""
    }
    onOpenedChanged: {
        if (!opened) {
            awaitingCopy = false
            resetSavedFeedback()
            resetPreview()
            keyInput.text = ""; defaultsInput.text = ""; settingsPage = "index"; showSettings = false; showSavedPrompts = false
            if (editor) editor.persistInstruction("instruction_remember")
        }
    }
    Connections {
        target: root.editor
        function onCaptured(requestId) {
            if (requestId === root.captureId) {
                root.controller.show()
            }
        }
        function onReplacementFinished(failed) {
            if (!root.awaitingReplacement) return
            root.awaitingReplacement = false
            if (failed) root.controller.show()
        }
        function onPromptSaved(text) {
            if (root.opened && !root.busy && root.editor.prompt === text) savedFeedbackAnimation.restart()
        }
        function onSourceChanged() {
            root.resetPreview()
        }
        function onSavedInstructionsChanged() {
            root.reconcileSavedPrompts()
        }
        function onPromptChanged() { root.resetSavedFeedback(); root.awaitingCopy = false }
        function onSettingsSaved() {
            keyInput.text = ""
            root.settingsPage = "index"
        }
        function onRewriteFinished() {
            if (root.opened && !root.showSettings) instruction.forceActiveFocus()
        }
        function onCopyFinished(failed) {
            if (!root.awaitingCopy) return
            root.awaitingCopy = false
            if (!failed) root.close()
        }
        function onReadyChanged() {
            if (!root.editor.ready) root.awaitingCopy = false
        }
    }
    component Label: Text {
        color: root.ink
        font.family: Style.font.family
        font.pixelSize: 13
        textFormat: Text.PlainText
        wrapMode: Text.WordWrap
    }
    component RewordIcon: Canvas {
        property color iconColor: root.ink
        implicitWidth: 24
        implicitHeight: 24
        antialiasing: true
        onIconColorChanged: requestPaint()
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.scale(width / 24, height / 24)
            ctx.strokeStyle = iconColor
            ctx.fillStyle = iconColor
            ctx.lineWidth = 1.65
            ctx.lineCap = "round"
            ctx.lineJoin = "round"
            ctx.beginPath()
            ctx.moveTo(3, 21)
            ctx.lineTo(6, 10)
            ctx.lineTo(12, 6)
            ctx.lineTo(18, 12)
            ctx.lineTo(14, 18)
            ctx.closePath()
            ctx.stroke()
            ctx.beginPath()
            ctx.moveTo(12, 6)
            ctx.lineTo(13.5, 4.5)
            ctx.lineTo(19.5, 10.5)
            ctx.lineTo(18, 12)
            ctx.stroke()
            ctx.beginPath()
            ctx.moveTo(3.5, 20.5)
            ctx.lineTo(9.5, 14.5)
            ctx.stroke()
            ctx.beginPath()
            ctx.arc(10.5, 13.5, 1.4, 0, Math.PI * 2)
            ctx.stroke()
            ctx.beginPath()
            ctx.moveTo(20, 1)
            ctx.lineTo(20.8, 3.2)
            ctx.lineTo(23, 4)
            ctx.lineTo(20.8, 4.8)
            ctx.lineTo(20, 7)
            ctx.lineTo(19.2, 4.8)
            ctx.lineTo(17, 4)
            ctx.lineTo(19.2, 3.2)
            ctx.closePath()
            ctx.fill()
        }
        Accessible.ignored: true
    }
    component Keycap: Rectangle {
        id: keycap
        required property string label
        implicitWidth: Math.ceil(keyLabel.implicitWidth) + 12
        implicitHeight: 24
        radius: 4
        color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.02)
        border.width: 1
        border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.15)
        Accessible.role: Accessible.StaticText
        Accessible.name: label
        Text {
            id: keyLabel
            anchors.centerIn: parent
            text: keycap.label
            color: root.muted
            font.family: "monospace"
            font.pixelSize: 11
            font.weight: Font.Normal
            font.letterSpacing: 0.2
            Accessible.ignored: true
        }
    }
    component Action: Controls.Button {
        id: action
        property color textColor: root.ink
        padding: 10
        font.family: Style.font.family
        font.pixelSize: 12
        contentItem: Text {
            text: action.text; color: action.textColor
            font: action.font; horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 7
            color: action.down ? Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.18)
                               : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, action.hovered ? 0.13 : 0.07)
            border.width: action.activeFocus ? 2 : 1
            border.color: action.activeFocus ? Color.accent : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.15)
        }
        opacity: enabled ? 1 : 0.4
    }
    component Link: Controls.Button {
        id: link
        property color textColor: Color.accent
        padding: 3
        font.underline: true
        font.family: Style.font.family
        font.pixelSize: 12
        contentItem: Text {
            text: link.text
            textFormat: Text.PlainText
            font: link.font
            color: link.textColor
            wrapMode: Text.Wrap
        }
        background: Rectangle {
            color: "transparent"
            radius: 3
            border.width: link.activeFocus ? 1 : 0
            border.color: Color.accent
        }
        opacity: enabled ? 1 : 0.4
        HoverHandler { cursorShape: Qt.PointingHandCursor }
    }
    component Field: Controls.TextField {
        color: root.ink
        placeholderTextColor: root.muted
        font.family: Style.font.family
        font.pixelSize: 13
        padding: 10
        selectByMouse: true
        background: Rectangle {
            radius: 7
            color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.04)
            border.width: 1
            border.color: parent.activeFocus ? Color.accent : root.muted
        }
    }
    BarIconButton {
        id: button
        bar: root.bar
        text: "󰦨"
        iconComponent: root.useRewordIcon ? rewordBarIcon : null
        tooltipText: "Reword"
        onPressed: root.toggle()
    }
    Component {
        id: rewordBarIcon
        RewordIcon {
            iconColor: button.active && button.useActiveColor ? button.activeColor : button.foreground
        }
    }
    Timer {
        id: replaceDelay
        interval: 200
        onTriggered: root.editor.replace()
    }
    SequentialAnimation {
        id: savedFeedbackAnimation
        ParallelAnimation {
            NumberAnimation { target: savedFeedback; property: "opacity"; from: 0; to: 1; duration: 140; easing.type: Easing.OutCubic }
            NumberAnimation { target: savedFeedback; property: "scale"; from: 0.9; to: 1; duration: 180; easing.type: Easing.OutBack }
        }
        PauseAnimation { duration: 1800 }
        NumberAnimation { target: savedFeedback; property: "opacity"; to: 0; duration: 180; easing.type: Easing.InCubic }
    }
    KeyboardPanel {
        id: popup
        anchorItem: button
        owner: root
        bar: root.bar
        open: root.opened
        focusTarget: !root.showSettings ? instruction : root.settingsPage === "defaults" ? defaultsInput
            : root.settingsPage === "provider" ? provider : settingsButton
        contentWidth: fittedContentWidth(500)
        contentHeight: root.showSettings ? (root.settingsPage === "index"
            ? fittedContentHeight(headerRow.implicitHeight + settingsIndex.implicitHeight + 12
                + (statusMessage.visible ? statusMessage.implicitHeight + 12 : 0))
            : cappedContentHeight(550))
            : fittedContentHeight(headerRow.implicitHeight + mainContent.implicitHeight + 12
                + (statusMessage.visible ? statusMessage.implicitHeight + 12 : 0))
        padding: 20

        FocusScope {
            anchors.fill: parent
            Keys.onEscapePressed: root.close()
            ColumnLayout {
                anchors.fill: parent
                spacing: 12
                RowLayout {
                    id: headerRow
                    Layout.fillWidth: true
                    spacing: 9
                    Item {
                        Layout.preferredWidth: 24
                        Layout.preferredHeight: 24
                        RewordIcon { anchors.fill: parent; visible: root.useRewordIcon }
                        Label { anchors.centerIn: parent; text: button.text; font.pixelSize: 22; visible: !root.useRewordIcon; Accessible.ignored: true }
                    }
                    Label { text: "Reword"; font.pixelSize: 20; font.weight: Font.DemiBold; Layout.fillWidth: true }
                    Action {
                        id: settingsButton
                        objectName: "settingsButton"
                        textColor: root.showSettings ? root.ink : root.muted
                        text: root.showSettings ? "‹ Back" : "\uf013"
                        font.pixelSize: root.showSettings ? 12 : 18
                        font.underline: root.showSettings && (hovered || visualFocus)
                        HoverHandler { cursorShape: Qt.PointingHandCursor }
                        padding: 8
                        Layout.minimumWidth: 36
                        Layout.minimumHeight: 36
                        Layout.preferredWidth: root.showSettings ? -1 : 36
                        Layout.preferredHeight: root.showSettings ? -1 : 36
                        contentItem: Item {
                            implicitWidth: settingsText.implicitWidth
                            implicitHeight: settingsText.implicitHeight
                            FontMetrics { id: settingsMetrics; font: settingsButton.font }
                            Text {
                                id: settingsText
                                readonly property rect inkBounds: settingsMetrics.tightBoundingRect(text)
                                text: settingsButton.text
                                font: settingsButton.font
                                color: settingsButton.textColor
                                x: root.showSettings ? (parent.width - width) / 2
                                                     : (parent.width - inkBounds.width) / 2 - inkBounds.x
                                y: root.showSettings ? (parent.height - height) / 2
                                                     : (parent.height - inkBounds.height) / 2 - inkBounds.y - baselineOffset
                            }
                        }
                        Accessible.name: root.showSettings ? "Back" : "Settings"
                        Controls.ToolTip.text: root.showSettings ? "Back" : "Settings"
                        Controls.ToolTip.visible: hovered
                        Controls.ToolTip.delay: 600
                        background: Rectangle {
                            radius: 7
                            color: root.showSettings ? "transparent" : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, settingsButton.down ? 0.13 : settingsButton.hovered || settingsButton.visualFocus ? 0.07 : 0)
                        }
                        enabled: !root.busy && !(root.editor && root.editor.settingsBusy)
                        onClicked: {
                            if (root.showSettings) root.backSettings()
                            else { root.showSettings = true; root.loadSettings() }
                        }
                    }
                }
                Label {
                    id: statusMessage
                    Layout.fillWidth: true
                    visible: root.editor && !!root.editor.error
                    text: root.editor ? root.editor.error : ""
                    color: root.editor && root.editor.error ? Color.urgent : root.muted
                    font.pixelSize: 12
                }
                Controls.ScrollView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: parent.width
                        spacing: 12
                        ColumnLayout {
                            id: mainContent
                            visible: !root.showSettings
                            Layout.fillWidth: true
                            spacing: 10
                            FocusScope {
                                id: selectionPreview
                                Layout.fillWidth: true
                                Layout.bottomMargin: 6
                                implicitHeight: root.previewExpanded ? Math.min(112, selectionText.implicitHeight) : collapsedSelection.implicitHeight
                                visible: root.editor && !!root.editor.source
                                activeFocusOnTab: true
                                Accessible.role: Accessible.Button
                                Accessible.name: "Selected text"
                                Accessible.description: root.previewExpanded ? "Collapse selected text" : "Expand selected text"
                                Accessible.onPressAction: root.previewExpanded = !root.previewExpanded
                                Keys.onSpacePressed: root.previewExpanded = !root.previewExpanded
                                Keys.onReturnPressed: root.previewExpanded = !root.previewExpanded
                                Keys.onEnterPressed: root.previewExpanded = !root.previewExpanded
                                Label {
                                    id: collapsedSelection
                                    anchors.fill: parent
                                    visible: !root.previewExpanded
                                    text: root.editor ? root.editor.source.replace(/\s+/g, " ").trim() : ""
                                    color: root.muted
                                    font.pixelSize: 12
                                    font.underline: selectionPreview.activeFocus
                                    wrapMode: Text.NoWrap
                                    elide: Text.ElideRight
                                }
                                Flickable {
                                    id: selectionScroll
                                    anchors.fill: parent
                                    visible: root.previewExpanded
                                    contentWidth: width
                                    contentHeight: selectionText.implicitHeight
                                    boundsBehavior: Flickable.StopAtBounds
                                    clip: true
                                    Controls.ScrollBar.vertical: Controls.ScrollBar {}
                                    Label {
                                        id: selectionText
                                        width: selectionScroll.width - 10
                                        text: root.editor ? root.editor.source : ""
                                        color: root.muted
                                        font.pixelSize: 12
                                        font.underline: selectionPreview.activeFocus
                                        wrapMode: Text.Wrap
                                    }
                                }
                                TapHandler {
                                    parent: root.previewExpanded ? selectionScroll : selectionPreview
                                    onTapped: {
                                        selectionPreview.forceActiveFocus()
                                        root.previewExpanded = !root.previewExpanded
                                    }
                                }
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                            }
                            Label { text: "PROMPT"; font.pixelSize: 10; color: root.muted }
                            Field {
                                id: instruction
                                Layout.fillWidth: true
                                text: root.editor ? root.editor.prompt : "Reword for clarity and keep it concise. No em dashes. Rarely include an emoji."
                                enabled: root.editor && root.editor.ready && root.editor.instructionsReady && !root.busy
                                maximumLength: 8000
                                Accessible.name: "Rewrite prompt"
                                onTextEdited: if (root.editor) root.editor.updatePrompt(text)
                                Keys.onReturnPressed: event => root.acceptPrompt(event)
                                Keys.onEnterPressed: event => root.acceptPrompt(event)
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Link {
                                    text: root.showSavedPrompts ? "Saved prompts ↑" : "Saved prompts"
                                    textColor: root.muted
                                    background: null
                                    font.weight: activeFocus ? Font.DemiBold : Font.Normal
                                    enabled: root.editor && root.editor.instructionsReady && !root.busy
                                    onClicked: root.showSavedPrompts = !root.showSavedPrompts
                                    Accessible.name: "Saved prompts"
                                    Accessible.description: root.showSavedPrompts ? "Hide saved prompts" : "Show saved prompts"
                                }
                                Link {
                                    text: "Add"
                                    visible: root.editor && !!root.editor.prompt.trim()
                                        && root.editor.prompt === root.editor.attemptedPrompt
                                        && root.editor.savedInstructions.indexOf(root.editor.prompt) < 0
                                    enabled: root.editor && root.editor.ready && root.editor.instructionsReady && !root.busy && !root.editor.instructionBusy
                                    Accessible.name: "Add current prompt to saved prompts"
                                    onClicked: root.editor.persistInstruction("instruction_save")
                                }
                                Rectangle {
                                    id: savedFeedback
                                    Layout.preferredWidth: 62
                                    Layout.preferredHeight: 24
                                    opacity: 0
                                    radius: 12
                                    color: Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.12)
                                    Label {
                                        anchors.centerIn: parent
                                        text: "✓ Saved"
                                        color: Color.accent
                                        font.pixelSize: 11
                                    }
                                    Accessible.ignored: opacity === 0
                                    Accessible.name: "Prompt saved"
                                    Accessible.role: Accessible.StaticText
                                }
                                Item { Layout.fillWidth: true }
                                Action {
                                    visible: root.editor && root.editor.phase === "generating"
                                    text: "Cancel"; onClicked: root.editor.cancel()
                                }
                                Action {
                                    id: generateButton
                                    text: root.editor && root.editor.phase === "generating" ? "Rewriting…" : "Rewrite"
                                    enabled: root.editor && root.editor.ready && root.editor.instructionsReady && !!root.editor.source && !!instruction.text.trim() && !root.busy
                                    onClicked: root.rewrite()
                                }
                            }
                            Rectangle {
                                id: savedPromptsCard
                                readonly property real expandedHeight: Math.min(150, Math.max(savedPromptsList.contentHeight, savedPromptModel.count === 0 ? emptySavedPrompts.implicitHeight + 16 : 0) + 16)
                                property real reveal: root.showSavedPrompts ? 1 : 0
                                Layout.fillWidth: true
                                Layout.preferredHeight: expandedHeight * reveal
                                visible: reveal > 0
                                enabled: root.showSavedPrompts
                                opacity: reveal
                                clip: true
                                radius: 9
                                color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.055)
                                border.width: 1
                                border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.13)
                                Behavior on reveal { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                                Controls.ScrollView {
                                    x: 8; y: 8
                                    width: parent.width - 16
                                    height: savedPromptsCard.expandedHeight - 16
                                    contentWidth: availableWidth
                                    clip: true
                                    ListView {
                                        id: savedPromptsList
                                        model: savedPromptModel
                                        spacing: 4
                                        clip: true
                                        displaced: Transition {
                                            NumberAnimation { properties: "x,y"; duration: 180; easing.type: Easing.InOutCubic }
                                        }
                                        delegate: Rectangle {
                                            required property string promptText
                                            id: savedPromptRow
                                            property bool removing: false
                                            enabled: !removing
                                            clip: true
                                            ListView.delayRemove: removing
                                            ListView.onRemove: {
                                                removing = true
                                                removeAnimation.start()
                                            }
                                            SequentialAnimation {
                                                id: removeAnimation
                                                ParallelAnimation {
                                                    NumberAnimation { target: savedPromptRow; property: "opacity"; to: 0; duration: 160 }
                                                    NumberAnimation { target: savedPromptRow; property: "height"; to: 0; duration: 180; easing.type: Easing.InOutCubic }
                                                }
                                                PropertyAction { target: savedPromptRow; property: "removing"; value: false }
                                            }
                                            readonly property bool selected: root.editor && root.editor.prompt === promptText
                                            width: savedPromptsList.width
                                            implicitHeight: savedPromptActions.implicitHeight
                                            radius: 6
                                            color: selected
                                                ? Qt.rgba(Color.accent.r, Color.accent.g, Color.accent.b, 0.13)
                                                : Qt.rgba(root.ink.r, root.ink.g, root.ink.b, usePrompt.hovered || removePrompt.hovered ? 0.07 : 0)
                                            Behavior on color { ColorAnimation { duration: 100 } }
                                            RowLayout {
                                                id: savedPromptActions
                                                width: parent.width
                                                spacing: 4
                                                Controls.Button {
                                                    id: usePrompt
                                                    Layout.fillWidth: true
                                                    Layout.minimumWidth: 0
                                                    padding: 9
                                                    text: savedPromptRow.promptText
                                                    enabled: root.editor && !root.busy && !root.editor.instructionBusy
                                                    contentItem: Label {
                                                        text: usePrompt.text
                                                        wrapMode: Text.Wrap
                                                        font.pixelSize: 12
                                                    }
                                                    background: Rectangle {
                                                        color: "transparent"
                                                        radius: 6
                                                        border.width: usePrompt.activeFocus ? 1 : 0
                                                        border.color: Color.accent
                                                    }
                                                    opacity: enabled ? 1 : 0.4
                                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                                    Accessible.name: "Use prompt: " + text
                                                    onClicked: root.selectPrompt(savedPromptRow.promptText)
                                                }
                                                Controls.Button {
                                                    id: removePrompt
                                                    text: "Remove"
                                                    Layout.alignment: Qt.AlignTop
                                                    Layout.topMargin: 4
                                                    Layout.rightMargin: 4
                                                    padding: 5
                                                    enabled: root.editor && root.editor.ready && !root.busy && !root.editor.instructionBusy
                                                    contentItem: Label {
                                                        text: removePrompt.text
                                                        color: removePrompt.hovered || removePrompt.activeFocus ? root.ink : root.muted
                                                        font.pixelSize: 11
                                                        Behavior on color { ColorAnimation { duration: 100 } }
                                                    }
                                                    background: Rectangle {
                                                        radius: 4
                                                        color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, removePrompt.hovered ? 0.09 : 0)
                                                        border.width: removePrompt.activeFocus ? 1 : 0
                                                        border.color: Color.accent
                                                        Behavior on color { ColorAnimation { duration: 100 } }
                                                    }
                                                    opacity: enabled ? 1 : 0.4
                                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                                    Accessible.name: "Remove saved prompt: " + savedPromptRow.promptText
                                                    onClicked: root.editor.removeInstruction(savedPromptRow.promptText)
                                                }
                                            }
                                        }
                                    }
                                }
                                Label {
                                    id: emptySavedPrompts
                                    x: 16; y: 16
                                    width: parent.width - 32
                                    visible: opacity > 0
                                    opacity: savedPromptModel.count === 0 ? 1 : 0
                                    text: "No saved prompts yet. Rewrite with a prompt, then click Add to save it."
                                    color: root.muted
                                    font.pixelSize: 12
                                    Behavior on opacity {
                                        SequentialAnimation {
                                            PauseAnimation { duration: savedPromptModel.count === 0 ? 180 : 0 }
                                            NumberAnimation { duration: 100 }
                                        }
                                    }
                                }
                            }
                            ColumnLayout {
                                visible: root.editor && !!root.editor.result
                                Layout.fillWidth: true
                                spacing: 10
                                Label { text: "REWRITTEN TEXT"; color: root.muted; font.pixelSize: 10 }
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 168
                                    radius: 8
                                    color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.04)
                                    border.width: 1; border.color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.1)
                                    Controls.ScrollView {
                                        anchors.fill: parent; anchors.margins: 6; clip: true
                                        Controls.TextArea {
                                            text: root.editor ? root.editor.result : ""
                                            color: root.ink; font.pixelSize: 13
                                            font.family: Style.font.family
                                            wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                                            readOnly: true; selectByMouse: true
                                            background: null
                                            Accessible.name: "AI rewrite"
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Item { Layout.fillWidth: true }
                                    Action {
                                        text: "Replace selection"
                                        visible: root.editor && root.editor.canReplace
                                        enabled: root.editor && !!root.editor.result && root.editor.canReplace && !root.busy
                                        onClicked: root.replaceSelection()
                                    }
                                    Action {
                                        id: copyButton
                                        text: root.editor && root.editor.copyConfirmed ? "Copied!" : "Copy rewrite"
                                        Layout.minimumWidth: Math.ceil(copyButtonWidth.implicitWidth + 2 * padding)
                                        Label { id: copyButtonWidth; text: "Copy rewrite"; font: copyButton.font; visible: false }
                                        enabled: root.editor && !!root.editor.result && !root.busy
                                        onClicked: { root.awaitingCopy = false; root.editor.copyResult() }
                                    }
                                }
                            }
                        }
                        ColumnLayout {
                            id: settingsIndex
                            visible: root.showSettings && root.settingsPage === "index"
                            Layout.fillWidth: true
                            spacing: 18
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 16
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    Label { text: "AI provider"; font.pixelSize: 15 }
                                    Label {
                                        Layout.fillWidth: true
                                        color: root.muted
                                        text: {
                                            if (!root.editor) return ""
                                            var id = root.editor.config.provider
                                            var entry = root.editor.config.providers[id]
                                            var name = ["OpenAI", "Claude", "Google Gemini", "Cursor"][root.providerIds.indexOf(id)]
                                            return name + (entry ? " · " + entry.model : "")
                                        }
                                    }
                                }
                                Action {
                                    objectName: "providerEditButton"
                                    text: "Edit"
                                    enabled: root.editor && root.editor.ready && !root.editor.settingsBusy
                                    Accessible.name: "Edit AI provider"
                                    onClicked: root.editProvider()
                                }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: root.muted; opacity: 0.25 }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 16
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    Label { text: "Writing defaults"; font.pixelSize: 15 }
                                    Label {
                                        Layout.fillWidth: true
                                        color: root.muted
                                        maximumLineCount: 2
                                        elide: Text.ElideRight
                                        text: root.editor && root.editor.config.defaultInstructions && root.editor.config.defaultInstructions.trim()
                                            ? root.editor.config.defaultInstructions : "No writing defaults"
                                    }
                                }
                                Action {
                                    objectName: "defaultsEditButton"
                                    text: "Edit"
                                    enabled: root.editor && root.editor.ready && !root.editor.settingsBusy
                                    Accessible.name: "Edit writing defaults"
                                    onClicked: root.editDefaults()
                                }
                            }
                            Rectangle { Layout.fillWidth: true; height: 1; color: root.muted; opacity: 0.25 }
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.bottomMargin: 6
                                spacing: 8
                                Label { text: "Keyboard shortcut"; font.pixelSize: 15; Layout.fillWidth: true }
                                Keycap { label: "SUPER" }
                                Label { text: "+"; color: root.muted; Accessible.ignored: true }
                                Keycap { label: "SHIFT" }
                                Label { text: "+"; color: root.muted; Accessible.ignored: true }
                                Keycap { label: "R" }
                            }
                        }
                        ColumnLayout {
                            visible: root.showSettings && root.settingsPage === "provider"
                            enabled: root.editor && root.editor.ready && !root.editor.settingsBusy
                            Layout.fillWidth: true
                            spacing: 12
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12
                                Label { text: "AI provider"; font.pixelSize: 15; Layout.fillWidth: true }
                                Controls.Button {
                                    id: apiKeyLink
                                    text: "Get your " + provider.currentText + " API key ↗"
                                    Layout.maximumWidth: popup.contentWidth * 0.58
                                    padding: 0
                                    topPadding: 2
                                    bottomPadding: 2
                                    background: null
                                    contentItem: Text {
                                        text: apiKeyLink.text
                                        wrapMode: Text.WordWrap
                                        horizontalAlignment: Text.AlignRight
                                        color: Color.accent
                                        font.family: Style.font.family
                                        font.pixelSize: 12
                                        font.underline: true
                                    }
                                    HoverHandler { cursorShape: Qt.PointingHandCursor }
                                    Accessible.name: "Open " + provider.currentText + " API key page in your browser"
                                    onClicked: Qt.openUrlExternally(root.providerKeyPages[root.providerIds[provider.currentIndex]])
                                }
                            }
                            Controls.ComboBox {
                                id: provider
                                objectName: "provider"
                                Layout.fillWidth: true
                                model: ["OpenAI", "Claude", "Google Gemini", "Cursor"]
                                padding: 10
                                rightPadding: 32
                                font.family: Style.font.family
                                font.pixelSize: 13
                                contentItem: Text {
                                    text: provider.displayText
                                    font: provider.font
                                    color: root.ink
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }
                                indicator: Text {
                                    x: provider.width - width - 12
                                    y: (provider.height - height) / 2
                                    text: "▾"
                                    color: root.ink
                                    font.pixelSize: 14
                                }
                                background: Rectangle {
                                    implicitHeight: 38
                                    radius: 7
                                    color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.04)
                                    border.width: 1
                                    border.color: provider.activeFocus ? Color.accent : root.muted
                                }
                                popup: Controls.Popup {
                                    y: provider.height + 4
                                    width: provider.width
                                    padding: 5
                                    implicitHeight: contentItem.implicitHeight + padding * 2
                                    contentItem: ListView {
                                        implicitHeight: contentHeight
                                        model: provider.popup.visible ? provider.delegateModel : null
                                        currentIndex: provider.highlightedIndex
                                        clip: true
                                    }
                                    background: Rectangle {
                                        radius: 7
                                        color: Color.background
                                        border.width: 1
                                        border.color: root.muted
                                    }
                                }
                                delegate: Controls.ItemDelegate {
                                    width: provider.width - 10
                                    padding: 10
                                    highlighted: provider.highlightedIndex === index
                                    contentItem: Text {
                                        text: modelData
                                        font: provider.font
                                        color: root.ink
                                    }
                                    background: Rectangle {
                                        radius: 5
                                        color: parent.highlighted
                                            ? Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.12)
                                            : "transparent"
                                    }
                                }
                                onActivated: root.loadProvider()
                                Accessible.name: "AI provider"
                            }
                            Label { text: "Model" }
                            Field { id: modelInput; objectName: "modelInput"; Layout.fillWidth: true; placeholderText: "Model ID"; Accessible.name: "Model ID" }
                            Label { text: "API key" }
                            Field {
                                id: keyInput
                                objectName: "keyInput"
                                Layout.fillWidth: true
                                echoMode: TextInput.Password
                                placeholderText: {
                                    var entry = root.editor ? root.editor.config.providers[root.providerIds[provider.currentIndex]] : null
                                    return entry && entry.hasKey ? "Key saved. Leave blank to keep it." : "Paste your API key"
                                }
                                Accessible.name: "API key"
                            }
                            Label {
                                Layout.fillWidth: true
                                text: provider.currentIndex === 3
                                    ? "Use a Cursor User API Key from your dashboard. Cursor CLI must be installed."
                                    : "Use an API key from your provider's developer console."
                                color: root.muted; font.pixelSize: 12
                            }
                            Label {
                                Layout.fillWidth: true
                                text: "Keys are saved in a private file on this computer. Reword sends the selected text and prompt to your chosen provider."
                                color: root.muted; font.pixelSize: 11
                            }
                            RowLayout {
                                Action {
                                    objectName: "providerSaveButton"
                                    text: "Save"
                                    enabled: modelInput.text.trim().length > 0
                                    onClicked: root.editor.save(root.providerIds[provider.currentIndex], modelInput.text.trim(), keyInput.text.trim(), false)
                                }
                                Action {
                                    text: "Remove key"
                                    onClicked: root.editor.save(root.providerIds[provider.currentIndex], modelInput.text.trim(), "", true)
                                }
                            }
                        }
                        ColumnLayout {
                            visible: root.showSettings && root.settingsPage === "defaults"
                            enabled: root.editor && root.editor.ready && !root.editor.settingsBusy
                            Layout.fillWidth: true
                            spacing: 12
                            Label { text: "Writing defaults"; font.pixelSize: 15 }
                            Label {
                                Layout.fillWidth: true
                                text: "Applied to every rewrite. Your rewrite prompt can override these preferences. Leave blank to turn them off."
                                color: root.muted
                            }
                            Controls.ScrollView {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 290
                                clip: true
                                Controls.TextArea {
                                    id: defaultsInput
                                    objectName: "defaultsInput"
                                    color: root.ink
                                    font.family: Style.font.family
                                    font.pixelSize: 13
                                    padding: 12
                                    wrapMode: TextEdit.Wrap
                                    textFormat: TextEdit.PlainText
                                    selectByMouse: true
                                    Accessible.name: "Writing defaults"
                                    background: Rectangle {
                                        radius: 7
                                        color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.04)
                                        border.width: 1
                                        border.color: defaultsInput.activeFocus ? Color.accent : root.muted
                                    }
                                }
                            }
                            Action {
                                objectName: "defaultsSaveButton"
                                Layout.alignment: Qt.AlignRight
                                text: "Save"
                                enabled: defaultsInput.text.length <= 8000
                                onClicked: root.editor.saveDefaults(defaultsInput.text)
                            }
                        }
                    }
                }
            }
        }
    }
}
