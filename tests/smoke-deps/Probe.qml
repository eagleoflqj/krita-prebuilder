import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Controls 2.15 as Controls
import QtQuick.Layouts
import QtQuick.Shapes 1.15
import QtQuick.Window 2.15

Item {
    property int result: grid.columns * 21
    property string buttonText: button.text
    GridLayout {
        id: grid
        columns: 2
        Button { id: button; text: "SDK Quick" }
        Controls.Button { text: "SDK Controls facade" }
        Shape {
            ShapePath {
                strokeColor: "red"
                startX: 0; startY: 0
                PathLine { x: 10; y: 10 }
            }
        }
    }
}
