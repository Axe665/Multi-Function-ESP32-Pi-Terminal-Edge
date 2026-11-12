import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

// 边节点图形化管理台（Qt 6.5.3 / QML）。
// 用途：在本机（同时是边节点）查看健康状态、设备列表，并为设备生成/刷新配对码。
// 直接调边 API：GET /api/v1/health、GET /api/v1/devices、POST /api/v1/devices/{id}/pair。
ApplicationWindow {
    id: app
    width: 1024
    height: 700
    visible: true
    title: "边节点管理台 · Edge Manager"
    color: "#0c1520"

    // 可配置：EDGE_API 环境变量（默认本机 8001）
    readonly property string apiBase: {
        const fromEnv = Qt.application.arguments.length > 1 ? Qt.application.arguments[1] : ""
        return fromEnv !== "" ? fromEnv : "http://127.0.0.1:8001"
    }

    property var health: ({})
    property var devices: []
    property int selectedIndex: -1
    property string pairCode: ""
    property int pairRemaining: 0
    property string statusMessage: ""
    property bool busy: false
    property int refreshTick: 0

    readonly property color bg: "#0c1520"
    readonly property color card: "#132230"
    readonly property color cardAlt: "#0f1b27"
    readonly property color line: "#22384a"
    readonly property color ink: "#e8f3fb"
    readonly property color inkDim: "#8fa8bb"
    readonly property color accent: "#85deff"
    readonly property color good: "#6ee7a8"
    readonly property color bad: "#ff8f8f"

    function request(method, path, body, callback) {
        const xhr = new XMLHttpRequest()
        xhr.open(method, app.apiBase + path)
        xhr.setRequestHeader("Content-Type", "application/json")
        xhr.timeout = 4000
        xhr.onreadystatechange = function () {
            if (xhr.readyState !== XMLHttpRequest.DONE) return
            let parsed = null
            try { parsed = xhr.responseText ? JSON.parse(xhr.responseText) : null } catch (e) {}
            callback(xhr.status, parsed)
        }
        xhr.send(body ? JSON.stringify(body) : null)
    }

    function loadHealth() {
        request("GET", "/api/v1/health", null, function (status, data) {
            if (status === 200 && data) {
                app.health = data
                app.statusMessage = ""
            } else {
                app.statusMessage = "无法连接边 API（" + app.apiBase + "）"
            }
            app.refreshTick++
        })
    }

    function loadDevices() {
        request("GET", "/api/v1/devices", null, function (status, data) {
            if (status === 200 && data) {
                app.devices = data
                if (app.selectedIndex >= app.devices.length) app.selectedIndex = -1
            }
        })
    }

    function selectedDevice() {
        if (app.selectedIndex < 0 || app.selectedIndex >= app.devices.length) return null
        return app.devices[app.selectedIndex]
    }

    function generatePairCode() {
        const device = app.selectedDevice()
        if (!device) return
        app.busy = true
        request("POST", "/api/v1/devices/" + encodeURIComponent(device.device_id) + "/pair", null,
                function (status, data) {
            app.busy = false
            if (status === 200 && data && data.code) {
                app.pairCode = data.code
                app.pairRemaining = data.ttl_s || 600
                app.statusMessage = "配对码已生成：" + data.code
            } else {
                app.pairCode = ""
                app.pairRemaining = 0
                app.statusMessage = "生成配对码失败（HTTP " + status + "）"
            }
        })
    }

    Timer {
        interval: 3000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: { app.loadHealth(); app.loadDevices() }
    }

    Timer {
        interval: 1000
        running: app.pairRemaining > 0
        repeat: true
        onTriggered: {
            if (app.pairRemaining > 0) app.pairRemaining--
            if (app.pairRemaining === 0) {
                app.pairCode = ""
                app.statusMessage = "配对码已过期，请刷新"
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        // ---------- 顶部：健康状态 ----------
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 108
            radius: 16
            color: app.card
            border.color: app.line
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 10

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 12
                    Text {
                        text: "边节点"
                        color: app.ink
                        font.pixelSize: 24
                        font.bold: true
                    }
                    Text {
                        text: (app.health.edge_id || "—")
                        color: app.accent
                        font.pixelSize: 18
                    }
                    Item { Layout.fillWidth: true }
                    Rectangle {
                        width: 10; height: 10; radius: 5
                        color: app.health.mqtt && app.health.mqtt.connected ? app.good : app.bad
                    }
                    Text {
                        text: app.health.mqtt && app.health.mqtt.connected ? "MQTT 已连接" : "MQTT 未连接"
                        color: app.inkDim
                        font.pixelSize: 14
                    }
                    Text {
                        text: "刷新 " + app.refreshTick
                        color: app.inkDim
                        font.pixelSize: 12
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 26
                    Repeater {
                        model: [
                            { k: "批次", v: app.health.batches !== undefined ? app.health.batches : "—" },
                            { k: "设备", v: app.devices.length },
                            { k: "MQTT 收包", v: app.health.mqtt ? app.health.mqtt.received : "—" },
                            { k: "拒收", v: app.health.mqtt ? app.health.mqtt.rejected : "—" },
                            { k: "磁盘余量(MB)", v: app.health.disk_free_mb !== undefined ? app.health.disk_free_mb : "—" },
                            { k: "库", v: app.health.db || "—" }
                        ]
                        delegate: Column {
                            required property var modelData
                            spacing: 2
                            Text { text: modelData.k; color: app.inkDim; font.pixelSize: 12 }
                            Text { text: String(modelData.v); color: app.ink; font.pixelSize: 18; font.bold: true }
                        }
                    }
                    Item { Layout.fillWidth: true }
                }

                Text {
                    Layout.fillWidth: true
                    text: app.statusMessage
                    color: app.statusMessage.indexOf("失败") >= 0 || app.statusMessage.indexOf("无法") >= 0 ? app.bad : app.inkDim
                    font.pixelSize: 13
                    elide: Text.ElideRight
                }
            }
        }

        // ---------- 主体：设备列表 + 配对面板 ----------
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            // 设备列表
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 520
                radius: 16
                color: app.card
                border.color: app.line
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 10

                    Text {
                        text: "设备（" + app.devices.length + "）"
                        color: app.ink
                        font.pixelSize: 17
                        font.bold: true
                    }

                    ListView {
                        id: deviceList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 6
                        model: app.devices
                        currentIndex: app.selectedIndex
                        onCurrentIndexChanged: app.selectedIndex = currentIndex

                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: deviceList.width
                            height: 62
                            radius: 10
                            color: app.selectedIndex === index ? "#1d3a4e" : app.cardAlt
                            border.color: app.selectedIndex === index ? app.accent : app.line
                            border.width: 1

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 10
                                spacing: 10
                                Rectangle {
                                    width: 9; height: 9; radius: 4.5
                                    color: modelData.online ? app.good : app.inkDim
                                }
                                Column {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        text: modelData.device_id
                                        color: app.ink
                                        font.pixelSize: 15
                                        font.bold: true
                                    }
                                    Text {
                                        text: (modelData.link || "?") + " · 模块 " +
                                              (modelData.modules ? modelData.modules.join(",") : "—")
                                        color: app.inkDim
                                        font.pixelSize: 12
                                    }
                                }
                                Text {
                                    text: modelData.online ? "在线" : "离线"
                                    color: modelData.online ? app.good : app.inkDim
                                    font.pixelSize: 12
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: {
                                    deviceList.currentIndex = index
                                    app.selectedIndex = index
                                    app.pairCode = ""
                                    app.pairRemaining = 0
                                }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            visible: app.devices.length === 0
                            text: "还没有设备上报"
                            color: app.inkDim
                            font.pixelSize: 14
                        }
                    }
                }
            }

            // 配对码面板
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: 400
                radius: 16
                color: app.card
                border.color: app.line
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 14

                    Text {
                        text: "配对码"
                        color: app.ink
                        font.pixelSize: 17
                        font.bold: true
                    }

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: app.selectedDevice()
                              ? "为 " + app.selectedDevice().device_id + " 生成 6 位配对码"
                              : "先在左侧选择一个设备"
                        color: app.inkDim
                        font.pixelSize: 13
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 116
                        radius: 14
                        color: app.cardAlt
                        border.color: app.pairCode !== "" ? app.accent : app.line
                        border.width: 1

                        Column {
                            anchors.centerIn: parent
                            spacing: 6
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: app.pairCode !== "" ? app.pairCode : "—— —— ——"
                                color: app.pairCode !== "" ? app.accent : app.inkDim
                                font.pixelSize: 44
                                font.bold: true
                                font.letterSpacing: 6
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: app.pairCode !== ""
                                      ? "剩余 " + Math.floor(app.pairRemaining / 60) + ":" +
                                        String(app.pairRemaining % 60).padStart(2, "0")
                                      : "10 分钟有效"
                                color: app.inkDim
                                font.pixelSize: 13
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12
                        Button {
                            Layout.fillWidth: true
                            text: app.pairCode !== "" ? "刷新配对码" : "生成配对码"
                            enabled: app.selectedDevice() !== null && !app.busy
                            onClicked: app.generatePairCode()
                        }
                        Button {
                            Layout.preferredWidth: 110
                            text: "清空"
                            enabled: app.pairCode !== ""
                            onClicked: { app.pairCode = ""; app.pairRemaining = 0; app.statusMessage = "" }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: "提示：配对码在终端「设置 → 网络连接管理」里输入；" +
                              "过期或已使用后点「刷新配对码」重新生成。"
                        color: app.inkDim
                        font.pixelSize: 12
                    }
                }
            }
        }
    }

    // 截图钩子：qml EdgeManager.qml -- --grab /tmp/edge-manager.png
    // 用于无人值守/无桌面环境下验证界面（渲染完成后保存并退出）。
    readonly property string grabPath: {
        const args = Qt.application.arguments
        const i = args.indexOf("--grab")
        return (i >= 0 && i + 1 < args.length) ? args[i + 1] : ""
    }
    Timer {
        interval: 1800
        running: app.grabPath !== ""
        onTriggered: {
            app.contentItem.grabToImage(function (result) {
                result.saveToFile(app.grabPath)
                Qt.quit()
            })
        }
    }
}
