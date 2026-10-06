import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: window
    objectName: "miwlWindow"
    visible: true
    width: 1380
    height: 900
    minimumWidth: 960
    minimumHeight: 640
    title: "Miwl 2"
    color: "#f6f6f3"
    font.family: "Helvetica Neue"
    font.pixelSize: 14
    property color ink: "#242723"
    property color muted: "#666b63"
    property color accent: "#245dc9"
    property color line: "#dedfd8"
    property bool syncingEditors: false
    property bool sidebarVisible: width >= 1100
    property bool inspectorVisible: width >= 1200
    property bool reduceMotion: false
    property int activeView: 0
    readonly property bool compact: width < 1180
    readonly property bool documentsBusy: typeof documentsContext !== "undefined" && documentsContext.busy
    readonly property bool voiceBusy: typeof voiceContext !== "undefined" && voiceContext.busy
    readonly property bool cloudReady: bridge.providerKind !== "cloud" || cloudConsent.checked
    readonly property int motionDuration: reduceMotion ? 0 : 120
    palette.windowText: ink
    palette.text: ink
    palette.buttonText: ink
    palette.base: "#ffffff"
    palette.button: "#f7f7f4"
    palette.highlight: "#dce8fc"
    palette.highlightedText: ink

    function flushEditors() {
        sourceSave.stop();
        resultSave.stop();
        bridge.updateSource(sourceEditor.text);
        bridge.updateResult(resultEditor.text);
    }
    function chooseSession(id) {
        flushEditors();
        bridge.selectSession(id);
        activeView = 0;
    }
    function newSession() {
        flushEditors();
        bridge.newSession();
        activeView = 0;
    }
    function sendPrompt() {
        if (bridge.busy || voiceBusy || !promptEditor.text.trim())
            return;
        flushEditors();
        if (!prepareCloudRequest()) return;
        activeView = 0;
        if (operationPicker.currentIndex === 1)
            bridge.writeArticle(promptEditor.text);
        else
            bridge.sendMessage(promptEditor.text);
        promptEditor.text = "";
    }
    function summarizeSource() {
        flushEditors();
        if (!prepareCloudRequest()) return;
        activeView = 0;
        bridge.summarize();
    }
    function paraphraseSource() {
        flushEditors();
        if (!prepareCloudRequest()) return;
        activeView = 0;
        bridge.paraphrase();
    }
    function toggleInspector() {
        if (!inspectorVisible && width < 1180)
            sidebarVisible = false;
        inspectorVisible = !inspectorVisible;
    }
    function prepareCloudRequest() {
        if (bridge.providerKind !== "cloud") return true;
        if (!cloudConsent.checked) return false;
        bridge.authorizeCloudRequest();
        cloudConsent.checked = false;
        return true;
    }
    function toggleSidebar() {
        if (!sidebarVisible && width < 1180)
            inspectorVisible = false;
        sidebarVisible = !sidebarVisible;
    }
    function focusSource() {
        if (width < 1180)
            sidebarVisible = false;
        inspectorVisible = true;
        sourceEditor.forceActiveFocus();
    }
    function rename() {
        renameField.text = bridge.sessionTitle;
        renameDialog.open();
    }
    onClosing: flushEditors()
    Shortcut {
        sequences: ["Ctrl+N", "Meta+N"]
        onActivated: window.newSession()
    }
    Shortcut {
        sequences: ["Ctrl+Return", "Meta+Return"]
        enabled: window.activeView < 2 && !window.documentsBusy
        onActivated: window.sendPrompt()
    }
    Shortcut {
        sequences: ["Ctrl+1", "Meta+1"]
        onActivated: window.activeView = 0
    }
    Shortcut {
        sequences: ["Ctrl+2", "Meta+2"]
        onActivated: window.activeView = 1
    }
    Shortcut {
        sequences: ["Ctrl+3", "Meta+3"]
        onActivated: window.focusSource()
    }
    Shortcut {
        sequences: ["Ctrl+F", "Meta+F"]
        onActivated: {
            window.sidebarVisible = true;
            sessionSearch.forceActiveFocus();
        }
    }
    Timer {
        id: sourceSave
        interval: 350
        onTriggered: bridge.updateSource(sourceEditor.text)
    }
    Timer {
        id: resultSave
        interval: 350
        onTriggered: bridge.updateResult(resultEditor.text)
    }
    Connections {
        target: bridge
        function onSourceTextChanged() {
            window.syncingEditors = true;
            sourceEditor.text = bridge.sourceText;
            window.syncingEditors = false;
        }
        function onResultTextChanged() {
            window.syncingEditors = true;
            resultEditor.text = bridge.resultText;
            window.syncingEditors = false;
        }
        function onCurrentSessionChanged() {
            cloudConsent.checked = false;
            promptEditor.text = "";
            chatView.followTail = true;
            Qt.callLater(function () {
                chatView.positionViewAtEnd();
            });
        }
        function onMessagesChanged() {
            if (chatView.followTail)
                Qt.callLater(function () {
                    chatView.positionViewAtEnd();
                });
        }
    }

    component Caption: Label {
        color: window.muted
        font.pixelSize: 12
    }
    component Hairline: Rectangle {
        color: window.line
        implicitHeight: 1
    }
    component Panel: Rectangle {
        radius: 16
        color: "#ffffff"
        border.color: window.line
    }
    component Action: Button {
        id: action
        property bool primary: false
        property bool quiet: false
        property bool selected: false
        property string glyph: ""
        property string hint: ""
        implicitHeight: 38
        implicitWidth: Math.ceil(contentItem.implicitWidth) + 34
        leftPadding: 16
        rightPadding: 16
        topPadding: 10
        bottomPadding: 10
        Accessible.name: text
        background: Item {
            Rectangle {
                anchors.fill: parent
                anchors.topMargin: 3
                anchors.bottomMargin: -3
                radius: 18
                color: "#160e1b08"
                visible: action.enabled && !action.down && !action.quiet
            }
            Rectangle {
                anchors.fill: parent
                anchors.topMargin: action.down ? 1 : 0
                anchors.bottomMargin: action.down ? -1 : 0
                radius: 18
                color: action.primary && action.enabled ? (action.down ? "#1e4fab" : action.hovered ? "#1f56bf" : window.accent) : !action.enabled ? "#eeefea" : action.selected ? "#e3ecfb" : action.down ? "#e5e7df" : action.hovered ? "#f0f2eb" : action.quiet ? "transparent" : "#ffffff"
                border.color: action.activeFocus ? window.accent : action.primary && action.enabled ? "#1e50ad" : action.selected ? "#bed0ef" : action.quiet ? "transparent" : "#d8dcd2"
                border.width: action.activeFocus ? 2 : 1
                Behavior on color {
                    ColorAnimation {
                        duration: window.motionDuration
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: 17
                    color: "transparent"
                    border.color: action.primary ? "#36ffffff" : "#ffffff"
                    visible: action.enabled && !action.down && !action.quiet
                }
            }
        }
        contentItem: Row {
            spacing: 7
            Glyph {
                visible: action.glyph !== ""
                name: action.glyph
                width: 16
                height: 16
                anchors.verticalCenter: parent.verticalCenter
                ink: !action.enabled ? "#838a7d" : action.primary ? "#ffffff" : action.selected ? window.accent : window.ink
            }
            Text {
                text: action.text
                font.pixelSize: 13
                font.family: window.font.family
                font.weight: Font.Medium
                color: !action.enabled ? "#777e71" : action.primary ? "#ffffff" : action.selected ? window.accent : window.ink
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        ToolTip.visible: hovered && hint !== ""
        ToolTip.text: hint
        ToolTip.delay: 500
    }
    component Editor: MiwlArea {
        color: window.ink
        selectionColor: "#dce8fc"
        selectedTextColor: window.ink
        placeholderTextColor: window.muted
        wrapMode: TextEdit.Wrap
        font.family: window.font.family
        font.pixelSize: 15
        textFormat: TextEdit.PlainText
        leftPadding: 20
        rightPadding: 20
        topPadding: 18
        bottomPadding: 18
        selectByMouse: true
        persistentSelection: true
        Accessible.role: Accessible.EditableText
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0
        Item {
            id: sidebar
            objectName: "sidebar"
            visible: window.sidebarVisible
            Layout.preferredWidth: 244
            Layout.fillHeight: true
            Rectangle {
                anchors.fill: parent
                anchors.margins: 8
                anchors.topMargin: 12
                anchors.bottomMargin: 4
                radius: 22
                color: "#150f2108"
            }
            Rectangle {
                anchors.fill: parent
                anchors.margins: 8
                radius: 22
                border.color: "#d3d9cf"
                gradient: Gradient {
                    GradientStop {
                        position: 0
                        color: "#f7ffffff"
                    }
                    GradientStop {
                        position: 1
                        color: "#f1e8ede4"
                    }
                }
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: 21
                    color: "transparent"
                    border.color: "#bdffffff"
                }
            }
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 24
                spacing: 18
                RowLayout {
                    Layout.topMargin: 7
                    spacing: 10
                    ColumnLayout {
                        spacing: 4
                        Image {
                            objectName: "brandLogo"
                            Accessible.name: "Miwl 2 logo"
                            source: "../assets/Miwl-2-logo.png"
                            Layout.preferredWidth: 186
                            Layout.preferredHeight: 62
                            fillMode: Image.PreserveAspectFit
                            mipmap: true
                        }
                        Caption {
                            text: "Your writing workspace"
                            font.pixelSize: 11
                        }
                    }
                    Item {
                        Layout.fillWidth: true
                    }
                }
                MiwlField {
                    id: sessionSearch
                    objectName: "sessionSearch"
                    Layout.fillWidth: true
                    implicitHeight: 38
                    placeholderText: "Search sessions"
                    placeholderTextColor: window.muted
                    Accessible.name: "Search sessions"
                    font.pixelSize: 12
                    color: window.ink
                    leftPadding: 30
                    selectByMouse: true
                    Glyph {
                        name: "search"
                        width: 15
                        height: 15
                        x: 9
                        anchors.verticalCenter: parent.verticalCenter
                        ink: window.muted
                    }
                }
                Action {
                    objectName: "newSessionButton"
                    Layout.fillWidth: true
                    implicitHeight: 44
                    text: "New session"
                    glyph: "plus"
                    onClicked: window.newSession()
                    hint: "⌘ N"
                }
                Action {
                    objectName: "clearSearchButton"
                    visible: sessionSearch.text.length > 0
                    text: "Clear search"
                    quiet: true
                    implicitHeight: 28
                    onClicked: sessionSearch.text = ""
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 9
                    Caption {
                        text: "Saved sessions"
                        font.weight: Font.DemiBold
                    }
                    Item {
                        Layout.fillWidth: true
                    }
                    Caption {
                        text: bridge.sessions.length
                        font.pixelSize: 11
                    }
                }
                ListView {
                    id: sessionsView
                    objectName: "sessionsView"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 4
                    activeFocusOnTab: true
                    keyNavigationEnabled: true
                    Accessible.name: "Saved sessions"
                    Keys.onReturnPressed: if (currentIndex >= 0 && currentIndex < count)
                        window.chooseSession(model[currentIndex].id)
                    section.property: "historyGroup"
                    section.criteria: ViewSection.FullString
                    section.delegate: Caption {
                        required property string section
                        text: section
                        height: 32
                        topPadding: 12
                        leftPadding: 10
                        font.pixelSize: 11
                    }
                    model: bridge.sessions.filter(function (session) {
                        return session.title.toLowerCase().indexOf(sessionSearch.text.toLowerCase()) >= 0;
                    })
                    delegate: Button {
                        id: sessionButton
                        required property var modelData
                        objectName: "session_" + modelData.id
                        width: sessionsView.width
                        height: 56
                        padding: 9
                        text: modelData.title
                        Accessible.name: modelData.title
                        onClicked: window.chooseSession(modelData.id)
                        ToolTip.visible: hovered
                        ToolTip.text: text
                        ToolTip.delay: 600
                        background: Rectangle {
                            radius: 14
                            color: sessionButton.modelData.id === bridge.currentSessionId ? "#dce8fc" : sessionButton.hovered ? "#e6e8df" : "transparent"
                            border.color: sessionButton.activeFocus ? window.accent : sessionButton.modelData.id === bridge.currentSessionId ? "#c2d4f5" : "transparent"
                            border.width: sessionButton.activeFocus ? 2 : 1
                            Behavior on color {
                                ColorAnimation {
                                    duration: window.motionDuration
                                }
                            }
                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 1
                                radius: 13
                                color: "transparent"
                                border.color: "#ceffffff"
                                visible: sessionButton.modelData.id === bridge.currentSessionId
                            }
                        }
                        contentItem: RowLayout {
                            spacing: 9
                            Glyph {
                                name: "document"
                                ink: sessionButton.modelData.id === bridge.currentSessionId ? window.accent : window.muted
                                width: 17
                                height: 17
                            }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 3
                                Label {
                                    Layout.fillWidth: true
                                    text: sessionButton.modelData.title
                                    color: window.ink
                                    font.pixelSize: 13
                                    font.weight: sessionButton.modelData.id === bridge.currentSessionId ? Font.Medium : Font.Normal
                                    elide: Text.ElideRight
                                }
                                Caption {
                                    text: sessionButton.modelData.updatedLabel
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                    Label {
                        anchors.centerIn: parent
                        width: parent.width - 20
                        visible: sessionsView.count === 0
                        objectName: "emptyHistoryLabel"
                        text: sessionSearch.text.length ? "No matching sessions.\nTry another name or clear the search." : "Your saved sessions will appear here.\nCreate a session to get started."
                        horizontalAlignment: Text.AlignHCenter
                        color: window.muted
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }
                    ScrollBar.vertical: MiwlScrollBar {
                        policy: ScrollBar.AsNeeded
                    }
                }
                Hairline {
                    Layout.fillWidth: true
                }
                RowLayout {
                    spacing: 8
                    Glyph {
                        name: "lock"
                        width: 14
                        height: 14
                        ink: window.muted
                    }
                    Caption {
                        text: "Saved on this Mac"
                        font.pixelSize: 11
                    }
                }
            }
        }
        ColumnLayout {
            id: mainArea
            objectName: "mainArea"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 24
            Layout.rightMargin: 24
            Layout.topMargin: 16
            Layout.bottomMargin: 20
            spacing: 16
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                spacing: 10
                Label {
                    visible: !window.sidebarVisible
                    text: "Miwl 2"
                    color: window.ink
                    font.pixelSize: 17
                    font.weight: Font.DemiBold
                    Layout.rightMargin: 4
                }
                Action {
                    objectName: "sidebarToggle"
                    text: window.sidebarVisible ? "Hide sessions" : "Sessions"
                    glyph: "sidebar"
                    selected: window.sidebarVisible
                    onClicked: window.toggleSidebar()
                    hint: "Search with ⌘ F"
                }
                Action {
                    objectName: "toolbarNewSessionButton"
                    visible: !window.sidebarVisible
                    text: "New session"
                    glyph: "plus"
                    onClicked: window.newSession()
                    hint: "⌘ N"
                }
                Item {
                    Layout.fillWidth: true
                }
                Action {
                    objectName: "providerButton"
                    enabled: !window.documentsBusy
                    visible: window.activeView < 2 || window.activeView === 3 || window.activeView === 5
                    text: bridge.providerLabel
                    quiet: true
                    onClicked: providerPopup.open()
                    hint: "Choose and configure the writing provider"
                }
                Action {
                    objectName: "inspectorToggle"
                    visible: window.activeView < 2 || window.activeView === 3
                    text: window.inspectorVisible ? "Hide source" : "Source notes"
                    glyph: "document"
                    selected: window.inspectorVisible
                    onClicked: window.toggleInspector()
                    hint: "Open source with ⌘ 3"
                }
            }
            Hairline {
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 8
                Layout.bottomMargin: 8
                spacing: 14
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    Label {
                        Layout.fillWidth: true
                        text: window.activeView === 5 ? "Documents" : window.activeView === 4 ? "Local gallery" : window.activeView === 2 ? "Camera sources" : window.activeView === 3 ? "Voice · " + bridge.sessionTitle : bridge.sessionTitle === "Untitled session" ? "New session" : bridge.sessionTitle
                        color: window.ink
                        font.pixelSize: window.compact ? 24 : 28
                        font.weight: Font.DemiBold
                        font.letterSpacing: -0.6
                        elide: Text.ElideRight
                    }
                    Caption {
                        text: window.activeView === 5 ? "Selected sources · local search · verifiable quotations" : window.activeView === 4 ? "Encrypted on this Mac · explicit consenting enrollment" : window.activeView === 2 ? "Two authorized sources · optional local face matching" : bridge.savedLabel
                        font.pixelSize: 12
                    }
                }
                Action {
                    objectName: "renameButton"
                    visible: window.activeView < 2 || window.activeView === 3
                    text: "Rename"
                    glyph: "edit"
                    onClicked: window.rename()
                    hint: "Change this session’s name"
                }
                Action {
                    objectName: "paraphraseButton"
                    visible: window.activeView < 2 || window.activeView === 3
                    text: "Paraphrase"
                    enabled: !bridge.busy && !window.voiceBusy && !window.documentsBusy && window.cloudReady && sourceEditor.text.trim().length > 0
                    onClicked: window.paraphraseSource()
                    hint: "Rewrite the source while preserving its meaning"
                }
                Action {
                    objectName: "summarizeButton"
                    visible: window.activeView < 2 || window.activeView === 3
                    text: "Summarize notes"
                    primary: true
                    glyph: "document"
                    enabled: !bridge.busy && !window.voiceBusy && !window.documentsBusy && window.cloudReady && sourceEditor.text.trim().length > 0
                    onClicked: window.summarizeSource()
                    hint: sourceEditor.text.trim().length > 0 ? "Create a draft from your source notes" : "Add source notes first"
                }
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Action {
                    objectName: "conversationTab"
                    text: "Conversation"
                    selected: window.activeView === 0
                    glyph: "chat"
                    onClicked: window.activeView = 0
                    hint: "⌘ 1"
                }
                Action {
                    objectName: "draftTab"
                    text: "Editable draft"
                    selected: window.activeView === 1
                    glyph: "document"
                    onClicked: window.activeView = 1
                    hint: "Edit and copy your saved result · ⌘ 2"
                }
                Action {
                    objectName: "cameraTab"
                    text: "Camera sources"
                    selected: window.activeView === 2
                    onClicked: window.activeView = 2
                }
                Action {
                    objectName: "galleryTab"
                    text: "Local gallery"
                    selected: window.activeView === 4
                    onClicked: window.activeView = 4
                }
                Action {
                    objectName: "documentsTab"
                    text: "Documents"
                    selected: window.activeView === 5
                    onClicked: window.activeView = 5
                }
                Action {
                    objectName: "voiceTab"
                    text: "Voice"
                    selected: window.activeView === 3
                    onClicked: window.activeView = 3
                }
                Item {
                    Layout.fillWidth: true
                }
            }
            CheckBox {
                id: cloudConsent
                objectName: "cloudConsent"
                Layout.fillWidth: true
                visible: bridge.providerKind === "cloud" && window.activeView < 2
                enabled: !bridge.busy && !window.voiceBusy && !window.documentsBusy
                text: "Send this request’s notes, draft and relevant history to OpenAI. Provider billing applies."
                onVisibleChanged: checked = false
                contentItem: Label {
                    text: cloudConsent.text
                    leftPadding: cloudConsent.indicator.width + cloudConsent.spacing
                    wrapMode: Text.Wrap
                    color: window.muted
                    font.pixelSize: 12
                }
            }
            Caption {
                Layout.fillWidth: true
                visible: bridge.providerKind === "cloud" && window.activeView < 2
                text: bridge.usageText
                wrapMode: Text.Wrap
            }
            Rectangle {
                objectName: "errorBanner"
                visible: (window.activeView < 2 || window.activeView === 3) && bridge.errorMessage.length > 0
                Layout.fillWidth: true
                implicitHeight: errorRow.implicitHeight + 20
                radius: 10
                color: "#fcf0f1"
                border.color: "#edd4da"
                RowLayout {
                    id: errorRow
                    anchors.fill: parent
                    anchors.margins: 10
                    spacing: 10
                    Label {
                        Layout.fillWidth: true
                        text: bridge.errorMessage
                        color: "#92324a"
                        font.pixelSize: 12
                        wrapMode: Text.Wrap
                    }
                    Action {
                        objectName: "retryButton"
                        text: "Retry"
                        enabled: bridge.retryAvailable && !window.voiceBusy && !window.documentsBusy && window.cloudReady
                        onClicked: {
                            window.flushEditors();
                            if (!window.prepareCloudRequest()) return;
                            bridge.retry();
                        }
                    }
                    Action {
                        text: "Dismiss"
                        glyph: "close"
                        onClicked: bridge.dismissError()
                    }
                }
            }
            CameraPanel {
                objectName: "cameraPanel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: window.activeView === 2
                cameraBridge: typeof cameraContext !== "undefined" ? cameraContext : null
                visionBridge: typeof visionContext !== "undefined" ? visionContext : null
            }
            DocumentsPanel {
                objectName: "documentsPanel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: window.activeView === 5
                documentsBridge: typeof documentsContext !== "undefined" ? documentsContext : null
                workspaceBridge: bridge
                externalBusy: bridge.busy || window.voiceBusy
            }
            GalleryPanel {
                objectName: "galleryPanel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: window.activeView === 4
                visionBridge: typeof visionContext !== "undefined" ? visionContext : null
            }
            VoicePanel {
                objectName: "voicePanel"
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: window.activeView === 3
                compact: window.compact
                voiceBridge: typeof voiceContext !== "undefined" ? voiceContext : null
                workspaceBridge: bridge
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: window.activeView < 2
                spacing: 22
                ColumnLayout {
                    id: conversationColumn
                    objectName: "conversationColumn"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 300
                    spacing: 12
                    StackLayout {
                        id: contentStack
                        objectName: "contentStack"
                        currentIndex: window.activeView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Item {
                            ColumnLayout {
                                anchors.centerIn: parent
                                width: Math.min(parent.width - 48, 460)
                                spacing: 14
                                visible: bridge.messages.length === 0
                                Glyph {
                                    name: "miwl"
                                    ink: window.accent
                                    width: 42
                                    height: 42
                                    Layout.bottomMargin: 9
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: "Start with your notes"
                                    color: window.ink
                                    font.pixelSize: window.compact ? 25 : 30
                                    font.weight: Font.DemiBold
                                    font.letterSpacing: -0.6
                                    lineHeight: 1.06
                                }
                                Label {
                                    Layout.fillWidth: true
                                    text: "1. Paste your text into Source notes.\n2. Choose Summarize notes.\n3. Open Editable draft to edit and copy it."
                                    color: window.muted
                                    font.pixelSize: 14
                                    wrapMode: Text.Wrap
                                    lineHeight: 1.45
                                }
                                RowLayout {
                                    Layout.topMargin: 8
                                    spacing: 9
                                    Action {
                                        objectName: "emptySampleButton"
                                        text: "Use sample notes"
                                        glyph: "document"
                                        onClicked: {
                                            window.flushEditors();
                                            bridge.loadSample();
                                            window.focusSource();
                                        }
                                    }
                                    Action {
                                        text: "Add source notes"
                                        glyph: "edit"
                                        onClicked: window.focusSource()
                                    }
                                }
                                Caption {
                                    text: "You can then ask Miwl for a shorter preview."
                                    font.pixelSize: 11
                                    Layout.topMargin: 4
                                }
                            }
                            ListView {
                                id: chatView
                                objectName: "chatView"
                                property bool followTail: true
                                visible: bridge.messages.length > 0
                                anchors.fill: parent
                                clip: true
                                spacing: 24
                                topMargin: 20
                                bottomMargin: 22
                                model: bridge.messages
                                onContentHeightChanged: if (followTail)
                                    Qt.callLater(function () {
                                        chatView.positionViewAtEnd();
                                    })
                                onMovementEnded: followTail = contentY + height >= contentHeight - 28
                                delegate: Item {
                                    id: message
                                    required property var modelData
                                    readonly property bool fromUser: modelData.role === "user"
                                    width: chatView.width
                                    height: messageColumn.implicitHeight + (fromUser ? 24 : 8)
                                    Rectangle {
                                        anchors.fill: messageColumn
                                        anchors.margins: -12
                                        visible: message.fromUser
                                        color: "#ecefe7"
                                        radius: 13
                                    }
                                    Column {
                                        id: messageColumn
                                        x: message.fromUser ? Math.max(38, parent.width * 0.17) : 7
                                        y: message.fromUser ? 12 : 4
                                        width: parent.width - x - 12
                                        spacing: 9
                                        Row {
                                            spacing: 7
                                            Glyph {
                                                visible: !message.fromUser
                                                name: "miwl"
                                                width: 18
                                                height: 18
                                                ink: window.accent
                                            }
                                            Label {
                                                text: message.fromUser ? "You" : "Miwl"
                                                color: window.ink
                                                font.pixelSize: 12
                                                font.weight: Font.DemiBold
                                            }
                                            Label {
                                                visible: !message.fromUser
                                                text: modelData.provider_is_test ? "Fixture · No AI" : (modelData.provider_label || "Local model")
                                                color: window.muted
                                                font.pixelSize: 11
                                                anchors.verticalCenter: parent.verticalCenter
                                            }
                                        }
                                        TextEdit {
                                            width: parent.width
                                            text: modelData.body || (modelData.status === "pending" ? "Preparing a response…" : "No text returned.")
                                            color: window.ink
                                            font.pixelSize: 14
                                            font.family: window.font.family
                                            wrapMode: TextEdit.Wrap
                                            textFormat: TextEdit.PlainText
                                            readOnly: true
                                            selectByMouse: true
                                            selectionColor: "#dce8fc"
                                            selectedTextColor: window.ink
                                        }
                                        Caption {
                                            visible: modelData.status !== "complete"
                                            text: modelData.status === "cancelled" ? "Stopped · saved draft unchanged" : modelData.status === "failed" ? "Interrupted · saved draft unchanged" : "Writing a response…"
                                            color: modelData.status === "failed" ? "#a03535" : window.muted
                                            font.pixelSize: 11
                                        }
                                    }
                                }
                                ScrollBar.vertical: MiwlScrollBar {
                                    policy: ScrollBar.AsNeeded
                                }
                            }
                        }
                        ColumnLayout {
                            spacing: 12
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.topMargin: 15
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 5
                                    Label {
                                        text: "Editable draft"
                                        color: window.ink
                                        font.pixelSize: 23
                                        font.weight: Font.DemiBold
                                        font.letterSpacing: -0.4
                                    }
                                    Caption {
                                        text: bridge.busy ? "Miwl is responding. Your saved draft stays here." : "Click the text to edit. Changes save automatically."
                                        font.pixelSize: 11
                                        wrapMode: Text.Wrap
                                        Layout.fillWidth: true
                                    }
                                }
                                Action {
                                    objectName: "copyResultButton"
                                    text: "Copy draft"
                                    glyph: "copy"
                                    enabled: resultEditor.text.trim().length > 0
                                    onClicked: {
                                        window.flushEditors();
                                        bridge.copyResult();
                                    }
                                }
                            }
                            Hairline {
                                Layout.fillWidth: true
                            }
                            ScrollView {
                                objectName: "draftScroll"
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                                ScrollBar.vertical: MiwlScrollBar {}
                                Editor {
                                    id: resultEditor
                                    objectName: "resultEditor"
                                    Accessible.name: "Draft"
                                    placeholderText: "Your completed response will appear here.\n\nYou can edit it, then copy it when you’re ready."
                                    readOnly: bridge.busy
                                    leftPadding: 16
                                    rightPadding: 18
                                    onTextChanged: if (!window.syncingEditors)
                                        resultSave.restart()
                                    Component.onCompleted: text = bridge.resultText
                                }
                            }
                        }
                    }
                    Item {
                        id: composer
                        objectName: "composer"
                        Layout.fillWidth: true
                        implicitHeight: Math.min(232, Math.max(168, promptEditor.contentHeight + 116))
                        InputSurface {
                            objectName: "composerSurface"
                            anchors.fill: parent
                            radius: 22
                            focused: promptEditor.activeFocus
                            hovered: promptEditor.hovered
                        }
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 16
                            spacing: 8
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                Caption {
                                    text: "Writing task"
                                    font.pixelSize: 11
                                    font.weight: Font.Medium
                                }
                                MiwlCombo {
                                    id: operationPicker
                                    objectName: "operationPicker"
                                    Accessible.name: "Writing task"
                                    model: ["Chat / refine", "Write article"]
                                    enabled: !bridge.busy
                                    implicitHeight: 34
                                    implicitWidth: 178
                                    font.pixelSize: 12
                                }
                                Item { Layout.fillWidth: true }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                spacing: 14
                                ScrollView {
                                    objectName: "promptScroll"
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    clip: true
                                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                                    ScrollBar.vertical: MiwlScrollBar {}
                                    Editor {
                                        id: promptEditor
                                        objectName: "promptEditor"
                                        Accessible.name: "Message Miwl"
                                        placeholderText: operationPicker.currentIndex === 1 ? "Article topic, audience and any requirements" : "For example: make it shorter"
                                        font.pixelSize: 15
                                        leftPadding: 2
                                        rightPadding: 14
                                        topPadding: 8
                                        bottomPadding: 8
                                        background: Item {
                                            objectName: "promptEditorSurface"
                                            readonly property bool focused: promptEditor.activeFocus
                                        }
                                    }
                                }
                                Button {
                                    id: sendButton
                                    objectName: "sendButton"
                                    Layout.alignment: Qt.AlignBottom
                                    Layout.bottomMargin: 2
                                    text: bridge.busy ? "Stop" : operationPicker.currentIndex === 1 ? "Write" : "Send"
                                    property string hint: bridge.busy ? "Stop this response; keep the saved draft" : "Send message · ⌘ Enter"
                                    implicitWidth: 104
                                    implicitHeight: 44
                                    padding: 14
                                    topPadding: 10
                                    bottomPadding: 10
                                    hoverEnabled: true
                                    Accessible.name: text
                                    Accessible.description: hint
                                    enabled: bridge.busy || (!window.voiceBusy && !window.documentsBusy && window.cloudReady && promptEditor.text.trim().length > 0)
                                    onClicked: bridge.busy ? bridge.stop() : window.sendPrompt()
                                    background: Item {
                                        Rectangle {
                                            anchors.fill: parent
                                            anchors.topMargin: 3
                                            anchors.bottomMargin: -3
                                            radius: 16
                                            color: "#25203e78"
                                            visible: sendButton.enabled && !sendButton.down
                                        }
                                        Rectangle {
                                            anchors.fill: parent
                                            anchors.margins: -3
                                            radius: 19
                                            color: "transparent"
                                            border.width: 3
                                            border.color: "#44245dc9"
                                            visible: sendButton.activeFocus
                                        }
                                        Rectangle {
                                            objectName: "sendButtonFace"
                                            anchors.fill: parent
                                            anchors.topMargin: sendButton.down ? 1 : 0
                                            anchors.bottomMargin: sendButton.down ? -1 : 0
                                            radius: 16
                                            color: !sendButton.enabled ? "#e9ede7" : sendButton.down ? "#1e4d9f" : bridge.busy ? "#314d72" : sendButton.hovered ? "#1f55bb" : window.accent
                                            border.color: !sendButton.enabled ? "#d5dcd1" : bridge.busy ? "#294261" : "#1f51ae"
                                            Rectangle {
                                                anchors.fill: parent
                                                anchors.margins: 1
                                                radius: 15
                                                color: "transparent"
                                                border.color: sendButton.enabled ? "#35ffffff" : "#85ffffff"
                                            }
                                            Behavior on color {
                                                ColorAnimation { duration: window.motionDuration }
                                            }
                                        }
                                    }
                                    contentItem: Row {
                                        spacing: 8
                                        Text {
                                            text: sendButton.text
                                            font.family: window.font.family
                                            font.pixelSize: 14
                                            font.weight: Font.DemiBold
                                            color: sendButton.enabled ? "#ffffff" : "#616e5d"
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                        Glyph {
                                            name: bridge.busy ? "stop" : "arrow"
                                            width: 17
                                            height: 17
                                            ink: sendButton.enabled ? "#ffffff" : "#616e5d"
                                            anchors.verticalCenter: parent.verticalCenter
                                        }
                                    }
                                    ToolTip.visible: hovered
                                    ToolTip.text: hint
                                    ToolTip.delay: 500
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.leftMargin: 2
                                spacing: 7
                                Rectangle {
                                    width: 5
                                    height: 5
                                    radius: 3
                                    color: bridge.busy ? "#bc7b32" : "#657a6f"
                                }
                                Caption {
                                    Layout.fillWidth: true
                                    text: bridge.noticeMessage || bridge.statusText
                                    font.pixelSize: 10
                                    elide: Text.ElideRight
                                }
                                Caption {
                                    text: "⌘ Enter"
                                    font.pixelSize: 10
                                }
                            }
                        }
                    }
                }
                Panel {
                    id: sourceInspector
                    objectName: "sourceInspector"
                    visible: window.inspectorVisible
                    Layout.preferredWidth: window.compact ? 286 : 318
                    Layout.fillHeight: true
                    radius: 16
                    border.color: window.line
                    ColumnLayout {
                        anchors.fill: parent
                        spacing: 0
                        RowLayout {
                            Layout.fillWidth: true
                            Layout.margins: 15
                            spacing: 8
                            Label {
                                Layout.fillWidth: true
                                text: "Source notes"
                                color: window.ink
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                            }
                            Action {
                                objectName: "hideSourceButton"
                                text: "Hide source"
                                quiet: true
                                onClicked: window.inspectorVisible = false
                            }
                        }
                        Caption {
                            Layout.leftMargin: 20
                            Layout.rightMargin: 20
                            Layout.bottomMargin: 14
                            Layout.fillWidth: true
                            text: "Paste the text you want Miwl to use."
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                        Hairline {
                            Layout.fillWidth: true
                            Layout.leftMargin: 16
                            Layout.rightMargin: 16
                        }
                        ScrollView {
                            objectName: "sourceScroll"
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.leftMargin: 12
                            Layout.rightMargin: 12
                            Layout.topMargin: 12
                            Layout.bottomMargin: 10
                            clip: true
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            ScrollBar.vertical: MiwlScrollBar {}
                            Editor {
                                id: sourceEditor
                                objectName: "sourceEditor"
                                Accessible.name: "Source notes"
                                placeholderText: "Paste notes, an article,\nor an unfinished thought.\n\nYour source stays here while\nyou work on the draft."
                                font.pixelSize: 14
                                onTextChanged: if (!window.syncingEditors)
                                    sourceSave.restart()
                                Component.onCompleted: text = bridge.sourceText
                            }
                        }
                        Caption {
                            Layout.fillWidth: true
                            Layout.leftMargin: 20
                            Layout.rightMargin: 20
                            text: bridge.busy ? "Editing source stops the response." : "Saved automatically · " + bridge.sourceWordCount + " words"
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }
                        Action {
                            objectName: "sampleButton"
                            Layout.fillWidth: true
                            Layout.margins: 15
                            text: "Use sample notes"
                            glyph: "document"
                            enabled: !bridge.busy
                            onClicked: {
                                window.flushEditors();
                                bridge.loadSample();
                            }
                        }
                    }
                }
            }
        }
    }
    Popup {
        id: providerPopup
        objectName: "providerPopup"
        parent: Overlay.overlay
        x: window.width - width - 30
        y: 72
        width: 410
        height: Math.min(providerForm.implicitHeight + 44, window.height - 104)
        padding: 22
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        onOpened: {
            providerPicker.currentIndex = bridge.providerKind === "cloud" ? 2 : bridge.providerKind === "ollama" ? 1 : 0;
            endpointField.text = bridge.providerEndpoint;
            modelField.text = bridge.providerModel;
        }
        background: Panel {
            radius: 18
        }
        contentItem: ScrollView {
            id: providerScroll
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical: MiwlScrollBar {}
            ColumnLayout {
            id: providerForm
            width: providerScroll.availableWidth
            spacing: 10
            Label {
                text: "Writing provider"
                color: window.ink
                font.pixelSize: 18
                font.weight: Font.DemiBold
            }
            Label {
                Layout.fillWidth: true
                text: providerPicker.currentIndex === 0 ? "The deterministic fixture uses fixed responses. It demonstrates the workflow without AI or network requests." : providerPicker.currentIndex === 2 ? "Cloud text uses OpenAI. Each request needs confirmation before notes, the draft and relevant history leave this Mac. Audio, images and biometrics are not sent. No automatic fallback." : "Runs an installed model through local Ollama. Miwl sends this session’s notes and relevant conversation to the loopback address below."
                color: window.muted
                font.pixelSize: 13
                wrapMode: Text.Wrap
                lineHeight: 1.3
            }
            MiwlCombo {
                id: providerPicker
                objectName: "providerPicker"
                Accessible.name: "Writing provider"
                Layout.fillWidth: true
                model: ["Deterministic fixture · No AI", "Local Ollama", "Cloud · OpenAI"]
                enabled: !bridge.busy
                onActivated: {
                    if (currentIndex === 2) {
                        endpointField.text = "https://api.openai.com/v1";
                        modelField.text = bridge.providerKind === "cloud" ? bridge.providerModel : "";
                    } else if (currentIndex === 1) {
                        endpointField.text = "http://127.0.0.1:11434";
                        modelField.text = "gemma3:4b";
                    }
                }
            }
            Label {
                visible: providerPicker.currentIndex !== 0
                text: providerPicker.currentIndex === 2 ? "Cloud endpoint" : "Local address"
                color: window.muted
                font.pixelSize: 12
            }
            MiwlField {
                id: endpointField
                hasError: bridge.providerError.length > 0
                objectName: "endpointField"
                Accessible.name: providerPicker.currentIndex === 2 ? "OpenAI endpoint" : "Local Ollama address"
                visible: providerPicker.currentIndex !== 0
                readOnly: providerPicker.currentIndex === 2
                Layout.fillWidth: true
                enabled: !bridge.busy
            }
            Label {
                visible: providerPicker.currentIndex !== 0
                text: providerPicker.currentIndex === 2 ? "Enabled Chat Completions model ID" : "Installed model"
                color: window.muted
                font.pixelSize: 12
            }
            MiwlField {
                id: modelField
                hasError: bridge.providerError.length > 0
                objectName: "modelField"
                Accessible.name: providerPicker.currentIndex === 2 ? "OpenAI model ID" : "Installed Ollama model"
                visible: providerPicker.currentIndex !== 0
                placeholderText: providerPicker.currentIndex === 2 ? "Enter a model enabled for your API project" : ""
                Layout.fillWidth: true
                enabled: !bridge.busy
            }
            Caption {
                Layout.fillWidth: true
                visible: providerPicker.currentIndex === 1
                text: "4096-token context · up to 1024 output tokens\nRuntime and models must already be installed."
                wrapMode: Text.Wrap
                font.pixelSize: 11
            }
            Caption {
                Layout.fillWidth: true
                visible: providerPicker.currentIndex === 2
                text: "Add your own API key in macOS Keychain Access:\nKeychain Item Name: org.aekam.miwl2.openai\nAccount Name: Miwl 2\nPassword: your API key\nMiwl reads it only when you send. Decide any macOS Keychain permission prompt yourself."
                wrapMode: Text.Wrap
                font.pixelSize: 11
            }
            Label {
                Layout.fillWidth: true
                visible: bridge.providerError.length > 0
                text: bridge.providerError
                color: "#a03535"
                wrapMode: Text.Wrap
                font.pixelSize: 12
            }
            Hairline {
                Layout.fillWidth: true
            }
            CheckBox {
                id: failureToggle
                objectName: "failureToggle"
                text: "Simulate one recoverable error"
                checked: bridge.simulateFailure
                enabled: !bridge.busy && bridge.providerIsTest
                visible: providerPicker.currentIndex === 0
                font.pixelSize: 12
                onToggled: bridge.setSimulateFailure(checked)
            }
            CheckBox {
                objectName: "reduceMotionToggle"
                text: "Reduce interface motion"
                checked: window.reduceMotion
                font.pixelSize: 12
                onToggled: window.reduceMotion = checked
            }
            Hairline { Layout.fillWidth: true }
            Action {
                objectName: "backupWorkspaceButton"
                text: "Back up writing"
                Layout.fillWidth: true
                onClicked: {
                    window.flushEditors();
                    bridge.backupWorkspace();
                }
            }
            Caption {
                Layout.fillWidth: true
                text: "Keeps five plaintext writing snapshots beside this workspace. Documents and the gallery are separate."
                wrapMode: Text.Wrap
                font.pixelSize: 11
            }
            Caption {
                Layout.fillWidth: true
                visible: bridge.noticeMessage.length > 0
                text: bridge.noticeMessage
                wrapMode: Text.Wrap
                font.pixelSize: 11
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                Action {
                    text: "Done"
                    onClicked: providerPopup.close()
                }
                Action {
                    objectName: "saveProviderButton"
                    text: "Save provider"
                    primary: true
                    enabled: !bridge.busy
                    onClicked: {
                        cloudConsent.checked = false;
                        if (bridge.configureProvider(providerPicker.currentIndex === 2 ? "cloud" : providerPicker.currentIndex === 1 ? "ollama" : "deterministic", endpointField.text, modelField.text))
                            providerPopup.close();
                    }
                }
            }
            }
        }
    }
    Dialog {
        id: renameDialog
        objectName: "renameDialog"
        title: "Rename session"
        palette.window: "#ffffff"
        palette.windowText: "#242723"
        modal: true
        anchors.centerIn: parent
        width: 380
        standardButtons: Dialog.Ok | Dialog.Cancel
        background: Panel {
            radius: 16
        }
        contentItem: MiwlField {
            id: renameField
            objectName: "renameField"
            Accessible.name: "Session name"
            color: window.ink
            selectByMouse: true
            onAccepted: renameDialog.accept()
        }
        onOpened: {
            renameField.forceActiveFocus();
            renameField.selectAll();
        }
        onAccepted: bridge.renameSession(renameField.text)
    }
}
