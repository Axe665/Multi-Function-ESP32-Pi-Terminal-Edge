# 边节点启动提示弹窗

部署后由 autostart 拉起的小弹窗（标准库 tkinter，无 Qt 依赖）：

- 显示边网页入口：本机 `http://localhost:5173` 与每个局域网 IP 的 `http://<ip>:5173`
- 每行「打开」按钮直接调默认浏览器
- 网页服务没起来时显示红色提示；底部标出边 API 端口

安装自启：

```sh
cp tools/edge-launch/edge-launch.desktop ~/.config/autostart/
```


## 依赖

只用标准库 tkinter（桌面环境一般已带）；最小化系统需要：

```sh
sudo apt install python3-tk
```
