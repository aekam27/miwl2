import QtQuick
import QtQuick.Controls

TextArea {
    id: control
    property bool hasError: false
    font.family: "Helvetica Neue"
    font.pixelSize: 14
    color: enabled ? "#242b23" : "#697464"
    placeholderTextColor: "#6c7768"
    selectionColor: "#cdddff"
    selectedTextColor: "#14261f"
    wrapMode: TextEdit.Wrap
    textFormat: TextEdit.PlainText
    padding: 16
    selectByMouse: true
    persistentSelection: true
    hoverEnabled: true
    activeFocusOnTab: true
    background: InputSurface {
        objectName: control.objectName + "Surface"
        implicitHeight: 0
        implicitWidth: 0
        radius: 16
        containedFocus: true
        focused: control.activeFocus
        hovered: control.hovered
        available: control.enabled
        invalid: control.hasError
        readOnly: control.readOnly
    }
}
