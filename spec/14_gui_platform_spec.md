# Spec 14：BidFlow GUI Platform

## Summary

BidFlow 需要一个面向普通用户的本地 GUI，把现有 CLI 的主要功能完整搬到图形界面。GUI 的目标不是替代 CLI，而是让用户不用记命令也能完成完整沙盒流程：生成 market、查看数据、运行 session、固定背景 replay、分析结果、查看日志和导出报告。

v1 采用本地 Web GUI：后端复用现有 `bidflow` Python 包和 `src` runner，前端使用静态 HTML/CSS/JS，由 `bidflow gui` 启动本机服务并自动打开浏览器。暂不引入 Electron、Tauri、Node/Vite 或数据库。

## User Journey

最短流程：

1. 用户运行：

```powershell
bidflow gui
```

2. 浏览器打开 `http://127.0.0.1:<port>`。
3. 用户在页面上输入学生数、教学班数和可选培养方案数，点击“生成沙盒”。
4. GUI 展示生成结果、CSV 文件、market 摘要和 validate/audit 状态。
5. 用户点击“跑基线市场”，选择 background agent、time points、run id 和输出目录。
6. 用户点击“固定背景回放”，选择 baseline、focal student、agent、CASS policy 或公式 policy。
7. 用户在“分析结果”页比较多个 run，查看录取率、效用指标、豆子浪费、focal student 结果和日志文件位置。

## Public Interface

新增 CLI：

```powershell
bidflow gui
bidflow gui --host 127.0.0.1 --port 8765
bidflow gui --no-browser
```

GUI 页面必须覆盖现有 CLI 能力：

| CLI 能力 | GUI 页面 |
| --- | --- |
| `agent list/info/init/register` | Agent 管理 |
| `market create/generate/scenarios/validate/info/course` | Market 工作台 |
| `session run` | Session 运行 |
| `replay run` | Replay 回放 |
| `analyze compare/summary/beans/focal/cass-sensitivity/crowding-boundary` | Analysis 分析 |

GUI 不直接读写私钥、API key 或 `.env.local` 内容。LLM 配置页只显示需要哪些环境变量、当前是否检测到变量，不显示变量值。

## Architecture

- 新增 `bidflow/gui/` 包，包含本地 HTTP server、API handlers、静态资源和 job 管理。
- 后端优先调用现有 Python 函数；无法直接复用时再通过 subprocess 委托 `python -m bidflow ...`，保持和 CLI 语义一致。
- 长任务统一进入 job 队列：market generate、session run、replay run、cass-sensitivity、crowding-boundary 都返回 `job_id`，前端轮询状态和日志。
- Job 状态至少包含：`queued`、`running`、`succeeded`、`failed`、`cancelled`、开始时间、结束时间、命令摘要、stdout/stderr 摘要、输出路径。
- 本地服务默认只绑定 `127.0.0.1`。如果用户显式绑定非 localhost，启动时必须打印安全提示。

## GUI Pages

### 1. Home

- 展示三条常用入口：生成沙盒、跑基线、看结果。
- 展示最近 markets、最近 runs、最近 replay outputs。
- 展示当前工作目录、Python 版本、BidFlow 版本和是否检测到 LLM 环境变量。

### 2. Agent 管理

- 列出 builtin agents：`behavioral`、`cass`、`llm/openai`。
- 支持查看 agent info。
- 支持初始化外部 agent 模板，等价于 `bidflow agent init`。
- 支持注册外部 agent，等价于 `bidflow agent register`。
- 明确提示：当前 session v1 只稳定支持 builtin agents；外部 agent 注册 API 存在，但完整 session 执行还不是稳定能力。

### 3. Market 工作台

- Simple Create 表单覆盖 `market create`：
  - `name`、`output`、`size`、`students`、`classes/sections`、`majors/profiles`、`codes/course-codes`、`competition-profile`、`seed`、`dry-run`、`audit`。
- Research Scenario 表单覆盖 `market generate`：
  - scenario 下拉、output、seed、n-students、n-course-sections、n-profiles、n-course-codes、competition-profile。
- Scenarios 列表覆盖 `market scenarios`。
- Validate/Info/Course 覆盖：
  - 选择 market 路径后可 validate、audit、查看 summary、查看某个 course id 的详情。
- 输出必须显示完整 CSV 清单，并用中文解释每个 CSV 的作用。

### 4. Session 运行

- 表单覆盖 `session run`：
  - market、population 字符串、population file、output、run id、time points、seed、config、experiment config、experiment group、interaction mode、formula prompt、background formula share、cass policy。
- 提供 population 构造器：
  - `background=behavioral`
  - `focal:S001=cass,background=behavioral`
  - `focal:S001=llm,background=behavioral`
- 运行完成后展示关键文件：
  - `decisions.csv`、`bid_events.csv`、`allocations.csv`、`utilities.csv`、`metrics.json`、`llm_traces.jsonl`、`llm_model_outputs.jsonl`。

### 5. Replay 回放

- 表单覆盖 `replay run`：
  - baseline、focal、agent 或 agents、output、data-dir、config、formula prompt、formula policy、formula prompt policy、CASS policy、CASS params。
- 支持多 agent replay，对应 `--agents cass,formula,llm`。
- 对 CASS params 使用 key-value 表格，不要求用户手写 `--param key=value`。
- 运行完成后展示 replay metrics、decision jsonl、metadata 和输出路径。

### 6. Analysis 分析

- Compare/Summary/Beans：选择多个 run，显示表格。
- Focal：选择 run 和 student id，展示该学生结果。
- CASS Sensitivity：覆盖 output dir、三张 table 输出、config、quick。
- Crowding Boundary：覆盖 run root、no sibling、quick、detail/summary/bin table、report、formula config。
- 分析结果表格可复制，可下载 CSV/JSON。

### 7. Logs And Files

- 提供文件浏览器，只允许访问仓库工作目录、用户选择的 market/output 目录和系统临时目录中的 BidFlow 输出。
- 支持打开文本文件、CSV 表格预览、JSON pretty view、JSONL 前 N 行预览。
- 不渲染或显示 `.env*`、私钥文件、SSH key、API key 文件。

## API Shape

v1 使用本地 JSON API，不承诺远程稳定协议，但内部结构固定，方便测试。

核心 endpoints：

```text
GET  /api/health
GET  /api/agents
POST /api/agents/init
POST /api/agents/register
GET  /api/markets/scenarios
POST /api/markets/create
POST /api/markets/generate
POST /api/markets/validate
POST /api/markets/info
POST /api/markets/course
POST /api/sessions/run
POST /api/replays/run
POST /api/analysis/summary
POST /api/analysis/beans
POST /api/analysis/focal
POST /api/analysis/cass-sensitivity
POST /api/analysis/crowding-boundary
GET  /api/jobs
GET  /api/jobs/<job_id>
POST /api/jobs/<job_id>/cancel
POST /api/files/preview
```

所有 mutating 或长任务 endpoints 返回：

```json
{
  "job_id": "job_...",
  "status": "queued"
}
```

失败返回：

```json
{
  "ok": false,
  "error": "human readable message",
  "details": {}
}
```

## Compatibility

- CLI 是事实标准；GUI 不应实现一套新的市场、session 或 replay 逻辑。
- GUI 表单字段名尽量使用 CLI 参数名，中文标签只是展示层。
- GUI 生成的输出目录结构必须和 CLI 完全一致。
- GUI 不能提交或写入 git；只生成本地 data/outputs。
- 旧 `src.*` 入口继续保留。

## Validation And Safety

- 前端做基础校验，后端仍必须复用 CLI/核心校验。
- 路径输入必须规范化，并拒绝明显危险路径，例如仓库根目录删除、系统根目录写入、`.git`、`.ssh`、`.env*`。
- `--output` 已存在时，必须在 GUI 上明确提示“将覆盖/重建目录”，由用户确认后才能执行。
- LLM agent 页面必须提示 API 调用会产生费用；GUI 只检测变量是否存在，不打印 key。
- Job 日志必须避免把环境变量完整 dump 到页面。

## Test Plan

- 单元测试：
  - `bidflow gui --help` 显示 host、port、no-browser。
  - API handler 能把 GUI request 转成和 CLI 等价的参数。
  - path guard 拒绝 `.env.local`、`.ssh`、`.git`。
  - job manager 能记录 succeeded/failed 状态和 stdout/stderr 摘要。
- GUI smoke：
  - 启动本地 server，访问 `/api/health`。
  - 通过 API 创建 12 学生、30 教学班、3 培养方案 market。
  - validate market 成功。
  - session run 小规模 behavioral baseline 成功。
  - replay run `S001 + cass_v2` 成功。
  - analysis summary/beans/focal 能读结果。
- 浏览器测试：
  - 用 Playwright 打开 Home、Market、Session、Replay、Analysis 页面。
  - 检查表单字段存在、错误提示可见、job 状态可轮询。
  - 桌面和窄屏下按钮和表格不重叠。
- 回归：
  - `python -m compileall src bidflow`
  - `python -m unittest discover -s tests`
  - `python -m bidflow --help`
  - `python -m bidflow gui --help`

## Milestones

1. M1：新增 `bidflow gui`、本地 server、health endpoint、静态首页。
2. M2：实现 Market 工作台，覆盖 create/generate/validate/info/course。
3. M3：实现 Job manager，接入 session run 和 replay run。
4. M4：实现 Analysis 页面和文件预览。
5. M5：实现 Agent 管理和 LLM 配置检测。
6. M6：补齐 Playwright smoke、文档和 README GUI quick start。

## Acceptance Criteria

- 一个新用户可以只用 GUI 完成：生成 market、validate、跑 behavioral baseline、跑 CASS replay、查看 summary。
- GUI 页面覆盖 CLI 当前公开功能，至少没有“只能回到命令行才能做”的核心流程断点。
- GUI 输出和 CLI 输出结构一致，现有分析脚本能继续读取。
- 默认本机运行，不暴露到局域网。
- 不提交生成数据、实验 outputs、`.env*`、API key、私钥或临时日志。
