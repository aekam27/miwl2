import QtQuick
import QtQuick.Controls
import QtQuick.Window

ComboBox {
    id: control
    property bool hasError: false
    implicitWidth: 190
    implicitHeight: 44
    leftPadding: 14
    rightPadding: 42
    topPadding: 10
    bottomPadding: 10
    spacing: 8
    font.family: "Helvetica Neue"
    font.pixelSize: 14
    hoverEnabled: true
    activeFocusOnTab: true
    Accessible.name: displayText
    background: InputSurface {
        objectName: control.objectName + "Surface"
        focused: control.activeFocus || control.popup.opened
        hovered: control.hovered
        available: control.enabled
        invalid: control.hasError
    }
    contentItem: Text {
        text: control.displayText
        textFormat: Text.PlainText
        font: control.font
        color: control.enabled ? "#242b23" : "#697464"
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Item {
        x: control.width - width - 9
        y: (control.height - height) / 2
        width: 26
        height: 26
        Rectangle {
            anchors.fill: parent
            radius: 9
            color: control.popup.opened ? "#e1ebfc" : "#edf2e8"
            border.color: "#dfe6d9"
        }
        Glyph {
            anchors.centerIn: parent
            width: 14
            height: 14
            name: control.popup.opened ? "chevron-up" : "chevron-down"
            ink: control.enabled ? "#4d6246" : "#82907a"
        }
    }
    delegate: ItemDelegate {
        id: option
        required property int index
        objectName: control.objectName + "Option" + index
        width: ListView.view.width
        implicitHeight: 42
        text: control.textAt(index)
        highlighted: control.highlightedIndex === index
        hoverEnabled: true
        Accessible.name: text
        contentItem: Row {
            spacing: 10
            Glyph {
                width: 16
                height: 16
                anchors.verticalCenter: parent.verticalCenter
                name: "check"
                ink: "#245dc9"
                opacity: control.currentIndex === option.index ? 1 : 0
            }
            Text {
                text: option.text
                textFormat: Text.PlainText
                font.family: control.font.family
                font.pixelSize: control.font.pixelSize
                font.weight: control.currentIndex === option.index ? Font.DemiBold : Font.Normal
                color: "#242b23"
                elide: Text.ElideRight
                width: option.width - 50
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        background: Rectangle {
            radius: 10
            color: option.highlighted ? "#dce8fc" : option.hovered ? "#edf3e8" : control.currentIndex === option.index ? "#f0f5fd" : "transparent"
            border.width: 1
            border.color: option.highlighted ? "#b8cdee" : "transparent"
        }
    }
    popup: Popup {
        objectName: control.objectName + "Menu"
        popupType: Popup.Item
        property point anchorPosition: Qt.point(0, 0)
        onAboutToShow: anchorPosition = control.mapToItem(null, 0, 0)
        x: Math.max(12 - anchorPosition.x,
                    Math.min(0, control.Window.width - 12 - anchorPosition.x - width))
        y: anchorPosition.y + control.height + height + 18 <= control.Window.height
           ? control.height + 6 : -height - 6
        width: Math.min(Math.max(control.width, 220), control.Window.width - 24)
        height: Math.min(contentItem.implicitHeight + 14, control.Window.height - 32)
        padding: 7
        topMargin: 12
        bottomMargin: 12
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        contentItem: ListView {
            objectName: control.objectName + "Options"
            clip: true
            implicitHeight: contentHeight
            model: control.delegateModel
            currentIndex: control.highlightedIndex
            highlightMoveDuration: 0
            spacing: 3
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: MiwlScrollBar { }
        }
        background: Item {
            Rectangle {
                anchors.fill: parent
                anchors.topMargin: 5
                anchors.bottomMargin: -5
                radius: 17
                color: "#16263c1c"
            }
            Rectangle {
                anchors.fill: parent
                radius: 17
                gradient: Gradient {
                    GradientStop { position: 0; color: "#ffffff" }
                    GradientStop { position: 1; color: "#f5f8f0" }
                }
                border.color: "#cbd7c3"
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: 16
                    color: "transparent"
                    border.color: "#ffffff"
                }
            }
        }
    }
}
