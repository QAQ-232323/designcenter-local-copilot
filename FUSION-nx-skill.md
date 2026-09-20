# 结合方案:内置 Copilot 页面 × nx-skill

> 两条线的合流设计。左半(`plchat-local`)来自本仓库;右半(`nx-skill`)来自
> `E:\AIprojects\nx-skill`(由 nx-codex-plugin v0.6.0 重写而来)。
> 证据出处见各节标注。

## 0. 一句话

`plchat-local` 提供**脸**(Designcenter 内置 Copilot 页面)和**脑**(任意大模型);
`nx-skill` 提供**手**(24 个 MCP 工具 / 批处理 journal / 人工节拍 review)。
拼起来 = 把原版"云脑 + 本地手"架构整个换成自己的,而且手比原版更强
(原版本地只有 3 个工具:`nx-edit-expression` / `nx-expression-query-tool` / `nx-clearance-tool`)。

## 1. 两侧现状

| | plchat-local(本仓库) | nx-skill |
|---|---|---|
| 形态 | 官方 PLChat.html + 本地 Node 宿主 | Python skill + MCP server + CLI + NX 菜单 |
| 已完成 | 页面完全渲染、问答链路跑通、mock + OpenAI 兼容双通路验证 | 44 文件 / 188 测试全绿 / 零运行时依赖;菜单已写好 |
| 缺口 | **手是空的**:只回文本,不碰 NX | **脸是 CLI/MCP**:工程师用不友好;**菜单出不来**(U13 未解决) |
| 证据 | `README.md`、`tools/verify-final.png` | `_dcmcp-analysis/session-9d75ad0e-*.md` A64/A118 |

## 2. 三条硬约束(决定架构,不能绕)

来自主会话 A68–A72 的实测结论:

1. **NXOpen 只能在 NX 主线程调用**,且 NX 没有 Timer / 回调队列 / 主线程调度原语
   (`ProcessEvents` / `DoEvents` **不存在**)。→ 后台 socket 线程**无法**把工作交回主线程。
2. **.NET 桥是"绕过"而非"解决"**:它用 `RemotingServices.Marshal(TheSession, "NXOpenSession")`
   把会话发布出去,调用跑在**非主线程** —— 这正是它在**模态对话框前会卡死**的根因;
   而 .NET Remoting 本身已废弃、还需要 csc 现场编译 + DLL 注入。
3. **NX 内嵌 Python 没有 pip,且可能是 2.7** → 纯标准库、不用 f-string 是硬约束。

**推论(用户 U10 定的调)**:凡是要"看着发生 / 人工复核"的操作(CAE 求解、保存、导出),
**不要用桥,用 review 模式** —— 每步都要人点,人就是同步机制,不需要任何后台线程:

```
agent 写计划 → 人在 NX 菜单点「下一步」→ SetUndoMark → 执行 → 截图 → run.json
```

## 3. 目标架构

```
Designcenter 内置 Copilot 页面(官方 UI,已跑通)
   ↓ 宿主桥 CallHost: GetAnswer
plchat-local/server.js   /api/ask
   ↓ function calling
你的模型(Ollama / DeepSeek / 任意 OpenAI 兼容)
   ↓ 工具调用
nx-skill(24 个 MCP 工具,或直接调 CLI)
   ├─ 只读/规划 → batch / 离线文档(随便调,零风险)
   └─ 改模型   → review plan.json → 人在 NX 里点(可控、可退、留痕)
```

## 4. 分档落地

| 档 | 内容 | 用到的东西 | 风险 |
|---|---|---|---|
| **P0** | `/api/ask` 注入环境上下文:开机调 `nx-skill doctor` + `nx_status`,把 NX 版本/工作区/桥状态塞进 system prompt | `src/nx_skill/discovery.py` | 零 |
| **P1** | 加 function calling,先暴露**只读 + 规划**类:`nx_status`、`nx_docs_search/member/type`、`nx_docs_samples`、`nx_route_intent`、`nx_modeling_plan`、`nx_visual_spec`。聊天页能查 API、出建模计划 | MCP stdio(`python -m nx_skill.mcp`) | 零(不碰模型) |
| **P2** | 接执行:`nx_review_submit` 写 plan 进 `workspace/queue/` → 人在 NX 菜单点 `Review Plan`(`Ctrl+Alt+Shift+R`)逐步执行 + 每步 PNG 留痕 + 精确回退 | `review.py` / `nx_review_executor.py` / `nx_review_executor.dlx` | 会改模型,**必须人在场** |
| **P3(可选)** | 接 .NET live 桥做只读探测(`nx_live_ping/status`),写操作仍只走 review | `NxLiveBridgeServer.dll` | 中(桥在模态对话框前会卡) |

## 5. 前置修复:菜单出不来(U13)

**根因**:`UGII_CUSTOM_DIRECTORY_FILE` 被 NXMCP 占着,指向
`E:\AIprojects\NXMCP\runtime\nxmcp_custom_dirs.dat`(内容只有 NXMCP 的 `runtime\current`)。
DC 读这个文件,里面没有 nx-skill → 菜单不出现。

**权威依据**(本次核查,`UGII/ugii_env_ug.dat` 第 1155–1158 行):

> Unigraphics will search the directories in **`UGII_UG_CUSTOM_DIRECTORY_FILE` first**,
> and then the directories in `UGII_CUSTOM_DIRECTORY_FILE`.

而 `UGII_UG_CUSTOM_DIRECTORY_FILE` = `UGII/menus/ug_custom_dirs.dat`,其**第一条就是 `$UGII_USER_DIR`**。

**结论**:设 `UGII_USER_DIR` 即可让菜单出现,**NXMCP 的注册项毫发无损**:

```bat
setx UGII_USER_DIR "E:\AIprojects\nx-skill\nx_runtime"
```


x-skill
x_runtime 的布局正好是 NX 要的形状:`startup/`(`nx_control.men` + `definitions_nx_control.btn` + `NxLiveBridgeServer.dll`)+ `application/`(真实实现)。

菜单项(`AFTER UG_HELP` → `NX Skill`):

| 按钮 | 快捷键 | 动作 |
|---|---|---|
| Review Plan | Ctrl+Alt+Shift+R | 打开人工节拍复核对话框 |
| Start NX Skill Live Bridge | Ctrl+Alt+Shift+B | 在 NX 进程内起 live 桥 |
| Create NX Skill Smoke Part | Ctrl+Alt+Shift+N | 建一个可见的冒烟零件 |

## 6. 边界与注意

* `nx-skill loader install` 会写**用户级**环境变量 `UGII_CUSTOM_DIRECTORY_FILE` ——
  **别用它**,会顶掉 NXMCP。用上面的 `UGII_USER_DIR` 路线。
* **历史事故**:主会话 A123 里测试套件曾调用真实 `_write_user_env`,**删掉过 NXMCP 的注册项**
  (A124 已恢复,并加了守护测试 `test_the_suite_is_isolated_from_the_real_user_environment`)。动注册表前先备份。
* 遗留变量 `NX2512_PROJECT_ROOT = E:\AIprojects\NXMCP` 会让 **nx-skill 与 NXMCP 双方 workspace 都落到 NXMCP**
  (A127)。建议给 nx-skill 显式设 `NX_SKILL_WORKSPACE` 做隔离。
* live 桥只实现了 **6 个命令**:`ping` / `status` / `create-modeling-part` / `create-block` /
  `prepare-session` / `run-python`。`module-list` / `run-python-inline` **不在桥里**
  (前者改本地文件扫描,后者落文件后走 `run-python`)。
* MCP 端口 `NX_SKILL_LIVE_PORT` 默认 **25121**(遗留 `NX2512_LIVE_PORT` 也是 25121)。
* 我们这条线的后端**不依赖西门子云**,与官方 Copilot 的额度/授权无关;官方云端功能仍需正常购买。

## 7. 验收标准

| 档 | 怎么算成功 |
|---|---|
| P0 | 聊天页里问"我这台机器装的什么 NX",回答里出现 `Designcenter 2606` 与真实工作区路径 |
| P1 | 问"ExtrudeBuilder 在哪个版本引入",回答引用离线 `NXOpen.xml` 且给出 `Created in NX…` |
| P2 | 聊天页给出 3 步建模计划 → NX 菜单出现 `NX Skill → Review Plan` → 逐步执行、每步出 PNG、可单步撤销 |
| U13 | DC 主菜单栏 Help 右侧出现 `NX Skill` 级联菜单 |
