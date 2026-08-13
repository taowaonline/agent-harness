# Harness 第二轮代码复审

评估对象：当前仓库的 Harness 实现（commit `0c15d0e` 及之前）
上轮：[HARNESS_EVALUATION_AND_IMPROVEMENTS.md](./HARNESS_EVALUATION_AND_IMPROVEMENTS.md)（战略层）
本轮：**战术层** —— 找代码 bug 和"假装生效"的字段

两份文档关系：
- **EVALUATION（战略）**：任务书够不够好？V1/V2 该做什么？
- **SECOND_REVIEW（战术，本文）**：代码有没有兑现自己的承诺？哪些字段是装饰？

---

## 一、复审执行

- 复审基线：commit `0c15d0e` "Treat empty tool_allowlist as advisory for non-AI projects"
- 复审方法：每条发现用 `grep` 或单测验证后留存证据
- 复审结论：**第二轮报告的 P0/P1 基本全部仍然存在**；本审计额外找到 3 个 quick-win bug

---

## 二、状态总览（grep 验证）

| 编号 | 第二轮原始发现 | 当前状态 | grep 证据 | 修复成本 |
|---|---|---|---|---|
| P0.1 | `harness` 硬编码 `_CANONICAL_HOME` | ⚠️ 仍存在 | `harness:20` | 中 |
| P0.2 | `skipped → exit 0` | ⚠️ 仍存在 | `_status_to_rc` 映射 | 小 |
| P0.3 | 无 SUT Runner 协议 | ⚠️ 仍存在 | `evals.py` 无 stdin/stdout | 大（V1.1） |
| P0.4 | Profile 不自动合并 | ⚠️ 仍存在 | `config.py` 无 loader | 大（V1.2） |
| P1.1 | `--strict` 死代码 | ⚠️ 仍存在 | `grep args.strict src/agent_harness/cli.py` → 空 | **极小** |
| P1.2 | `timeout`/`cost`/`repetitions` 不生效 | ⚠️ 仍存在 | `repetitions` 只在 dataclass | 中 |
| P1.3 | `max_regression` 装饰 | ⚠️ 仍存在 | 仅 `_threshold_block` 展示 | **小** |
| P1.5 | 秒级时间戳 → 同秒覆盖 | ⚠️ 仍存在 | `_persist_report` 用 `started_at` | **极小** |
| P1.6 | 路径依赖 cwd 而非 config dir | ⚠️ 仍存在 | `load_dataset` 用 `Path(...)` | 小 |
| P1.7 | Schema 与 parser 矛盾 | ⚠️ 仍存在 | schema `minItems:1` vs Python 允许 `[]` | **极小** |

**10 项中 4 项是 < 30 分钟修复**，可以一次 quick-win 冲刺清掉。

---

## 三、自第二轮以来已修复

| 问题 | 修复 commit | 说明 |
|---|---|---|
| 空 `tool_allowlist` 对 non-AI 项目硬失败 | `0c15d0e` | 改成 advisory（写进 metrics.advisory 不阻断） |
| `harness init` argparser 拒绝 `--language other` | `0c15d0e` | argparser 与 config enum 对齐 |
| GitHub secret scanning 拦下文档级 `sk_test_...` | `7bd4b35` | 测试源码改用运行时拼接 |
| `harness init` 不存在 | `7bd4b35` 之前 | 已实现，支持 6 种语言模板 |

---

## 四、复审后新发现的代码 bug

第二轮没提到，但本轮 grep 时浮出来的：

### S1. `--strict` 是死代码（确认 P1.1）

`cli.py` 注册了 `--strict` flag：
```python
sp.add_argument("--strict", action="store_true", help="Treat warnings as errors.")
```
但 `_cmd_validate` **从不读 `args.strict`**。`grep -n "args.strict" src/agent_harness/cli.py` 返回空。

CI 用 `./agent_harness validate --strict` 比用 `./agent_harness validate` **看起来**更严格，实际**完全一样**。这是 trust 杀手。

**最小修法**（如果不想真做 warnings，就删 flag）：

```python
# 选 A: 删除
# sp.add_argument("--strict", ...)   # 删掉

# 选 B: 真做 warnings
warnings: list[str] = []
# ... 检查未知字段、过松阈值等 ...
if warnings:
    result.summary["warnings"] = warnings
    if args.strict:
        return EXIT_VALIDATION
```

### S2. 配置字段"假装生效"（确认 P1.2）

`harness.toml` 用户写的：

```toml
[evals.smoke]
timeout_seconds = 120
max_cost_usd = 2.0
repetitions = 3
```

代码实际行为：
- `repetitions = 3` → **从不循环**，每次只跑 1 次
- `max_cost_usd = 2.0` → 无价格表，永远不阻断
- `timeout_seconds = 120` → 不传给任何 subprocess

接入者看 harness.toml 会以为这些起作用。比"漏实现"更糟的是"看起来实现了"。

**修法（任选其一）**：

- **A. 实现**（推荐顺序）：
  1. `timeout_seconds` → 传给 `subprocess.run(timeout=...)`
  2. `repetitions` → for 循环 + 取最差 pass_rate
  3. `max_cost_usd` → 需要 provider 价格表，先标 planned
- **B. 至少 warn**：解析时如果字段非空，validate 阶段输出 `"warning: field X is parsed but not enforced, see roadmap"`，避免静默假装。

### S3. `max_regression` 是装饰（确认 P1.3）

`compare_reports` 算 delta，CLI 在任何 `regression > 0` 时失败，无视 toml 里 `max_regression = 0.02`。

```bash
./agent_harness baseline compare a.json b.json
# regression = 0.001 → 失败
# regression = 0.5 → 失败（一样）
# 配置 max_regression = 0.02 → 被无视
```

**修法**（30 行代码）：让 `compare` 支持 `--config` 和 `--eval-kind`：

```python
if ec.max_regression is not None and delta["regression"] <= ec.max_regression:
    verdict = "within_threshold"  # 不阻断
elif delta["regression"] > 0:
    verdict = "regressed"
```

### S4. 秒级时间戳 → 同秒覆盖（确认 P1.5）

`_persist_report` 用 `started_at`（秒级 ISO）拼文件名。CI 重试或并行 eval 同秒会覆盖之前的报告。

```python
safe_started = report.started_at.replace(":", "").replace("-", "")
fname = f"{report.name}-{safe_started}.json"  # 同秒会撞
```

**修法**（10 行代码）：用 `run_id` 短哈希（已经是 uuid hex）：

```python
fname = f"{report.name}-{report.started_at_compact}-{report.run_id[:8]}.json"
```

或者直接 `report.run_id` 当主键。

### S5. Schema 与 parser 矛盾（确认 P1.7）

```bash
python3 -c "import json; s=json.load(open('harness.schema.json')); print(s['properties']['commands']['additionalProperties']['minItems'])"
# → 1
```

但 Python 接受 `typecheck = []` 并解释为 skipped。`tests/unit/config_test.py::test_empty_argv_list_allowed_as_skipped` 显式锁定了这个分歧。

**修法**（1 行 JSON）：

```diff
- "minItems": 1
+ "minItems": 0
```

（外层 commands 的 additionalProperties 的 minItems）

### S6. 路径解析依赖 cwd 而非 config dir（确认 P1.6）

```bash
cd /tmp && harness validate --config /path/to/project/harness.toml
# → 找不到 dataset（因为 load_dataset 用 Path(...) 即 cwd 相对）
```

**修法**（小但需要测试覆盖）：

```python
# Config 里加 project_root
self.project_root = Path(source_path).parent


# load_dataset 等改用
def load_dataset(path, project_root=None):
    p = Path(path)
    if not p.is_absolute() and project_root:
        p = project_root / p
    ...
```

### S7. dry-run 顶层状态可能是 "passed"（新发现）

`RunRequest.dry_run = True` 时，单 stage 是 `skipped`，但 workflow 顶层在某些路径下仍可能报 `passed`。`tests/integration/cli_test.py::test_run_check_dry_run` 显式断言 dry-run 顶层是 `passed`，**这本身就违反了 "skipped 不应静默 claim passed"** 的契约。

**修法**：dry-run 永远报顶层 `skipped`（reason "dry-run"），禁止 `passed`。同时改那个测试。

---

## 五、Quick-Win 冲刺建议（1-2 天可完成）

按修复成本排序，前 4 项**可以一次提交全部清掉**：

| 顺序 | 项 | 工时 | 风险 |
|---|---|---|---|
| 1 | **S5 schema minItems** | 5 分钟 | 0（已有测试覆盖） |
| 2 | **S4 时间戳加 run_id** | 10 分钟 | 0（向后兼容） |
| 3 | **S1 删 `--strict`**（短期）| 15 分钟 | 0（删 dead code） |
| 4 | **S7 dry-run 顶层 skipped** | 30 分钟 | 小（要改 1 个测试） |
| 5 | **S3 max_regression 真生效** | 1 小时 | 小 |
| 6 | **S6 路径相对 config dir** | 2 小时 | 中（要加集成测试） |
| 7 | **S2 字段 warn 不生效** | 1 小时 | 0（只加 warning） |

做完 1-4 项就把"虚假安全感"问题清掉 70%。做完 1-7 项就把代码层 bug 清光，剩下 P0.3/P0.4 是 V1 战略问题（见 EVALUATION 文档）。

---

## 六、与 EVALUATION 文档的分工

| 问题类别 | 文档 | 例子 |
|---|---|---|
| 战略 / 设计 / Roadmap | [EVALUATION_AND_IMPROVEMENTS](./HARNESS_EVALUATION_AND_IMPROVEMENTS.md) | V1.1 Runner 协议、V1.2 Profile 合并、V1.3 Monorepo |
| 代码 bug / 假装生效 | **本文（SECOND_REVIEW）** | `--strict` 死代码、`max_regression` 装饰、schema 矛盾 |

读完 EVALUATION 知道**该做什么**，读完本文知道**哪些已经坏了**。

---

## 七、本次复审的实际命令（可复现）

```bash
# P0.1 hardcoded path
grep -n "_CANONICAL_HOME" harness
# → 20:_CANONICAL_HOME = "/Users/tommacmini4/Documents/code/harness"

# P1.1 --strict 死代码
grep -n "args.strict" src/agent_harness/cli.py
# → (空)

# P1.2 字段不生效
grep -nE "repetitions|timeout_seconds|max_cost_usd" src/agent_harness/evals.py | grep -v dataclass | grep -v threshold_block
# → (空，除了 dataclass 定义和展示)

# P1.3 max_regression
grep -n "max_regression" src/agent_harness/evals.py
# → 508: 在 _threshold_block 里展示

# P1.7 schema 矛盾
python3 -c "import json; s=json.load(open('harness.schema.json')); print('outer:', s['properties']['commands']['additionalProperties'].get('minItems')); print('inner:', s['properties']['commands']['additionalProperties']['items'].get('minItems'))"
# → outer: 1 / inner: 1  （但 Python 允许空）

# 跑测试套件
python3 -m unittest discover -s tests/unit -p '*_test.py' 2>&1 | tail -3
# → Ran 90 tests in 0.454s / OK
```

---

## 八、最终判断

第二轮发现的问题**都是真的**，且**没一个被修复**（自第二轮写作以来）。最大的 trust 风险不是漏功能，而是：

1. **S1（`--strict`）** —— 虚假严格性
2. **S2（字段不生效）** —— 虚假门禁
3. **S5（schema 矛盾）** —— 虚假契约

这三个"虚假"比 V1.1（Runner 协议）的"未实现"更危险 —— 因为接入者**以为自己被保护了，实际没有**。

**建议**：在 V1.1/V1.2 还需要时间的情况下，**先把第五节的 7 项 quick-win 清掉**。这是 1-2 天的工作量，能把代码层 trust 拉满。然后再做 V1 战略冲刺。

---

## 九、变化日志

| 日期 | 变化 |
|---|---|
| 第二轮原始版本 | 写作时的状态 |
| 本次优化 | 加 grep 证据列；标"S1-S7"重新分组；加修复 recipe；与 EVALUATION 文档明确分工 |
