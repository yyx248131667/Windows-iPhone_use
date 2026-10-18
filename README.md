# Windows-iPhone_use

基于 Windows 控制与自动化 iOS 设备（iPhone / iPad）的完整工具链与服务框架。适配 **iOS 17+ CoreDevice 隧道**架构、**WebDriverAgent XCTest 驱动机制**、并提供 **FastAPI 接口与 Python 控制层**。

---

## 📌 核心认知与架构要点

### 1. WDA 不是普通 iOS 应用，而是 XCTest Runner
* **运行机制差异**：普通 iOS 应用通过 SpringBoard 独立运行，而 **WebDriverAgent (WDA)** 依赖 iOS 底层的 **XCTest 测试框架与调试通道**拉起。
* **构建产物保留**：编译阶段**绝不能仅仅打包一个 Runner.ipa**，必须完整保留测试配置 `.xctestrun` 文件、`WebDriverAgentRunner-Runner.app` 及其依赖测试 Bundle。
* **全链路闭环验证**：成功安装签名后的 Runner IPA 并不代表可以启动测试服务。构建、签名、安装、XCTest 调起与 HTTP 通信必须作为一个完整链路进行端到端验证。

### 2. Windows 签名与验证
* **工具选择**：可在 Windows 上使用 Sideloadly、zsign 或配合个人免费/付费 Apple ID 证书进行签名。
* **签名要点**：签名时必须保留 `get-task-allow` 调试权限与测试 runner 的 entitlements 结构，并确保签名后的 Bundle ID 与 `.xctestrun` 配置中的标识符保持一致。
* **可用性校验**：签名安装后，先通过 `device/wda_runner.py` 或 `go-ios` 验证 XCTest 通道是否可被正常引导并启动 HTTP 8100 端口服务。

### 3. iOS 17+ CoreDevice 隧道与 RemoteXPC
* **iOS 16 及以下**：设备通信主要走传统的 `usbmuxd`，可通过端口转发（如 `ios forward 8100 8100` 或 `iproxy`）直接连通 WDA。
* **iOS 17+**：苹果重构为 **CoreDevice** 架构，使用 IPv6 隧道承载 RemoteXPC 通信。在 Windows 下必须通过 `ios tunnel start`（或 `pymobiledevice3 remote tunneld`）建立通信隧道，才能访问设备上的 WDA 服务。

### 4. GitHub Actions 编译考量
* 预置 macOS Runner（macOS 14 + Xcode 15/16）进行 `xcodebuild build-for-testing`。
* 自动打包上传 `.xctestrun` + `WebDriverAgentRunner-Runner.app` 完整测试包，并可选输出未签名的测试 IPA。
* 默认 Artifact 保留期设置为 14 天，充分平衡 GitHub Actions 配额与构建产物留存。

---

## 📁 项目目录结构

```text
Windows-iPhone_use/
├── .github/
│   └── workflows/
│       └── build-wda.yml      # GitHub Actions: 自动编译并打包保留 .xctestrun 与测试 Bundle
│
├── device/
│   ├── discovery.py          # 发现已连接的 iPhone，识别 iOS 版本与连接方式
│   ├── pairing.py            # 配对检查与信任握手引导
│   ├── tunnel.py             # iOS 17+ CoreDevice 隧道与端口转发管理
│   ├── installer.py          # 验证并安装 IPA / 测试 Bundle
│   └── wda_runner.py         # XCTest 驱动与 WDA 启动生命周期管理
│
├── wda/
│   ├── client.py             # WDA RESTful HTTP 客户端（含重试与状态检测）
│   ├── session.py            # 会话生命周期管理与屏幕参数获取
│   ├── screenshot.py         # 极速屏幕截图（支持 PIL Image、PNG 字节与 Base64）
│   ├── elements.py           # 控件树解析与元素定位（XPath / Predicate / Class）
│   └── gestures.py           # 触摸、双击、长按、滑动、拖拽、文本输入与硬件按键
│
├── agent/
│   ├── controller.py         # 顶层自动化控制器，串联设备生命周期与操作执行
│   └── actions.py            # 强类型动作定义（Pydantic 规范化）
│
├── api/
│   └── server.py             # FastAPI HTTP 服务接口
│
├── config/
│   └── settings.yaml         # 全局设备、工具、隧道与服务配置
│
├── requirements.txt          # Python 依赖清单
├── .gitignore                # Git 忽略配置
├── main.py                   # CLI 命令行入口
└── README.md                 # 项目说明文档
```

---

## 🚀 快速上手

### 1. 环境准备
* 操作系统：Windows 10 / 11 (x64)
* Python 版本：Python 3.10+
* 驱动与依赖工具：
  - 安装 [iTunes for Windows](https://www.apple.com/itunes/) 或 Apple Devices 应用（提供基础 usbmuxd 驱动）。
  - 安装 [go-ios](https://github.com/danielpaulus/go-ios)（将其加入系统环境变量 `PATH`，或者在 `config/settings.yaml` 中配置路径）。

安装 Python 依赖：
```bash
pip install -r requirements.txt
```

---

### 2. 编译 WebDriverAgent
由于 Windows 环境无法直接运行 Xcode，本仓库提供了自动化 GitHub Actions 编译工作流：
1. 打开 GitHub 仓库的 **Actions** 选项卡。
2. 选择 **Build WebDriverAgent for Testing** 工作流，点击 **Run workflow**。
3. 工作流执行完毕后，在构建页面下方下载：
   - `WDA-Full-XCTest-Bundle`：包含完整 `.xctestrun` 配置文件与 `WebDriverAgentRunner-Runner.app`。
   - `WebDriverAgentRunner-Runner-IPA`：用于 Windows 签名工具的测试安装包。
4. 解压下载的产物，将 `.xctestrun` 和解压后的应用放置在本地 `artifacts/` 目录下。

---

### 3. Windows 签名与安装
1. 使用 **Sideloadly** 或 **zsign** 对 `WebDriverAgentRunner-Runner.ipa` 进行重签名（使用您的个人免费 Apple ID 或开发者证书）。
2. 将已签名的 IPA 安装到 iPhone：
   ```bash
   python main.py discover
   ```
   或使用模块化安装工具：
   ```python
   from device.installer import AppInstaller
   installer = AppInstaller()
   installer.install("artifacts/signed-WebDriverAgentRunner.ipa")
   ```
3. 在 iPhone 上进入 **设置 -> 通用 -> VPN 与设备管理**，信任签名证书，并在 **隐私与安全性** 中打开 **开发者模式**（重启后生效）。

---

### 4. 启动与验证

#### 命令行方式 (CLI)

1. **发现设备**：
   ```bash
   python main.py discover
   ```
2. **开启 iOS 17+ 隧道**（如果是 iOS 17+ 设备）：
   ```bash
   python main.py tunnel
   ```
3. **启动 WDA XCTest 服务**：
   ```bash
   python main.py run-wda
   ```
4. **截屏测试**：
   ```bash
   python main.py screenshot -o screen.png
   ```
5. **一键全流程验证**：
   ```bash
   python main.py init
   ```

#### 启动 FastAPI 服务
```bash
python main.py server --port 8000
```
启动后访问接口文档：`http://127.0.0.1:8000/docs`。

---

## 🌐 FastAPI 常用接口

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `GET` | `/health` | 健康检查与 WDA 在线状态 |
| `GET` | `/device/discovery` | 发现当前连接的 iOS 设备列表 |
| `POST` | `/device/initialize` | 自动执行隧道建立、WDA 启动与会话初始化 |
| `GET` | `/screenshot` | 截取屏幕（可选 `?raw=true` 直接获取 PNG 二进制） |
| `GET` | `/source` | 获取当前界面的 UI 控件层级树（XML / JSON） |
| `POST` | `/action/tap?x=200&y=400` | 点击指定坐标 |
| `POST` | `/action/swipe` | 滑动屏幕（支持设定起始坐标与持续时间） |
| `POST` | `/action/type?text=Hello` | 输入文本 |
| `POST` | `/action/home` | 返回桌面 / 按下 Home 键 |
| `POST` | `/action/app/launch` | 根据 Bundle ID 启动目标应用 |
| `POST` | `/action/app/terminate` | 根据 Bundle ID 终止目标应用 |
| `POST` | `/action/execute` | 执行标准化 JSON Action 指令 |

---

## 🐍 Python 代码调用示例

```python
from agent.controller import iPhoneController
from agent.actions import TapAction, SwipeAction, InputAction

# 初始化控制器（自动读取 config/settings.yaml）
controller = iPhoneController()
ok, msg = controller.initialize()
if not ok:
    print(f"初始化失败: {msg}")
    exit(1)

# 1. 截屏
img = controller.capture_screenshot()
img.save("current.png")

# 2. 点击指定坐标
controller.execute_action(TapAction(x=200, y=350))

# 3. 输入文本
controller.execute_action(InputAction(text="Hello from Windows!"))

# 4. 滑动屏幕
controller.execute_action(SwipeAction(from_x=200, from_y=600, to_x=200, to_y=200, duration=0.4))

# 5. 返回主屏幕
controller.gestures.press_home()
```

---

## 📄 开源许可
MIT License.
