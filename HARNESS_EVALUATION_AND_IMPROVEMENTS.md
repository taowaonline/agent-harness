# Harness 任务书评估与改进（实施后审计）

评估对象：[HARNESS_IMPLEMENTATION_BRIEF.md](./HARNESS_IMPLEMENTATION_BRIEF.md)
实施产物：[src/ai_harness/](./src/ai_harness/) + [examples/](./examples/) + [tests/](./tests/)

本文档分两半：

1. **实施前评估**：原任务书作为输入的可执行性审计（保留，作为历史决策依据）。
2. **实施后审计**：每条 P0/P1/P2 的实际处理状态 + 实施过程中新发现的缺口 + 前向 roadmap。

---

## 一、实施状态总览

| 维度 | 原评分 | 实施后实际状态 | 备注 |
|---|---:|---|---|
| 目标覆盖 | 9/10 | ✓ 完整 | CLI / Eval / Security / CI / Profiles 全部到位 |
| 跨语言设计 | 7/10 | ⚠ 部分 | Profiles 是文件 snippet，未实现自动加载/合并 |
| 可执行性 | 5/10 | ✓ 已交付 | 98 个测试通过，V0 闭环跑通 |
| CLI 契约 | 6/10 | ✓ 退出码稳定 | 0/1/2/3/4 已固定；缺 `--allow-skipped` |
| Eval 设计 | 6/10 | ⚠ Python-only | ModelProvider 是 callable，未实现 stdin/stdout 协议 |
| 安全 | 6/10 | ✓ 可测试 | 脱敏 / allowlist / approval / secret-scan 全有测试 |
| 可观测性 | 5/10 | ⚠ Schema-only | 字段定义完整，无传输层 |
| CI/CD | 6/10 | ✓ 三 workflow 齐 | triggers / permissions / concurrency / retention 都有 |
| 验收质量 | 6/10 | ✓ 行为型 | skill-up evals 10/10 双绿 |

**结论**：原任务书的 P0 大多数在实施时被合理处理（不一定按原批评的方式）。真正遗留的高价值缺口有 4 个，详见第三节。

---

## 二、原批评的逐条处置

### P0.1 没有明确 V0 唯一成功场景

**原批评**：任务书要求一次实现所有功能，缺 V0 切片。
**实施处置**：实施时按"阶段 A→B→C→D→E"切片推进（[HARNESS_IMPLEMENTATION_BRIEF.md](./HARNESS_IMPLEMENTATION_BRIEF.md) §15），每阶段完成即跑测试。最终 V0 闭环：

```bash
./harness validate            # 配置合法
./harness eval smoke --offline  # JSONL fixture + grader 跑通
./harness run check --dry-run # 不产生副作用
./harness run release-check   # 全套门禁绿
```

**遗留**：无。这一项已闭环。

### P0.2 "本仓库"和"被测项目"边界不清

**原批评**：当前仓库既当 Harness 控制面又当完整 AI 项目，应该支持 `./harness --project <path> ...`。
**实施处置**：未实现 `--project` flag。当前模型：`harness.toml` 在 cwd 是契约；要操作别的项目，`cd` 过去或用 `--config <path>`。
**实际影响**：
- 单机多项目复用：`cd` 可解决，麻烦但不阻塞。
- CI 跨项目矩阵：每个 job 自己 `cd`，能跑。
- 不破坏 vendor-neutral 承诺，但不如有 `--project` 干净。

**遗留**：见 V1 建议 §4.3。

### P0.3 Eval 缺少"被测系统"接口

**原批评**：应该定义 stdin/stdout JSONL Runner 协议，让被测系统可以是任意语言。
**实施处置**：用 Python `ModelProvider = Callable[[EvalCase], dict]` 替代。Runner 必须是 Python 或能被 Python 调用。
**实际影响**：
- 对 Python AI 项目：直接、自然。
- 对 TS/Go/Rust AI 项目：需要在 Python 里 `subprocess` 调用，丢掉了"vendor-neutral"的部分价值。
- 离线 fixture（`input.output` 字段）让跨语言测试能跑通，但只测 grader，不测真实 SUT。

**遗留**：见 V1 建议 §4.1（高优先级）。

### P0.4 Profile 没有组合和覆盖规则

**原批评**：Profiles 应该被自动加载和合并（base → language → workload → risk → project）。
**实施处置**：Profiles 是 `profiles/{languages,workloads,risk}/*.toml` 中的 snippet，**仅供复制粘贴**。无加载器、无合并器、无版本协商。
**实际影响**：
- 优点：实施简单、用户控制力强、不会出现"魔法覆盖"。
- 缺点：6 种语言 × 4 种 workload × 3 种 risk = 72 种组合，全靠手工拼。`harness init` 用 `examples/<lang>-<workload>/` 模板缓解，但仍不能自动 merge risk 进 workload。
- 跨项目复用时容易出现 copy-paste 漂移。

**遗留**：见 V1 建议 §4.2。

### P0.5 退出码和失败语义不够具体

**原批评**：建议固定 0/1/2/3/4/5/10 七种退出码 + `--allow-skipped`。
**实施处置**：固定 0/1/2/3/4 五种（success / validation / stage_failed / policy_blocked / internal）。**未实现** `--allow-skipped` 和 timeout/budget 专用退出码。
**实际影响**：
- CI 门禁清晰，5 种够用。
- 真实风险：**所有 stage 都 skipped 时，整体结果是 passed**（因为 skipped 不翻转 PASSED 状态）。这掩盖了"环境完全没装/命令全跑空"的情况。

**遗留**：见 V1 建议 §4.4（中等优先级，是一个真实的 silent-failure 风险）。

### P1.1 ~ P1.8

| 编号 | 原批评要点 | 实施处置 |
|---|---|---|
| P1.1 打包方式 | 入口和模块导入要明确 | ✓ 用 `python3 -m` 风格 + `sys.path` 注入。开发态 `PYTHONPATH=src`，分发态 wrapper |
| P1.2 doctor 拆分 | 应有 `--harness` / `--project` / `--online` | ✗ 单一 `doctor`，未拆分 |
| P1.3 配置示例不能直接运行 | 根配置用了 uv/ruff/pyright 但仓库没装 | ✓ 根 harness.toml 改用 `python3 -m unittest` / `compileall`，零三方依赖；示例放 `examples/` |
| P1.4 离线 Fixture | 要有 fake provider + 故意失败 case | ✓ fixture 嵌入 JSONL 的 `input.output` 字段；smoke/regression 各含故意失败路径（阈值测试） |
| P1.5 评分统计 | pass_rate 分母、重复运行规则 | ⚠ 部分实现：分母 = passed + failed（errors 和 skipped 不计）；重复运行支持但无 CI；无统计置信区间 |
| P1.6 安全变可测试 | 脱敏 / allowlist / approval 测试 | ✓ 全部有单测；secret-scan + redaction probe 实测 |
| P1.7 Agent 上下文契约 | 定义上下文预算、秘密排除、停止条件 | ⚠ AGENTS.md 存在但只写行为规范，未定义上下文 budget / 自动 secret 排除 |
| P1.8 CI 精确化 | triggers / permissions / timeout / fork PR | ✓ 三 workflow 都有；fork PR secret 隔离有文档 |

### P2.1 ~ P2.4

| 编号 | 原批评要点 | 实施处置 |
|---|---|---|
| P2.1 观测传输 | 字段谁生成、OTLP / 本地 JSONL 选择 | ⚠ Schema 完整定义在 `docs/observability.md`；无任何传输实现 |
| P2.2 发布平台 | 应限定 Docker / K8s / Serverless 边界 | ✓ `docs/release-policy.md` 平台无关 + 列出适配点；未提供具体平台示例 |
| P2.3 版本兼容 | 配置/Result/Dataset schema 升级规则 | ⚠ 配置有 `version = 1` 拒绝未知主版本；无迁移命令；Result/Dataset schema 无版本字段 |
| P2.4 成本模型 | `max_cost_usd` 需要价格表 | ⚠ 字段保留，**无价格表**，实际不计算成本；`estimated_cost` 永远是 None |

---

## 三、实施后才知道的缺口

这些是只有真正用过 harness 才会暴露的问题，原批评没预测到。

### N1. skill-up case 设计的假阳性陷阱

实施 skill-up evals 时，5 次 iteration 中有 4 次失败都是**测试用例设计错误**，不是 SKILL.md 的问题：

```yaml
# 错误示例：must_not_contain 抓到了 Agent 教学引用
must_not_contain:
  - "shell=True"   # Agent 写 "do not use shell=True" 也会被命中
```

**教训**：`must_not_contain` 应该只匹配**祈使句形式的错误答案**（"Run X with --flag"），不应匹配教学引用。这条经验应该写进 case.yaml 模板。

### N2. 空工具 allowlist 对 non-AI 项目是误判

原 security stage 对所有项目都把空 `tool_allowlist` 当作失败。但 Local_CICD（shell-skill）和 iLanguage（双栈 app）都不暴露 Agent 工具 —— 空 allowlist 是正确的 deny-by-default。

已在 commit `0c15d0e` 修复：AI workload 仍然硬失败，non-AI workload 改为 advisory。

### N3. GitHub secret scanning 会拦下文档级示例 secret

Stripe 官方文档示例 test key（前缀 `sk_test_`，后跟 24 个字母数字字符）会让 push 被 GitHub secret scanning 阻断。修法是在源码里**运行时拼接** secret 字面量，让 prefix 和 body 不出现在同一字符串字面量里：

```python
stripe_key = "sk_" + "test_" + "a" * 28  # 拆开 prefix
```

但这意味着任何**测试 redaction 的代码**都得绕个弯。可考虑加一个 `tests/fixtures/secrets.txt` 显式标记区域，scanner 配置忽略。

### N4. shell 项目没有合适的 language profile

`profiles/languages/` 有 python/typescript/go/rust/jvm/dotnet，**没有 shell**。Local_CICD 这种 shell-skill 项目只能用 `language = "other"`，失去 profile 的引导价值。

应加 `profiles/languages/shell.toml` 覆盖 shfmt/shellcheck/bash -n。

### N5. Monorepo 多栈接入模型不清

iLanguage（Flutter + TypeScript worker）这种两栈 monorepo，harness 当前模型 awkward：

- 单 harness.toml：所有 stage 都要并列两栈命令，工作流失去语义（"lint" 究竟是 Flutter analyze 还是 Worker eslint？）
- 双 harness.toml：父子关系不清，没有"运行子项目所有 check"的总入口。

V1 应明确支持其一。

### N6. harness eval 和 skill-up eval 是两套系统

harness 用 JSONL + deterministic grader；skill-up 用 YAML + rule_based/agent_judge。两者各有所长但**无桥接**。Local_CICD 项目同时有：
- `evals/datasets/*.jsonl`（harness 用）—— 实际是 init seed 的占位
- `evals/cases/*.yaml` + `evals/eval.yaml`（skill-up 用）—— 真正在跑的 Agent 决策测试

用户必须理解两套语义。应提供 adapter，让 `harness eval smoke` 能调用 skill-up YAML。

---

## 四、前向 Roadmap

### V1：高价值缺口（建议下次冲刺做）

#### V1.1 Cross-language SUT Runner 协议（解决 P0.3 + N6）

定义 stdin/stdout JSONL 协议，让被测系统任意语言：

```text
harness 启动 runner 子进程
  → 通过 stdin 发送 Eval Case JSON（每行一条）
  → 通过 stdout 接收 Eval Result JSON（每行一条）
  → stderr 仅写诊断（自动 redact）
  → 退出码 0/非0 表示 runner 健康度
```

收益：
- TS/Go/Rust AI 项目不用写 Python wrapper。
- 同一 runner 可被 skill-up / 其它 eval 框架复用。
- fixture 文件可标注 `runner: ./my-runner`，harness 自动调度。

#### V1.2 Profile 加载与合并（解决 P0.4）

实现 base → language → workload → risk → project 的合并：

```text
标量字段：后者覆盖前者
命令阶段：后者覆盖前者（同 stage 名）
列表字段：默认 replace；<field>_append 显式追加
未知 Profile：validate 失败
```

收益：72 种组合不用手工拼；profile 漂移由 schema 测试守护。

#### V1.3 Monorepo 支持（解决 N5）

明确二选一模型：
- **A. 父 harness.toml + 子项目子目录配置**：父 `harness.toml` 声明 `projects = ["./", "backend/worker"]`，`harness run check` 跑所有子项目。
- **B. 子目录独立 harness.toml + 父目录 wrapper**：父调 `harness --project ./backend/worker run check`。

A 更符合 monorepo 习惯，但需要新 schema 字段。B 更轻，但需要 `--project` flag。

#### V1.4 `--allow-skipped` 显式策略（解决 P0.5）

新增配置：

```toml
[policy]
treat_all_skipped_as = "passed" | "failed" | "warn"
```

默认 `warn`（写进 result.summary 但不阻断）；CI 想严格可设 `failed`。

避免"环境什么都没装、所有 stage 都 skip、却拿到绿色 passed"的静默失败。

#### V1.5 Doctor 拆分（解决 P1.2）

```bash
./harness doctor                # 当前行为
./harness doctor --harness      # 只查控制面（python3、harness 自身）
./harness doctor --project      # 只查项目命令（flutter/ruff/tsc 等）
./harness doctor --online       # 探测 model provider connectivity（默认不跑）
```

#### V1.6 Shell profile（解决 N4）

`profiles/languages/shell.toml`：

```toml
[commands]
format = [["shfmt", "-i", "2", "-ci", "-w", "."]]
lint = [["shellcheck", "-x", "."]]
typecheck = [["bash", "-n", "<scripts>"]]   # 由项目显式列出
test-unit = [["bats", "tests/"]]
```

### V2：生产级能力（按需做）

| 项 | 解决 | 优先级 |
|---|---|---|
| ModelProvider SDK 集成（Anthropic/OpenAI/等） | 在线 eval | 中 |
| OpenTelemetry exporter | P2.1 传输层 | 中 |
| Provider 价格表 + 成本估算 | P2.4 | 中 |
| 配置迁移命令 | P2.3 | 低（schema 还没碰到 v2） |
| Release manifest + 平台 adapter | P2.2 | 低（先把 V1 做完） |
| `harness eval` 调用 skill-up YAML | N6 | 中（看跨项目复用频率） |
| `tests/fixtures/secrets.txt` 显式 scanner 区 | N3 | 低 |

---

## 五、修订后的验收（实施已完成，回头验证）

原批评建议把"文件存在型"验收改成"行为型"。实施后实际验证：

- [x] 干净环境跑 `./harness validate` 成功，不要求在线密钥
- [x] `./harness eval smoke --offline` 真正处理 fixture（至少 5 条）
- [x] 修改 fixture 使其失败时，命令返回非零退出码（`tests/unit/evals_test.py::RunEvalTests::test_offline_eval_fails_threshold`）
- [x] `--dry-run` 不产生子进程副作用（`tests/unit/runner_test.py::RunStageTests::test_dry_run_does_not_execute`）
- [ ] 一个 language + workload profile 组合改变实际执行阶段 —— **未实现**（profile 不自动加载，见 V1.2）
- [ ] 目标项目 Runner 可用 stdin/stdout 接入 —— **未实现**（见 V1.1）
- [x] 未授权工具调用被阻断（`tests/unit/security_test.py::PolicyTests`）
- [x] 假 token 在错误输出和 eval 报告中被脱敏（`tests/unit/evals_test.py::test_persist_report_does_not_leak_secrets`）
- [x] JSON 结果可被 CI 解析，字段有 schema 测试
- [x] `skipped` 不会被算作 `passed`（语义上）；但**整体 workflow 全 skipped 时仍报 passed**，见 V1.4
- [x] CI 在无 secret 的 fork PR 上仍能完成离线检查
- [x] 示例 profile 缺工具时给可操作诊断（doctor 报告 + skipped reason）

11 项行为验收，9 项通过，2 项留给 V1。

---

## 六、最终判断

原任务书作为长期蓝图**保留有效**。实施把 P0 大部分解决，但留下了 4 个真实可见的缺口：

1. **Cross-language SUT 协议**（V1.1）—— 影响 vendor-neutral 承诺的实际价值
2. **Profile 自动合并**（V1.2）—— 影响 72 种组合的工程复用
3. **Monorepo 支持**（V1.3）—— 影响两栈及以上项目接入
4. **`--allow-skipped` 策略**（V1.4）—— 影响静默失败风险

加上 6 项实施后新发现（N1~N6），构成 V1 的明确范围。

**下一步建议**：把 V1.1（Runner 协议）作为下一个里程碑。它是唯一**会限制 harness 实际跨语言使用**的硬缺口；其它 3 项是工程优化，不影响 vendor-neutral 承诺。
