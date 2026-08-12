# 通用 AI 开发 Harness：实施任务书

> 本文件是给另一个编码模型直接执行的自包含任务说明。执行者应在当前仓库中完成实现、测试和文档，不要只输出方案。

## 1. 任务角色

你是本仓库的实现者。请建立一套同时覆盖以下两类活动的、可执行的 AI 开发 Harness：

1. **AI 辅助软件开发**：让编码 Agent 能稳定理解项目、规划修改、执行检查、提交可审查的变更。
2. **AI 应用生命周期**：管理 Prompt、模型、工具、数据集、评测、Tracing、安全门禁和发布回滚。

目标项目可能使用 Python、TypeScript、Go、Rust、Java、Kotlin 或 .NET，也可能采用 RAG、工具型 Agent、聊天、抽取、代码生成等不同 AI 架构。因此，Harness 必须采用“稳定内核 + 可替换适配器”，不得把项目工作流绑定到某一种业务语言、模型供应商或 AI 框架。

当前仓库是一个基本为空的 Git 仓库。请直接在当前仓库实施。

## 2. 最终目标

交付一个可以被人类和编码 Agent 共同使用的 Harness 模板，使任意项目能够获得一致的入口：

```text
需求/验收标准
    → Agent 获取受控上下文
    → 计划与小步实现
    → 格式、静态检查、类型检查、测试
    → AI Smoke Eval、完整回归、安全评测
    → PR 门禁与人工评审
    → 灰度发布与回滚
    → 线上 Trace 和失败样本回流
```

实现完成后，项目应对外暴露以下稳定命令语义：

| 命令 | 含义 |
|---|---|
| `doctor` | 检查 Harness、配置和项目工具链是否可用 |
| `validate` | 校验配置、数据集和策略文件 |
| `bootstrap` | 安装或准备项目依赖 |
| `dev` | 启动本地开发环境 |
| `format` | 格式化代码 |
| `lint` | 静态检查 |
| `typecheck` | 类型检查或编译检查 |
| `test-unit` | 单元测试 |
| `test-integration` | 集成测试 |
| `eval-smoke` | PR 级、快速、低成本 AI 评测 |
| `eval-full` | 完整质量与回归评测 |
| `security` | 密钥、依赖、输入攻击和工具权限检查 |
| `check` | 本地和 PR 合并前的确定性检查集合 |
| `release-check` | 发布前全部门禁 |

具体语言可以把这些语义映射到不同工具，但命令名称和结果语义必须保持稳定。

## 3. 设计约束

### 3.1 控制面与目标项目分离

- Harness 控制面可以选择一个小型、可维护的实现语言，但目标项目不得因此被限制为相同语言。
- 优先选择 **Python 3.11+ 标准库**实现控制面 CLI，使用 `tomllib` 读取配置、`subprocess` 执行命令、`unittest` 测试；除非有充分理由，不要给控制面增加第三方运行时依赖。
- 提供根目录可执行入口 `./harness`，用户不需要记住 Python 模块路径。
- Windows 原生支持可以记录为后续能力；当前必须支持 macOS、Linux 和 GitHub Actions。

### 3.2 安全执行

- 配置中的外部命令使用 argv 数组表达，并通过 `subprocess` 的参数数组执行。
- 不要默认使用 `shell=True`，不要通过拼接未验证字符串执行命令。
- 禁止在配置、Fixture、日志或 Eval 报告中写入真实 API Key、Token、Cookie 或个人数据。
- 所有外部写操作应区分只读、可逆写入和高风险写入；高风险写入必须支持人工批准门禁。
- 默认最小权限，工具采用显式 allowlist。

### 3.3 可复现性

- Prompt、工具定义、模型标识、评测数据集、评分器和质量阈值都必须版本化。
- 生产配置应允许固定模型版本；模型升级必须先与当前基线对比。
- 相同配置和离线 Fixture 应产生稳定结果。
- 在线模型评测不能成为基础单元测试的必要条件。

### 3.4 渐进式采用

- 没有模型密钥时，`doctor`、`validate`、Harness 自身单测和离线 Eval 必须能够运行。
- 没有配置的可选阶段应明确报告 `skipped` 及原因；不得假装通过。
- `eval-smoke` 用于 PR，必须限制样本量、预算和超时。
- `eval-full` 可以由手动触发、定时任务或发布流程运行。

## 4. 建议目录结构

允许根据实现需要小幅调整，但职责边界必须保留：

```text
.
├── AGENTS.md
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE                         # 无法确定许可证时先不要猜测创建
├── harness                         # 可执行入口
├── harness.toml                    # 本仓库自身配置
├── harness.schema.json             # 配置的机器可读契约
├── pyproject.toml                  # 仅用于 Harness 控制面
├── src/agent_harness/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── runner.py
│   ├── result.py
│   ├── policy.py
│   ├── evals.py
│   └── redaction.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── docs/
│   ├── architecture.md
│   ├── development-workflow.md
│   ├── evaluation-policy.md
│   ├── security-model.md
│   ├── observability.md
│   ├── release-policy.md
│   └── adr/
├── prompts/
│   ├── README.md
│   └── manifest.example.toml
├── evals/
│   ├── README.md
│   ├── datasets/
│   │   ├── smoke.example.jsonl
│   │   ├── regression.example.jsonl
│   │   └── adversarial.example.jsonl
│   ├── baselines/
│   ├── graders/
│   └── reports/                    # 生成物应被 Git 忽略，基线除外
├── profiles/
│   ├── languages/
│   │   ├── python.toml
│   │   ├── typescript.toml
│   │   ├── go.toml
│   │   ├── rust.toml
│   │   ├── jvm.toml
│   │   └── dotnet.toml
│   ├── workloads/
│   │   ├── chat.toml
│   │   ├── rag.toml
│   │   ├── agent.toml
│   │   └── extraction.toml
│   └── risk/
│       ├── prototype.toml
│       ├── standard.toml
│       └── high-risk.toml
├── examples/
│   ├── python-rag/
│   ├── typescript-agent/
│   ├── go-ai-api/
│   └── rust-extraction/
└── .github/
    ├── pull_request_template.md
    ├── ISSUE_TEMPLATE/
    └── workflows/
        ├── ci.yml
        ├── evals.yml
        └── security.yml
```

## 5. 配置契约

使用 `harness.toml` 作为项目配置。至少支持以下概念：

```toml
version = 1

[project]
name = "example"
language = "python"
workload = "rag"
risk = "standard"

[commands]
bootstrap = [["uv", "sync"]]
format = [["uv", "run", "ruff", "format", "."]]
lint = [["uv", "run", "ruff", "check", "."]]
typecheck = [["uv", "run", "pyright"]]
test-unit = [["uv", "run", "pytest", "tests/unit"]]
test-integration = [["uv", "run", "pytest", "tests/integration"]]

[workflows]
check = ["format", "lint", "typecheck", "test-unit"]
release-check = ["check", "test-integration", "eval-full", "security"]

[evals.smoke]
dataset = "evals/datasets/smoke.jsonl"
sample_limit = 20
timeout_seconds = 120
max_cost_usd = 2.0
min_pass_rate = 0.90

[evals.full]
dataset = "evals/datasets/regression.jsonl"
repetitions = 3
max_cost_usd = 50.0
min_pass_rate = 0.95
max_regression = 0.02

[security]
redact_inputs = true
redact_outputs = true
tool_allowlist = ["search", "retrieve"]
require_approval_for = ["external_write", "delete", "payment", "deploy"]
```

要求：

- 上述内容是配置能力示例，不要求盲目照抄字段。
- 定义明确的版本策略，并拒绝未知的主版本。
- 校验未知字段或至少对其发出明确警告，防止拼写错误静默失效。
- 命令必须表示为 argv 数组；一个阶段可以顺序执行多个 argv 数组。
- 工作流可以引用阶段或其他工作流，但必须检测循环依赖。
- 支持 `--dry-run`，只打印将执行的阶段和安全转义后的 argv。
- 支持 `--json` 输出稳定的机器可读结果。
- 退出码至少区分：成功、验证失败、阶段失败、策略门禁失败、内部错误。

`harness.schema.json` 应与实际解析逻辑一致，并由测试覆盖关键字段。

## 6. CLI 最小功能

至少实现：

```bash
./harness doctor
./harness validate
./harness list
./harness run <stage-or-workflow>
./harness run <stage-or-workflow> --dry-run
./harness run <stage-or-workflow> --json
./harness eval <smoke|full> --offline
```

建议但非强制：

```bash
./harness init --language python --workload rag --risk standard
./harness explain <stage-or-policy>
./harness baseline compare <report-a> <report-b>
```

每次执行产生结构化结果，至少包含：

```json
{
  "schema_version": 1,
  "run_id": "...",
  "status": "passed|failed|skipped|blocked",
  "started_at": "...",
  "duration_ms": 123,
  "stages": [],
  "summary": {},
  "errors": []
}
```

不得把密钥、完整敏感 Prompt 或未经脱敏的用户数据写入结果。

## 7. 编码 Agent 工作流

### 7.1 `AGENTS.md`

创建简洁、可执行的根级 Agent 契约，至少写明：

- 修改前先阅读 `README.md`、相关代码和测试。
- 先明确验收标准；复杂任务先给出短计划。
- 只修改任务范围内的文件，保留用户已有变更。
- 优先小步、可审查的 Diff，不做无关重构。
- 不猜测命令，通过 `./harness list` 或文档获取入口。
- 完成前运行与变更风险相匹配的 Harness 检查。
- 不读取、提交或打印秘密信息。
- 不绕过失败测试、质量阈值、人工批准和发布门禁。
- 发现失败时报告根因与未完成事项，不把 `skipped` 表述为 `passed`。

### 7.2 Issue 与 PR 模板

Issue 模板至少包含：

- 背景和用户价值。
- 范围与非目标。
- 可验证的验收标准。
- 风险等级。
- 测试与 Eval 计划。
- 回滚方案。

PR 模板至少包含：

- 改动摘要及原因。
- 关联验收标准。
- 测试证据。
- AI 行为、Prompt、模型或工具是否变化。
- Eval 基线差异。
- 安全、隐私、成本和延迟影响。
- 发布与回滚说明。

### 7.3 Definition of Done

在文档中定义统一完成标准：

1. 验收标准满足。
2. 相关文档与 ADR 已更新。
3. 格式、Lint、类型检查和相关测试通过。
4. AI 行为变更已加入或更新 Eval 样本。
5. 没有未说明的质量、成本或延迟回退。
6. 没有泄漏秘密或扩大工具权限。
7. 可观测性足以定位失败。
8. 发布和回滚路径明确。

## 8. AI Eval 体系

### 8.1 数据集格式

采用 JSONL。每条记录至少支持：

```json
{
  "id": "rag-001",
  "input": {"query": "..."},
  "expected": {
    "contains": ["..."],
    "not_contains": ["..."],
    "schema": null
  },
  "tags": ["smoke", "rag", "zh-CN"],
  "metadata": {
    "source": "synthetic",
    "risk": "normal"
  }
}
```

数据规则：

- `id` 必须稳定且唯一。
- 明确区分人工黄金样本、合成样本和线上失败回流样本。
- 线上回流前必须脱敏并记录来源类别，不能保存不必要的原始数据。
- 数据集变更应像代码一样接受 Review。
- 测试集不得混入用于调整 Prompt 的开发集；至少在文档中定义 train/dev/test 或 equivalent 分区规则。

### 8.2 评分器

先实现离线、确定性的最小评分器：

- exact match。
- contains / not-contains。
- 正则匹配。
- JSON 是否可解析。
- 简化 JSON Schema 或指定字段检查。
- 工具调用名称和参数检查。
- 最大步骤数、延迟、Token、成本等阈值检查。

为语义相似度、模型评分器和人工评分预留插件接口，但不要让基础测试依赖真实模型 API。

模型评分器文档必须提醒：

- Judge Prompt 和 Judge 模型也要固定版本。
- 关键评测需要抽样人工校准。
- 避免让同一模型无校准地既生成又裁判。
- 非确定性任务应重复运行，报告均值、分位数和失败率，而非只跑一次。

### 8.3 不同工作负载的指标

提供以下 profile 文档或示例配置：

| 工作负载 | 核心指标 |
|---|---|
| Chat | 正确性、相关性、拒答、上下文保持 |
| RAG | 检索 Recall、引用准确性、忠实度、无答案检测 |
| Agent | 工具选择、参数正确性、任务成功率、步骤数、副作用 |
| Extraction | Schema 合法率、字段精确率/召回率 |
| Code Agent | 构建率、测试通过率、补丁范围、安全性 |

### 8.4 基线与门禁

- Eval 报告必须记录 Harness 版本、Git SHA、数据集摘要、Prompt 版本、模型标识和运行参数。
- 支持绝对阈值与相对回退阈值。
- 不允许用总体平均分掩盖高风险分类的失败。
- 单独报告质量、稳定性、延迟、Token 和成本。
- 基线更新必须是显式操作，不能在普通测试运行中自动覆盖。

## 9. Prompt、模型与工具版本管理

定义 Prompt manifest 示例，至少记录：

```toml
id = "support-answer"
version = "1.2.0"
template = "support-answer.md"
input_schema = "schemas/support-input.json"
output_schema = "schemas/support-output.json"
owner = "team-name"
```

规则：

- Prompt 正文不应散落在业务代码中；允许由构建工具嵌入，但源文件必须可追踪。
- 模型配置至少记录 provider、model、snapshot/version、temperature、reasoning effort、最大输出和超时。
- 工具定义必须有输入 Schema、权限级别、超时、重试、幂等性说明和审计字段。
- Prompt、模型、检索配置或工具行为变化都视为需要 Eval 的行为变更。

## 10. 安全与隐私

在 `docs/security-model.md` 中建立威胁模型，并提供最小对抗样本。至少覆盖：

- Prompt injection 与间接 Prompt injection。
- 数据外泄和跨租户访问。
- 越权工具调用。
- 任意命令、路径遍历、SSRF 等工具参数风险。
- Secret 泄漏。
- 不可信模型输出进入数据库、Shell、HTML 或后续工具。
- 资源耗尽、无限循环和成本失控。
- 高风险写入缺少人工批准。

安全实现要求：

- 配置和日志脱敏函数必须有单元测试。
- 提供 secret scanning 和依赖扫描接入点；若第三方工具未安装，应明确说明安装方法和 CI 行为。
- Agent 工具默认只读；写权限按工具单独授予。
- 网络、文件系统、Shell 和部署权限分别建模，不能用一个笼统的 `admin=true`。

## 11. 可观测性

定义厂商中立的 Trace/Event Schema，字段至少包含：

- `trace_id`、`span_id`、`run_id`、时间和环境。
- Git SHA、应用版本、Prompt ID/版本。
- 模型 provider/name/version 和推理参数。
- 输入/输出 Token、缓存 Token、延迟、重试和估算成本。
- 工具调用名称、状态、耗时和安全级别。
- Eval/用户反馈结果和错误类别。

要求：

- 默认不记录完整敏感输入和输出。
- 支持采样、脱敏和保留期策略。
- 文档说明如何映射到 OpenTelemetry；内部核心不要强绑定某个商业观测平台。
- 定义最小 SLI：成功率、P50/P95 延迟、单次成本、质量代理指标、工具失败率、安全阻断率。

## 12. CI/CD

### 12.1 PR CI

`.github/workflows/ci.yml` 至少执行：

1. Harness 配置校验。
2. Harness 自身格式/静态检查（若实际配置）。
3. 单元测试。
4. 集成测试。
5. 离线 `eval-smoke`。

确保 Required Check 对所有目标 PR 都会产生明确状态，不要让路径过滤导致必需检查永远 Pending。

### 12.2 完整 Eval

`.github/workflows/evals.yml`：

- 支持 `workflow_dispatch`。
- 支持定时运行。
- 在线评测仅在明确配置 secrets 时运行。
- 设置并发限制、超时和预算。
- 上传脱敏报告 Artifact。
- 不在 Fork PR 上暴露 Secrets。

### 12.3 发布

在发布策略中定义：

```text
PR checks
  → full eval
  → staging/shadow
  → human approval（standard/high-risk）
  → canary
  → health/quality/cost gate
  → gradual rollout
  → rollback if breached
```

发布配置应支持环境保护、单环境部署并发、版本标记和上一稳定版本回滚。

## 13. 语言与框架 Profiles

Profiles 是可复制、可覆盖的示例配置，不应在用户未选择时自动安装依赖。

至少提供以下映射：

| Profile | format/lint | typecheck/build | unit test |
|---|---|---|---|
| Python | Ruff | Pyright 或 Mypy | Pytest |
| TypeScript | Prettier/ESLint | `tsc` | Vitest 或 Jest |
| Go | gofmt/golangci-lint | `go vet`/`go build` | `go test` |
| Rust | rustfmt/Clippy | `cargo check` | `cargo test` |
| JVM | Spotless/Checkstyle | Gradle 或 Maven | JUnit |
| .NET | `dotnet format` | `dotnet build` | `dotnet test` |

Profile 中的命令必须使用 argv 数组。若一个生态存在多个主流选项，选一个默认值，并在注释或文档中说明如何替换，不要同时强行执行所有工具。

框架差异（如 FastAPI、Django、Next.js、NestJS、Spring、ASP.NET）应体现在可覆盖的 `dev`、集成测试和部署命令中，不得复制整套核心工作流。

## 14. 测试要求

Harness 控制面至少测试：

- 合法/非法 TOML 配置。
- 未知配置版本。
- argv 命令解析与执行。
- dry-run 不产生副作用。
- 阶段顺序、失败即停和退出码。
- 工作流嵌套与循环检测。
- 未配置可选阶段的 `skipped` 状态。
- JSON 输出符合契约。
- JSONL 数据集的合法性、唯一 ID 和错误定位。
- 离线评分器。
- 阈值通过、回退和阻断。
- 日志及报告脱敏。
- 超时和子进程错误处理。

集成测试不能调用收费 API，使用 Fixture 或本地假 Provider。

## 15. 实施顺序

按以下顺序执行，每个阶段完成后运行相关测试：

### 阶段 A：契约和最小内核

1. 创建 `README.md`、`AGENTS.md`、架构文档。
2. 定义 `harness.toml` 和 Schema。
3. 实现 `doctor`、`validate`、`list`、`run`、`--dry-run`、`--json`。
4. 为核心解析和执行逻辑编写单元测试。

### 阶段 B：离线 Eval

1. 定义 JSONL 数据格式。
2. 实现确定性评分器和聚合报告。
3. 实现阈值/回退门禁。
4. 添加 smoke、regression、adversarial 示例数据。
5. 测试数据校验、评分、报告和脱敏。

### 阶段 C：适配器与示例

1. 添加语言、工作负载和风险 Profiles。
2. 添加至少四种跨语言配置示例。
3. 验证每个示例配置均能通过 `validate`。
4. 不要求在 CI 安装并运行所有语言生态；配置正确性测试必须覆盖它们。

### 阶段 D：协作和 CI/CD

1. 添加 Issue、PR 模板和 Definition of Done。
2. 添加 CI、完整 Eval 和安全 Workflow。
3. 文档化分支保护、Required Checks、环境审批和回滚。

### 阶段 E：安全、观测与收尾

1. 完成威胁模型和对抗数据。
2. 完成脱敏与观测 Schema。
3. 运行所有可用检查。
4. 对照本任务书逐项审计，修复缺口。

## 16. 验收标准

以下条件全部满足才算完成：

- [ ] `./harness --help` 清晰列出稳定命令。
- [ ] `./harness doctor` 在当前仓库给出可操作的诊断。
- [ ] `./harness validate` 成功校验本仓库和所有示例配置。
- [ ] `./harness list` 显示阶段、工作流和配置来源。
- [ ] `./harness run check --dry-run` 不执行子进程且展示正确顺序。
- [ ] `./harness eval smoke --offline` 使用 Fixture 生成确定性报告。
- [ ] 不设置任何模型 API Key，也能执行全部 Harness 自身测试。
- [ ] 至少包含 Python、TypeScript、Go、Rust、JVM、.NET Profiles。
- [ ] 至少包含 Chat、RAG、Agent、Extraction Profiles。
- [ ] 至少包含 prototype、standard、high-risk 策略。
- [ ] 工作流能区分 `passed`、`failed`、`skipped`、`blocked`。
- [ ] 日志和报告不会泄漏测试中的假密钥或敏感字段。
- [ ] CI 使用离线测试并有清晰退出码。
- [ ] 文档解释如何将线上失败脱敏后回流成回归样本。
- [ ] 文档解释如何比较 Prompt/模型变更与已有基线。
- [ ] `git status` 中不包含缓存、临时报告、虚拟环境或秘密文件。
- [ ] 最终回复列出创建的关键文件、实际运行的命令、测试结果及仍存在的限制。

## 17. 非目标与防止过度设计

当前版本不要实现：

- 完整的商业级模型网关。
- 自建分布式 Trace 后端。
- 自建 Secret Manager。
- 自建 CI 平台。
- 自动执行真实生产部署。
- 自动调用收费模型生成大量基线。
- 为每个 Web 框架复制独立工作流。
- 在没有用户授权的情况下推送远端、修改分支保护或创建云资源。

正确做法是定义清楚接口、策略、示例和接入点，并让本地控制面、离线 Eval 与 CI 骨架真正可运行。

## 18. 执行规则

1. 先检查仓库状态和现有文件，保留所有非本任务变更。
2. 若仓库存在额外的 `AGENTS.md`，先遵守其指令。
3. 使用小步、易审查的修改；不要重写不相关内容。
4. 不要停留在分析或给建议，直接创建文件并实现。
5. 遇到非关键歧义时采用本任务书给出的默认值，并在 ADR 中记录。
6. 只有涉及真实外部账号、生产资源、付费 API 或不可逆选择时才向用户询问。
7. 不得伪造测试成功。无法运行的检查要说明原因和影响。
8. 完成前必须实际运行适用测试、配置校验、dry-run 和离线 Eval。

## 19. 最终交付格式

实施完成后，用简洁摘要回复用户：

```text
完成内容：
- ...

验证：
- command → result

关键设计决定：
- ...

尚未覆盖：
- ...

建议下一步：
- 选择第一个真实项目的 language/workload/risk profile 并接入。
```

