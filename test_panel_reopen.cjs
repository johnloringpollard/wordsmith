const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

// Run the QML JavaScript itself, with only the Qt signals and backend replaced.
function qmlFunction(file, name, indent = 4) {
    const source = fs.readFileSync(path.join(__dirname, file), 'utf8');
    const spaces = ' '.repeat(indent);
    const match = source.match(new RegExp(
        `^${spaces}function ${name}\\([^\\n]*\\) \\{\\n[\\s\\S]*?^${spaces}\\}`, 'm'));
    assert.ok(match, `${file} must define ${name}`);
    return match[0];
}

function harness(phase = 'idle') {
    const messages = [];
    let shown = 0;
    const saved = [];
    let closed = 0;
    let replacements = 0;
    let focused = 0;
    const editor = vm.createContext({
        ready: true, settingsBusy: false, config: {provider: "openai", defaultInstructions: "No em dashes.", providers: {openai: {model: "original-model", hasKey: true}}}, instructionsReady: true, savedInstructions: [], instructionBusy: false,
        promptDirty: false, promptRevision: 0, lastPromptWriteId: 0, lastPromptWriteRevision: 0, phase, source: 'Previous selection', result: 'Previous rewrite',
        prompt: 'Previous instruction', attemptedPrompt: 'Previous instruction', error: '', notice: '', canReplace: true,
        sourceApp: 'chrome', sequence: 7, generationId: 7, copyRequestId: 0,
        copyFeedback: { running: false, stop() { this.running = false; }, restart() { this.running = true; } },
        rememberDelay: { restart() {}, stop() {} },
        backend: { write: value => messages.push(JSON.parse(value)) },
        captured: id => panel.onCaptured(id),
        replacementFinished() {}, settingsSaved() {}, promptSaved: text => saved.push(text),
        rewriteFinished: () => panel.onRewriteFinished(),
        copyFinished: failed => panel.onCopyFinished(failed),
    });
    for (const name of ['send', 'capture', 'generate', 'receive', 'updatePrompt', 'persistInstruction', 'removeInstruction', 'copyResult', 'cancel', 'save', 'saveDefaults']) {
        vm.runInContext(qmlFunction('Service.qml', name), editor);
    }
    const feedback = { opacity: 1, scale: 0.9 };
    let feedbackStarts = 0;
    let feedbackStops = 0;
    const rows = [];
    const modelChanges = [];
    const savedPromptModel = {
        get count() { return rows.length; },
        get(index) { return rows[index]; },
        insert(index, row) { rows.splice(index, 0, row); modelChanges.push(['insert', index]); },
        remove(index) { rows.splice(index, 1); modelChanges.push(['remove', index]); },
        move(from, to, count) {
            assert.equal(count, 1);
            rows.splice(to, 0, rows.splice(from, 1)[0]);
            modelChanges.push(['move', from, to]);
        },
    };
    const panel = vm.createContext({
        editor, captureId: 0, opened: true, busy: false,
        showSettings: false, awaitingCopy: false, awaitingReplacement: false,
        instruction: { forceActiveFocus() { focused++; } },
        replaceDelay: { restart() { replacements++; } },
        close() { this.opened = false; closed++; },
        savedFeedback: feedback, savedPromptModel, previewExpanded: false,
        selectionScroll: { contentY: 0 }, keyInput: { text: '' },
        settingsPage: 'index', providerIds: ['openai', 'claude', 'google', 'cursor'],
        provider: { currentIndex: 0 }, modelInput: { text: '' }, defaultsInput: { text: '' },
        savedFeedbackAnimation: { restart() { feedbackStarts++; }, stop() { feedbackStops++; } },
        controller: { show() { shown++; } },
    });
    panel.root = panel;
    for (const name of ['resetPreview', 'reconcileSavedPrompts', 'acceptPrompt', 'replaceSelection', 'rewrite', 'loadSettings', 'loadProvider', 'editProvider', 'editDefaults', 'backSettings']) {
        vm.runInContext(qmlFunction('Panel.qml', name), panel);
    }
    for (const name of ['onSourceChanged', 'onSavedInstructionsChanged', 'onRewriteFinished', 'onCopyFinished', 'onReadyChanged', 'onSettingsSaved']) {
        vm.runInContext(qmlFunction('Panel.qml', name, 8), panel);
    }
    editor.settingsSaved = () => panel.onSettingsSaved();
    let savedInstructions = editor.savedInstructions;
    Object.defineProperty(editor, 'savedInstructions', {
        get() { return savedInstructions; },
        set(value) { savedInstructions = value; panel.onSavedInstructionsChanged(); },
    });
    let source = editor.source;
    Object.defineProperty(editor, 'source', {
        get() { return source; },
        set(value) {
            if (source === value) return;
            source = value;
            panel.onSourceChanged();
        },
    });
    vm.runInContext(qmlFunction('Panel.qml', 'resetSavedFeedback'), panel);
    vm.runInContext(qmlFunction('Panel.qml', 'onPromptSaved', 8), panel);
    vm.runInContext(qmlFunction('Panel.qml', 'open'), panel);
    vm.runInContext(qmlFunction('Panel.qml', 'onCaptured', 8), panel);
    return { editor, panel, messages, saved, rows, modelChanges, feedback, feedbackStarts: () => feedbackStarts, feedbackStops: () => feedbackStops, shown: () => shown, closed: () => closed, replacements: () => replacements, focused: () => focused };
}

for (const phase of ['idle', 'generating']) {
    test(`reopening from ${phase} captures fresh text and discards the old rewrite`, () => {
        const { editor, panel, messages, shown } = harness(phase);
        if (phase === 'generating') editor.result = '';
        const oldGenerationId = editor.generationId;
        panel.open();
        assert.deepEqual(messages, [{ type: 'capture', id: 8 }]);
        assert.equal(panel.captureId, 8);
        assert.equal(editor.phase, 'capturing');
        assert.equal(editor.source, 'Previous selection');
        assert.equal(editor.result, phase === 'generating' ? '' : 'Previous rewrite');
        assert.equal(editor.prompt, 'Previous instruction');
        assert.equal(editor.canReplace, false);
        assert.equal(editor.generationId, oldGenerationId);
        assert.equal(editor.attemptedPrompt, 'Previous instruction');
        assert.equal(shown(), 0);

        editor.receive({ type: 'capture', id: 8,
            data: { text: 'New Chrome selection', app: 'chrome', canReplace: true, result: '', retained: false } });
        assert.equal(editor.source, 'New Chrome selection');
        assert.equal(editor.attemptedPrompt, '');
        assert.equal(editor.result, '');
        assert.equal(editor.phase, 'idle');
        assert.equal(shown(), 1);
        editor.receive({ type: 'generate', id: oldGenerationId, data: { text: 'Even later rewrite' } });
        assert.equal(editor.source, 'New Chrome selection');
        assert.equal(editor.attemptedPrompt, '');
        assert.equal(editor.result, '');
    });
}

for (const phase of ['capturing', 'replacing']) {
    test(`reopening during ${phase} preserves the operation`, () => {
        const { editor, panel, messages, shown } = harness(phase);
        panel.open();
        assert.deepEqual(messages, []);
        assert.equal(editor.phase, phase);
        assert.equal(editor.source, 'Previous selection');
        assert.equal(editor.result, 'Previous rewrite');
        assert.equal(editor.prompt, 'Previous instruction');
        assert.equal(editor.generationId, 7);
        assert.equal(shown(), 0);
    });
}

test('opening without a service does nothing', () => {
    const { panel, messages, shown } = harness();
    panel.editor = null;
    panel.open();
    assert.deepEqual(messages, []);
    assert.equal(shown(), 0);
});

test('capture startup failure opens the panel to show its error', () => {
    const { editor, panel, messages, shown } = harness();
    editor.ready = false;
    panel.open();
    assert.deepEqual(messages, []);
    assert.equal(panel.captureId, 0);
    assert.equal(editor.result, 'Previous rewrite');
    assert.match(editor.error, /starting/);
    assert.equal(shown(), 1);
});

test('an unrelated capture notification does not open this panel', () => {
    const { panel, shown } = harness();
    panel.open();
    panel.onCaptured(99);
    assert.equal(shown(), 0);
});

test('startup loads the remembered instruction and saved list', () => {
    const { editor } = harness();
    editor.instructionsReady = false;
    editor.receive({ type: 'instructions', data: { last: 'Use my tone', saved: ['Shorten this'] } });
    assert.equal(editor.prompt, 'Use my tone');
    assert.equal(editor.savedInstructions[0], 'Shorten this');
    assert.equal(editor.instructionsReady, true);
});

test('capture flushes a draft before reading the next selection', () => {
    const { editor, panel, messages } = harness();
    editor.updatePrompt('Make it warmer');
    panel.open();
    assert.deepEqual(messages.map(m => m.type), ['instruction_remember', 'capture']);
    assert.equal(messages[0].text, 'Make it warmer');
    assert.equal(editor.prompt, 'Make it warmer');
});

test('an old acknowledgement cannot mark newer edits persisted', () => {
    const { editor, messages } = harness();
    editor.updatePrompt('Instruction A');
    editor.persistInstruction('instruction_remember');
    const first = messages[0].id;
    editor.updatePrompt('Instruction B');
    editor.persistInstruction('instruction_remember');
    editor.updatePrompt('Instruction A');
    editor.receive({ type: 'instruction_remember', id: first, data: { last: 'Instruction A', saved: [] } });
    assert.equal(editor.promptDirty, true);
    editor.persistInstruction('instruction_remember');
    editor.receive({ type: 'instruction_remember', id: messages[2].id, data: { last: 'Instruction A', saved: [] } });
    assert.equal(editor.promptDirty, false);
});

test('saving a favorite does not replace text edited while its response was pending', () => {
    const { editor, messages } = harness();
    editor.updatePrompt('Saved version');
    editor.persistInstruction('instruction_save');
    assert.equal(editor.instructionBusy, true);
    editor.updatePrompt('New draft');
    editor.receive({ type: 'instruction_save', id: messages[0].id,
        data: { last: 'Saved version', saved: ['Saved version'] } });
    assert.equal(editor.prompt, 'New draft');
    assert.equal(editor.promptDirty, true);
    assert.equal(editor.savedInstructions[0], 'Saved version');
    assert.equal(editor.instructionBusy, false);
});

test('removing a favorite keeps the current draft', () => {
    const { editor, messages } = harness();
    editor.updatePrompt('My draft');
    editor.removeInstruction('Saved version');
    assert.equal(messages[0].text, 'Saved version');
    editor.receive({ type: 'instruction_remove', data: { last: 'Old draft', saved: [] } });
    assert.equal(editor.prompt, 'My draft');
    assert.equal(editor.promptDirty, true);
    assert.equal(editor.instructionBusy, false);
});

test('reconnecting preserves and persists a draft not yet acknowledged', () => {
    const { editor, messages } = harness();
    editor.updatePrompt('Unsaved draft');
    editor.ready = false;
    editor.instructionsReady = false;
    editor.persistInstruction('instruction_remember');
    assert.equal(messages.length, 0);
    editor.receive({ type: 'ready', data: {} });
    editor.receive({ type: 'instructions', data: { last: 'Older disk copy', saved: [] } });
    assert.equal(editor.prompt, 'Unsaved draft');
    assert.equal(messages[0].text, 'Unsaved draft');
});

test('instruction errors do not cancel a rewrite', () => {
    const { editor } = harness('generating');
    editor.promptDirty = true;
    editor.receive({ type: 'instruction_remember', error: 'Cannot save the instruction file.' });
    assert.equal(editor.phase, 'generating');
    assert.equal(editor.generationId, 7);
    assert.equal(editor.promptDirty, true);
    assert.match(editor.error, /Cannot save/);
});

test('rewriting records the submitted prompt and allows a later prompt attempt', () => {
    const { editor, messages } = harness();
    editor.updatePrompt('Make it friendly');
    editor.generate();
    assert.equal(editor.attemptedPrompt, 'Make it friendly');
    assert.equal(editor.phase, 'generating');
    assert.equal(messages.at(-1).prompt, 'Make it friendly');
    editor.updatePrompt('Make it shorter');
    assert.equal(editor.attemptedPrompt, 'Make it friendly');
    editor.receive({ type: 'generate', id: editor.generationId, error: 'Provider unavailable' });
    assert.equal(editor.attemptedPrompt, 'Make it friendly');
    editor.generate();
    assert.equal(editor.attemptedPrompt, 'Make it shorter');
});

test('a failed send does not mark a new prompt as attempted', () => {
    const { editor, messages } = harness();
    editor.ready = false;
    editor.updatePrompt('Never submitted');
    editor.generate();
    assert.equal(editor.attemptedPrompt, 'Previous instruction');
    assert.equal(editor.phase, 'idle');
    assert.equal(messages.length, 0);
});

test('a failed capture preserves the attempted prompt', () => {
    const { editor } = harness();
    editor.ready = false;
    editor.capture();
    assert.equal(editor.attemptedPrompt, 'Previous instruction');
});

test('backend exit clears attempted prompt and leaves the draft intact', () => {
    const { editor } = harness();
    const source = fs.readFileSync(path.join(__dirname, 'Service.qml'), 'utf8');
    const handler = source.match(/        onExited: \{([\s\S]*?)^        \}/m);
    assert.ok(handler);
    editor.root = editor;
    editor.restart = { restart() {} };
    vm.runInContext(handler[1], editor);
    assert.equal(editor.attemptedPrompt, '');
    assert.equal(editor.prompt, 'Previous instruction');
    assert.equal(editor.ready, false);
});

test('choosing a saved prompt remembers it, collapses the list, and focuses the field', () => {
    const { editor, panel, messages } = harness();
    let focused = false;
    panel.showSavedPrompts = true;
    panel.instruction = { forceActiveFocus() { focused = true; } };
    vm.runInContext(qmlFunction('Panel.qml', 'selectPrompt'), panel);
    panel.selectPrompt('Saved wording');
    assert.equal(editor.prompt, 'Saved wording');
    assert.equal(messages[0].type, 'instruction_remember');
    assert.equal(messages[0].text, 'Saved wording');
    assert.equal(panel.showSavedPrompts, false);
    assert.equal(focused, true);
});

test('rewriting collapses the saved prompts list', () => {
    const { editor, panel } = harness();
    panel.showSavedPrompts = true;
    vm.runInContext(qmlFunction('Panel.qml', 'rewrite'), panel);
    panel.rewrite();
    assert.equal(panel.showSavedPrompts, false);
    assert.equal(editor.phase, 'generating');
});


test('successful save emits saved text after updating persistence state without a global notice', () => {
    const { editor, messages, saved } = harness('generating');
    editor.updatePrompt('Save this wording');
    editor.persistInstruction('instruction_save');
    assert.equal(saved.length, 0);
    editor.receive({ type: 'instruction_save', id: messages[0].id,
        data: { last: 'Save this wording', saved: ['Save this wording'] } });
    assert.deepEqual(saved, ['Save this wording']);
    assert.equal(editor.promptDirty, false);
    assert.equal(editor.instructionBusy, false);
    assert.equal(editor.savedInstructions[0], 'Save this wording');
    assert.equal(editor.phase, 'generating');
    assert.equal(editor.generationId, 7);
    assert.equal(editor.result, 'Previous rewrite');
    assert.equal(editor.notice, '');
});

test('failed save reports its error without emitting success or changing saved prompts', () => {
    const { editor, messages, saved } = harness('generating');
    editor.updatePrompt('Save this wording');
    editor.persistInstruction('instruction_save');
    editor.receive({ type: 'instruction_save', id: messages[0].id, error: 'Disk is full' });
    assert.deepEqual(saved, []);
    assert.equal(editor.savedInstructions.length, 0);
    assert.equal(editor.promptDirty, true);
    assert.equal(editor.instructionBusy, false);
    assert.equal(editor.error, 'Disk is full');
    assert.equal(editor.notice, '');
    assert.equal(editor.phase, 'generating');
    assert.equal(editor.generationId, 7);
});

test('remember and remove acknowledgements do not emit save feedback', () => {
    const { editor, saved } = harness();
    for (const type of ['instructions', 'instruction_remember', 'instruction_remove']) {
        editor.receive({ type, data: { last: editor.prompt, saved: [] } });
    }
    assert.deepEqual(saved, []);
    assert.equal(editor.notice, '');
});

test('save feedback ignores a late response after editing and only animates matching text', () => {
    const { editor, panel, messages, saved, feedbackStarts } = harness();
    editor.persistInstruction('instruction_save');
    editor.updatePrompt('New draft');
    editor.receive({ type: 'instruction_save', id: messages[0].id,
        data: { last: 'Previous instruction', saved: ['Previous instruction'] } });
    panel.onPromptSaved(saved[0]);
    assert.equal(feedbackStarts(), 0);
    panel.onPromptSaved('New draft');
    assert.equal(feedbackStarts(), 1);
    panel.opened = false;
    panel.onPromptSaved('New draft');
    assert.equal(feedbackStarts(), 1);
    panel.opened = true;
    panel.busy = true;
    panel.onPromptSaved('New draft');
    assert.equal(feedbackStarts(), 1);
});

test('rewriting stops and clears previous save feedback', () => {
    const { panel, feedback, feedbackStops } = harness();
    vm.runInContext(qmlFunction('Panel.qml', 'rewrite'), panel);
    panel.rewrite();
    assert.equal(feedbackStops(), 1);
    assert.equal(feedback.opacity, 0);
    assert.equal(feedback.scale, 1);
});


test('removal mutates only the confirmed row after persistence succeeds', () => {
    const { editor, rows, modelChanges, messages } = harness();
    editor.receive({ type: 'instructions', data: { last: editor.prompt, saved: ['First', 'Second', 'Third'] } });
    const [first, second, third] = rows;
    modelChanges.length = 0;
    editor.removeInstruction('Second');
    assert.equal(messages.at(-1).type, 'instruction_remove');
    assert.deepEqual(rows, [first, second, third]);
    assert.deepEqual(modelChanges, []);
    editor.receive({ type: 'instruction_remove', data: { last: editor.prompt, saved: ['First', 'Third'] } });
    assert.deepEqual(modelChanges, [['remove', 1]]);
    assert.equal(rows[0], first);
    assert.equal(rows[1], third);
    assert.equal(editor.notice, '');
});

test('failed removal retains rows and reports the persistence error', () => {
    const { editor, rows, modelChanges } = harness();
    editor.savedInstructions = ['Only prompt'];
    const row = rows[0];
    modelChanges.length = 0;
    editor.removeInstruction('Only prompt');
    editor.receive({ type: 'instruction_remove', error: 'Cannot write saved prompts' });
    assert.equal(editor.error, 'Cannot write saved prompts');
    assert.equal(editor.notice, '');
    assert.equal(editor.instructionBusy, false);
    assert.equal(rows[0], row);
    assert.deepEqual(modelChanges, []);
    editor.removeInstruction('Only prompt');
    editor.receive({ type: 'instruction_remove', data: { last: editor.prompt, saved: [] } });
    assert.equal(rows.length, 0);
    assert.deepEqual(modelChanges, [['remove', 0]]);
});

test('remembering, saving, and reordering preserve unchanged row identity and exact prompt text', () => {
    const { editor, rows, modelChanges } = harness();
    const prompts = ['Line one\nLine two', 'Line one Line two', '<b>Plain text</b>'];
    editor.savedInstructions = prompts;
    const original = rows.slice();
    modelChanges.length = 0;
    editor.receive({ type: 'instruction_remember', data: { last: editor.prompt, saved: prompts.slice() } });
    assert.deepEqual(modelChanges, []);
    editor.receive({ type: 'instruction_save', data: { last: 'New', saved: ['New', ...prompts] } });
    assert.deepEqual(modelChanges, [['insert', 0]]);
    original.forEach((row, index) => assert.equal(rows[index + 1], row));
    editor.savedInstructions = [prompts[2], 'New', prompts[0], prompts[1]];
    assert.equal(rows[0], original[2]);
    assert.equal(rows[2], original[0]);
    assert.equal(rows[3], original[1]);
    assert.deepEqual(rows.map(row => row.promptText), [prompts[2], 'New', prompts[0], prompts[1]]);
});

test('changing selected text resets expansion and scroll position', () => {
    const { editor, panel } = harness();
    panel.previewExpanded = true;
    panel.selectionScroll.contentY = 80;
    editor.source = 'A new selection';
    assert.equal(panel.previewExpanded, false);
    assert.equal(panel.selectionScroll.contentY, 0);
});

test('closing resets the preview and its scroll position', () => {
    const { panel } = harness();
    panel.previewExpanded = true;
    panel.selectionScroll.contentY = 80;
    panel.opened = false;
    const qml = fs.readFileSync(path.join(__dirname, 'Panel.qml'), 'utf8');
    const handler = qml.match(/    onOpenedChanged: \{([\s\S]*?)^    \}/m);
    assert.ok(handler);
    vm.runInContext(handler[1], panel);
    assert.equal(panel.previewExpanded, false);
    assert.equal(panel.selectionScroll.contentY, 0);
});

test('copy feedback waits for clipboard success and clears for a repeated copy', () => {
    const { editor, messages } = harness();
    editor.copyResult();
    assert.equal(editor.copyFeedback.running, false);
    editor.receive({ type: 'copy', id: messages.at(-1).id });
    assert.equal(editor.copyFeedback.running, true);
    assert.equal(editor.notice, '');
    editor.copyResult();
    assert.equal(editor.copyFeedback.running, false);
    editor.receive({ type: 'copy', id: messages.at(-1).id, error: 'Clipboard unavailable' });
    assert.equal(editor.copyFeedback.running, false);
    assert.equal(editor.error, 'Clipboard unavailable');
});

for (const next of ['capture', 'generate']) {
    test(`copy acknowledgement cannot affect a later ${next}`, () => {
        const { editor, messages } = harness();
        editor.copyResult();
        const id = messages.at(-1).id;
        editor[next]();
        editor.receive({ type: 'copy', id });
        assert.equal(editor.copyFeedback.running, false);
        editor.receive({ type: 'copy', id, error: 'Old failure' });
        assert.equal(editor.error, '');
    });
}

test('older copy acknowledgement cannot confirm a newer copy attempt', () => {
    const { editor, messages } = harness();
    editor.copyResult();
    const oldId = messages.at(-1).id;
    editor.copyResult();
    editor.receive({ type: 'copy', id: oldId });
    assert.equal(editor.copyFeedback.running, false);
    editor.receive({ type: 'copy', id: messages.at(-1).id });
    assert.equal(editor.copyFeedback.running, true);
});

test('Enter rewrites then replaces and closes on the next distinct press', () => {
    const { editor, panel, messages, closed, replacements, focused } = harness();
    editor.result = '';
    editor.canReplace = true;
    const event = { isAutoRepeat: false, accepted: false };
    panel.acceptPrompt(event);
    assert.equal(event.accepted, true);
    assert.equal(messages.at(-1).type, 'generate');
    assert.equal(closed(), 0);
    editor.receive({ type: 'generate', id: editor.generationId, data: { text: 'New rewrite' } });
    assert.equal(focused(), 1);
    panel.acceptPrompt(event);
    assert.equal(replacements(), 1);
    assert.equal(closed(), 1);
    assert.equal(editor.phase, 'replacing');
});

test('changed prompt regenerates instead of replacing an older result', () => {
    const { editor, panel, messages, replacements } = harness();
    editor.prompt = 'A new prompt';
    editor.canReplace = true;
    panel.acceptPrompt({ isAutoRepeat: false });
    assert.equal(messages.at(-1).type, 'generate');
    assert.equal(replacements(), 0);
});

test('held Enter, busy, settings and closed states cannot apply a rewrite', () => {
    const { panel, replacements, messages } = harness();
    panel.acceptPrompt({ isAutoRepeat: true });
    panel.busy = true;
    panel.acceptPrompt({ isAutoRepeat: false });
    panel.busy = false;
    panel.showSettings = true;
    panel.acceptPrompt({ isAutoRepeat: false });
    panel.showSettings = false;
    panel.opened = false;
    panel.acceptPrompt({ isAutoRepeat: false });
    assert.equal(replacements(), 0);
    assert.deepEqual(messages, []);
});

test('clipboard Enter closes only after successful copy acknowledgement', () => {
    const { editor, panel, messages, closed } = harness();
    editor.canReplace = false;
    panel.acceptPrompt({ isAutoRepeat: false });
    assert.equal(messages.at(-1).type, 'copy');
    assert.equal(panel.awaitingCopy, true);
    assert.equal(closed(), 0);
    panel.acceptPrompt({ isAutoRepeat: false });
    assert.equal(messages.length, 1);
    editor.receive({ type: 'copy', id: messages.at(-1).id, error: 'Clipboard unavailable' });
    assert.equal(panel.awaitingCopy, false);
    assert.equal(closed(), 0);
    panel.acceptPrompt({ isAutoRepeat: false });
    editor.receive({ type: 'copy', id: messages.at(-1).id });
    assert.equal(closed(), 1);
});

test('copy send failure and disconnect leave keyboard flow retryable', () => {
    const { editor, panel, closed } = harness();
    editor.canReplace = false;
    editor.send = () => 0;
    panel.acceptPrompt({ isAutoRepeat: false });
    assert.equal(panel.awaitingCopy, false);
    panel.awaitingCopy = true;
    editor.ready = false;
    panel.onReadyChanged();
    assert.equal(panel.awaitingCopy, false);
    assert.equal(closed(), 0);
});

test('mouse copy keeps panel open and late rewrite cannot steal focus from settings', () => {
    const { editor, panel, messages, closed, focused } = harness();
    editor.copyResult();
    editor.receive({ type: 'copy', id: messages.at(-1).id });
    assert.equal(closed(), 0);
    panel.showSettings = true;
    panel.onRewriteFinished();
    panel.showSettings = false;
    panel.opened = false;
    panel.onRewriteFinished();
    assert.equal(focused(), 0);
});

test('mouse rewrite supersedes pending Enter-copy and keeps next Enter usable', () => {
    const { editor, panel, messages, closed } = harness();
    editor.canReplace = false;
    panel.acceptPrompt({ isAutoRepeat: false });
    const copyId = messages.at(-1).id;
    panel.rewrite();
    assert.equal(panel.awaitingCopy, false);
    editor.receive({ type: 'copy', id: copyId });
    assert.equal(closed(), 0);
    editor.receive({ type: 'generate', id: editor.generationId, data: { text: 'Newer rewrite' } });
    panel.acceptPrompt({ isAutoRepeat: false });
    assert.equal(messages.at(-1).type, 'copy');
    editor.receive({ type: 'copy', id: messages.at(-1).id });
    assert.equal(closed(), 1);
});


test('retained capture restores backend result and keeps the matching instruction', () => {
    const { editor, panel, messages } = harness();
    panel.open();
    editor.receive({ type: 'capture', id: panel.captureId, data: {
        text: 'Previous selection', app: 'chrome', canReplace: true,
        result: 'Backend completed rewrite', retained: true,
    } });
    assert.equal(editor.source, 'Previous selection');
    assert.equal(editor.result, 'Backend completed rewrite');
    assert.equal(editor.attemptedPrompt, 'Previous instruction');
    assert.equal(editor.canReplace, true);
    editor.copyResult();
    assert.equal(messages.at(-1).type, 'copy');
});

test('capture failure keeps comparison visible and replacement disabled', () => {
    const { editor, panel, shown } = harness();
    editor.generationId = 0;
    panel.open();
    editor.receive({ type: 'capture', id: panel.captureId, error: 'Focus changed' });
    assert.equal(editor.source, 'Previous selection');
    assert.equal(editor.result, 'Previous rewrite');
    assert.equal(editor.attemptedPrompt, 'Previous instruction');
    assert.equal(editor.canReplace, false);
    assert.equal(editor.phase, 'idle');
    assert.equal(editor.error, 'Focus changed');
    assert.equal(shown(), 1);
});

for (const completionFirst of [false, true]) {
    test(`unchanged reopen retains a rewrite completing ${completionFirst ? 'before' : 'after'} capture`, () => {
        const { editor, panel, shown } = harness('generating');
        editor.result = '';
        panel.open();
        const completion = { type: 'generate', id: 7, data: { text: 'Fresh rewrite' } };
        if (completionFirst) {
            editor.receive(completion);
            assert.equal(editor.phase, 'capturing');
            assert.equal(editor.generationId, 0);
        }
        editor.receive({ type: 'capture', id: panel.captureId, data: {
            text: 'Previous selection', app: 'chrome', canReplace: true,
            result: completionFirst ? 'Fresh rewrite' : '', retained: true,
            generationId: completionFirst ? 0 : 7,
        } });
        assert.equal(shown(), 1);
        assert.equal(editor.phase, completionFirst ? 'idle' : 'generating');
        if (!completionFirst) editor.receive(completion);
        assert.equal(editor.phase, 'idle');
        assert.equal(editor.generationId, 0);
        assert.equal(editor.result, 'Fresh rewrite');
        assert.equal(editor.attemptedPrompt, 'Previous instruction');
    });
}

test('completion before a changed capture is cleared with the old instruction', () => {
    const { editor, panel } = harness('generating');
    editor.result = '';
    panel.open();
    editor.receive({ type: 'generate', id: 7, data: { text: 'Old rewrite' } });
    assert.equal(editor.phase, 'capturing');
    editor.receive({ type: 'capture', id: panel.captureId, data: {
        text: 'New selection', app: 'chrome', canReplace: true,
        result: '', retained: false, generationId: 0,
    } });
    assert.equal(editor.result, '');
    assert.equal(editor.attemptedPrompt, '');
    assert.equal(editor.generationId, 0);
    editor.receive({ type: 'generate', id: 7, data: { text: 'Stale rewrite' } });
    assert.equal(editor.result, '');
});

for (const completionFirst of [false, true]) {
    test(`provider failure ${completionFirst ? 'before' : 'after'} capture finishes the retained request`, () => {
        const { editor, panel } = harness('generating');
        editor.result = '';
        panel.open();
        const failure = { type: 'generate', id: 7, error: 'Provider unavailable' };
        if (completionFirst) {
            editor.receive(failure);
            assert.equal(editor.phase, 'capturing');
        }
        editor.receive({ type: 'capture', id: panel.captureId, data: {
            text: 'Previous selection', app: 'chrome', canReplace: true,
            result: '', retained: true, generationId: completionFirst ? 0 : 7,
        } });
        if (!completionFirst) editor.receive(failure);
        assert.equal(editor.phase, 'idle');
        assert.equal(editor.generationId, 0);
        assert.equal(editor.result, '');
        assert.equal(editor.error, 'Provider unavailable');
    });
}

test('capture error preserves a pending rewrite and leaves replacement disabled', () => {
    const { editor, panel, shown } = harness('generating');
    editor.result = '';
    panel.open();
    editor.receive({ type: 'capture', id: panel.captureId, error: 'Focus changed' });
    assert.equal(shown(), 1);
    assert.equal(editor.phase, 'generating');
    assert.equal(editor.generationId, 7);
    editor.receive({ type: 'generate', id: 7, data: { text: 'Fresh rewrite' } });
    assert.equal(editor.result, 'Fresh rewrite');
    assert.equal(editor.generationId, 0);
    assert.equal(editor.phase, 'idle');
    assert.equal(editor.canReplace, false);
    assert.equal(editor.error, 'Focus changed');
});

test('cancel after reopening discards the pending response', () => {
    const { editor, panel, messages } = harness('generating');
    editor.result = '';
    panel.open();
    editor.receive({ type: 'capture', id: panel.captureId, data: {
        text: 'Previous selection', app: 'chrome', canReplace: true,
        result: '', retained: true, generationId: 7,
    } });
    editor.cancel();
    assert.equal(messages.at(-1).type, 'cancel');
    editor.receive({ type: 'generate', id: 7, data: { text: 'Canceled rewrite' } });
    assert.equal(editor.result, '');
    assert.equal(editor.generationId, 0);
    assert.equal(editor.phase, 'idle');
});

test('provider failure before a changed capture cannot leak onto the new input', () => {
    const { editor, panel } = harness('generating');
    editor.result = '';
    panel.open();
    editor.receive({ type: 'generate', id: 7, error: 'Old provider error' });
    editor.receive({ type: 'capture', id: panel.captureId, data: {
        text: 'New selection', app: 'chrome', canReplace: true,
        result: '', retained: false, generationId: 0,
    } });
    assert.equal(editor.error, '');
    assert.equal(editor.phase, 'idle');
    assert.equal(editor.result, '');
});


test('settings editors save to the index and preserve a failed draft', () => {
    const { editor, panel, messages } = harness();
    panel.showSettings = true;
    panel.loadSettings();
    panel.editDefaults();
    assert.equal(panel.settingsPage, 'defaults');
    assert.equal(panel.defaultsInput.text, 'No em dashes.');
    panel.defaultsInput.text = 'Use em dashes freely.';
    editor.saveDefaults(panel.defaultsInput.text);
    const request = messages.at(-1);
    assert.equal(request.type, 'save_defaults');
    assert.equal(request.defaultInstructions, panel.defaultsInput.text);
    assert.equal(editor.settingsBusy, true);
    panel.backSettings();
    assert.equal(panel.settingsPage, 'defaults');
    editor.saveDefaults('Duplicate');
    assert.equal(messages.at(-1), request);
    editor.receive({type: 'save_defaults', id: request.id, error: 'Cannot save'});
    assert.equal(editor.settingsBusy, false);
    assert.equal(panel.settingsPage, 'defaults');
    assert.equal(panel.defaultsInput.text, 'Use em dashes freely.');
    assert.equal(editor.config.defaultInstructions, 'No em dashes.');
    editor.saveDefaults(panel.defaultsInput.text);
    editor.receive({type: 'save_defaults', id: messages.at(-1).id, data: {...editor.config, defaultInstructions: panel.defaultsInput.text}});
    assert.equal(panel.settingsPage, 'index');
    assert.equal(panel.showSettings, true);
    panel.editDefaults();
    assert.equal(panel.defaultsInput.text, 'Use em dashes freely.');
    panel.defaultsInput.text = '';
    editor.saveDefaults('');
    editor.receive({type: 'save_defaults', id: messages.at(-1).id, data: {...editor.config, defaultInstructions: ''}});
    assert.equal(editor.config.defaultInstructions, '');
    assert.equal(panel.settingsPage, 'index');
});

test('Back cancels editor drafts and provider save returns to Settings', () => {
    const { editor, panel, messages } = harness();
    panel.showSettings = true;
    panel.editDefaults();
    panel.defaultsInput.text = 'Discard';
    panel.backSettings();
    panel.editDefaults();
    assert.equal(panel.defaultsInput.text, editor.config.defaultInstructions);
    panel.backSettings();
    panel.editProvider();
    assert.equal(panel.modelInput.text, 'original-model');
    panel.modelInput.text = 'discard-model';
    panel.keyInput.text = 'discard-key';
    panel.backSettings();
    assert.equal(panel.keyInput.text, '');
    panel.editProvider();
    assert.equal(panel.modelInput.text, 'original-model');
    editor.save('openai', 'new-model', 'new-key', false);
    assert.equal(editor.settingsBusy, true);
    editor.receive({type: 'save', id: messages.at(-1).id, error: 'Cannot save'});
    assert.equal(panel.settingsPage, 'provider');
    assert.equal(editor.settingsBusy, false);
    editor.save('openai', 'new-model', 'new-key', false);
    editor.receive({type: 'save', id: messages.at(-1).id, data: {...editor.config, providers: {openai: {model: 'new-model', hasKey: true}}}});
    assert.equal(panel.settingsPage, 'index');
    assert.equal(panel.showSettings, true);
    assert.equal(panel.keyInput.text, '');
    panel.backSettings();
    assert.equal(panel.showSettings, false);
});
