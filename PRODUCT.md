# Designcenter 本地工作台

<!-- impeccable:product-schema 1 -->

## Platform
web（Windows 浏览器和 Designcenter 内嵌页面）

## Product Purpose
通过现有本地宿主接口，将模型配置、聊天、建模计划、人工复核与执行进度集中在同一页。

## Stack
现有 Node.js 零依赖宿主；原生 HTML、CSS、JavaScript 前端。

## Capabilities and Constraints
复用 plchat-local 的 API，不更换 NX 执行层。新页面独立于官方前端资源；原页面保留为 legacy.html。不把接口连通等同于 NX 已连接，不把计划或静态校验等同于执行成功。Review 与自动执行结果分别显示。

## Confirmed Direction
用户要求模仿 Siemens Designcenter 2026 风格，确认聊天居中、计划并排显示。左侧配置和环境，底部日志。
