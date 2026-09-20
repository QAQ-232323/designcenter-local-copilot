# tools —— 调试与自检脚本

这些不是宿主运行必需的,是开发/排障时用的。路径都可以用环境变量覆盖:

| 变量 | 默认值 | 含义 |
|---|---|---|
| `NX_SKILL_DIR` | `E:/AIprojects/nx-skill` | nx-skill 项目根目录 |
| `NX_SKILL_WORKSPACE` | `E:/AIprojects/nx-workspace` | 工作区(`review/` `parts/` 所在处) |
| `NX_HOST_URL` | `http://127.0.0.1:8765` | 本地宿主地址 |

## 页面调试(在浏览器 DevTools Console 里粘贴运行)

宿主页面是 WebView2 / Chrome,直接用 CDP 或 Console 操作最方便。

| 文件 | 作用 |
|---|---|
| `expr.js` `expr-render.js` | 读出 `<des-plchat-acc>` 当前渲染出来的文本,用来确认回答有没有真的画到页面上 |
| `click.js` | 自动往输入框里塞一个问题并发送,省得手点 |
| `open-settings.js` | 点开 ⚙ 设置面板 |
| `show-progress.js` | 手动派发 `plchat-local-busy` 事件,单独试进度浮层(思考链)长什么样 |
| `probe.js` | **主力度量工具**:用 CDP 打开页面,收集 console 报错 / 网络请求 / 截图。页面白屏时第一个该跑它 |

## 端到端自检

| 文件 | 作用 |
|---|---|
| `e2e.js` | 全链路:提问 → 生成计划 → 执行 → 轮询状态,最后打印结果。改完 server.js 拿它回归 |
| `gate-test.js` | 拿 `review/scripts/` 里已有的脚本过一遍静态门禁(语法 + NXOpen API 名),验证门禁本身没失灵 |
| `check-journal.sh` | 命令行的"复核队列"查看器:列出 plan.json 的步骤和脚本文件,不依赖页面 |
| `test-async.js` | 只测异步生成计划这一条路(测生成耗时/重试次数) |
| `test-mimo.js` | 验证 MiMo Token Plan 的 OpenAI 兼容接口 + function calling 是否正常 |
| `test-stdin.js` | 验证 nx-skill 走 stdin 提交时中文编码正确(Windows 上踩过乱码) |

## 环境相关

| 文件 | 作用 |
|---|---|
| `check-bridge.js` | 检查 .NET 实时桥的两个产物是不是"已钉死 127.0.0.1"的版本(见 `integrations/nx-skill/`) |
| `build-nxopen-index.py` | 从本机 NX 安装的 `NXOpen.xml` 抽全部 API 名 → `../cache/nxopen-names.txt`。静态门禁靠它判断"你写的这个 API 名到底存不存在" |

## 会话工具(与 NX 无关,是研究阶段用的)

| 文件 | 作用 |
|---|---|
| `list-sessions.js` | 列出本机 DSH 会话(带标题摘要),用来挑要引用的历史会话 |
| `analyze-session.js` | 把一个 DSH 会话 dump 成结构化摘要 |

`build-nxopen-index.py` 用法:

```bash
python build-nxopen-index.py --xml "D:/Program Files/Siemens/DC 2606/NXOPEN/NXOpen.xml" \
                             --out ../cache/nxopen-names.txt
```
