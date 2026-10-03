import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: panel
    property var visionBridge: null
    clip: true
    contentWidth: availableWidth
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical: MiwlScrollBar {}
    readonly property bool unlocked: visionBridge && visionBridge.unlocked
    readonly property bool busy: visionBridge && visionBridge.busy
    component GalleryAction: Button {
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
    ColumnLayout {
        width: panel.availableWidth
        spacing: 14
        Label {
            Layout.fillWidth: true
            text: "Enroll only people who have agreed. Recognition suggests a possible match, uncertain or unknown; it is not identity verification or authentication. Real-face accuracy and spoof resistance have not been tested."
            color: "#666b63"
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: vault.implicitHeight + 32
            color: "white"
            radius: 16
            border.color: "#dedfd8"
            ColumnLayout {
                id: vault
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 16
                spacing: 10
                Label { text: "Local named gallery"; font.pixelSize: 18; font.weight: Font.DemiBold; color: "#242723" }
                Label {
                    objectName: "galleryStatus"
                    Layout.fillWidth: true
                    text: panel.visionBridge ? panel.visionBridge.statusText : "Local gallery unavailable"
                    color: "#666b63"
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
                RowLayout {
                    Layout.fillWidth: true
                    MiwlField {
                        id: passphrase
                        hasError: panel.visionBridge && panel.visionBridge.error.length > 0
                        objectName: "galleryPassphrase"
                        Accessible.name: "Gallery passphrase"
                        Layout.fillWidth: true
                        visible: !panel.unlocked
                        echoMode: TextInput.Password
                        placeholderText: "Your passphrase · 12–256 characters"
                        maximumLength: 256
                        enabled: !panel.busy
                    }
                    GalleryAction {
                        objectName: "galleryUnlock"
                        visible: !panel.unlocked
                        text: panel.visionBridge && panel.visionBridge.exists ? "Unlock gallery" : "Create gallery"
                        primary: true
                        enabled: panel.visionBridge && !panel.busy && passphrase.text.length >= 12
                        onClicked: {
                            panel.visionBridge.unlock(passphrase.text, !panel.visionBridge.exists);
                            passphrase.clear();
                        }
                    }
                    GalleryAction {
                        objectName: "galleryLock"
                        visible: panel.unlocked || panel.busy
                        text: "Lock now"
                        onClicked: { panel.visionBridge.lock(); passphrase.clear(); }
                    }
                }
                Label {
                    Layout.fillWidth: true
                    text: "Names and descriptors are encrypted on disk. No photos, saved passphrase or Keychain entry. Keep your passphrase safe: there is no recovery. Locks after 10 minutes without gallery interaction."
                    wrapMode: Text.Wrap
                    color: "#666b63"
                    font.pixelSize: 11
                }
                Label {
                    objectName: "galleryError"
                    Layout.fillWidth: true
                    visible: panel.visionBridge && panel.visionBridge.error.length > 0
                    text: panel.visionBridge ? panel.visionBridge.error : ""
                    color: "#a03535"
                    font.pixelSize: 12
                    wrapMode: Text.Wrap
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            visible: panel.unlocked
            implicitHeight: enrollment.implicitHeight + 32
            color: "white"
            radius: 16
            border.color: "#dedfd8"
            ColumnLayout {
                id: enrollment
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 16
                spacing: 10
                Label { text: "Enroll from a current frame"; font.pixelSize: 18; font.weight: Font.DemiBold; color: "#242723" }
                RowLayout {
                    Layout.fillWidth: true
                    MiwlField {
                        id: enrollmentName
                        objectName: "galleryName"
                        Accessible.name: "Consenting person's name"
                        Layout.fillWidth: true
                        maximumLength: 80
                        placeholderText: "Name"
                        enabled: !panel.busy
                    }
                    MiwlCombo {
                        id: sourcePicker
                        objectName: "gallerySource"
                        Accessible.name: "Enrollment source"
                        model: ["Source 1", "Source 2"]
                        enabled: !panel.busy
                        implicitWidth: 120
                    }
                }
                CheckBox {
                    id: enrollmentConsent
                    objectName: "galleryEnrollmentConsent"
                    text: "This person has agreed to named enrollment and local face matching"
                    font.pixelSize: 12
                }
                RowLayout {
                    GalleryAction {
                        objectName: "galleryEnroll"
                        text: "Enroll current frame"
                        primary: true
                        enabled: panel.visionBridge && panel.visionBridge.available && !panel.busy && enrollmentConsent.checked && enrollmentName.text.trim().length > 0
                        onClicked: {
                            panel.visionBridge.enroll(sourcePicker.currentIndex, enrollmentName.text, enrollmentConsent.checked);
                            enrollmentConsent.checked = false;
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        text: "One clear face · no photographs saved · up to 100 people"
                        color: "#666b63"
                        font.pixelSize: 11
                        wrapMode: Text.Wrap
                    }
                }
                Label { text: "Enrolled people"; color: "#242723"; font.pixelSize: 14; font.weight: Font.DemiBold }
                Label {
                    visible: panel.visionBridge && panel.visionBridge.profiles.length === 0
                    text: "Gallery is empty. Nothing is recognized by name yet."
                    color: "#666b63"
                    font.pixelSize: 12
                }
                Repeater {
                    model: panel.visionBridge ? panel.visionBridge.profiles : []
                    RowLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        Label { text: modelData.name; Layout.fillWidth: true; color: "#242723"; elide: Text.ElideRight }
                        GalleryAction {
                            objectName: "galleryDelete" + modelData.id
                            text: "Delete…"
                            onClicked: { deleteDialog.profileId = modelData.id; deleteDialog.open(); }
                        }
                    }
                }
            }
        }
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: thresholds.implicitHeight + 32
            color: "white"
            radius: 16
            border.color: "#dedfd8"
            ColumnLayout {
                id: thresholds
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: 16
                spacing: 10
                Label { text: "Matching settings · this session"; font.pixelSize: 16; font.weight: Font.DemiBold; color: "#242723" }
                Label {
                    Layout.fillWidth: true
                    text: "Cosine similarity is a comparison score, not a probability. Defaults have not been calibrated on your population. A close second candidate stays uncertain. Recognition is off until each source receives separate permission."
                    font.pixelSize: 12
                    color: "#666b63"
                    wrapMode: Text.Wrap
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: 10
                    Column {
                        Label { text: "Match threshold"; font.pixelSize: 11; color: "#666b63" }
                        MiwlField { id: threshold; objectName: "visionThreshold"; text: "0.50"; implicitWidth: 125; validator: DoubleValidator { bottom: 0.35; top: 0.90; decimals: 2; locale: "en_US" } }
                    }
                    Column {
                        Label { text: "Uncertain band"; font.pixelSize: 11; color: "#666b63" }
                        MiwlField { id: band; text: "0.10"; implicitWidth: 125; validator: DoubleValidator { bottom: 0.01; top: 0.20; decimals: 2; locale: "en_US" } }
                    }
                    Column {
                        Label { text: "Second-candidate margin"; font.pixelSize: 11; color: "#666b63" }
                        MiwlField { id: margin; text: "0.08"; implicitWidth: 150; validator: DoubleValidator { bottom: 0.01; top: 0.30; decimals: 2; locale: "en_US" } }
                    }
                    GalleryAction {
                        objectName: "visionApplySettings"
                        text: "Apply"
                        enabled: panel.visionBridge && threshold.acceptableInput && band.acceptableInput && margin.acceptableInput
                        onClicked: panel.visionBridge.configure(Number(threshold.text), Number(band.text), Number(margin.text))
                    }
                }
            }
        }
    }
    Dialog {
        id: deleteDialog
        objectName: "galleryDeleteDialog"
        property string profileId: ""
        title: "Delete this enrollment?"
        modal: true
        anchors.centerIn: Overlay.overlay
        standardButtons: Dialog.Ok | Dialog.Cancel
        Label { text: "Removes the encrypted record from the active local gallery.\nCopies and backups require separate deletion."; color: "#666b63" }
        onAccepted: panel.visionBridge.deleteProfile(profileId)
    }
    Connections {
        target: panel.visionBridge
        function onChanged() {
            if (!panel.unlocked) { enrollmentConsent.checked = false; enrollmentName.clear(); }
        }
    }
}
