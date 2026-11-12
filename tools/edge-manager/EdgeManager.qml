import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

// 边节点管理台（Qt 6.5.3 / QML）。
// 视觉遵循 Material 3 深色角色：surface 分层、filled/text 两种按钮、
// display-small 只给配对码用（页面唯一的大元素）。
// 功能：GET /api/v1/health、GET /api/v1/devices、POST /api/v1/devices/{id}/pair。
ApplicationWindow {
    id: app
    width: 1080
    height: 720
    visible: true
    title: "边节点管理台"
    color: tokens.background

    readonly property string apiBase: {
        const args = Qt.application.arguments
        const i = args.indexOf("--api")
        if (i >= 0 && i + 1 < args.length) return args[i + 1]
        return "http://127.0.0.1:8001"
    }

    property var health: ({})
    property var devices: []
    property int selectedIndex: -1
    property string pairCode: ""
    property int pairRemaining: 0
    property string hint: ""
    property bool hintBad: false
    property bool busy: false
    property int refreshTick: 0

    readonly property var tokens: ({
        background: "#0B141C",
        surface: "#101B24",
        surfaceAlt: "#16242F",
        surfaceHigh: "#1D2E3B",
        primary: "#8CD8F5",
        onPrimary: "#003544",
        primaryContainer: "#0E4A5E",
        onSurface: "#E1ECF2",
        onSurfaceVariant: "#A9BCC8",
        outline: "#3A4F5E",
        success: "#7DDDA4",
        danger: "#FFB4AB",
        radiusLarge: 28,
        radiusCard: 18,
        radiusButton: 22
    })

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

    function showHint(text, bad) {
        app.hint = text
        app.hintBad = bad === true
    }

    function loadHealth() {
        request("GET", "/api/v1/health", null, function (status, data) {
            if (status === 200 && data) {
                app.health = data
                if (app.hintBad) app.showHint("", false)
            } else {
                app.showHint("连不上边 API：" + app.apiBase, true)
            }
            app.refreshTick++
        })
    }

    function loadDevices() {
        request("GET", "/api/v1/devices", null, function (status, data) {
            console.log("devices:", status, data ? data.length : -1)
            if (status === 200 && data) {
                app.devices = data
                if (app.selectedIndex >= app.devices.length) app.selectedIndex = -1
                // 抓图模式：直接摆出“已生成配对码 + 状态文字”的最坏情况，
                // 用来确认底部提示不会被撑出卡片（不依赖点击与网络往返）。
                if (app.grabPath !== "" && app.devices.length > 0) {
                    app.selectedIndex = 0
                    app.pairCode = "123456"
                    app.pairRemaining = 600
                    app.showHint("已为 " + app.devices[0].device_id + " 生成配对码", false)
                }
            }
        })
    }

    function selectedDevice() {
        if (app.selectedIndex < 0 || app.selectedIndex >= app.devices.length) return null
        return app.devices[app.selectedIndex]
    }

    function reportCloud() {
        app.busy = true
        request("POST", "/api/v1/report/cloud", null, function (status, data) {
            app.busy = false
            if (status === 200 && data) {
                const state = String(data.cloud || "ok")
                app.showHint("云上报：" + state, state !== "sent")
            } else {
                app.showHint("云上报失败（HTTP " + status + "）", true)
            }
        })
    }

    function generatePairCode() {
        const device = app.selectedDevice()
        if (!device) return
        app.busy = true
        console.log("generate pair for", device.device_id)
        request("POST", "/api/v1/devices/" + encodeURIComponent(device.device_id) + "/pair", null,
                function (status, data) {
            console.log("pair response", status, data ? data.code : "-")
            app.busy = false
            if (status === 200 && data && data.code) {
                app.pairCode = data.code
                app.pairRemaining = data.ttl_s || 600
                app.showHint("已为 " + device.device_id + " 生成配对码", false)
            } else {
                app.pairCode = ""
                app.pairRemaining = 0
                app.showHint("生成失败（HTTP " + status + "）", true)
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
            if (app.pairRemaining === 0 && app.pairCode !== "") {
                app.pairCode = ""
                app.showHint("配对码已过期，可重新生成", false)
            }
        }
    }

    // ---- 基础组件：M3 按钮（全部自定义，不用默认白底控件） ----
    component M3FilledButton: Rectangle {
        id: btn
        property string label
        property bool enabled: true
        signal activated()
        implicitWidth: btnLabel.implicitWidth + 44
        implicitHeight: 44
        radius: tokens.radiusButton
        color: !btn.enabled ? tokens.surfaceHigh
             : tap.pressed ? Qt.darker(tokens.primary, 1.15)
             : tokens.primary
        Text {
            id: btnLabel
            anchors.centerIn: parent
            text: btn.label
            color: btn.enabled ? tokens.onPrimary : tokens.onSurfaceVariant
            font.pixelSize: 14
            font.weight: Font.Medium
        }
        MouseArea {
            id: tap
            anchors.fill: parent
            enabled: btn.enabled
            onClicked: btn.activated()
        }
    }

    component M3TextButton: Rectangle {
        id: btn
        property string label
        property bool enabled: true
        signal activated()
        implicitWidth: btnLabel.implicitWidth + 32
        implicitHeight: 44
        radius: tokens.radiusButton
        color: tap.pressed ? tokens.surfaceHigh : "transparent"
        Text {
            id: btnLabel
            anchors.centerIn: parent
            text: btn.label
            color: btn.enabled ? tokens.primary : tokens.onSurfaceVariant
            font.pixelSize: 14
            font.weight: Font.Medium
        }
        MouseArea {
            id: tap
            anchors.fill: parent
            enabled: btn.enabled
            onClicked: btn.activated()
        }
    }

    // ---- 页面 ----
    ColumnLayout {
        id: rootLayout
        anchors.fill: parent
        anchors.margins: 26
        spacing: 20

        // 页头
        RowLayout {
            Layout.fillWidth: true
            spacing: 16
            ColumnLayout {
                spacing: 2
                Text {
                    text: "边节点管理台"
                    color: tokens.onSurface
                    font.pixelSize: 24
                    font.weight: Font.DemiBold
                }
                Text {
                    text: app.health.edge_id ? ("节点 " + app.health.edge_id) : "节点未连接"
                    color: tokens.onSurfaceVariant
                    font.pixelSize: 13
                }
            }
            Item { Layout.fillWidth: true }
            RowLayout {
                spacing: 8
                Rectangle {
                    width: 8; height: 8; radius: 4
                    color: (app.health.mqtt && app.health.mqtt.connected) ? tokens.success : tokens.danger
                }
                Text {
                    text: (app.health.mqtt && app.health.mqtt.connected) ? "MQTT 已连接" : "MQTT 未连接"
                    color: tokens.onSurfaceVariant
                    font.pixelSize: 13
                }
            }
            RowLayout {
                spacing: 8
                Rectangle {
                    width: 8; height: 8; radius: 4
                    color: (app.health.cloud && app.health.cloud.configured) ? tokens.success : tokens.outline
                }
                Text {
                    text: (app.health.cloud && app.health.cloud.configured) ? "云已配置" : "云未配置"
                    color: tokens.onSurfaceVariant
                    font.pixelSize: 13
                }
            }
            M3TextButton {
                label: "配置云"
                onActivated: {
                    cloudUrlField.text = app.health.cloud_url || ""
                    cloudDialog.open()
                }
            }
            Text {
                text: "每 3 秒自动刷新"
                color: tokens.onSurfaceVariant
                font.pixelSize: 12
            }
        }

        // 指标条：label 12 / value 18
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 84
            radius: tokens.radiusCard
            color: tokens.surface
            border.color: tokens.outline
            border.width: 1
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 24
                anchors.rightMargin: 24
                spacing: 40
                Repeater {
                    model: [
                        { k: "5 分钟批次", v: app.health.batches },
                        { k: "设备", v: app.devices.length },
                        { k: "MQTT 收包", v: app.health.mqtt ? app.health.mqtt.received : "—" },
                        { k: "拒收", v: app.health.mqtt ? app.health.mqtt.rejected : "—" },
                        { k: "磁盘余量 MB", v: app.health.disk_free_mb },
                        { k: "库", v: app.health.db }
                    ]
                    delegate: Column {
                        required property var modelData
                        spacing: 4
                        Text {
                            text: modelData.k
                            color: tokens.onSurfaceVariant
                            font.pixelSize: 12
                        }
                        Text {
                            text: (modelData.v === undefined || modelData.v === null) ? "—" : String(modelData.v)
                            color: tokens.onSurface
                            font.pixelSize: 18
                            font.weight: Font.Medium
                        }
                    }
                }
                Item { Layout.fillWidth: true }
            }
        }

        // 主体
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 20

            // 设备卡
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: tokens.radiusCard
                color: tokens.surface
                border.color: tokens.outline
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 14

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            text: "设备"
                            color: tokens.onSurface
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                        Text {
                            text: app.devices.length + " 台"
                            color: tokens.onSurfaceVariant
                            font.pixelSize: 12
                        }
                        Item { Layout.fillWidth: true }
                        M3TextButton {
                            label: "刷新"
                            onActivated: { app.loadHealth(); app.loadDevices() }
                        }
                    }

                    ListView {
                        id: deviceList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        spacing: 4
                        model: app.devices
                        currentIndex: app.selectedIndex
                        onCurrentIndexChanged: app.selectedIndex = currentIndex

                        delegate: Rectangle {
                            required property var modelData
                            required property int index
                            width: deviceList.width
                            height: 62
                            radius: 12
                            color: app.selectedIndex === index ? tokens.surfaceHigh : "transparent"
                            // 选中态用左侧竖条，而不是整块高亮
                            Rectangle {
                                visible: app.selectedIndex === index
                                width: 3
                                height: 26
                                radius: 2
                                color: tokens.primary
                                anchors.left: parent.left
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 16
                                anchors.rightMargin: 12
                                spacing: 12
                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: modelData.online ? tokens.success : tokens.outline
                                }
                                Column {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text {
                                        text: modelData.device_id
                                        color: tokens.onSurface
                                        font.pixelSize: 15
                                        font.weight: Font.Medium
                                    }
                                    Text {
                                        text: (modelData.link || "未知链路") +
                                              " · 模块 " + (modelData.modules ? modelData.modules.join(", ") : "—")
                                        color: tokens.onSurfaceVariant
                                        font.pixelSize: 12
                                    }
                                }
                                Column {
                                    Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                                    spacing: 2
                                    Text {
                                        anchors.right: parent.right
                                        text: modelData.online ? "在线" : "离线"
                                        color: modelData.online ? tokens.success : tokens.onSurfaceVariant
                                        font.pixelSize: 12
                                    }
                                    // 已配对 = 设备用配对码换过证书（paired_at 有值）；
                                    // 未配对只完成过上报，不能走 mTLS。
                                    // 以证书指纹为准：paired_at 可能被 status 更新，
                                    // 只有 cert_fp 才代表边真的签发过证书。
                                    Text {
                                        anchors.right: parent.right
                                        text: modelData.cert_fp
                                              ? ("已配对 · " + String(modelData.cert_fp).slice(0, 8))
                                              : "未配对"
                                        color: modelData.cert_fp ? tokens.primary : tokens.onSurfaceVariant
                                        font.pixelSize: 11
                                    }
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
                            text: "还没有设备上报。终端连上边之后会出现在这里。"
                            color: tokens.onSurfaceVariant
                            font.pixelSize: 13
                        }
                    }
                }
            }

            // 配对码卡
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: 400
                radius: tokens.radiusCard
                color: tokens.surface
                border.color: tokens.outline
                border.width: 1

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 20
                    spacing: 12

                    Text {
                        text: "配对码"
                        color: tokens.onSurface
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: app.selectedDevice()
                              ? ("为 " + app.selectedDevice().device_id + " 生成一次性配对码，10 分钟内有效")
                              : "先在左侧选择一台设备"
                        color: tokens.onSurfaceVariant
                        font.pixelSize: 13
                    }

                    // 配对码：全页唯一的大字号元素
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 116
                        radius: 16
                        color: tokens.surfaceAlt
                        border.color: app.pairCode !== "" ? tokens.primary : tokens.outline
                        border.width: 1
                        Column {
                            anchors.centerIn: parent
                            spacing: 8
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: app.pairCode !== "" ? app.pairCode : "······"
                                color: app.pairCode !== "" ? tokens.primary : tokens.outline
                                font.pixelSize: 44
                                font.weight: Font.DemiBold
                                font.letterSpacing: 8
                            }
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: app.pairCode !== ""
                                      ? (Math.floor(app.pairRemaining / 60) + ":" +
                                         String(app.pairRemaining % 60).padStart(2, "0") + " 后过期")
                                      : "尚未生成"
                                color: tokens.onSurfaceVariant
                                font.pixelSize: 12
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        M3FilledButton {
                            Layout.fillWidth: true
                            label: app.pairCode !== "" ? "刷新配对码" : "生成配对码"
                            enabled: app.selectedDevice() !== null && !app.busy
                            onActivated: app.generatePairCode()
                        }
                        M3TextButton {
                            label: "清空"
                            enabled: app.pairCode !== ""
                            onActivated: {
                                app.pairCode = ""
                                app.pairRemaining = 0
                                app.showHint("", false)
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    M3TextButton {
                        Layout.fillWidth: true
                        label: "立即上报云"
                        enabled: !app.busy
                        onActivated: app.reportCloud()
                    }

                    Text {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        maximumLineCount: 3
                        elide: Text.ElideRight
                        text: app.hint !== ""
                              ? app.hint
                              : "在终端「设置 → 网络连接管理」输入这 6 位码；过期或被使用后点「刷新配对码」。"
                        color: app.hintBad ? tokens.danger : tokens.onSurfaceVariant
                        font.pixelSize: 12
                    }
                }
            }
        }
    }

    // 云连接配置：手填局域网云地址与令牌（落盘 data/cloud.json，重启仍生效）。
    Dialog {
        id: cloudDialog
        objectName: "cloudDialog"
        parent: Overlay.overlay
        modal: true
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        width: Math.min(560, app.width - 48)
        padding: 24
        background: Rectangle {
            color: tokens.surface
            radius: 20
            border.color: tokens.outline
            border.width: 1
        }
        contentItem: Column {
            spacing: 14
            Text {
                text: "连接云"
                color: tokens.onSurface
                font.pixelSize: 20
                font.weight: Font.DemiBold
            }
            Text {
                width: parent.width
                wrapMode: Text.Wrap
                text: "填写局域网内云节点的地址（HTTPS），保存后立即尝试上报一次。"
                color: tokens.onSurfaceVariant
                font.pixelSize: 13
            }
            TextField {
                id: cloudUrlField
                width: parent.width
                placeholderText: "https://cloud.local:8443"
                color: tokens.onSurface
                placeholderTextColor: tokens.onSurfaceVariant
                background: Rectangle {
                    color: tokens.surfaceAlt
                    radius: 10
                    border.color: cloudUrlField.activeFocus ? tokens.primary : tokens.outline
                    border.width: 1
                }
            }
            TextField {
                id: cloudTokenField
                width: parent.width
                placeholderText: "访问令牌（可选）"
                color: tokens.onSurface
                placeholderTextColor: tokens.onSurfaceVariant
                background: Rectangle {
                    color: tokens.surfaceAlt
                    radius: 10
                    border.color: cloudTokenField.activeFocus ? tokens.primary : tokens.outline
                    border.width: 1
                }
            }
            Text {
                width: parent.width
                wrapMode: Text.Wrap
                visible: app.hint !== "" && cloudDialog.opened
                text: app.hint
                color: app.hintBad ? tokens.danger : tokens.onSurfaceVariant
                font.pixelSize: 12
            }
            Row {
                width: parent.width
                spacing: 8
                anchors.right: parent.right
                M3TextButton {
                    label: "取消"
                    onActivated: cloudDialog.close()
                }
                M3FilledButton {
                    label: "保存并连接"
                    onActivated: {
                        app.busy = true
                        app.request("POST", "/api/v1/cloud/config",
                                    { url: cloudUrlField.text.trim(), token: cloudTokenField.text.trim() },
                                    function (status, data) {
                            app.busy = false
                            if (status === 200 && data) {
                                app.showHint(data.configured ? "云已配置：" + data.url : "已清空云配置", false)
                                cloudDialog.close()
                                app.reportCloud()
                            } else {
                                app.showHint("保存失败（HTTP " + status + "）", true)
                            }
                        })
                    }
                }
            }
        }
    }

    // 截图钩子：qml EdgeManager.qml -- --grab /tmp/edge-manager.png
    readonly property string grabPath: {
        const args = Qt.application.arguments
        const i = args.indexOf("--grab")
        return (i >= 0 && i + 1 < args.length) ? args[i + 1] : ""
    }
    Timer {
        interval: 3500
        running: app.grabPath !== ""
        onTriggered: {
            rootLayout.grabToImage(function (result) {
                result.saveToFile(app.grabPath)
                Qt.quit()
            })
        }
    }
}
