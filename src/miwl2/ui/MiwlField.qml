import QtQuick
import QtQuick.Controls

TextField {
    id: control
    property bool hasError: false
    implicitWidth: 220
    implicitHeight: 44
    leftPadding: 14
    rightPadding: 14
    topPadding: 11
    bottomPadding: 11
    font.family: "Helvetica Neue"
    font.pixelSize: 14
    color: enabled ? "#242b23" : "#697464"
    placeholderTextColor: enabled ? "#6c7768" : "#747f70"
    selectionColor: "#cdddff"
    selectedTextColor: "#14261f"
    selectByMouse: true
    persistentSelection: true
    hoverEnabled: true
    activeFocusOnTab: true
    verticalAlignment: TextInput.AlignVCenter
    background: InputSurface {
        objectName: control.objectName + "Surface"
        focused: control.activeFocus
        hovered: control.hovered
        available: control.enabled
        invalid: control.hasError || (!control.acceptableInput && control.text.length > 0)
        readOnly: control.readOnly
    }
}
