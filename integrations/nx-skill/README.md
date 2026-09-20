# integrations/nx-skill —— NX 侧的集成件

本地宿主(`../../plchat-local/`)是"脸和嘴",真正动手建模的是 **nx-skill**。
本目录放的是为了让 nx-skill 跟本地宿主对上话而做的改动。

> nx-skill 不在本仓库里(它是独立项目)。把这里的文件复制到你的 nx-skill 检出即可。

## 1. 菜单 / 工具条:在 NX 里打开本地页面

| 文件 | 放到 nx-skill 的 | 作用 |
|---|---|---|
| `nx_runtime/startup/nx_copilot.tbr` | `nx_runtime/startup/` | 工具条定义 |
| `nx_runtime/startup/nx_control.men` | `nx_runtime/startup/` | 菜单项(**是往原文件里追加,不是覆盖**) |
| `nx_runtime/startup/definitions_nx_control.btn` | `nx_runtime/startup/` | 按钮图标定义 |
| `nx_runtime/startup/open_local_copilot.py` | `nx_runtime/startup/` | 菜单回调:用 `UF_UI_display_url` 把本地页面开进 NX |
| `nx_runtime/application/open_local_copilot.py` | `nx_runtime/application/` | 同上,给脚本方式调用 |

**踩过的坑:`.tbr` 的关键字有顺序要求。** 必须先 `TITLE` 再 `VERSION` 再 `DOCK`,
写成 `VERSION` 在前 NX 会报 `发现意外的关键字 VERSION。期望 TITLE` 并直接忽略整个工具条。

## 2. .NET 实时桥:让宿主编排"当前打开的那个 NX 会话"

nx-skill 有两种执行方式:

- **batch** —— 起一个无界面 NX 进程,新建零件文件跑 journal。不碰你现在开着的活儿。
- **live** —— 通过 .NET Remoting 桥,把 journal 送进**当前正开着的** NX 会话执行。

live 模式的桥有两个产物:

| 产物 | 来源 |
|---|---|
| `nx_runtime/startup/NxLiveBridgeServer.dll` | 编译 `scripts/dotnet_bridge/server/NxLiveBridgeServer.cs` |
| `scripts/dotnet_bridge/bin/NxLiveBridgeClient.exe` | 编译 `scripts/dotnet_bridge/client/NxLiveBridgeClient.cs` |

本目录下的 `dotnet_bridge/` 是**打完补丁的完整源码**,直接覆盖你 nx-skill 里的同名文件。

### 补丁内容:两端钉死 127.0.0.1

**症状**:开着 Clash / 其它 TUN 模式代理时,live 模式报
`无法连接到远程服务器 198.18.0.1:25121`。

**原因**:桥服务端用 `Dns.GetHostName()` 之类拿到本机名,再交给客户端去连。
TUN 代理会劫持 DNS,把本机名解析成 `198.18.x.x` 这种假 IP(Clash 的 fake-ip 段),
于是客户端连了个不存在的地址。这跟 NX、跟代码都没关系,是代理在捣鬼。

**改法**(两处,必须同时改,只改一边没用):

```csharp
// server/NxLiveBridgeServer.cs —— 注册通道时把对外主机名写死
props["machineName"] = "127.0.0.1";          // 原来用的是本机主机名

// client/NxLiveBridgeClient.cs —— 连接时也走 127.0.0.1
var url = "http://127.0.0.1:" + port + "/" + channelName;   // 原来是 http://<主机名>:...
```

改完**两个都要重新编译**,只重编译一边等于没改。编译好后用
`../tools/check-bridge.js` 确认 `127.0.0.1` 字符串确实进了二进制。

### 验证 live 模式

1. 重启 Designcenter
2. 菜单 `NX Skill → Start NX Skill Live Bridge`
3. `node ../tools/check-bridge.js` —— 看两个产物都含 `127.0.0.1`
4. 回到页面,用「▶ 在当前 NX 会话执行」

### live 模式的硬约束(别绕)

NXOpen 只能在 NX 主线程调用,而且**不能**用 `ProcessEvents` / `DoEvents` 去泵消息。
桥的做法是把请求丢到后台线程,靠 .NET Remoting 绕开消息泵 —— 代价是:
**NX 弹出模态对话框时,后台线程会卡死**。所以 live 模式只适合跑不需要人工交互的步骤。

需要用户点确认的步骤(删除、布尔失败、CAE 求解)在计划里标 `gate: "manual"`,
宿主不会自动执行,会停下来等你。

## 3. 环境变量

nx-skill 靠这几个变量找路径,宿主在起子进程时会自己设好
(见 `server.js` 的 `nxEnv()`):

| 变量 | 值 | 作用 |
|---|---|---|
| `NX_SKILL_WORKSPACE` | 工作区目录 | `review/` `parts/` 的落点 |
| `NX_SKILL_PROJECT_ROOT` | nx-skill 根目录 | 桥会校验"脚本路径必须在项目根之下",不设就报 `Python script path must be under ...` |

另外 `UGII_USER_DIR` 要指向 `nx-skill/nx_runtime`,NX 才会加载上面那些菜单/工具条。
用 `../../plchat-local/dc/user-dir-on.cmd` 一键设置(写在 `HKCU\Environment`,不动 NXMCP 的 `UGII_CUSTOM_DIRECTORY_FILE`)。
