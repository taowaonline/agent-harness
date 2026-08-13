# Harness 第四轮独立验证报告

> **本报告的定位**：最新一次独立验证快照。
> 战略与设计取舍见 [EVALUATION_AND_IMPROVEMENTS](./HARNESS_EVALUATION_AND_IMPROVEMENTS.md)；
> 代码 bug 清单与修复 recipe 见 [SECOND_REVIEW](./HARNESS_SECOND_REVIEW.md)；
> 历史变化见 [THIRD_REVIEW](./HARNESS_THIRD_REVIEW.md)。
> 本文**不重复**这些文档的内容，只回答两个问题：**"现在还能跑吗？"** 和 **"之前指出的问题还在吗？"**

---

## 一、验证元信息

| 项 | 值 |
|---|---|
| 验证日期 | 2026-08-08 |
| 验证基线 | commit `0c15d0e` "Treat empty tool_allowlist as advisory for non-AI projects" |
| 验证机器 | macOS（本机） |
| 自第二/三轮以来的源码改动 | security.py 改 advisory（commit `0c15d0e`）+ cli.py argparser 接受 `other`（同 commit） |
| 评分 | **7.8/10**（维持，无变化） |

---

## 二、可运行性验证（实际跑过的命令）

```text
$ python3 -m unittest discover -s tests/unit -p '*_test.py'
Ran 90 tests in 0.454s
OK

$ ./agent_harness validate
[validate] passed
  summary: {"validated": {"commands": [...6 stages], "evals": ["full", "smoke"], ...}}

$ ./agent_harness validate --strict --json
status: passed
（注意：--strict 与不加 --strict 输出完全一致，见 §三 P1-1）

$ ./agent_harness run check
[run] passed
  - check [workflow] passed
    - lint [command] passed
    - test-unit [command] passed

$ ./agent_harness eval smoke --offline
[eval] passed
  - smoke [eval] passed

$ ./agent_harness eval full --offline
[eval] passed

$ ./agent_harness run release-check
[run] passed
  - release-check [workflow] passed
```

**结论**：本地 V0 闭环仍然稳定。所有已配置路径回归通过。

---

## 三、Bug 复现（确认仍然存在）

每条都是本轮实际跑过、可一键复现的。

### B1. `skipped` 仍可被顶层报告为 `passed`

```text
$ ./agent_harness run typecheck --dry-run --json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'])"
passed
```

子阶段是 `skipped :: dry-run`，顶层却是 `passed`，退出码 0。**违反 skipped 契约**。详见 [SECOND_REVIEW §S7](./HARNESS_SECOND_REVIEW.md)。

### B2. 入口仍含本机绝对路径

```text
$ grep -n "_CANONICAL_HOME" harness
20:_CANONICAL_HOME = "/Users/tommacmini4/Documents/code/harness"
29:        _CANONICAL_HOME,
```

跨机器分发未证明。详见 [SECOND_REVIEW §P0.1](./HARNESS_SECOND_REVIEW.md)。

### B3. `--strict` 是死代码

```text
$ grep -c "args.strict" src/agent_harness/cli.py
0
```

CLI 注册了 `--strict` 但 `_cmd_validate` 从不读它。`validate` 与 `validate --strict` 输出**完全一致**。详见 [SECOND_REVIEW §S1](./HARNESS_SECOND_REVIEW.md)。

### B4. 字段"假装生效"

```text
$ grep -nE "repetitions|timeout_seconds|max_cost_usd" src/agent_harness/evals.py | grep -vE "(dataclass|threshold_block|EvalConfig|=.*None|=.*ec\.|self\.|= int)"
510:        "timeout_seconds": ec.timeout_seconds,
511:        "max_cost_usd": ec.max_cost_usd,
```

只在 `_threshold_block` 里**展示**，没有任何执行逻辑。`repetitions`、`timeout`、`cost` 全部不生效。详见 [SECOND_REVIEW §S2](./HARNESS_SECOND_REVIEW.md)。

### B5. 路径解析依赖 cwd 而非 config dir

```text
$ cd /tmp && harness validate --config /Users/tommacmini4/Documents/code/harness/harness.toml
[validate] failed
  error: [evals.smoke]: Dataset not found: evals/datasets/smoke.example.jsonl
  error: [evals.full]: Dataset not found: evals/datasets/regression.example.jsonl
```

dataset 路径按 `/tmp` 解析，找不到。详见 [SECOND_REVIEW §S6](./HARNESS_SECOND_REVIEW.md)。

### B6. Schema 与 parser 仍矛盾

```text
$ python3 -c "import json; s=json.load(open('harness.schema.json')); print('outer minItems:', s['properties']['commands']['additionalProperties']['minItems'])"
outer minItems: 1
```

但 Python parser 接受 `typecheck = []`。详见 [SECOND_REVIEW §S5](./HARNESS_SECOND_REVIEW.md)。

---

## 四、与前三轮的对照

| 问题 | 第一轮 | 第二轮 | 第三轮 | 第四轮（本轮） |
|---|---|---|---|---|
| 没有 V0 闭环 | 提出 | ✓ 关闭 | — | 稳定 |
| 入口本机路径 | — | 提出 | 重复 | **仍存在（B2）** |
| skipped → passed | 提出 | 重复 | 重复 | **仍存在（B1）** |
| 无 SUT Runner | 提出 | 重复 | 重复 | 仍存在（V1.1） |
| Profile 不合并 | 提出 | 重复 | 重复 | 仍存在（V1.2） |
| `--strict` 死代码 | — | 提出 | 重复 | **仍存在（B3）** |
| 字段不生效 | — | 提出 | 重复 | **仍存在（B4）** |
| 路径依赖 cwd | — | 提出 | 重复 | **仍存在（B5）** |
| Schema 矛盾 | — | 提出 | 重复 | **仍存在（B6）** |
| 报告时间戳 | — | 提出 | 重复 | 仍存在 |
| 安全 advisory 改进 | — | — | — | ✓ 已修（commit `0c15d0e`） |

**关键观察**：第一轮提出的战略问题（Runner / Profile）需要 V1 设计；第二轮提出的代码 bug（B1-B6）**至今未修**，且都是 quick-win（详见 [SECOND_REVIEW §五](./HARNESS_SECOND_REVIEW.md) 的修复排序）。

---

## 五、明确的"不要做"清单

当前版本（commit `0c15d0e`）下，**不要**：

| 不要 | 理由 |
|---|---|
| 复制到其它项目直接用 | 入口含本机路径（B2） |
| 把 `release-check` 当生产门禁 | skipped 可被报为 passed（B1），字段不生效（B4） |
| 宣称支持跨语言 AI 应用 Eval | 离线路径只读 fixture，无 Runner（见 [EVALUATION V1.1](./HARNESS_EVALUATION_AND_IMPROVEMENTS.md)） |
| 把 `passed` 直接当质量证明 | 多个静默失败路径（B1/B3/B4） |
| 在 CI 里依赖 `--strict` | 死代码（B3），与普通 `validate` 无差别 |
| 从仓库外 cwd 用 `--config` | dataset 路径会找不到（B5） |

---

## 六、可以做的事

当前版本**适合**：

| 适合 | 理由 |
|---|---|
| 单仓库、单机本地开发 | V0 闭环稳定，98 个测试通过 |
| 学习 Harness 设计模式 | 代码量小，文档完整，ADRs 清晰 |
| 作为 V1 开发的起点 | 已识别缺口清楚，[EVALUATION V1](./HARNESS_EVALUATION_AND_IMPROVEMENTS.md) 和 [SECOND_REVIEW quick-win](./HARNESS_SECOND_REVIEW.md) 都有具体下一步 |
| 在 macOS 本机做 wrapping（如 Local_CICD） | 已验证可用（见 [Local_CICD](https://github.com/taowaonline/local-cicd) 接入 commit `a867dad`） |
| 配合 skill-up 做 Agent 决策测试 | 已验证（harness 自身 skill-up evals 10/10 双绿） |

---

## 七、推荐下一步

按优先级：

1. **立刻**：做 [SECOND_REVIEW §五](./HARNESS_SECOND_REVIEW.md) 的 quick-win 冲刺（B3/B5/B6 等共 7 项，1-2 天可清完）
2. **本周**：完成 B1（skipped 顶层语义）+ B2（去掉本机路径），让"passed" 可信
3. **下周起**：进入 V1 战略冲刺（Runner 协议 → Profile 合并 → Monorepo）
4. **V2**：在线 ModelProvider / OTel exporter / 价格表 / 平台 adapter

---

## 八、本轮验证的可复现脚本

任何人都能跑：

```bash
cd /Users/tommacmini4/Documents/code/harness   # 或 clone 后的等价路径

# 可运行性
python3 -m unittest discover -s tests/unit -p '*_test.py'
./agent_harness validate
./agent_harness run check
./agent_harness eval smoke --offline
./agent_harness run release-check

# Bug 复现
./agent_harness run typecheck --dry-run --json | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])"
grep -n "_CANONICAL_HOME" harness
grep -c "args.strict" src/agent_harness/cli.py
cd /tmp && harness validate --config /Users/tommacmini4/Documents/code/harness/harness.toml
```

每条输出已在 §二、§三 留存。

---

## 九、最终判断

**评分维持 7.8/10，无变化。**

- 本地 V0 闭环稳定（§二 全绿）。
- 第二轮指出的代码 bug 全部仍然存在（§三 B1-B6）。
- 唯一关闭的是 security.py 对 non-AI 项目空 allowlist 的误判（commit `0c15d0e`）。
- 信任价值最大的 3 项仍未修：B3（`--strict` 死代码）、B4（字段假装生效）、B5（cwd 路径）。

**结论**：当前版本可以继续作为开发沙盒，**但不应该进入新的生产项目接入**，直到 [SECOND_REVIEW quick-win 冲刺](./HARNESS_SECOND_REVIEW.md) 完成。

---

## 十、变化日志

| 日期 | 变化 |
|---|---|
| 第四轮原始版本 | 列出 P0-1~P0-3 + P1-1~P1-6，但与第二/第三轮重复 |
| 本次优化 | 删除重复内容；改为"独立验证快照"定位；加可复现命令输出；加四轮对照表；加"不要做/可以做"清单；明确交叉引用 |
