# Harness 第五轮完整评估报告

评估对象：当前工作区中的 Harness 实现。

基线：`0c15d0e`（`Treat empty tool_allowlist as advisory for non-AI projects`）。

对照报告：

- [HARNESS_EVALUATION_AND_IMPROVEMENTS.md](./HARNESS_EVALUATION_AND_IMPROVEMENTS.md)
- [HARNESS_SECOND_REVIEW.md](./HARNESS_SECOND_REVIEW.md)
- [HARNESS_THIRD_REVIEW.md](./HARNESS_THIRD_REVIEW.md)
- [HARNESS_FOURTH_REVIEW.md](./HARNESS_FOURTH_REVIEW.md)

## 一、重要前提：未检测到新的源码修改

本轮开始时检查了工作区：

```text
git diff --stat
→ 无输出

git diff --name-only
→ 无输出

git status --short
→ 仅有四份未跟踪评估 Markdown：
   HARNESS_EVALUATION_AND_IMPROVEMENTS.md
   HARNESS_SECOND_REVIEW.md
   HARNESS_THIRD_REVIEW.md
   HARNESS_FOURTH_REVIEW.md
```

因此本轮没有发现你所说的新源码、配置或测试修改。以下报告评估的是当前 HEAD 与工作区可见内容；如果新修改在另一个分支、未保存目录或尚未同步到该工作区，本报告无法覆盖它。

## 二、执行摘要

当前评分：**7.8/10，维持上一轮评分**。

当前版本已经具备：

- 可运行的统一 CLI 命令面；
- 配置加载、基础校验和 workflow 执行；
- argv 数组子进程调用；
- 离线确定性 Eval 和 grader；
- 基础安全策略、脱敏和工具 allowlist；
- 单元测试、集成测试和 CI workflow；
- 初始化模板与跨语言示例配置。

但以下问题仍然阻止其成为可复制、可跨机器运行、可作为可信发布门禁的通用 Harness：

1. `skipped` 仍可能在顶层变成 `passed` 和 exit 0；
2. 入口仍包含本机绝对路径，初始化产物不自洽；
3. Eval 没有真实目标程序 Runner 协议；
4. `--strict` 是无效参数；
5. Eval 的 timeout、repetitions、cost、regression 限制没有完整执行；
6. `--config` 的相对路径按 cwd 解析，而不是按配置文件目录解析；
7. Profiles 仍只是模板，没有运行时加载与合并；
8. 外部 secret/dependency scanner 缺失时 CI 仍然成功；
9. 报告文件名只有秒级时间戳，存在覆盖风险。

定位仍是：

> 单仓库、本机可运行的 Harness 控制面原型。

## 三、验证范围与结果

### 3.1 文档与代码范围

已读取并对照：

- `README.md`
- `docs/architecture.md`
- `src/ai_harness/` 下 CLI、配置、Runner、Eval、结果、安全、策略和脱敏实现
- `harness.schema.json`
- `tests/unit/` 与 `tests/integration/` 测试
- `.github/workflows/ci.yml`
- `.github/workflows/evals.yml`
- `.github/workflows/security.yml`
- `profiles/`、`harness.toml` 和 Eval 数据集

### 3.2 本地命令结果

```text
./harness doctor --json
→ exit 0，status=passed
→ smoke dataset 8 cases，full dataset 10 cases
→ python3、git 可用

./harness validate --json
→ exit 0，status=passed

./harness list --json
→ exit 0，列出 6 个 stages、2 个 workflows、2 个 evals

./harness run check --json
→ exit 0，status=passed
→ compileall 通过，unit tests 通过

./harness run check --dry-run --json
→ exit 0，但顶层 status=passed，子阶段 status=skipped

./harness eval smoke --offline --json
→ exit 0，8/8 passed，pass_rate=1.0

./harness eval full --offline --json
→ exit 0，10/10 passed，pass_rate=1.0

./harness run release-check --json
→ exit 0，check、integration、full eval、security 全部通过

python3 -m unittest discover -s tests -p '*_test.py'
→ exit 0，Ran 99 tests，OK

git diff --check
→ exit 0

skill-up --version
→ 0.7.0 可用
```

`skill-up` 可用，但本仓库评估对象是 Harness 控制面，不是一个带 `SKILL.md` 的 Agent Skill；本轮使用仓库自身的 `harness` 验证体系，没有误把 skill-up 结果当作 Harness Eval 结果。

## 四、按维度评估

| 维度 | 评价 | 当前判断 |
|---|---|---|
| CLI 命令面 | 8/10 | 命令稳定、结果结构化，但 skipped 语义不安全 |
| 配置与 Schema | 6/10 | 严格未知字段和版本校验存在，但 Schema 与 parser 有矛盾 |
| Runner 执行 | 7/10 | argv、超时默认值、fail-fast 和 dry-run 基础能力存在 |
| 跨机器分发 | 3/10 | 入口绑定本机路径，init 不复制运行时源码 |
| Workflow | 7/10 | 组合、循环检测和失败传播存在，跳过传播仍有问题 |
| Eval 基础能力 | 6/10 | 离线 grader 可用，但实际是 fixture grader |
| Eval 门禁 | 4/10 | min pass rate 生效，其他限制字段不完整 |
| Profiles | 4/10 | 示例模板齐全，未接入运行时合并 |
| 安全 | 7/10 | 脱敏、allowlist、approval 和内置扫描有测试 |
| CI/CD | 7/10 | workflow、权限、timeout、artifact 配置较完整 |
| 可观测性 | 4/10 | 结果 Schema 完整，但没有传输层 |
| 测试与文档 | 8/10 | 99 项测试通过，文档覆盖广，但部分文档承诺超出实现 |

综合判断仍为 **7.8/10**：原型完成度较高，生产可信度受少数高影响语义问题限制。

## 五、阻断级问题

### P0-1：`skipped` 顶层状态仍可能伪装成 `passed`

执行：

```text
./harness run check --dry-run --json
```

结果中同时出现：

```text
top-level status = passed
workflow status = skipped
child status = skipped
exit code = 0
```

代码中 `_status_to_rc` 仍明确将 skipped 映射为成功：

```python
STATUS_SKIPPED: EXIT_SUCCESS
```

这与 README 和 architecture 中“missing optional stages report skipped，never silently claim passed”的承诺冲突。当前 dry-run 作为计划操作可以 exit 0，但结果状态不能是 passed；普通 workflow 的部分 skipped 也应有显式策略。

建议：

- 顶层 status 保留 `skipped` 或新增 `planned`；
- 默认 skipped 不得映射为 passed；
- 增加显式 `allow_skipped` 策略；
- 为纯 skipped、部分 skipped、dry-run 分别添加回归测试。

### P0-2：入口仍绑定当前机器路径

`harness` 仍包含：

```python
_CANONICAL_HOME = "/Users/tommacmini4/Documents/code/harness"
```

当前机器因为该目录存在，所以入口可以正常运行；这不能证明复制到其他机器后仍然可用。

此外，`init` 生成的目标项目只复制：

- `harness` executable；
- `harness.schema.json`；
- 配置、数据集目录和 `.gitignore`。

它没有复制 `src/ai_harness`，也没有写入固定版本的可安装依赖。因此初始化产物依赖：

- 目标机仍有相同源码路径；或
- 目标机通过 `HARNESS_HOME` 提供源码；或
- 目标机已经安装 `ai_harness`。

这不是一个自洽的 vendored project。

建议选择并明确一种正式分发方式：可安装 CLI、完整 vendored CLI，或明确限制为 monorepo 内部使用。

### P0-3：离线 Eval 不是真实目标程序 Eval

当前 `run_eval` 的 offline 路径直接读取：

- `case.input.output`；或
- `case.metadata.output`。

随后对 fixture 输出执行 grader。它能验证 grader 和阈值，但不能验证被测系统本身。

当前没有配置形式如下的语言无关 Runner：

```toml
runner = ["python3", "tests/fixtures/fake_provider.py"]
```

因此尚未覆盖：

- 任意语言目标程序；
- stdin/stdout JSONL 交互；
- runner 非零退出；
- malformed JSON；
- runner timeout；
- stderr 诊断和 redaction。

## 六、重要非阻断问题

### P1-1：`--strict` 是死参数

本轮分别执行：

```text
./harness validate --json
./harness validate --strict --json
```

剔除 `run_id`、`started_at` 和 `duration_ms` 后，两份 JSON 完全相同，均为 `status=passed`。

CLI 注册了 `--strict`，但 `_cmd_validate` 没有读取 `args.strict`，也没有 warnings 集合。当前 CI 使用 `./harness validate --strict`，实际没有额外门禁。

建议实现 warnings/strict，或删除该参数并同步 CI 和文档。

### P1-2：Eval 限制字段没有完整执行

当前配置和报告中存在：

- `timeout_seconds`
- `max_cost_usd`
- `repetitions`
- `max_regression`

但实现存在以下缺口：

- `timeout_seconds` 没有作为 Eval Runner 的执行超时；
- `repetitions` 没有让 Eval 实际执行多次；
- `max_cost_usd` 没有价格表和成本计算；
- `max_regression` 被写入 thresholds，但 baseline compare 不读取配置阈值。

这类字段比完全不存在更危险，因为接入者会认为限制已经生效。

### P1-3：相对路径按 cwd 解析

执行：

```text
cd /tmp
/Users/tommacmini4/Documents/code/harness/harness \
  validate --config /Users/tommacmini4/Documents/code/harness/harness.toml --json
```

结果：配置文件本身可读取，但：

```text
[evals.smoke]: Dataset not found: evals/datasets/smoke.example.jsonl
[evals.full]: Dataset not found: evals/datasets/regression.example.jsonl
```

相对 dataset、report、security scan 等路径应默认相对于配置文件目录，而非进程 cwd。

### P1-4：Schema 与 Python parser 不一致

当前 `harness.schema.json`：

```text
commands.*.minItems = 1
commands.*.items.minItems = 1
```

但 Python parser 接受：

```toml
[commands]
typecheck = []
```

并将其解释为“configured but no commands”，Runner 返回 skipped。应统一为允许空数组，或改用显式 disabled 字段。

### P1-5：报告文件名存在覆盖风险

`_persist_report` 使用：

```python
safe_started = report.started_at.replace(":", "").replace("-", "")
fname = f"{report.name}-{safe_started}.json"
```

时间戳只有秒级精度。同一秒并发或快速重试可能覆盖前一份报告。应加入 `run_id` 或毫秒精度，并考虑原子写入。

### P1-6：Profiles 没有运行时加载

`profiles/languages`、`profiles/workloads` 和 `profiles/risk` 文件存在，测试也确认它们可解析；但代码中没有 Profile loader、继承顺序、覆盖规则或来源追踪。

目前 `language`、`workload` 和 `risk` 主要用于配置元数据与 init 模板选择，不会自动把 profile 命令合并到运行时配置。

应明确 Profiles 是：

- 仅供人工复制的模板；或
- 正式运行时适配器。

如果是后者，应实现并测试 base → language → workload → risk → project 的合并规则。

### P1-7：外部安全工具缺失时 CI 仍成功

`.github/workflows/security.yml` 中：

- gitleaks 未安装时只输出 notice；
- pip-audit 未安装时只输出 notice。

对 prototype 可以接受，但 standard/high-risk 项目不应默认把缺失 scanner 当作成功。应按 risk profile 选择 notice、warning 或 blocked。

## 七、已验证的正向能力

本轮没有发现以下方面的回归：

### 7.1 基础命令与结构化结果

- `doctor`、`validate`、`list` 可用；
- 结果包含 `schema_version`、`run_id`、status、stages、summary、errors；
- exit code 0/1/2/3/4 的基本约定仍存在；
- workflow 能组合 commands、built-ins 和子 workflow。

### 7.2 子进程安全边界

代码使用 argv 数组和 `shell=False`，没有发现 `shell=True`。dry-run 不启动子进程，并对 argv 做脱敏。

### 7.3 基础安全能力

已存在并有测试覆盖：

- API key、Bearer、JWT、AWS key、GitHub token 等模式脱敏；
- tool allowlist；
- 高风险写操作 approval 检查；
- 内置 secret-shaped pattern scan；
- Eval 报告写入前 redaction；
- AI workload 空 allowlist 阻断；
- non-AI workload 空 allowlist advisory。

本次 `release-check` 的 security stage 结果为 passed，`findings_count=0`，`advisory_count=0`。

### 7.4 测试与 CI

- 全量 99 项测试通过；
- unit、integration、compileall 均通过；
- CI 具备 push、PR、schedule、workflow_dispatch、permissions、concurrency 和 timeout 配置；
- offline smoke/full eval 不依赖模型密钥。

这些是有效的回归证据，但不能抵消 P0 的分发、Eval Runner 和 skipped 语义问题。

## 八、建议新增的回归测试

下一次代码修改后，至少增加：

```text
1. 纯 skipped workflow 不得返回顶层 passed/exit 0
2. 部分 skipped workflow 的顶层状态和 exit code 明确可配置
3. dry-run 顶层 status 不得为 passed
4. 复制入口到临时目录、移除源码路径后仍能运行 --help
5. init 生成项目在干净环境中可运行
6. stdin/stdout JSONL Runner 成功、非零退出、malformed JSON、timeout
7. timeout_seconds 真正限制 Runner 执行
8. repetitions = 3 实际执行三次并聚合结果
9. max_regression = 0.02 允许 0.01 回退、阻断 0.03 回退
10. --strict 与普通 validate 存在可观察差异
11. 从非项目 cwd 使用 --config 时 dataset 路径正确
12. Schema 对空 command 的判断与 parser 一致
13. 报告同秒写入不互相覆盖
14. standard/high-risk 缺少外部 scanner 时按策略阻断或告警
15. language/workload/risk profile 的加载、覆盖和来源追踪
```

## 九、修复优先级

```text
第一阶段：修复 skipped 语义和入口分发
第二阶段：增加真实 JSONL Runner
第三阶段：修复配置根目录路径
第四阶段：实现 timeout、repetitions、max_regression 和 strict
第五阶段：统一 Schema，修复报告命名
第六阶段：明确并实现 Profiles 运行时模型
第七阶段：按 risk profile 强化外部安全工具缺失策略
```

## 十、最终判断

本轮完整评估没有发现新的源码修改，历史报告指出的问题仍然有效。

当前可以可信地宣称：

> Harness 原型在本仓库、本机和当前已配置路径下可运行，离线 Eval 与 99 项回归测试通过。

当前不能可信地宣称：

- 已经可以复制给其他项目直接使用；
- 已经支持跨语言真实 AI 应用 Eval；
- `release-check` 已经是可信的生产发布门禁；
- `passed` 可以证明所有阶段实际执行且未被跳过；
- timeout、cost、repetitions 和 regression 门禁已经生效。

本轮仅新增本报告，没有修改源码、配置或测试。
