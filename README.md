# Windows-iPhone_use

在 Windows 上通过 WebDriverAgent（WDA）控制 iPhone，提供 WebUI、FastAPI 接口和 Python 控制层。iOS 17+ 使用 CoreDevice 用户态隧道，并单独转发 WDA 的 HTTP 端口。

## 开源版本包含什么

仓库提供控制程序、通用配置、测试和 WDA 编译工作流。**不提供任何个人签名版本、签名证书、私钥、描述文件或预设设备 UDID。** 每位使用者自行准备适用于其设备的 WDA 签名与安装包。默认包名仅作示例，不代表已完成签名。

`artifacts/` 用于本机存放构建包和签名包，目录中的文件默认不纳入 Git。不要把证书、证书密码、设备配对身份或已签名 IPA 加入公开仓库。

## 环境准备

- Windows 10 / 11，Python 3.10+。
- 安装 Apple Devices 或 iTunes 所提供的 Apple USB 设备支持。
- 从 [go-ios 官方仓库](https://github.com/danielpaulus/go-ios) 获取适用于 Windows 的程序，放到项目根目录并命名为 `ios.exe`。
- 手机通过 USB 连接，解锁并信任电脑；按设备提示开启开发者模式，准备所需开发者磁盘映像。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

不同 go-ios 版本的参数可能有差异，签名、安装和隧道命令以本机 `ios.exe --help` 为准。

## 准备自己的 WDA

### 构建或获取未签名包

本仓库的 Actions 提供 `Build WebDriverAgent for Testing` 工作流。运行后下载 `WDA-Full-XCTest-Bundle` 和 `WebDriverAgentRunner-Runner-IPA`；工作流关闭了代码签名，产物需要由使用者自行签名。也可以参考 [Appium 官方预构建 WDA 说明](https://github.com/appium/appium-xcuitest-driver/blob/master/docs/getting-started/provisioning-profile/generic-device-config.md)。

保留原始 Runner.app、内嵌 `.xctest` 和构建生成的 `.xctestrun` 供排查使用。本项目当前通过 `go-ios runwda` 按已安装的应用包名启动 XCTest，不要求本地存在 `.xctestrun`；配置中的 `xctestrun_path` 不会作为启动参数传给 go-ios。

### iOS 17+ 的框架兼容处理

[Appium 官方说明](https://appium.github.io/appium-xcuitest-driver/latest/guides/run-preinstalled-wda/)指出：预安装 WDA 应使用设备本地的 XCTest 框架；包内旧版 `Frameworks/XC*.framework` 可能造成启动退出。

对于采用此方案的兼容 WDA 构建，在**原始包副本**中移除 Runner.app 顶层 `Frameworks/` 下的 `XC*.framework`，然后重新签名。保留 `PlugIns/WebDriverAgentRunner.xctest` 及 WDA 自身依赖。不要对所有框架或任意版本的 WDA 直接套用删除操作，具体要求以相应 WDA 版本文档为准。

任何改包操作都应在签名前完成；修改已签名包后必须重新签名。

### 签名和安装

使用自己的证书与描述文件，通过支持 iOS 应用签名的工具完成签名：

1. 让主应用的 Bundle ID 与描述文件授权的 App ID 匹配；内嵌测试组件也要正确签名。
2. 检查描述文件覆盖目标设备且未过期，签名完成后再安装。
3. 开发签名和分发签名的权限不同。不能仅凭签名工具名称判断证书类型，也不能把手工修改 `get-task-allow` 当作修复办法；应以描述文件授权和实际启动验证为准。

例如，安装自己生成的签名包：

```powershell
.\ios.exe install --path=artifacts/signed-WebDriverAgentRunner.ipa
```

安装成功只说明安装阶段通过，还需要验证 XCTest、HTTP 服务和会话初始化。WDA 通常由电脑端驱动启动，不能仅以点击手机图标后的表现判断是否可用。

## 配置与启动

个人配置可写入已被 Git 忽略的 `config/settings.local.yaml`，程序会将其合并到通用默认配置，避免把个人包名放进开源文件。

编辑配置，将两个包名改为**自己实际安装的 WDA 主应用包名**：

```yaml
device:
  udid: ""  # 留空自动发现；多设备时填写自己的 UDID
  bundle_id: "com.example.WebDriverAgentRunner.xctrunner"
  testrunner_bundle_id: "com.example.WebDriverAgentRunner.xctrunner"
  xctestrun_path: ""
  app_path: "artifacts/signed-WebDriverAgentRunner.ipa"
```

`com.example...` 是占位示例。`app_path` 是安装包路径配置；WebUI 一键流程不会自动签名或安装 IPA，需要先完成安装。

```powershell
.\.venv\Scripts\python.exe main.py web --no-open
```

打开 [WebUI](http://127.0.0.1:8000/)，点击“一键全流程连接与启动”。依次验证设备发现、配对、隧道、WDA 和会话；完成后显示实际屏幕尺寸。

也可分别在终端运行：

```powershell
# 查看设备
.\.venv\Scripts\python.exe main.py discover
# 保持此终端运行隧道与端口转发
.\.venv\Scripts\python.exe main.py tunnel
# 在另一终端启动 WDA，并保持运行
.\.venv\Scripts\python.exe main.py run-wda
```

## USB 连续画面

默认“自动：优先 USB”通过独立端口读取 WDA 的 MJPEG 连续画面，无需在手机上选择接收器。画面端口与控制请求分开，网页不再反复调用截图接口。默认 30 fps、50% 尺寸、40% JPEG 质量；实际帧率取决于手机和 WDA。可通过 `wda.settings` 调整这三个 MJPEG 设置，通过 `usb_screen` 修改本机和手机端口。

自动模式依次选择 USB、已连接的 AirPlay、截图预览；也可手动选择来源。页面不可见或停止同步后，无其他观看连接时会在约 8 秒后停止读取 USB 画面，只保留最新一帧。USB 不会消除 XCTest 控制本身的耗时。

设计参考 [iPhone-use](https://github.com/zhongerxin/iPhone-use) 的独立 USB MJPEG 通道、最新帧缓存及滚轮合并策略；Windows 转发和网页接入在本项目实现。

## AirPlay 连续画面（可选）

可使用开源 [UxPlay](https://github.com/FDH2/UxPlay) 接收 iPhone 的 AirPlay 屏幕镜像，WDA 继续负责点击、滑动、输入和应用启动。画面与控制相互独立，AirPlay 不会自动缩短 XCTest 执行动作的时间。

Windows 安装方式（Python 3.12+、Git，需要下载约数百 MB，安装后约 2 GB）：

```powershell
.\.venv\Scripts\python.exe tools/setup_airplay.py
```

脚本在 `.runtime/airplay/` 中安装便携 MSYS2、GStreamer，并从固定的 UxPlay 上游源码版本编译接收器，不安装系统服务。这些运行时和 UxPlay 生成的本机身份文件不纳入 Git。UxPlay 使用 GPLv3 许可；若另外分发其二进制，应遵守上游许可要求。

1. 正常启动 WebUI 与 WDA，在画面上方点击“启动 AirPlay”。
2. iPhone 与电脑接入可互通的同一局域网，在控制中心选择“屏幕镜像”→“Windows-iPhone”。
3. 默认优先使用 USB；可手动选择“AirPlay 画面”，或在 USB 不可用时由自动模式选择 AirPlay。连续画面接通后停止截图轮询。
4. 画面已投送但无法点击时，检查 WDA 是否在线。AirPlay 画面可以独立显示，但控制仍需 WDA。

接收器使用 TCP/UDP 7100–7102 和局域网 mDNS 发现。若手机找不到接收器，检查 Windows 的应用防火墙授权、VPN 和路由器的客户端隔离；不要把本地 WebUI 或帧转发端口暴露到公网。

如果手机列表里找不到接收器，且 Windows 防火墙拦截了接收器，可在**管理员 PowerShell**中运行（项目目录下）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\configure_airplay_firewall.ps1
```

脚本仅为接收器程序在选定网卡的本地子网放行所需端口，兼容“专用”和“公用”网络分类，不关闭防火墙，也不开放网页服务或本地画面桥接端口。自定义路径或网卡时可传入 `-ReceiverPath`、`-InterfaceAlias`；用 `-Remove` 可移除这两条规则。若自定义了接收端口，需要相应调整脚本中的端口范围。

实现方式：UxPlay 解码手机发送的视频，由 GStreamer 将画面编码为 JPEG，通过仅监听 `127.0.0.1:7110` 的桥接端口送入 Python；网页使用连续 MJPEG 显示。只保留最新帧，慢客户端不会积压历史帧。此版本不转发音频，不是浏览器原生 H.264/WebRTC 播放；帧率目标为 30 fps，实际延迟与帧率需要按设备和网络实测。

已自行安装 UxPlay 时，可在 `config/settings.local.yaml` 中设置 `airplay.uxplay_bin`。WebUI 提供 `/api/airplay/status`、`/api/airplay/start`、`/api/airplay/stop` 和 `/api/airplay/stream` 接口。启动或退出接收器不会停止 WDA；退出后端服务时会停止其管理的接收器。

## WDA 启动超时排查

| 表现 | 检查方向 |
| --- | --- |
| 没有发现设备 | USB 驱动、数据线、解锁和信任状态 |
| 隧道进程运行，但无法启动 XCTest | 确认隧道信息已就绪；本程序兼容本地 60105、28100 信息端口，并向启动进程传入设备地址、RSD 端口和用户态端口 |
| XCTest 已启动，但本机 8100 不通 | CoreDevice 隧道与 WDA 端口转发是两个步骤；确认 `ios forward 8100 8100` 运行 |
| `Failed to establish connection to the IDE` | 查看手机端日志，检查 WDA/XCTest 框架兼容性、签名包名和驱动版本；不能只靠延长超时解决 |
| WDA 在线但无法控制 | 检查会话初始化错误、开发者模式和设备自动化权限 |

程序合并读取子进程输出，避免标准错误管道阻塞；启动失败会显示近期日志，超时会结束本次启动进程。

## API 与测试

实验性低延迟点击的 GitHub 编译、安装后启用方法及测量结果见 [WDA fast touch](docs/wda-fast-touch.md)。签名在本地完成，证书、设备配对记录和签名产物不纳入 Git。

交互采用标准触摸动作，点击与滑动按顺序执行，最多暂存两次后续操作；操作失败会清空待执行动作。画面留白不参与坐标换算，鼠标滚轮可滑动手机页面。WDA 会话默认缩短空闲等待并关闭动画冷却，可通过 `wda.settings` 调整；页面仍在动画中时，建议等待画面稳定后再点击。

接口文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/status/all` | 设备、隧道、WDA、会话与流程状态 |
| POST | `/api/pipeline/start` | 启动全流程 |
| POST | `/api/pipeline/stop` | 停止会话与后台进程 |
| GET | `/api/screen/latest` | Base64 截图 |
| GET | `/api/screen/raw` | PNG 截图 |
| POST | `/api/action/tap` | 点击，JSON 请求体包含 x、y |
| POST | `/api/action/type` | 输入，JSON 请求体包含 text |
| POST | `/api/action/app/launch` | 启动应用，JSON 请求体包含 bundle_id |
| GET | `/api/logs` | 运行日志 |

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试覆盖隧道目标选择、用户态连接参数、端口转发生命周期和 XCTest 握手失败处理。单元测试通过不等于所有 iOS、WDA 和签名组合都已实机验证。
