import QtQuick

Canvas {
    property string name: "document"
    property color ink: "#24232a"
    implicitWidth: 20
    implicitHeight: 20
    onNameChanged: requestPaint()
    onInkChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        var c = getContext("2d");
        c.reset();
        c.scale(width / 24, height / 24);
        c.strokeStyle = ink;
        c.fillStyle = ink;
        c.lineWidth = 1.65;
        c.lineCap = "round";
        c.lineJoin = "round";
        function line(x1, y1, x2, y2) {
            c.moveTo(x1, y1);
            c.lineTo(x2, y2);
        }
        c.beginPath();
        switch (name) {
        case "plus":
            line(12, 5, 12, 19);
            line(5, 12, 19, 12);
            break;
        case "search":
            c.arc(10.5, 10.5, 6.2, 0, Math.PI * 2);
            line(15, 15, 20, 20);
            break;
        case "sidebar":
            c.roundedRect(3, 4, 18, 16, 3, 3);
            line(9, 4, 9, 20);
            break;
        case "document":
            c.moveTo(5, 3);
            c.lineTo(14, 3);
            c.lineTo(19, 8);
            c.lineTo(19, 21);
            c.lineTo(5, 21);
            c.closePath();
            line(14, 3, 14, 8);
            line(14, 8, 19, 8);
            line(8, 12, 16, 12);
            line(8, 16, 14, 16);
            break;
        case "chat":
            c.moveTo(7, 4);
            c.lineTo(17, 4);
            c.quadraticCurveTo(21, 4, 21, 8);
            c.lineTo(21, 14);
            c.quadraticCurveTo(21, 18, 17, 18);
            c.lineTo(9, 18);
            c.lineTo(4, 21);
            c.lineTo(4, 17);
            c.quadraticCurveTo(3, 16, 3, 14);
            c.lineTo(3, 8);
            c.quadraticCurveTo(3, 4, 7, 4);
            break;
        case "copy":
            c.roundedRect(8, 8, 13, 13, 2, 2);
            c.moveTo(15, 5);
            c.lineTo(15, 3);
            c.lineTo(3, 3);
            c.lineTo(3, 15);
            c.lineTo(5, 15);
            break;
        case "arrow":
            line(12, 19, 12, 5);
            line(6, 11, 12, 5);
            line(12, 5, 18, 11);
            break;
        case "stop":
            c.roundedRect(6, 6, 12, 12, 2, 2);
            break;
        case "close":
            line(6, 6, 18, 18);
            line(18, 6, 6, 18);
            break;
        case "edit":
            c.moveTo(5, 15);
            c.lineTo(15, 5);
            c.lineTo(19, 9);
            c.lineTo(9, 19);
            c.lineTo(4, 20);
            c.closePath();
            line(13, 7, 17, 11);
            break;
        case "lock":
            c.roundedRect(5, 10, 14, 11, 3, 3);
            c.moveTo(8, 10);
            c.lineTo(8, 7);
            c.arc(12, 7, 4, Math.PI, 0);
            c.lineTo(16, 10);
            line(12, 14, 12, 17);
            break;
        case "chevron-down":
            line(6, 9, 12, 15);
            line(12, 15, 18, 9);
            break;
        case "chevron-up":
            line(6, 15, 12, 9);
            line(12, 9, 18, 15);
            break;
        case "check":
            line(5, 12, 10, 17);
            line(10, 17, 19, 7);
            break;
        case "miwl":
            c.lineWidth = 2.5;
            c.moveTo(3, 17);
            c.lineTo(3, 9);
            c.bezierCurveTo(3, 2, 10, 2, 10, 9);
            c.lineTo(10, 15);
            c.moveTo(10, 9);
            c.bezierCurveTo(10, 2, 17, 2, 17, 9);
            c.lineTo(17, 17);
            line(22, 7, 22, 17);
            break;
        }
        c.stroke();
    }
}
