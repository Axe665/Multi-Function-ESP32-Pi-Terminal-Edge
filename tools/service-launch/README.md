# 服务控制台

边、云两仓共用的一份小工具：看服务在不在跑，启停单个或全部，看日志、看健康检查。

## 怎么打开

```sh
./tools/service-launch/launch.sh
```

第一次会起一个只给控制台用的进程（边 8101、云 8102），然后叫出浏览器。
之后再点就是直接开页面。想放进应用菜单：

```sh
sed "s#@ROOT@#$PWD#" deploy/edge.desktop.in > ~/.local/share/applications/edge-console.desktop
```

（云仓把 `deploy/edge.desktop.in` 换成 `deploy/cloud.desktop.in`。）

默认不装开机自启。要装就把生成的 .desktop 拷进 `~/.config/autostart/`。

## 两套部署都认

| 模式 | 怎么认 | 启停方式 |
|---|---|---|
| Docker | compose 项目里已经有容器在跑 | `docker compose up -d` / `stop` / `restart` |
| 原生进程 | 没在跑 docker，或者手动切过去 | 控制台自己拉起仓库根的 `run.sh`，PID 和日志在 `.run/` 下 |

顶栏右侧能手动锁定模式。自动判定看的是 compose 里有没有容器在跑，不是装没装 docker。

原生模式下，如果端口已经被 Docker 那套占着，启动会直接告诉你，不会起两个抢同一个端口。

云仓的原生模式只起 api：定时任务和 AI 报告仍由 compose 里的 worker 负责，两套各跑一份会重复出报告。库和缓存还是容器，compose 已经把 5432 和 6379 发布到 127.0.0.1，只给宿主机上的原生模式用。

还有一个坑在这里堵住：`run.sh` 的 `CLOUD_AUTOSEED` 默认是 1，而 `cloud/seed.py` 会先 `DELETE` 全部业务表再写演示数据。控制台拉起时固定传 `CLOUD_AUTOSEED=0`，不会把演示数据写进真实库。手动跑 `./run.sh` 时还是原来的行为，自己留意。

## 配置

仓库根的 `launcher.toml`：

```toml
[console]
title = "边节点控制台"
port = 8101                      # 控制台自己监听的端口，只绑 127.0.0.1
web_url = "http://127.0.0.1:8001/"          # 底栏「打开网页」跳这里
health_url = "http://127.0.0.1:8001/api/v1/health"   # 健康探测
compose_file = "docker/compose.yml"

[native]
service = "edge-run"             # PID 文件名，也是日志前缀
label = "原生进程 run.sh"         # 界面上显示的名字
script = "run.sh"                # 原生模式下要拉起的脚本
ports = [8001]                   # 起之前查冲突、起来之后查存活
deps = []                        # 云仓是 ["postgres", "redis"]

[native.env]                     # 传给脚本的环境变量，覆盖脚本里的默认值
CLOUD_AUTOSEED = "0"

[services.mosquitto]
label = "MQTT 接入"
note = "8883 设备上行，8884 本机调试"
```

服务清单本身来自 `docker compose config --services`，所以 compose 里加了服务，
控制台会自动多一行（没有配中文名就显示服务名）。这里只补显示用的元数据。

## 安全边界

- 只监听 `127.0.0.1`，局域网访问不到。
- 改状态的请求要带启动时生成的令牌，并且只接受本机 Origin，别的标签页没法顺手把服务停了。
- 「全部停止」只 `compose stop`，不删容器、不碰数据卷。这两个动作都会先弹确认框。

## 两仓同步

`tools/service-launch/` 里的代码和静态页两仓字节相同（跟 `web/src/styles/m3.css` 一个套路），
差异只在各自的 `launcher.toml`。改完一边：

```sh
python3 tools/service-launch/checksums.py     # 重写 CHECKSUMS
diff -r ../Modular-Terminal-Cloud/tools/service-launch tools/service-launch   # 应无输出
```

CI 会跑 `checksums.py --check`，漏同步就红。

## 依赖

Python 3.11 自带 `tomllib`；3.10 上要 `pip install tomli`。此外只要 docker CLI
（原生模式下不需要）。前端没有构建步骤，`m3.css` 和图标字体直接读网页端那一份。
