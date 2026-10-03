import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs

ScrollView {
    id: voicePanel
    property var voiceBridge: null
    property var workspaceBridge
    property bool compact: false
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical: MiwlScrollBar {}
    readonly property bool busy: voiceBridge ? voiceBridge.busy : false
    component VoiceAction: Button {
        id: action
        property bool primary: false
        implicitHeight: 38
        implicitWidth: contentItem.implicitWidth + 26
        Accessible.name: text
        contentItem: Text {
            text: action.text
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
        id: audioPicker
        title: "Transcribe a local WAV recording"
        nameFilters: ["16 kHz mono PCM WAV (*.wav)"]
        onAccepted: voicePanel.voiceBridge.transcribeFile(selectedFile)
    }
    Connections {
        target: voicePanel.voiceBridge
        function onTranscriptChanged() {
            transcriptEditor.text = voicePanel.voiceBridge.transcript;
        }
    }
    ColumnLayout {
        width: voicePanel.availableWidth
        spacing: 14
        Label {
            Layout.fillWidth: true
            text: "Record up to 60 seconds, then review the transcript before sending. Audio stays on this Mac and temporary recordings are discarded. No background listening."
            wrapMode: Text.Wrap
            color: "#666b63"
            font.pixelSize: 13
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            VoiceAction {
                objectName: "voiceRecordButton"
                text: "Record"
                primary: true
                Accessible.name: text
                enabled: voicePanel.voiceBridge && voicePanel.voiceBridge.recordingAvailable && !voicePanel.busy && !workspaceBridge.busy && !workspaceBridge.documentsBusy
                onClicked: voicePanel.voiceBridge.record()
            }
            VoiceAction {
                objectName: "voiceImportButton"
                text: "Transcribe WAV…"
                Accessible.name: text
                enabled: voicePanel.voiceBridge && voicePanel.voiceBridge.available && !voicePanel.busy && !workspaceBridge.busy && !workspaceBridge.documentsBusy
                onClicked: audioPicker.open()
            }
            VoiceAction {
                objectName: "voiceFinishButton"
                text: "Finish recording"
                enabled: voicePanel.voiceBridge && voicePanel.voiceBridge.phase === "recording"
                onClicked: voicePanel.voiceBridge.finishRecording()
            }
            VoiceAction {
                objectName: "voiceCancelButton"
                text: "Cancel voice"
                enabled: voicePanel.busy
                onClicked: voicePanel.voiceBridge.stop()
            }
        }
        Label {
            objectName: "voiceStatus"
            Layout.fillWidth: true
            text: voicePanel.voiceBridge ? voicePanel.voiceBridge.statusText : "Voice runtime is not connected in this preview."
            color: "#245dc9"
            wrapMode: Text.Wrap
        }
        Label {
            objectName: "voiceError"
            Layout.fillWidth: true
            visible: text.length > 0
            text: voicePanel.voiceBridge ? voicePanel.voiceBridge.error : ""
            color: "#92324a"
            wrapMode: Text.Wrap
        }
        Label { text: "Transcript · review before sending"; font.bold: true; font.pixelSize: 16 }
        ScrollView {
            objectName: "voiceTranscriptScroll"
            Layout.fillWidth: true
            Layout.preferredHeight: voicePanel.compact ? 130 : 175
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical: MiwlScrollBar {}
            MiwlArea {
                id: transcriptEditor
                objectName: "voiceTranscript"
                Accessible.name: "Editable voice transcript"
                placeholderText: "Your local transcript appears here. Correct names, numbers and wording before sending."
                wrapMode: TextEdit.Wrap
                readOnly: voicePanel.busy
                selectByMouse: true
                padding: 12
                Component.onCompleted: text = voicePanel.voiceBridge ? voicePanel.voiceBridge.transcript : ""
                onTextChanged: if (voicePanel.voiceBridge && !voicePanel.busy) voicePanel.voiceBridge.editTranscript(text)
            }
        }
        Flow {
            Layout.fillWidth: true
            spacing: 8
            VoiceAction {
                objectName: "voiceSendButton"
                text: "Send reviewed transcript"
                enabled: !voicePanel.busy && !workspaceBridge.busy && !workspaceBridge.documentsBusy && transcriptEditor.text.trim().length > 0
                onClicked: voicePanel.voiceBridge.sendTranscript()
            }
            VoiceAction {
                objectName: "voiceStopResponseButton"
                text: "Stop response"
                enabled: workspaceBridge.busy
                onClicked: workspaceBridge.stop()
            }
            VoiceAction {
                objectName: "voiceSpeakButton"
                text: "Speak saved draft"
                enabled: voicePanel.voiceBridge && !voicePanel.busy && !workspaceBridge.busy && !workspaceBridge.documentsBusy && workspaceBridge.resultText.trim().length > 0
                onClicked: voicePanel.voiceBridge.speakDraft()
            }
        }
        Label {
            Layout.fillWidth: true
            text: "Playback uses the Mac’s installed Samantha voice, up to 5,000 characters. Stop voice cancels transcription or playback. The transcript is temporary until you send it to this session."
            color: "#666b63"
            font.pixelSize: 12
            wrapMode: Text.Wrap
        }
        Label { text: "Saved draft"; font.bold: true; font.pixelSize: 16 }
        ScrollView {
            objectName: "voiceReplyScroll"
            Layout.fillWidth: true
            Layout.preferredHeight: 140
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical: MiwlScrollBar {}
            MiwlArea {
                objectName: "voiceReply"
                text: workspaceBridge.busy ? workspaceBridge.statusText : workspaceBridge.resultText
                placeholderText: "The completed response for this session appears here."
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                padding: 12
            }
        }
    }
}
