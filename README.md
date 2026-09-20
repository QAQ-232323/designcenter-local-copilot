# Designcenter 2606 内置 AI(Copilot)页面 — 本地调出方案

把 Siemens Designcenter / NX **内置的 Copilot 页面**在本地宿主里跑起来,后端换成你自己的模型,
再通过 [nx-skill](nx-skill/)(本仓库子项目)让它**真的能建模** —— 出计划、过门禁、在 NX 里执行。

**这个仓库里有什么**

| | |
|---|---|
| `plchat-local/` | 本地宿主:页面桥 + 多供应商后端 + 计划生成 / 静态门禁 / 执行编排 |
| `nx-skill/` | **子项目**:NXOpen 技能包 —— Python 包 + CLI + MCP server(23 个工具)/ 批处理 journal / 人工节拍 review,外加 NX 侧菜单与 .NET 实时桥 |
| `README.md` | 从"页面为什么点不动"到"live 模式为什么连不上"的完整踩坑记录(18 节) |
| `FUSION-nx-skill.md` | 两者融合的设计(脸 / 脑 / 手分层, P0–P3 实施分级) |

**这个仓库里没有什么**

**不含任何西门子文件**(版权归 Siemens Industry Software)。官方前端 —— 页面脚本 `plchat.js`、
`NXService.js` 等 8 个,以及 webpack 应用 `plchat_v2` —— 都由 `plchat-local/fetch-frontend.sh`
从**你自己已授权的 Designcenter/NX 安装目录**里重建。详见第 10 节。

### 三步跑起来

```bash
cd plchat-local

# 1) 从本机安装重建官方前端(仓库不含这部分)
bash fetch-frontend.sh          # 自动探测安装目录;只取本地脚本不联网: 加 --skip-cdn

# 2) 配置模型
cp config.example.json config.json     # 填入你自己的 API Key(config.json 不入库)

# 3) 起宿主
node server.js 8765                    # 或双击 start.cmd
# 浏览器打开 http://127.0.0.1:8765/
```

`config.example.json` 默认选中 `mock` 供应商(不联网、回显问题),先用它确认链路通了,再填真 Key。

## 1. 先说结论

* 你装的 **Siemens Designcenter 2606**(\`D:\\Program Files\\Siemens\\DC 2606\`)里**确实内置了 AI**,产品名叫 **Designcenter Copilot**。
* 内置页面本体就在你的硬盘上:

  \`\`\`
  D:\\Program Files\\Siemens\\DC 2606\\UGII\\copilot\\plchat\\PLChat.html
  \`\`\`

  它调用 \`<des-plchat-acc>\` 这个 Web Component,真正的聊天界面(plchat_v2,西门子云上的 webpack 应用)通过内嵌 webview 加载。
* 命令入口在 **帮助(Help)菜单 → Co&pilot...**(内部名 \`UG_APP_COPILOT\`)。
* **为什么你的软件"没接入":** 这条命令要连西门子云 —— 需要 **Siemens 账号登录(HSaaS)** + **nx_copilot_tdoc 授权**,并消耗每月消息额度。官方提示语写得很直白:

  \`\`\`
  UG_APP_COPILOT_HINT = "This command is available in Designcenter X."
  \`\`\`

  没登录/没授权时,命令不可用,所以你在界面上看不到这个页面。

## 2. 这个目录做了什么

把**软件自带的那套 Copilot 前端原样跑起来**,用一个本地宿主(Node)替代 Designcenter 的 WebView2 宿主桥,
并把云端前端(plchat_v2)与配置资源全部镜像到本地 —— 于是不登录西门子云,也能把这个内置页面调出来,
再接上**你自己的大模型**(本地 Ollama / OpenAI 兼容接口 / DeepSeek 等)回答问题。

已实测:页面完整渲染(标题栏、问候语、5 个预设问题、输入框、AI 免责声明),点击预设问题能拿到本地后端返回的答案。

## 3. 快速开始

见文首「三步跑起来」。三步里**只有第一步需要联网**(且可以 `--skip-cdn` 跳过)。

`fetch-frontend.sh` 干的事:

1. 自动探测 Designcenter/NX 安装目录(也可用 `NX_INSTALL="D:/Program Files/Siemens/DC 2606"` 指定);
2. 把官方页面脚本拷过来,并自动打一处必要补丁(见第 7 节);
3. 从西门子 CDN 下载 webpack 前端与配置资源 —— **默认已存在就不重下,下载失败也绝不覆盖本地可用文件**;
4. 把 bundle 里写死的云端地址改写成本地路径(幂等,重复跑不会重复改)。

已实测:从一个"只有自研代码"的目录出发跑完本脚本,8 个页面脚本 + 11 个 bundle 文件
都能**字节级还原**到可用状态(md5 一致)。

## 4. 接真实大模型

配置在 `plchat-local/config.json`,结构是"一组供应商 + 一个当前选中":

```jsonc
{
  "activeProvider": "deepseek",
  "providers": {
    "deepseek": { "baseUrl": "https://api.deepseek.com/v1",     "apiKey": "sk-xxx", "model": "deepseek-chat" },
    "ollama":   { "baseUrl": "http://127.0.0.1:11434/v1",       "apiKey": "",       "model": "qwen2.5:7b"   },
    "mock":     { "baseUrl": "http://127.0.0.1:8765/mock/v1",   "apiKey": "x",      "model": "mock"         }
  },
  "systemPrompt": "……CAD 领域提示词……"
}
```

内置预设见第 13 节。也可以直接在页面上点 ⚙ 改,不用手编 JSON(config.json 已被 .gitignore 排除,
不会误提交)。`systemPrompt` 放 CAD 领域提示词,让回答更贴 Designcenter/NX 操作。

## 5. 可选:挂进 Designcenter 内部

Designcenter 本身留了官方接口(环境变量),可让内嵌 webview 加载**你自己的页面**,并让回答走**你自己的后端**:

\`\`\`bat
set UGII_PLCHATUI_LOCAL_APP_URL=http://127.0.0.1:8765/
set UGII_PLCHAT_CUSTOM_BACKEND_URL=http://127.0.0.1:8765/api/ask
\`\`\`

前提是 **Help → Copilot 命令本身可用**(即已登录且已授权)。命令一旦能打开,webview 里的页面就换成我们这个本地页,
\`host-stub.js\` 检测到 WebView2 宿主(window.chrome.webview)会自动让位给真实宿主桥,不抢。
其它相关开关(从 libcopilotui.dll 里挖出来的):\`UGII_SET_PLCHATUI_DEV_MODE\`(INT / INT_DEV / int / preprod)、
\`UGII_COPILOT_CORE_URL\`、\`UGII_COPILOT_AGENT_SERVICE_URL\`、\`GENX_TOKEN_URL\`。

## 6. 目录结构

```
├─ README.md                    本文档
├─ FUSION-nx-skill.md           本方案与 nx-skill 融合的设计(脸/脑/手分层, P0–P3 分级)
├─ LICENSE                      MIT(本仓库自研代码; nx-skill/ 另有自己的 MIT)
├─ nx-skill/                    ★子项目: NXOpen 技能包(独立 MIT, 详见该目录 README)
│  ├─ src/nx_skill/               Python 包: CLI + MCP server + 发现 / 计划 / 评审
│  ├─ nx_runtime/                 NX 加载侧: 菜单 / 工具条 / 回调脚本
│  ├─ scripts/dotnet_bridge/      .NET 实时桥源码(已含 127.0.0.1 补丁)
│  └─ docs/                       架构 / 官方文档摘要 / 排障
└─ plchat-local/                本地宿主
   ├─ start.cmd                   一键启动(起服务 + 开浏览器)
   ├─ server.js                   ★宿主后端(零依赖): 静态托管 + /api/ask
   │                              + 计划生成 / 静态门禁 / 执行编排 / 多供应商
   ├─ host-stub.js                ★核心: 替代 Designcenter 的 WebView2 宿主桥
   ├─ settings.js                 页面内 ⚙ 面板(模型 / 复核队列 / nx-skill)
   ├─ index.html                  宿主页(官方 PLChat.html 的结构 + 上面两个脚本)
   ├─ des-plchat-acc-local.js     本地版 ACC loader(替代云端 des-plchat-acc-loader-v2.js)
   ├─ config.example.json         配置模板 —— 复制成 config.json 再填 Key
   ├─ fetch-frontend.sh           ★从本机安装重建"西门子那部分"(见第 3、10 节)
   ├─ dc/*.cmd                    环境变量开关(帮助页指向本页 / 用户目录 / 实时桥修复)
   ├─ cache/nxopen-names.txt      NXOpen API 名索引(由 tools/build-nxopen-index.py 生成)
   ├─ tools/                      调试与自检脚本(见 tools/README.md)
   ├─ plchat.js / NXService.js / ...   ← 不随仓库分发, 由 fetch-frontend.sh 重建
   └─ plchat_v2/                       ← 同上, 官方前端镜像
```

> **关于路径**: `nx-skill/` 的物理位置在仓库内。本机的 `E:\AIprojects\nx-skill` 是一个
> **目录联接(junction)** 指向它,所以 `UGII_USER_DIR`、`config.json` 里的 `nxSkillRoot`、
> NX 菜单配置等既有设置**全部照旧可用,不需要改**。换机器时把 `nxSkillRoot` 指到
> `<仓库>\nx-skill` 即可(注意 NX/Python 对含中文的路径敏感,建议放在纯 ASCII 路径下)。

## 7. 原理(宿主桥协议)

官方页面的启动流程是"页面问宿主,宿主给资源":

1. 页面加载完 → 调 \`window.globalhostedInfo.Init()\`;
2. 页面用 \`CallHost({FQN:"com.siemens.nx.copilot.webservice"}, {Method:"InitPLChat"})\` 向宿主问初始化数据;
3. 宿主回 \`{ scripts:[loader], icebreakerQuestionList:[...], plchatElement:"{...属性...}", enableCustomBackend, enableCustomTheme }\`;
4. 页面加载 loader,创建 \`<des-plchat-acc>\` 并挂上 \`color-theme / plservice-identifier / enable-streaming ...\` 等属性;
5. 用户提问时(自定义后端模式),页面发 \`CallHost({Method:"GetAnswer", MethodData:{question, product:{identifier:"NX_X", version}}})\`,
   宿主把答案灌回元素的 \`plservice-response\` 属性,UI 渲染出来。

`host-stub.js` 就是替宿主实现第 3、5 步。另有三处必要改动,都由 `fetch-frontend.sh` 自动完成:

| 文件 | 改动 | 不改会怎样 |
|---|---|---|
| `plchat.js` | `script.integrity = scriptSrc.SRI` → 仅当 SRI 存在时才校验 | 本地副本 SRI 对不上,浏览器拒绝执行,**整页白屏** |
| `runtime~main.js` | webpack `publicPath` 的云端地址 → `/plchat_v2/` | 懒加载 chunk 回去联网,离线白屏 |
| `dynamic-config.js` | 硬编码 `baseUrl` 的云端地址 → `/plchat_v2/assets` | 配置/i18n 跨域被 CORS 挡,界面出现 `{{i18n.xxx}}` 未翻译占位 |

前两处是「把页面搬出 Designcenter」必然带来的,第三处是因为我们把资源镜像到了本地。

## 8. 重新同步前端(可选)

西门子更新云上前端后可以重跑 `fetch-frontend.sh`:

```bash
bash fetch-frontend.sh            # 页面脚本(从本机安装) + bundle + assets, 一次搞定
bash fetch-frontend.sh --force    # 强制重下(默认已存在的文件不动)
bash fetch-frontend.sh --skip-cdn # 只从本机安装取页面脚本, 完全不联网
```

脚本会自动做第 7 节提到的那些改写,并逐个文件报告结果
(`OK` 已是本地路径 / `PATCH` 刚改好 / `WARN` 结构变了要人工确认)。

两个注意点:

* 该 CDN(`acc.adhoc.sws.siemens.com`)在国内网络下会掉连接,脚本已带 `--retry`;
  某文件 HTTP 非 200 时**会保留你本地的原文件**,所以重跑是安全的,不会把能用的前端搞坏。
* 官方改版换了文件名哈希时,脚本会报 `WARN ... upstream layout may have changed`,
  需要人工确认新的文件名并更新脚本里的清单。

## 9. 已知限制

* **只走本地后端问答**。ACC 云会话(\`acc-session-id\`)没有,控制台会有一条
  \`Unable to decode acc session id\`(无害);依赖 ACC 的能力(命令上下文跳转、代理(Agent)列表、
  语音、部分遥测)用不了。问答链路完全不依赖它。
* 发给模型的只有问题文本 + 产品标识(\`NX_X / 2606\`),**不带 NX 模型上下文**(当前零件、特征、选择集)。
  想要"看懂模型"的回答,需要在 \`server.js\` 的 \`/api/ask\` 里自行接 NXOpen/journal 导出上下文。
* 前端是西门子云上的产物,官方随时可能改哈希/结构,改了就要按第 8 节重新同步。

## 10. 合规提醒

本方案做的是「把随软件安装的官方 Copilot 页面在本地宿主里跑起来 + 由你自己的后端供答案」,
**不涉及破解授权**。西门子官方云端 Copilot(`nx_copilot_tdoc` 授权 + 云登录)仍需正常购买/登录才能使用;
商用请遵守与 Siemens 的许可协议。

### 本仓库为什么不含西门子文件

官方前端(页面脚本 + `plchat_v2` bundle)版权归 Siemens Industry Software,仓库不再分发。
它们在**你自己的机器上、从你自己已授权的安装目录**重建:

| 文件 | 从哪来 | 怎么重建 |
|---|---|---|
| `plchat.js` `NXService.js` `HostInteropService.js` `PLChat*.js` `AppService.js` `hostInterop_async.js` | 安装目录 `UGII/copilot/plchat/` | `fetch-frontend.sh` 直接拷贝 + 打 1 处补丁 |
| `plchat_v2/`(webpack 应用、配置、图标) | 西门子 CDN | `fetch-frontend.sh` 下载 + 打 2 处补丁 |
| `cache/nxopen-names.txt` | 安装目录 `NXOpen.xml` | `tools/build-nxopen-index.py` 生成 |

`LICENSE`(MIT)**只覆盖本仓库的自研代码** —— 即 `server.js`、`settings.js`、`host-stub.js`、
`des-plchat-acc-local.js`、`index.html`、`fetch-frontend.sh`、`dc/*.cmd`、`tools/*`、
`integrations/` 下我们改的部分,以及全部文档。

### 同样不入库的

* `config.json` —— 里面有你的 API Key(仓库只放 `config.example.json`);
* `server.log`、调试截图、抓包存档等运行期产物。

完整规则见 `.gitignore`。

## 11. 原版架构:云脑 + 本地手(实测证据)

回答"原版答案到底在哪算的":**推理在云端,工具在本地,提示词两边都有。**

### 云端负责
| 证据 | 出处 |
|---|---|
| `query GetChatAnswer` → POST `/acc/orchestrate`(带 accSessionId),返回 `data.data.getChatAnswer.answerObject` | plchat_v2/dynamic-plchat |
| `AgentServiceClient` 直连云端 Agent Service:`…/agentList`、`definitions/icebreakers`、`conversations/`,注释 `Authentication token is required to send chat to agent service` | plchat_v2 |
| `AgentService::GetServiceUrl` 默认 `https://cloud.<region>.sws.siemens.com/api/nxxai-<env>/v1/`,区域 us1/eu1/ap1;`UGII_COPILOT_AGENT_SERVICE_URL` 可改 | libcopilot.dll |
| WebSocket `agent/socket`;服务端下发 `toolExecution` 请求,NX 回 `toolOutput`;最终 `AgentService::OnEndChat - Final Response: %s` | libcopilot.dll |
| 额度与授权:`/data/usageInfo`、`nx_copilot_tdoc`、"您已用完当月的所有消息" | libcopilot(Base).dll / libcopilotui.dll |

安装目录里**没有** Copilot 用的大模型文件(找到的 `mcd_preferences_inference.onnx`、`DesignParameterRecommender_DraftAnglePredictor.onnx` 是机电一体化与设计参数推荐用的,与 Copilot 无关)。

### 本地负责(Agent + 工具 + 局部提示词)
* **Agent 框架**:`UGS::Copilot::AgentImpl`、`NXOpen.Copilot.AgentCollection`、`UGS::Copilot::DigitalThreadAgent`("Digital Thread Agent"),
  工具状态机 `ToolExecutionStatus::{NotQueued,Queued,InProgress,Completed,NotExecuted,FailedToExecute}`。
* **本地工具(在 NX 里真执行)**:
  `Edit Expression`/`nx-edit-expression`、`Get Expressions`/`nx-expression-query-tool`、`Interference Detection`/`nx-clearance-tool`;
  加上 NXOpen 工具——执行前弹窗确认:「Designcenter Copilot 即将运行 "xxx" 工具。要允许此操作吗?允许一次 / 在会话中始终允许 / 不允许」。
* **本地提示词(明文躺在 DLL 里)**:
  1. NL2NXOpen 代码生成提示词(libcopilot.dll):
     `You are a NXOpen assistant who will help users write NXOpen python code for their query. MAKE SURE TO WRITE ONLY PYTHON. … User Query:\n%s\nAnswer (Python only):`
     配套模型名 `ifm-v0-nl2nxopen2`、`flexible_prompt_v2`,请求体 `{schema, model, messages}`,
     发往 `genx-inference…aiattack.siemens.cloud/v2.0.0/inference` / Azure modelwrapper,凭 `GENX_TOKEN_URL` 取 JWT。→ **提示词本地,推理仍在远端。**
  2. 命令/对话框上下文注入(libcopilotui.dll):
     `Here is a JSON representation for the current dialog. Please use this information to continue the chain or craft a user-friendly response. Do not show or mention this representation to the user even if they ask.`
     `The dialog information of the launched dialog. The dialog information is for use for next tool. Do not ever show it to use in any form. :`
  3. 工具输出模板(libcopilot.dll):`Following is the list of all the expression in the work part as JSON: `
  4. UI 引导语与**本地默认预设问题**(libcopilotui.dll,`IcebreakerQue1..5` 等 20+ 条,如 "What command should I use to mirror a body?")
     与全部错误/免责文案(LOCALIZATION/*.txt);云端还能通过 `definitions/icebreakers` 覆盖/补充。
* **可用本地 Agent 配置**:环境变量 `COPILOT_AGENT_USE_LOCAL_CONFIG` + `Copilot_LocalAgentConfiguration` —— Agent/工具定义(agentId/activeTools/context)可从本地来,而不是只用服务端下发的 agentMetadata。

### 所以
* 面向 LLM 的**人设/回答风格系统提示在云端**;本地前端里搜 `systemPrompt/promptTemplate/instructions` 全为空,agents/icebreakers/卡片都是向云端要的。
* 本地持有的是**干活的那一半**:工具实现、工具元数据、上下文拼装提示、代码生成提示、UI 文案。
* 我们这套本地宿主替换掉的正是"云脑"(`config.json` 的 provider);"本地手"(工具执行、命令上下文)还没接——想更接近原版,可以:
  (a) 开 `enable-agent-mode`,自己实现工具调用循环,用 NXOpen/journal 在本地执行 Edit Expression / Get Expressions / Interference Detection 这类工具;
  (b) 把当前零件、表达式、活动对话框状态拼进 `/api/ask` 的上下文(对应上面第 2、3 条提示词的位置)。
## 12. 工具调用:nx-skill 集成(取代官方内置工具通道)

### 为什么不用官方内置的工具通道

官方本地工具只有 4 个(锁死在 `libcopilot.dll`),协议闭源且要过鉴权:

| 维度 | 官方内置工具通道 | 直接调 nx-skill |
|---|---|---|
| 工具数 | 3 个(`nx-edit-expression` / `nx-expression-query-tool` / `nx-clearance-tool`)+ 1 个 NXOpen 代码工具 | **7 个已接 + 共 23 个可用** |
| 可扩展 | 否,DLL 里写死 | 开源,随时加 |
| 协议 | 闭源 WebSocket `agent/socket`;`{requestId,toolId,toolParameters}` → `{result,requestId}`;还需 agentMetadata(`agentId/activeTools/context/dev`) | 开放:CLI / MCP stdio,契约有测试 |
| 鉴权 | 需要 ACC 会话 + auth token(前端原话 `Authentication token is required to send chat to agent service`) | 无 |
| 任意 NXOpen | 不行 | `run-python` 随便跑 |
| 人工复核 | 无(只有"允许一次/始终允许"弹窗) | **review 模式**:step gate + UndoMark 精确回退 + 每步 PNG |
| 原生工具卡片 UI | ✅ | ❌ → 我们自己用 HTML 渲染(已实现,见下) |

官方唯一赢的是"原生工具卡片"。但代价是实现西门子整套 agent 协议 + 绕鉴权,工具集还被锁死 4 个,不划算。

好在官方 UI 留了余地:工具的**执行**由 `/api/ask` 负责,工具的**展示**由我们自己在答案 HTML 里画。

### 已实现(阶段 1)

`server.js` 现在是一个带 function calling 的 agent 后端:

```
内置 Copilot 页面 → /api/ask → 你的模型
                                  ↔ 工具调用
                                    nx-skill CLI
```

暴露的 **7 个只读 / 规划类工具**(全部零风险,不碰模型):

| 工具 | 作用 | 实测耗时 |
|---|---|---|
| `nx_status` | 本机 NX 环境:安装根、版本、能力、工作区 | ~1.9s |
| `nx_docs_search` | 离线 API 文档按关键字搜 | ~0.6s |
| `nx_docs_member` | 单个成员签名/参数/引入版本 | ~0.6s |
| `nx_docs_type` | 类型成员列表 | ~1s |
| `nx_route_intent` | 自然语言 → NX 应用路由(支持中文) | ~0.5s |
| `nx_modeling_plan` | 建模计划骨架(分阶段/命名约定) | ~0.5s |
| `nx_visual_spec` | 三视图/识图建模规则 | ~0.5s |

**执行类工具(`journal` / `live` / `review submit`)故意没有暴露** —— 见第 2 节的硬约束:
NXOpen 只能在主线程调用且没有 `ProcessEvents`/`DoEvents`,能改模型的操作必须由人在 NX 里点,
所以第二阶段接的是 `nx_review_submit`(写计划)而不是直接执行。

### 怎么启用

`config.json` 填上你的模型即可(工具自动生效):

```jsonc
{ "provider": "openai", "baseUrl": "https://api.deepseek.com/v1", "apiKey": "sk-…", "model": "deepseek-chat",
  "nxSkillRoot": "E:\\AIprojects\\nx-skill",
  "nxWorkspace": "E:\\AIprojects\\nx-workspace" }
```

**没有模型也能先试工具闭环** —— 内置伪 OpenAI 端点:

```jsonc
{ "provider": "openai", "baseUrl": "http://127.0.0.1:8765/mock/v1", "apiKey": "x", "model": "mock-model" }
```

它会按问题内容确定性地触发一次工具调用,用来验证"模型→工具→答案→卡片"整条链路。

调试用接口:`GET /api/tools`(列出工具)、`POST /api/tool {"name":"nx_status","args":{}}`(直调单个工具)。

### 工具卡片

自定义后端模式下官方不画工具卡片,所以我们在答案 HTML 里自己渲染(答案支持 HTML):

> 🔧 nx-skill 工具调用 1 次(点击展开)
> ✅ nx_status · 1874 ms
> `{ "installations": [ { "root": "D:\Program Files\Siemens\DC 2606", … } ] }`

另注:`plservice-response` 是 **observedAttribute**(每次改都触发 `plchatResponsePropUpdateAction`),
所以将来要做"先推进度、再推结果"的伪流式是可行的;`enable-streaming` 官方默认就是 `true`。

### 隔离

`config.json` 里的 `nxWorkspace` 会设成 `NX_SKILL_WORKSPACE`,避免 nx-skill 与你的 NXMCP 项目
共用工作区(遗留变量 `NX2512_PROJECT_ROOT = E:\AIprojects\NXMCP` 会让两边都落到 NXMCP)。
## 13. 多供应商 + 页面内设置面板

### 支持的供应商(内置预设)

| id | 名称 | Base URL | 默认模型 |
|---|---|---|---|
| `mimo-tokenplan` | 小米 MiMo(Token Plan,`tp-` 密钥) | `https://token-plan-cn.xiaomimimo.com/v1` | `mimo-v2.5` |
| `mimo` | 小米 MiMo(标准 `sk-` 密钥) | `https://api.xiaomimimo.com/v1` | `mimo-v2.5` |
| `deepseek` | DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| `openai` | OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| `ollama` | Ollama(本地) | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` |
| `lmstudio` | LM Studio(本地) | `http://127.0.0.1:1234/v1` | `local-model` |
| `mock` | 内置自测 | `http://127.0.0.1:8765/mock/v1` | `mock-model` |
| `custom` | 自定义(任意 OpenAI 兼容) | 自己填 | 自己填 |

注:MiMo 官方已声明 `mimo-v2-pro` / `mimo-v2-omni` / `mimo-v2-flash` / `mimo-v2-tts` 于 2026-06-30 下线。
`mimo-v2.5` 支持 **全模态理解 + Function Call**,1M 上下文;纯文本可用 `mimo-v2.5-pro`。

### 页面内设置面板

打开 **http://127.0.0.1:8765/**,右下角 **⚙** 按钮:

* 供应商下拉(标记"← 当前")+ Base URL + API Key(已存的只显示掩码,留空即不改)+ 模型(带预设补全)
* **测试连接** —— 用面板里的值直接打一次真实请求,回显耗时与模型回复,不写盘
* **保存并启用** —— 写入 `config.json`,**下一条消息即生效**(服务端每条请求都重读配置)
* 系统提示词、nx-skill 根目录、NX 安装根目录、nx-skill 工作区、最大工具轮数
* 已接入工具列表

后端接口:`GET /api/settings`、`POST /api/settings`、`POST /api/settings/test`。
旧版扁平配置(顶层 `provider/baseUrl/apiKey/model`)会自动迁移到新的多供应商结构,不用手改。

### 工具循环的三处加固

第一版实测时 MiMo 在一个问题上连调 6 次工具、把轮数用光,最后返回空。已修:

1. **兜底轮**:最后一轮用 `tool_choice:"none"` 强制出文本,再补一次纯文本请求
2. **收敛提示**:第 3 轮起注入"已有足够结果,请立刻作答,不要再调工具"
3. **同参去重**:同一工具 + 同一参数只真正执行一次,重复调用直接返回缓存结果
4. 工具结果回灌从 20000 字符收紧到 6000,避免上下文被撑爆

实测(Q1/Q3 两个问题):工具调用 1–2 次,30 秒内给出完整准确答案。
## 14. 在 Designcenter 里怎么把它调出来

**先说清楚:DC 里没有"命令行"。** 有的是**命令查找器**(功能区右上角放大镜)和菜单,
所以是"搜命令名 / 点菜单",不是敲命令。当前有三条路:

### 路线 A —— 把 DC 的"帮助页"指向本地宿主(今天就能用,零授权)★推荐

依据:`UGII/ugii_env_ug.dat` 第 1061–1067 行原文 ——
*"URL for starting NX on-line documentation. The default for this variable is now set internally by NX…
However **if the variable is set it will be used** which supports the customer overriding the value."*
且经核实 `UGII_HTML_UGDOC` 确实被 `NXBIN/libsyss.dll` 读取(未设时回退
`${UGII_UGDOC_BASE}/${UGII_UGDOC_LANG}/product/%s`)。

```bat
plchat-local\dc\help-url-on.cmd      :: setx UGII_HTML_UGDOC "http://127.0.0.1:8765/"
```

然后 **重启 Designcenter** → **帮助(Help) → Designcenter Help...**
(命令查找器的 `SYNONYMS` 是 `documentation`,搜 "help" 或 "documentation" 也能命中)
→ NX 用内置 WebView2(`webviewbrowser.dll`)打开我们的页面。

* 还原:`plchat-local\dc\help-url-off.cmd`
* 代价:整个帮助页被替换,**F1 上下文帮助**也会落到这个地址 —— 需要官方文档时先还原。
* 前提:宿主已在跑(`plchat-local\start.cmd`)。

### 路线 B —— 官方 Copilot 面板加载我们的页面(需授权)

```bat
plchat-local\dc\copilot-hooks-on.cmd
```

设 `UGII_PLCHATUI_LOCAL_APP_URL` + `UGII_PLCHAT_CUSTOM_BACKEND_URL`,重启 DC 后走
**帮助(Help) → Co&pilot...**(命令查找器搜 `Copilot`)。

* **前提**:该命令在你机器上可用。官方提示语是 `HINT This command is available in Designcenter X.`,
  需要 `nx_copilot_tdoc` 授权 + 云登录。**如果它是灰的,这条路直接不通**,请走路线 A。
* 还原:`plchat-local\dc\copilot-hooks-off.cmd`

### 路线 C —— 自建菜单入口(需先做 UGII_USER_DIR 修复)

设 `UGII_USER_DIR=E:\AIprojects\nx-skill\nx_runtime` 后,DC 主菜单 Help 右边会出现
**NX Skill** 级联(Review Plan / Start Live Bridge / Create Smoke Part)。
要加"打开本地 Copilot 宿主"按钮,可以在这个菜单里再加一条,但按钮的 `ACTIONS` 只能跑
journal/python(会拉起**外部浏览器**),不是内嵌。想要内嵌就用路线 A。

### 一句话对照

| 你想干什么 | 在 DC 里操作 |
|---|---|
| 打开我们的 AI 页面(内嵌) | 设 `help-url-on.cmd` → **帮助 → Designcenter Help...** |
| 打开官方 Copilot 面板(若已授权) | 设 `copilot-hooks-on.cmd` → **帮助 → Co&pilot...** |
| 打开 NX Skill 的 Review 对话框 | 先设 `UGII_USER_DIR` → **Help 右侧 NX Skill → Review Plan** |
| 让模型能改模型 | 上面那条 + 聊天页出计划 → 归档成 `plan.json` → 人在 NX 里逐步点 |

### 实测状态

* 路线 A 的机制已核实(变量确被 `libsyss.dll` 读取);**尚未在运行中的 DC 上实点验证** ——
  需要你重启 DC 试一次,把结果告诉我(成功/报错/白屏都行)。
* 路线 B 是否可用取决于你的授权,我这边无法替你判断,只能你把 `Co&pilot...` 菜单项的灰/亮状态告诉我。
## 15. NX Skill Review 集成(AI 出计划 → 人在 NX 里执行)

### 做了什么

把 nx-skill 的**人工节拍复核**(review)接进了 AI 页面,闭环如下:

```
你在 Copilot 页面里说需求
      ↓
模型: nx_route_intent → nx_modeling_plan → nx_review_submit
      ↓
<nx-skill 工作区>/review/plan.json   ← 计划落盘,【不执行】
      ↓
页面 ⚙ 面板「复核队列」实时显示每一步的状态/门槛
      ↓
你在 Designcenter: NX Skill → Review Plan → 逐步点
      每步 SetUndoMark + 自动导出 PNG + 写 run.json
      ↓
面板刷新可见 done / undone / failed
```

### 新增的三个工具

| 工具 | 作用 | 是否改模型 |
|---|---|---|
| `nx_review_submit` | 提交计划到队列(计划走 stdin 传给 CLI) | ❌ 只写文件 |
| `nx_review_status` | 查队列进度 | ❌ |
| `nx_review_clear` | 清空队列 | ❌(只删 plan.json / run.json) |

计划的步骤 schema(工具会校验,但不合格由 nx-skill 报错):

```jsonc
{ "steps": [
  { "name": "01_Base_Block", "operation": "create_block", "gate": "auto",
    "params": { "length": 80, "width": 50, "height": 25, "feature_name": "01_Base_Block" } },
  { "name": "02_Export_STEP", "operation": "noop", "gate": "manual",
    "note": "文件 → 导出 → STEP" }
] }
```

* `name` 必须形如 `NN_Short_Action_Object`(编号让人看出历史顺序)
* `operation` ∈ `create_block | journal | status | screenshot | noop`
* `gate`: `auto` 可连续执行;`manual` 必须人点(默认)。破坏性步骤一律 manual
* `journal` 步骤的脚本要放在 `<workspace>/review/scripts/`

### 页面面板

⚙ 面板顶部新增**复核队列**:
工作区路径、计划 id / 步数 / 原始需求、每步的 **状态徽章**(pending/done/undone/failed/running)
与 **门槛徽章**(auto/manual)、执行入口提示,以及「刷新队列 / 清空队列」。
面板打开时每 5 秒自动刷新。

### ⚠ 关键前提:两边必须看同一个队列目录

NX 侧对话框解析工作区的顺序是(`nx_review_executor.py`):

```python
NX_SKILL_WORKSPACE  →  NX2512_PROJECT_ROOT  →  DC2512_PROJECT_ROOT  →  ~/NXSkillWorkspace
```

本机 `NX2512_PROJECT_ROOT = E:\AIprojects\NXMCP`,所以**不设 `NX_SKILL_WORKSPACE` 的话,
NX 会去 `NXMCP\review\` 找计划,而宿主写在 `nx-workspace\review\` —— 必然报
"No plan found"**(源码里甚至写了句 `is NX_SKILL_WORKSPACE the same for NX and the agent?`)。

```bat
plchat-local\dc\review-workspace-on.cmd   :: setx NX_SKILL_WORKSPACE "…\\nx-workspace"
```

改完**重启 Designcenter**。页面面板会自动检测这个不一致并红字告警
(`/api/review` 返回 `envWorkspace` + `workspaceMismatch`)。

另外,对话框的**入口**在 NX 菜单里,还需要 `UGII_USER_DIR`(见第 14 节路线 C)。

### 实测

* 工具层:提交 → `plan.json` 落盘(中文完好) → `/api/review` 正确回读
* 模型层:提问「创建 80x50x25 方块并导出 STEP,提交到复核队列」→ 模型自主走
  `nx_route_intent → nx_modeling_plan → nx_review_submit`,产出 2 步计划
  (`01_Base_Block_Create` auto / `02_Export_STEP_File` manual),56 秒给出完整中文答复并指引去 NX 点 Review Plan

### 顺带修掉的两个真 bug

1. **模型不遵守 `tool_choice:"none"`**(MiMo 实测):禁止调用工具时它仍返回 `tool_calls` 且
   `content` 为空 → 答案为空。**可靠做法是根本不发 `tools` 参数**,已改。并新增
   `maxToolCalls`(默认 8)总调用数硬上限 —— 光限轮数管不住"一轮多调"。
2. **工作区不一致**导致 NX 找不到计划(见上),已加检测与告警。
## 16. 把 Copilot 放进最左侧工具栏

### 机制

NX 的工具栏由 `.tbr` 文件定义(安装目录里有现成样例,如 `UGII/menus/ug_selection.tbr`):

```
TITLE  <工具栏名>        <-- 必须第一行(注释之后)
VERSION 160              <-- 必须在 TITLE 之后,写反会报语法错误
DOCK   TOP|LEFT|RIGHT|BOTTOM|NO
BUTTON <按钮ID>          <-- 直接引用已存在的按钮定义
```

> ⚠️ **踩过的坑**:把 `VERSION` 写在 `TITLE` 前面,启动时会弹
> 「工具条语法错误 … 发现意外的关键字 "VERSION"。期望 TITLE」。
> 顺序是从 NX 自己的关键字表里核实的(`NXBIN/libugutils.dll` 里 `tbr_utils.c` 的
> `TITLE → VERSION → DOCK → RELOAD → CATEGORY …`)。
> 另外 `TOP/BOTTOM/LEFT/RIGHT` 这些**取值不在关键字表里**(按标识符解析),
> 所以 `DOCK LEFT` 本身不构成语法错误;不认的话工具栏会浮空,手动拖到左边缘即可。

关键点:**`BUTTON` 可以引用已有的命令 ID**,所以不用写任何新动作,直接把内置的
`UG_APP_COPILOT` 放进一个自定义工具栏即可。

> 说明:窗口最左侧那条竖条是 NX 的 **Resource Bar(资源条)**,里面装的是**面板/导航器**
> (部件导航器、装配导航器、Web 浏览器、工具箱…),不是普通命令。所以 Copilot 这类命令
> 的合适落点是**左侧停靠的自定义工具栏** —— 视觉上同样贴在最左边,但是竖排按钮条。

### 方案一:用现成的工具栏文件(推荐)

已创建:`E:\AIprojects\nx-skill\nx_runtime\startup\nx_copilot.tbr`(**纯 ASCII**,避免编码问题),
内含三个按钮:

| 按钮 | 引用的命令 |
|---|---|
| Copilot | `UG_APP_COPILOT` |
| Review Plan | `NX_SKILL_CONTROL_REVIEW_PLAN` |
| Start NX Skill Live Bridge | `NX_SKILL_CONTROL_START_BRIDGE` |

```bat
plchat-local\dc\user-dir-on.cmd     :: setx UGII_USER_DIR "E:\AIprojects\nx-skill\nx_runtime"
```

**启用步骤**:重启 DC → 功能区空白处右键 **定制** → **工具栏** 页 → 勾选 **Copilot** →
(若未自动靠左)把它拖到窗口最左边缘停靠。

这一个环境变量同时解决两件事:
1. 定制对话框里出现 **Copilot** 工具栏(可停靠最左)
2. 菜单里 Help 右侧出现 **NX Skill** 级联(Review Plan / Live Bridge / Smoke Part)

### 方案二:不装文件,手工拖(立刻能做)

功能区空白处右键 → **定制** → **命令** 页 → 分类选 **帮助**(或搜索框输 `Copilot`)→
把 **Copilot** 图标拖到窗口最左边缘 → 出现竖直停靠条时松手。会存进用户界面设置,重启仍在。

### 让"点开的那个面板"真的用上我们的东西

上面只解决入口。要让它加载**我们的页面 + 我们的模型 + 复核队列**,还要两个脚本
(见 `plchat-local\dc\`):`copilot-hooks-on.cmd`、`review-workspace-on.cmd`。

### 本机已确认

* `Copilot` 命令在你的授权下**可用**(命令查找器里没灰,提示"此命令在 Designcenter X 中可用")
* 因此路线 B(官方面板加载我们的页面/后端)是首选,优于第 14 节的"劫持帮助页"
## 17. 为什么官方 Copilot 按钮点不动 + 我们自己的替代按钮

### 结论:官方命令是**被授权门禁停用**的,不是坏了

按钮定义里写死了:

```
BUTTON UG_APP_COPILOT
HINT This command is available in Designcenter X.
BITMAP ai_indicator
ACTIONS STANDARD
```

`ACTIONS STANDARD` 表示动作在 `libcopilotui.dll` 内部,而它要先**签出 `nx_copilot_tdoc` 授权**并连西门子云。
经典版 Designcenter(非 Designcenter X)上这个检查过不去 → 命令**灰掉/点不动**。
命令查找器**仍然会列出它**(查找器不查授权状态),所以看起来"有这个命令但按了没反应"。

**这不是配置问题,改环境变量也救不回来** —— 所以别在它身上耗时间,用下面这个替代品。

### 我们自己的按钮(同款图标,无需授权)

用的 API 是 `NXOpen.UF.UFUi.DisplayUrl` —— 官方文档明确写着 **License requirements: None**,
NX 自己就是用它把 Check-Mate 报告、帮助页显示在**内嵌浏览器**里的。

新增文件(都在 `E:\AIprojects\nx-skill\nx_runtime\`):

| 文件 | 作用 |
|---|---|
| `application/open_local_copilot.py` | 调用 `UF_UI_display_url` 打开本地宿主页面(先试 `DisplayUrlAndActivate`,失败退回 `DisplayUrl`,再失败提示手工打开) |
| `startup/open_local_copilot.py` | thin forwarder(nx-skill 的既有写法) |
| `startup/definitions_nx_control.btn` | 新增按钮 `NX_SKILL_CONTROL_OPEN_COPILOT`:`BITMAP ai_indicator`(**和官方那颗一样的闪光图标**)、快捷键 `Ctrl+Alt+Shift+C` |
| `startup/nx_control.men` | 菜单里置顶 |
| `startup/nx_copilot.tbr` | 工具栏里第一颗按钮 |

地址默认 `http://127.0.0.1:8765/`,可用环境变量 `NX_SKILL_COPILOT_URL` 覆盖。

### 启用步骤

```bat
plchat-local\dc\user-dir-on.cmd      :: setx UGII_USER_DIR "E:\AIprojects\nx-skill\nx_runtime"
```

重启 Designcenter 后,**三种入口任选**:

1. **菜单栏**:Help 右侧出现 **NX Skill** → **Copilot (Local)...**
2. **快捷键**:`Ctrl+Alt+Shift+C`
3. **最左侧工具栏**:功能区右键 → 定制 → 工具栏 → 勾选 **Copilot** → 拖到窗口最左边缘停靠

点下去页面会开在 **Designcenter 内嵌浏览器**里(不是外部浏览器)。
脚本出错时信息写到 **信息窗口(Listing Window)**,那里能看到具体原因。

### 前提

本地宿主必须先在跑:`plchat-local\start.cmd`(保持窗口开着)。

## 18. 在当前 NX 会话里执行计划(live 模式)

### 两种执行方式的区别

| 方式 | 作用对象 | 看不看得到过程 | 入口 |
|---|---|---|---|
| **live(当前会话)** | 你**正打开的零件**(当前工作零件) | 看得见(就在你的 NX 窗口里) | 面板「▶ 在当前 NX 会话执行」 |
| **batch(headless)** | 新建零件文件 `<workspace>\parts\plan_<id>.prt` | 看不见 | 面板「⚡ 后台新建零件执行」 |

live 模式走 nx-skill 的 **live 桥**:桥的 DLL 跑在 NX 进程内,我们的脚本通过
`nx-skill live python --stage <步骤名>` 推进去执行,直接作用在当前工作零件上。
**脚本本身不保存** —— 想留档自己 Ctrl+S。

### 前置条件

1. Designcenter 里点过 **NX Skill → Start NX Skill Live Bridge**(每次开 DC 点一次)
2. 设置 `NX_SKILL_PROJECT_ROOT`(宿主会自动带上 = `nxWorkspace`)——
   桥的 C# 客户端用它校验"脚本必须在工程目录下",不设会回退到遗留的
   `NX2512_PROJECT_ROOT`(= NXMCP)然后拒掉我们的脚本

### ⚠ 踩到的坑:Clash / TUN 模式会让 live 桥连不上

现象:客户端连 `198.18.0.1:25121` 超时(198.18.0.0/15 是 Clash 的 fake-IP 段),
报 `无法连接到远程服务器`,60 秒后退出码 143。

根因:服务端(`NxLiveBridgeServer.cs`)注册通道时只给了 `port`/`name`,于是
**.NET Remoting 用机器名发布对象 URI**;机器名被 TUN 模式的 fake-IP DNS 劫持。

修法(已改好源码,需重新编译):
```csharp
props["machineName"] = "127.0.0.1";   // 显式用回环地址发布
```
客户端侧也把 `http://localhost:...` 改成了 `http://127.0.0.1:...`。

> 打完补丁的完整源码就在 `nx-skill/scripts/dotnet_bridge/`(server + client 两边都改了)。
> 这条坑已写进 `nx-skill/docs/troubleshooting.md` 的 live bridge 小节。

**应用步骤**(DLL 被运行中的 NX 锁着,必须关掉 DC):
```bat
plchat-local\dc\fix-live-bridge.cmd
```
脚本会先检查 `ugraf.exe` 是否还在跑,在跑就提示先关;确认关闭后重新编译
server + client。做完重启 Designcenter,再点一次 Start NX Skill Live Bridge。

> 已用 `-ClientOnly` 单独编译验证过:补丁本身**编译通过**,原先的失败是
> `error CS0016 无法写入输出文件…另一个进程正在使用` —— 纯粹是文件锁,不是语法错。

---

## 贡献者

见 [`CONTRIBUTORS.md`](CONTRIBUTORS.md)。

* **kamao6757-crypto** —— 项目作者:需求、方向、真机验证,以及 `nx-skill` 子项目。
* **DeepSeek Harness** —— AI 编程代理:本仓库绝大部分代码与文档的实现。

第三方归属与授权边界见该文件末尾与 `LICENSE`。
