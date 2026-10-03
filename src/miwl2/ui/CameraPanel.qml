import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: panel
    required property var cameraBridge
    property var visionBridge: null
    component CameraAction: Button {
        id: action
        property bool primary: false
        implicitHeight: 38
        implicitWidth: contentItem.implicitWidth + 26
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
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical: MiwlScrollBar {}
    contentWidth: availableWidth
    ColumnLayout {
        width: panel.availableWidth
        spacing: 16
        Label {
            Layout.fillWidth: true
            text: "Configure two authorized MJPEG sources. Nothing connects on startup. Pause and Stop close the connection; reconnect is manual. Unlock Local gallery to enable local matching separately for each source, after permission from everyone visible."
            wrapMode: Text.Wrap
            color: "#666b63"
            font.pixelSize: 13
        }
        GridLayout {
            Layout.fillWidth: true
            columns: panel.availableWidth >= 760 ? 2 : 1
            columnSpacing: 16
            rowSpacing: 16
            Repeater {
                model: 2
                delegate: Rectangle {
                    required property int index
                    property bool settingsExpanded: false
                    readonly property bool showSettings: settingsExpanded || ["idle", "stopped", "paused", "failed"].indexOf(record.state) >= 0
                    property var vision: panel.visionBridge ? panel.visionBridge.sources[index] : ({enabled: false, result: "Recognition unavailable"})
                    property var record: panel.cameraBridge ? panel.cameraBridge.sources[index] : ({name: "Source " + (index + 1), url: "", authorized: false, state: "idle", detail: "Not connected", error: "", pending: false, hasFrame: false, frameRevision: 0})
                    Layout.fillWidth: true
                    implicitHeight: cameraColumn.implicitHeight + 32
                    radius: 16
                    color: "white"
                    border.color: "#dedfd8"
                    ColumnLayout {
                        id: cameraColumn
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.margins: 16
                        spacing: 10
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                Layout.fillWidth: true
                                text: "Source " + (index + 1) + (record.state === "streaming" ? " · " + record.name : "")
                                color: "#242723"
                                font.pixelSize: 18
                                font.weight: Font.DemiBold
                                elide: Text.ElideRight
                            }
                            CameraAction {
                                visible: ["streaming", "connecting", "reconnecting"].indexOf(record.state) >= 0
                                text: settingsExpanded ? "Hide settings" : "Edit source"
                                onClicked: settingsExpanded = !settingsExpanded
                            }
                        }
                        MiwlField {
                            id: nameField
                            visible: showSettings
                            objectName: "cameraName" + index
                            Accessible.name: "Source " + (index + 1) + " name"
                            Layout.fillWidth: true
                            Component.onCompleted: text = record.name
                            placeholderText: "Source name"
                        }
                        MiwlField {
                            id: urlField
                            hasError: record.error.length > 0
                            visible: showSettings
                            objectName: "cameraUrl" + index
                            Accessible.name: "Source " + (index + 1) + " MJPEG URL"
                            Layout.fillWidth: true
                            Component.onCompleted: text = record.url
                            placeholderText: "http://192.168.1.20/video"
                            selectByMouse: true
                        }
                        Label {
                            Layout.fillWidth: true
                            visible: showSettings
                            text: "HTTP(S) multipart MJPEG · numeric IP or localhost\nUp to 1920 × 1080 · RTSP and webcams are not connected"
                            color: "#666b63"
                            font.pixelSize: 11
                            wrapMode: Text.Wrap
                        }
                        CheckBox {
                            id: authorizedField
                            visible: showSettings
                            objectName: "cameraAuthorized" + index
                            text: "I own this source or have permission to use it"
                            Component.onCompleted: checked = record.authorized
                            font.pixelSize: 11
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            visible: showSettings
                            CameraAction {
                                objectName: "cameraSave" + index
                                text: "Save source"
                                enabled: !record.pending
                                onClicked: panel.cameraBridge.configure(index, nameField.text, urlField.text, authorizedField.checked)
                            }
                            CameraAction {
                                objectName: "cameraConnect" + index
                                primary: true
                                text: "Connect"
                                enabled: record.url.length > 0 && record.authorized && !record.pending && ["idle", "stopped", "paused"].indexOf(record.state) >= 0
                                onClicked: panel.cameraBridge.connectSource(index)
                            }
                            Item { Layout.fillWidth: true }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            implicitHeight: Math.min(230, width * 0.5625)
                            color: "#f1f3ed"
                            radius: 10
                            clip: true
                            Image {
                                anchors.fill: parent
                                source: record.hasFrame ? "image://cameras/" + index + "/" + record.frameRevision : ""
                                cache: false
                                fillMode: Image.PreserveAspectFit
                            }
                            Label {
                                anchors.centerIn: parent
                                visible: !record.hasFrame
                                text: "No frame · source not connected"
                                color: "#666b63"
                                font.pixelSize: 12
                            }
                        }
                        Label {
                            objectName: "cameraState" + index
                            Layout.fillWidth: true
                            text: record.error || record.detail
                            color: record.error || record.state === "failed" ? "#a03535" : "#666b63"
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                        CheckBox {
                            objectName: "cameraRecognitionConsent" + index
                            checked: vision.enabled
                            enabled: panel.visionBridge && panel.visionBridge.unlocked && panel.visionBridge.available && record.state === "streaming"
                            text: "Everyone visible has agreed to local face matching"
                            font.pixelSize: 11
                            onClicked: panel.visionBridge.enableSource(index, checked)
                            contentItem: Label {
                                text: parent.text
                                leftPadding: parent.indicator.width + parent.spacing
                                wrapMode: Text.Wrap
                                font.pixelSize: 11
                                color: parent.enabled ? "#242723" : "#969b91"
                            }
                        }
                        Label {
                            objectName: "cameraRecognitionResult" + index
                            Layout.fillWidth: true
                            text: vision.result
                            color: "#245dc9"
                            wrapMode: Text.Wrap
                            font.pixelSize: 12
                        }
                        Label {
                            Layout.fillWidth: true
                            text: "Possible / uncertain / unknown · cosine is not probability"
                            color: "#666b63"
                            font.pixelSize: 10
                            wrapMode: Text.Wrap
                        }
                        RowLayout {
                            CameraAction {
                                objectName: "cameraReconnect" + index
                                text: "Reconnect"
                                enabled: record.url.length > 0 && record.authorized && !record.pending
                                onClicked: panel.cameraBridge.reconnect(index)
                            }
                            CameraAction {
                                objectName: "cameraPause" + index
                                text: "Pause"
                                enabled: ["connecting", "streaming", "reconnecting"].indexOf(record.state) >= 0
                                onClicked: panel.cameraBridge.pause(index)
                            }
                            CameraAction {
                                objectName: "cameraStop" + index
                                text: "Stop"
                                enabled: record.pending || (record.state !== "idle" && record.state !== "stopped")
                                onClicked: panel.cameraBridge.stop(index)
                            }
                        }
                    }
                }
            }
        }
    }
}
