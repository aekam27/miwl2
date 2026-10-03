import QtQuick

Item {
    id: surface
    property bool focused: false
    property bool hovered: false
    property bool available: true
    property bool invalid: false
    property bool readOnly: false
    property bool containedFocus: false
    property int radius: 14
    implicitWidth: 220
    implicitHeight: 44
    Rectangle {
        anchors.fill: parent
        anchors.topMargin: 2
        anchors.bottomMargin: -2
        radius: surface.radius
        color: "#0c20341e"
        visible: surface.available
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: surface.radius + 3
        color: "transparent"
        border.width: 3
        border.color: surface.invalid ? "#22ad3946" : "#22245dc9"
        visible: surface.focused && surface.available && !surface.containedFocus
    }
    Rectangle {
        anchors.fill: parent
        radius: surface.radius
        gradient: Gradient {
            GradientStop { position: 0; color: !surface.available ? "#eff1ed" : surface.readOnly ? "#f6f8f3" : "#ffffff" }
            GradientStop { position: 1; color: !surface.available ? "#e9ede6" : surface.readOnly ? "#f0f4ec" : "#f8faf5" }
        }
        border.width: surface.focused ? 1.5 : 1
        border.color: surface.invalid ? "#b0444b" : surface.focused ? "#245dc9" : surface.hovered && surface.available ? "#a3b39e" : "#cbd4c5"
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: surface.radius - 1
            color: "transparent"
            border.color: "#d9ffffff"
        }
    }
    Rectangle {
        objectName: surface.objectName + "ContainedFocus"
        anchors.fill: parent
        anchors.margins: 2
        radius: surface.radius - 2
        color: "transparent"
        border.width: 3
        border.color: surface.invalid ? "#22ad3946" : "#22245dc9"
        visible: surface.focused && surface.available && surface.containedFocus
    }
}
