import QtQuick
import QtQuick.Controls

ScrollBar {
    id: control
    implicitWidth: 10
    implicitHeight: 10
    orientation: Qt.Vertical
    x: parent ? parent.width - width : 0
    y: 0
    width: implicitWidth
    height: parent ? parent.height : implicitHeight
    padding: 2
    hoverEnabled: true
    minimumSize: 0.08
    policy: ScrollBar.AsNeeded
    visible: policy === ScrollBar.AlwaysOn || (policy === ScrollBar.AsNeeded && size < 0.999)
    contentItem: Rectangle {
        implicitWidth: 6
        implicitHeight: 6
        radius: 3
        color: control.pressed ? "#65775e" : control.hovered ? "#85967c" : "#aebba5"
        opacity: control.active || control.hovered || control.pressed ? 1 : 0.65
    }
    background: Rectangle { color: "transparent" }
}
