# Harness 第六轮完整评估报告

评估对象：本轮用户修改后的 Harness 工作区。

基线 commit：`0c15d0e`。

## 一、结论

当前评分：**8.3/10**，较上一轮 7.8/10 有明显提升。

本轮修改已经关闭了上一轮的大部分 P0/P1 问题，当前版本可以更准确地称为：

> 支持 Profile、配置根目录、跳过门禁和 JSONL Runner 原型的 Harness 控制面。

但还不能称为完全可信的通用生产门禁，仍有三个需要修复的问题：

1. TOML 配置中的 `runner` 字段被解析后丢弃，真实配置无法启用 JSONL Runner；
2. malformed Runner 输出会让 case 变成 skipped，但 Eval 顶层仍可能为 passed；
3. `validate --strict` 返回 exit 1 时，JSON 结果仍写成 `status=passed`。

此外，`init` 仍只复制入口和 Schema，不复制 `src/agent_harness`；跨机器使用需要额外安装包或手工 vendoring，分发契约还需要进一步明确。

## 二、变更范围核验

本轮检测到 11 个已修改文件，涉及：

- `.github/workflows/ci.yml`、`.github/workflows/security.yml`
- `harness`、`harness.schema.json`
- `src/agent_harness/cli.py`
- `src/agent_harness/config.py`
- `src/agent_harness/evals.py`
- `src/agent_harness/policy.py`
- `src/agent_harness/runner.py`
- `tests/integration/cli_test.py`
- `tests/unit/runner_test.py`

新增了 `fake_provider.py` 以及 Eval enforcement、Profile、路径、风险扫描、Runner protocol、Schema/report、skipped semantics 测试。

## 三、验证结果

```text
python3 -m unittest discover -s tests -p '*_test.py'
→ exit 0，Ran 140 tests，OK

./agent_harness validate --json
→ exit 0，status=passed，带有 max_cost_usd 未实现 warning

./agent_harness validate --strict --json
→ exit 1，但 JSON status 仍为 passed（见 P1-3）

./agent_harness run check --json
→ exit 0，status=passed

./agent_harness run check --dry-run --json
→ exit 10，顶层 status=skipped，workflow status=skipped

./agent_harness run check --dry-run --allow-skipped --json
→ exit 0，顶层 status=skipped

./agent_harness eval smoke --offline --json
→ exit 0，8/8 passed，pass_rate=1.0

./agent_harness eval full --offline --json
→ exit 0，10/10 passed，pass_rate=1.0

./agent_harness run release-check --json
→ exit 0，check、integration、full eval、security 全部通过

git diff --check
→ exit 0
```

相比上一轮 99 项测试，本轮新增到 140 项，全部通过。

### 跨 cwd 验证

从 `/tmp` 执行：

```text
/Users/tommacmini4/Documents/code/harness/harness \
  validate --config /Users/tommacmini4/Documents/code/harness/harness.toml --json
```

结果为 exit 0，dataset 路径正确解析，上一轮的路径问题已关闭。

### Entry 隔离验证

复制 `harness` 和 `src/` 到临时目录，设置 `HARNESS_HOME=/nonexistent` 后执行 `--version`：

```text
isolated_rc=0
stdout=harness 0.1.0
```

入口不再包含 `/Users/tommacmini4` 或 `_CANONICAL_HOME`。

## 四、上一轮问题关闭情况

| 问题 | 状态 | 证据 |
|---|---|---|
| `skipped` 顶层伪装 `passed` | 已修复 | 顶层变为 skipped，默认 exit 10，`--allow-skipped` 可显式放行 |
| 入口硬编码本机路径 | 已修复 | 删除 `_CANONICAL_HOME`，隔离复制运行成功 |
| 配置根目录路径 | 已修复 | 外部 cwd 使用绝对 config 成功 |
| Schema 空 command 矛盾 | 已修复 | Schema 删除 outer `minItems` |
| 报告同秒覆盖 | 已修复 | 文件名加入 run_id，并使用原子替换 |
| `max_regression` 不生效 | 已修复 | 小回退 `within_threshold`，大回退 `regressed` |
| `repetitions` 不执行 | 部分修复 | 直接构造 `EvalConfig` 时执行，TOML runner 仍被丢弃 |
| `--strict` 无区别 | 部分修复 | 已产生 warning 和 exit 1，但 status 未改为 failed |
| Profiles 未接入运行时 | 已修复 | `extends = ["languages.python"]` 可加载 commands |
| 无真实 JSONL Runner | 部分修复 | Runner 实现存在，但 TOML 配置无法传递 runner |
| 外部 scanner 缺失无风险策略 | 已修复 | prototype/standard/high-risk 分别 notice/warning/block |

## 五、已关闭的核心能力

### 5.1 skipped 策略

workflow 中任意 skipped 子阶段会传播到顶层，dry-run 也强制为 skipped。CLI 新增 `--allow-skipped`，默认 exit code 为 10，只有显式允许时才返回 0。

这已经消除了上一轮最严重的“绿色但没执行”风险。

### 5.2 Profile runtime loading

配置支持：

```toml
extends = ["languages.python", "workloads.rag", "risk.standard"]
```

当前实现支持 Profile 定位、多 Profile 顺序合并、project 覆盖、commands/workflows 按 stage 覆盖、security 合并，以及未知/缺失 Profile 拒绝。

### 5.3 配置根目录与 baseline

`Config.project_root` 已加入配置对象，dataset、report 等路径通过 project root 解析。

baseline compare 新增 `--max-regression`、`--eval-kind`、`--config`，实测：

```text
0.95 → 0.94，允许回退 0.02 → within_threshold
0.95 → 0.94，允许回退 0.005 → regressed
```

### 5.4 报告与安全扫描

Eval report 现在拥有独立 `run_id`，文件名包含 run_id，并使用临时文件加 `os.replace` 原子写入。

`security.yml` 已按 risk level 处理工具缺失：prototype 为 notice，standard 为 warning，high-risk 为 error/block。高风险还会安装 pinned gitleaks，standard/high-risk 会安装 pip-audit。

## 六、仍未关闭的问题

### P0-1：TOML `runner` 字段被静默丢弃

`EvalConfig`、Schema 和 `_ALLOWED_EVAL_KEYS` 已支持：

```toml
runner = ["python3", "runner.py"]
```

但 `_build_evals()` 构造 `EvalConfig` 时没有传入 `runner=body.get("runner")`。

黑盒验证结果：

```text
TOML contains runner = ["python3", "runner.py"]
load_config(...).evals["smoke"].runner → None
```

后果是直接构造 Python `EvalConfig` 的测试通过，但真实用户在 `harness.toml` 中配置 Runner 时，Runner 不会启动；`repetitions`、timeout 和跨语言 SUT 在真实配置路径上仍不可用。

建议：验证 runner 是非空 string list，并把它传给 `EvalConfig`；新增“从 TOML 加载后实际启动 fake_provider”的集成测试。

### P0-2：malformed Runner 输出仍可能导致 Eval 假通过

使用只输出 `not-json` 的 Runner 进行黑盒验证，结果为：

```text
stage_status = passed
summary = total=1, passed=0, failed=0, errors=0, skipped=1
result.errors = ["runner: malformed JSON ..."]
```

`_invoke_subprocess_runner()` 把 malformed JSON 写入顶层 `result.errors`，但没有为对应 case 生成 `CaseResult(status="error")`；`_grade_case()` 随后返回 skipped。由于 case summary 的 errors 为 0，Eval 仍可能通过。

此外，返回的 `case_id` 集合没有强制与输入 case 集合完全一致，未知、重复或缺失 case_id 可能表现为 skipped。

建议将 protocol error 转成对应 case 的 error，或直接阻断 stage；任何 malformed、缺失、重复或错位 case_id 都不得产生 passed。

### P1-3：strict exit code 与结果 status 不一致

当前执行：

```text
./agent_harness validate --strict --json
```

结果是 exit 1，但 JSON 为 `status=passed`、`errors=[]`，warning 出现在 summary 中。

`_cmd_validate()` 在 strict warning 分支直接返回 `EXIT_VALIDATION`，没有先设置 `result.status = STATUS_FAILED`。

另一个设计问题是当前仓库的 `max_cost_usd` 没有成本跟踪，因此 strict 会因为 planned 字段 warning 失败。CI 已改回普通 `validate`，避免常态失败，但也意味着 CI 当前不执行严格 warning 门禁。

建议设置 failed status，并明确 `max_cost_usd` 是 enforced、planned 还是允许 warning；不要通过改用普通 validate 来掩盖真正应阻断的 warning。

## 七、其他观察

### 7.1 Runner timeout 语义

Runner 使用 `subprocess.run(..., timeout=ec.timeout_seconds)`，这是有效的整体 subprocess timeout，但文档注释称“每个 stdout line 必须在 timeout 内到达”，实现并没有逐行读取。应统一文档和实现语义。

### 7.2 cost 仍未实现但已可见

`max_cost_usd` 仍没有 provider price table 或实际成本计算；现在会产生 warning，信任风险低于上一轮，但不能视为成本门禁已完成。

### 7.3 init 仍不是完全自包含的 vendored 安装

入口现在明确要求入口旁有 `src/agent_harness`、设置 `HARNESS_HOME` 或 pip/pipx 安装包。但 `harness init` 仍只复制入口和 Schema，不复制 `src/`，也没有生成 package pin。

本轮隔离测试复制了 `harness + src`，证明的是 vendored layout 可运行，不是 `init` 产物单独可运行。

## 八、建议新增回归测试

```text
1. TOML runner 字段加载到 EvalConfig.runner
2. 从 TOML 配置真实 fake_provider 并验证 output 被 grader 使用
3. malformed Runner output 生成 case error 并阻断 Eval
4. Runner 返回重复/未知/缺失 case_id 时阻断 Eval
5. validate --strict 的 JSON status 必须是 failed
6. strict warning 的 CI 策略明确区分 planned 字段和真正错误
7. init 生成项目在无源仓库路径、无 HARNESS_HOME、无预装包环境中运行
8. Runner 文档明确整体 timeout 或实现逐行 timeout
```

## 九、最终判断

本轮修改是实质性进展，不是表面改名：140 项测试通过，上一轮大部分问题已获得实现和回归覆盖。

当前可以可信地宣称：

> Harness 已具备 honest skipped 语义、配置根目录、Profile runtime loading、baseline regression threshold、报告原子写入和风险感知 scanner 策略。

当前仍不能可信地宣称：

- TOML 用户已经可以实际启用 JSONL Runner；
- malformed Runner 输出一定会阻断 Eval；
- strict 的结构化结果 status 与退出码一致；
- `init` 产物在没有额外安装或 vendoring 的干净环境中自洽运行；
- `max_cost_usd` 已经执行成本门禁。

本轮仅新增本报告，没有修改用户源码或测试。
