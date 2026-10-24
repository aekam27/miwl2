import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

Item {
    id: panel
    property var documentsBridge: null
    property var workspaceBridge
    property bool externalBusy: false
    readonly property bool busy: documentsBridge && documentsBridge.busy
    property string draftText: ""
    property bool showDraft: false
    property bool libraryExpanded: true
    property bool compact: false
    readonly property bool splitView: !compact && width >= 820
    signal draftEdited(string text)
    signal quoteRequested(string citation)
    signal copyDraftRequested
    onDraftTextChanged: if (researchDraft.text !== draftText)
        researchDraft.text = draftText
    function insertQuotationText(text) {
        var position = Math.max(researchDraft.selectionStart, researchDraft.selectionEnd);
        researchDraft.insert(position, text);
        researchDraft.cursorPosition = position + text.length;
        if (!splitView)
            showDraft = true;
        researchDraft.forceActiveFocus();
    }
    Connections {
        target: panel.documentsBridge
        function onResultsChanged() {
            if (panel.documentsBridge.results.length > 0)
                panel.libraryExpanded = false;
        }
        function onDocumentsChanged() {
            panel.libraryExpanded = true;
        }
    }
    component DocumentAction: Button {
        id: action
        property bool primary: false
        implicitHeight: 38
        implicitWidth: contentItem.implicitWidth + 26
        contentItem: Text {
            text: action.text
            textFormat: Text.PlainText
            font.pixelSize: 12
            color: !action.enabled ? "#969b91" : action.primary ? "white" : "#242723"
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 12
            color: !action.enabled ? "#eeefea" : action.primary ? "#245dc9" : action.down ? "#e3ecfb" : "white"
            border.color: action.activeFocus ? "#245dc9" : "#d8dcd2"
        }
    }
    FileDialog {
        id: documentPicker
        objectName: "documentPicker"
        title: "Import a selected local document"
        nameFilters: ["UTF-8 text and Markdown (*.txt *.md *.markdown)"]
        onAccepted: panel.documentsBridge.importFile(selectedFile)
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: 12
        RowLayout {
            Layout.fillWidth: true
            Label {
                text: "Research workspace"
                color: "#242723"
                font.pixelSize: 18
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
            DocumentAction {
                objectName: "researchSourcesTab"
                visible: !panel.splitView
                text: "Sources"
                primary: !panel.showDraft
                onClicked: panel.showDraft = false
            }
            DocumentAction {
                objectName: "researchDraftTab"
                visible: !panel.splitView
                text: "Draft"
                primary: panel.showDraft
                onClicked: panel.showDraft = true
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16
            ScrollView {
                id: sourceViewport
                objectName: "researchSourceViewport"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: panel.width * 0.53
                Layout.minimumWidth: 0
                visible: panel.splitView || !panel.showDraft
                clip: true
                contentWidth: availableWidth
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ScrollBar.vertical: MiwlScrollBar {}
                ColumnLayout {
                    width: sourceViewport.availableWidth
                    spacing: 14
                    Label {
                        Layout.fillWidth: true
                        text: "Search selected local snapshots. Review a passage, then insert it beside your writing."
                        wrapMode: Text.Wrap
                        color: "#666b63"
                        font.pixelSize: 13
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: sources.implicitHeight + 32
                        color: "white"
                        radius: 16
                        border.color: "#dedfd8"
                        ColumnLayout {
                            id: sources
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 16
                            spacing: 10
                            RowLayout {
                                Layout.fillWidth: true
                                Label {
                                    text: "Sources · " + (panel.documentsBridge ? panel.documentsBridge.documents.length : 0)
                                    color: "#242723"
                                    font.pixelSize: 18
                                    font.weight: Font.DemiBold
                                    Layout.fillWidth: true
                                }
                                DocumentAction {
                                    objectName: "documentLibraryToggle"
                                    text: panel.libraryExpanded ? "Hide list" : "Choose sources"
                                    visible: panel.documentsBridge && panel.documentsBridge.documents.length > 0
                                    onClicked: panel.libraryExpanded = !panel.libraryExpanded
                                }
                                DocumentAction {
                                    objectName: "documentsImport"
                                    text: "Import file…"
                                    primary: true
                                    enabled: panel.documentsBridge && !panel.busy && !panel.externalBusy
                                    onClicked: documentPicker.open()
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                visible: panel.libraryExpanded
                                text: "UTF-8 .txt / .md · 1 MB per file · 100 files / 10 MB total · originals are unchanged"
                                font.pixelSize: 11
                                color: "#666b63"
                                wrapMode: Text.Wrap
                            }
                            Label {
                                objectName: "documentsEmpty"
                                visible: !panel.documentsBridge || panel.documentsBridge.documents.length === 0
                                text: "No documents imported. Choose a local file to begin."
                                font.pixelSize: 12
                                color: "#666b63"
                            }
                            ListView {
                                id: sourceList
                                visible: panel.libraryExpanded
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.min(contentHeight, 180)
                                clip: true
                                model: panel.documentsBridge ? panel.documentsBridge.documents : []
                                spacing: 4
                                ScrollBar.vertical: MiwlScrollBar {}
                                delegate: RowLayout {
                                    required property var modelData
                                    width: sourceList.width
                                    spacing: 8
                                    CheckBox {
                                        objectName: "documentSelected" + modelData.id
                                        checked: modelData.selected
                                        enabled: !panel.busy
                                        text: modelData.name
                                        Accessible.name: "Use " + modelData.name + " for search"
                                        Layout.fillWidth: true
                                        contentItem: Text {
                                            text: parent.text
                                            textFormat: Text.PlainText
                                            leftPadding: parent.indicator.width + parent.spacing
                                            font.pixelSize: 12
                                            color: "#242723"
                                            elide: Text.ElideMiddle
                                        }
                                        onClicked: panel.documentsBridge.selectDocument(modelData.id, checked)
                                    }
                                    Label {
                                        text: modelData.chunks + " passages"
                                        font.pixelSize: 11
                                        color: "#666b63"
                                    }
                                    DocumentAction {
                                        objectName: "documentDelete" + modelData.id
                                        text: "Remove…"
                                        enabled: !panel.busy && !panel.externalBusy
                                        onClicked: {
                                            removeDialog.documentId = modelData.id;
                                            removeDialog.open();
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: queryForm.implicitHeight + 32
                        color: "white"
                        radius: 16
                        border.color: "#dedfd8"
                        ColumnLayout {
                            id: queryForm
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            anchors.margins: 16
                            spacing: 10
                            Label {
                                text: "Find source evidence"
                                font.pixelSize: 18
                                font.weight: Font.DemiBold
                                color: "#242723"
                            }
                            MiwlField {
                                id: question
                                hasError: panel.documentsBridge && panel.documentsBridge.error.length > 0
                                objectName: "documentsQuestion"
                                Accessible.name: "Question for selected documents"
                                Layout.fillWidth: true
                                maximumLength: 500
                                placeholderText: "For example: how many respondents reported saving time?"
                                enabled: !panel.busy && !panel.externalBusy
                                onAccepted: panel.documentsBridge.search(text)
                            }
                            Flow {
                                Layout.fillWidth: true
                                spacing: 8
                                DocumentAction {
                                    objectName: "documentsSearch"
                                    text: "Search selected sources"
                                    primary: true
                                    enabled: panel.documentsBridge && !panel.busy && !panel.externalBusy && question.text.trim().length > 0
                                    onClicked: panel.documentsBridge.search(question.text)
                                }
                                DocumentAction {
                                    objectName: "documentsQuote"
                                    text: "Choose quotations with local AI"
                                    enabled: panel.documentsBridge && !panel.busy && !panel.externalBusy && panel.documentsBridge.canUseModel && panel.documentsBridge.results.length > 0
                                    onClicked: panel.documentsBridge.chooseQuotations()
                                }
                                DocumentAction {
                                    objectName: "documentsStop"
                                    text: "Stop"
                                    enabled: panel.busy
                                    onClicked: panel.documentsBridge.stop()
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                text: "FTS5 uses matching keywords; paraphrases may need more specific terms. Local AI receives this question and retrieved text only. Writing notes, conversation, voice and gallery data stay outside the request. Cloud document requests are disabled."
                                color: "#666b63"
                                font.pixelSize: 11
                                wrapMode: Text.Wrap
                            }
                            Label {
                                objectName: "documentsStatus"
                                Layout.fillWidth: true
                                text: panel.documentsBridge ? panel.documentsBridge.statusText : "Documents unavailable"
                                color: "#245dc9"
                                font.pixelSize: 12
                                wrapMode: Text.Wrap
                            }
                            Label {
                                objectName: "documentsError"
                                Layout.fillWidth: true
                                visible: panel.documentsBridge && panel.documentsBridge.error.length > 0
                                text: panel.documentsBridge ? panel.documentsBridge.error : ""
                                color: "#a03535"
                                font.pixelSize: 12
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                    Repeater {
                        model: panel.documentsBridge ? panel.documentsBridge.results : []
                        Rectangle {
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: passage.implicitHeight + 32
                            color: "white"
                            radius: 16
                            border.color: "#dedfd8"
                            ColumnLayout {
                                id: passage
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 16
                                spacing: 8
                                DocumentAction {
                                    objectName: "documentCitation" + modelData.id
                                    text: modelData.name + " · lines " + modelData.lineStart + "–" + modelData.lineEnd
                                    enabled: !panel.busy
                                    onClicked: panel.documentsBridge.openCitation(modelData.citation)
                                }
                                MiwlArea {
                                    objectName: "documentPassage" + modelData.id
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Math.min(implicitHeight, 160)
                                    readOnly: true
                                    selectByMouse: true
                                    textFormat: TextEdit.PlainText
                                    wrapMode: TextEdit.Wrap
                                    text: modelData.text
                                    color: "#242723"
                                    font.pixelSize: 13
                                }
                                DocumentAction {
                                    objectName: "insertQuotation" + modelData.id
                                    text: "Insert quotation in draft"
                                    primary: true
                                    enabled: !panel.busy && !panel.externalBusy
                                    onClicked: panel.quoteRequested(modelData.citation)
                                }
                                Label {
                                    text: "Imported snapshot · citation " + modelData.id + " · characters " + modelData.start + "–" + modelData.end
                                    color: "#666b63"
                                    font.pixelSize: 11
                                }
                            }
                        }
                    }
                }
            }
            Rectangle {
                objectName: "researchDraftPane"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: panel.width * 0.47
                Layout.minimumWidth: 0
                visible: panel.splitView || panel.showDraft
                color: "white"
                radius: 16
                border.color: "#dedfd8"
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12
                    RowLayout {
                        Layout.fillWidth: true
                        Label {
                            text: "Your draft"
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                            color: "#242723"
                            Layout.fillWidth: true
                        }
                        DocumentAction {
                            objectName: "researchCopyDraft"
                            text: "Copy"
                            enabled: researchDraft.text.trim().length > 0
                            onClicked: panel.copyDraftRequested()
                        }
                    }
                    Label {
                        text: "Keep the evidence in view. Insert a passage at the cursor, then write around it."
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: "#666b63"
                        font.pixelSize: 12
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ScrollBar.vertical: MiwlScrollBar {}
                        MiwlArea {
                            id: researchDraft
                            objectName: "researchDraftEditor"
                            Accessible.name: "Research draft"
                            placeholderText: "Build a draft from the passages beside you…"
                            readOnly: panel.busy || panel.externalBusy
                            text: panel.draftText
                            onTextChanged: if (text !== panel.draftText)
                                panel.draftEdited(text)
                        }
                    }
                    Label {
                        text: panel.workspaceBridge && panel.workspaceBridge.editorSaveFailed ? "Unsaved edits remain here. Retry saving or copy them before closing." : "Same saved draft · local edits save automatically"
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: "#666b63"
                        font.pixelSize: 11
                    }
                    Label {
                        text: "Inserted quotations keep the source name, lines and snapshot hash as text. They remain in your draft if the imported source is removed."
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        color: "#666b63"
                        font.pixelSize: 11
                    }
                }
            }
        }
    }
    Dialog {
        id: removeDialog
        objectName: "documentRemoveDialog"
        property string documentId: ""
        title: "Remove this imported source?"
        palette.window: "#ffffff"
        palette.windowText: "#242723"
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        background: Rectangle {
            color: "#ffffff"
            radius: 20
            border.color: "#d8dcd2"
        }
        Label {
            text: "Removes the imported copy and search entries.\nThe original file and backups remain separate."
            color: "#666b63"
        }
        onAccepted: panel.documentsBridge.deleteDocument(documentId)
    }
    Dialog {
        id: reader
        objectName: "documentCitationDialog"
        title: "Imported source snapshot"
        palette.window: "#ffffff"
        palette.windowText: "#242723"
        parent: Overlay.overlay
        modal: true
        width: Math.min(760, panel.Window.width - 48)
        height: Math.min(560, panel.Window.height - 80)
        anchors.centerIn: parent
        standardButtons: Dialog.Close
        background: Rectangle {
            objectName: "documentCitationBackground"
            color: "#ffffff"
            radius: 20
            border.color: "#d8dcd2"
        }
        contentItem: ColumnLayout {
            spacing: 10
            Label {
                objectName: "documentCitationHeading"
                Layout.fillWidth: true
                text: panel.documentsBridge && panel.documentsBridge.citation.name ? panel.documentsBridge.citation.name + " · lines " + panel.documentsBridge.citation.lineStart + "–" + panel.documentsBridge.citation.lineEnd : ""
                textFormat: Text.PlainText
                font.pixelSize: 16
                color: "#242723"
            }
            Label {
                Layout.fillWidth: true
                text: panel.documentsBridge && panel.documentsBridge.citation.sourcePath ? panel.documentsBridge.citation.sourcePath : ""
                textFormat: Text.PlainText
                font.pixelSize: 11
                color: "#666b63"
                elide: Text.ElideMiddle
            }
            Label {
                Layout.fillWidth: true
                text: panel.documentsBridge && panel.documentsBridge.citation.sha256 ? "Imported bytes SHA-256: " + panel.documentsBridge.citation.sha256 : ""
                textFormat: Text.PlainText
                font.pixelSize: 10
                color: "#666b63"
                wrapMode: Text.Wrap
            }
            Label {
                objectName: "documentCitationQuote"
                Layout.fillWidth: true
                visible: panel.documentsBridge && panel.documentsBridge.citation.quotedText !== panel.documentsBridge.citation.text
                text: panel.documentsBridge && panel.documentsBridge.citation.quotedText ? "Cited quotation: " + panel.documentsBridge.citation.quotedText : ""
                textFormat: Text.PlainText
                font.pixelSize: 12
                color: "#245dc9"
                wrapMode: Text.Wrap
            }
            ScrollView {
                objectName: "documentCitationScroll"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ScrollBar.vertical: MiwlScrollBar {}
                MiwlArea {
                    objectName: "documentCitationText"
                    text: panel.documentsBridge && panel.documentsBridge.citation.text ? panel.documentsBridge.citation.text : ""
                    readOnly: true
                    textFormat: TextEdit.PlainText
                    selectByMouse: true
                    wrapMode: TextEdit.Wrap
                    color: "#242723"
                }
            }
        }
    }
    Connections {
        target: panel.documentsBridge
        function onCitationChanged() {
            if (panel.documentsBridge.citation.text)
                reader.open();
            else
                reader.close();
        }
    }
}
