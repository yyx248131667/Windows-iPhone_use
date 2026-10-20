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

编辑 `config/settings.yaml`，将两个包名改为**自己实际安装的 WDA 主应用包名**：

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
