# 当前 Harness 改动质量完整评估（第二次复评）

> 本文已于 2026-08-10 对 `HEAD=33dac33` 重新评估。第 11 节为本次复评的最新结论，并覆盖前一轮对 R1/R2/R3 的旧结论。

## 1. 评估结论

**第二次复评结论：R1（check 覆盖）和 R3（标准风险安全扫描）已完成修复；R2（成本控制）已具备显式 enforcement 机制，但本仓库默认配置仍因没有 runner 而处于 advisory 状态。当前版本质量明显提升，可以合并，但仍不能把离线 eval 解释为真实模型生产质量。**

本次复评针对当前工作树 `HEAD=33dac33` 进行。工作树在评估开始时干净，因此本文评估的是从初始实现 `7bd4b35` 到当前 `HEAD` 的累计改动质量，而不是某个未提交 diff。

建议评级：**A-（可合并，存在已明确且可控的能力边界）**。

| 维度 | 结论 | 说明 |
|---|---|---|
| 功能正确性 | 通过 | `validate`、串行 `check`、`release-check`、156 个单元/集成测试均通过 |
| 离线评测 | 通过 | smoke 8/8，full 10/10，均无 failed/skipped/error |
| 回归控制 | 通过 | 与当前 baseline 的 pass-rate delta 为 0，regression 为 0 |
| CLI/结果语义 | 通过 | skipped、failed、dry-run、退出码及 JSON 结果有专项回归覆盖 |
| 安全基础能力 | 通过但有限 | argv 执行、脱敏、allowlist、审批策略、内置扫描有覆盖 |
| 质量门禁完整性 | 通过 | 默认 `check` 已执行 Ruff format/check、Pyright 和 unit tests |
| 成本控制 | 部分通过 | 已支持显式 `enforce_max_cost`，本仓库无 runner 时仍明确告警为 advisory |
| 真实 AI 行为验证 | 未覆盖 | 本次 full/smoke 为离线 fixture eval，不验证真实模型/provider |

## 2. 评估范围与验收标准

### 2.1 范围

覆盖以下累计改动区域：

- CLI 稳定命令、JSON 输出、退出码、`--dry-run` 与 `--allow-skipped`；
- 配置加载、profile `extends`、项目根目录解析、schema 对齐；
- runner 的 argv-only 执行、超时、fail-fast、工作流和跳过语义；
- eval dataset、subprocess runner、grader、重复执行、阈值和 baseline compare；
- secret redaction、tool allowlist、审批策略、风险感知扫描与 `scan_exclude`；
- CI/security workflow、示例 profile、单元/集成测试及离线评测。

### 2.2 验收标准

本评估采用以下可验证标准：

1. 配置与数据集可验证，且错误能以失败状态和非零退出码暴露；
2. 代码执行不使用 `shell=True`，命令以 argv 数组传递；
3. `passed`、`failed`、`skipped`、`blocked` 的状态和退出码一致；
4. dry-run 不产生实际副作用，跳过不被静默当成通过；
5. eval runner 的 malformed JSON、case ID、行数、超时和非零退出均阻断评测；
6. 离线 smoke/full 达到配置阈值，baseline compare 不产生回归；
7. 安全策略、敏感信息脱敏和风险等级行为有测试证据；
8. 对未实现能力、未执行工具和测试边界必须明确标注，不能将 advisory/skipped 描述为 passed。

## 3. 代码与架构评估

### 3.1 做得较好的部分

#### CLI 契约和结果语义清晰

`./harness list` 暴露稳定 stage/workflow 名称，`doctor`、`validate`、`run`、`eval`、`baseline compare` 等命令职责清楚。当前实现对 skipped 语义进行了较完整的收紧：

- dry-run 顶层状态为 `skipped`；
- workflow 中出现 partial skip 时顶层不会伪装为 `passed`；
- failed 优先级高于 skipped；
- 默认遇到 skipped 返回专用非零码，只有显式 `--allow-skipped` 才允许返回 0。

这些行为由 `tests/unit/skipped_semantics_test.py`、`tests/integration/cli_test.py` 及 runner 测试覆盖，属于本轮改动中最有价值的质量提升之一。

#### 配置边界和项目根目录处理得到增强

配置支持严格字段校验、profile 合并、未知 profile 拒绝和从非项目 cwd 调用时的数据集路径解析。`tests/unit/profile_loader_test.py` 和 `tests/unit/project_root_test.py` 对这些边界有直接覆盖，降低了“在仓库目录能运行、从 CI/外部目录不能运行”的风险。

#### subprocess runner 协议防御充分

runner 使用 argv 数组并显式 `shell=False`，同时对以下异常进行硬失败处理：

- executable 不存在或执行时消失；
- subprocess 超时或返回非零；
- stdout 行数与输入 case 数不一致；
- JSON malformed；
- 缺少字符串 `case_id`；
- case 顺序或 ID 不匹配。

这部分不仅有实现，也有 `runner_protocol_test.py` 和 `sixth_review_regression_test.py` 的回归锁定，能够防止评测结果因 runner 输出损坏而被错误解释。

#### 安全与隐私默认值合理

当前配置默认开启 input/output redaction，报告写入前再次进行脱敏，并使用临时文件加 `os.replace` 原子写入。allowlist、approval gate、敏感环境变量和多类 token 格式均有测试。最新 key=value regex 调整还避免了把普通源码赋值误报为 secret，同时保留真实 secret 的捕获能力。

#### 变更后的测试可维护性较好

本轮增加的测试不是单纯 happy path，包含项目根目录、风险等级、扫描排除、报告原子性、状态一致性、runner 协议和初始化分发等回归场景。全量测试共 162 个，实际运行全部通过。

## 4. 实测证据

评估时间：2026-08-10（Asia/Shanghai）；报告中的 UTC 时间由 harness 自动生成。

### 4.1 仓库规定的质量门禁

| 命令 | 结果 | 关键证据 |
|---|---|---|
| `./harness validate` | 通过（带 advisory warning） | 配置、workflow、dataset 可加载；两个 `max_cost_usd` 为 `PLANNED` 警告 |
| `./harness run check` | 通过 | `lint` 通过，`test-unit` 通过 |
| `./harness eval smoke --offline` | 通过 | 8/8，pass rate 1.0，skipped 0，failed 0 |
| `./harness eval full --offline` | 通过 | 10/10，pass rate 1.0，skipped 0，failed 0 |
| `./harness baseline compare evals/baselines/latest.json evals/reports/full-20260810T033207Z-e903de7d.json` | 通过 | delta 0.0，regression 0.0，verdict `unchanged` |
| `./harness run release-check --json` | 通过 | check、integration、full、security 全部通过 |
| `python3 -m unittest discover -s tests -p '*_test.py' -v` | 通过 | Ran 162 tests；OK |

最新 full 报告：[`evals/reports/full-20260810T033207Z-e903de7d.json`](evals/reports/full-20260810T033207Z-e903de7d.json)。该报告记录 git SHA `8ecbd02`，因此与本次评估对象一致。

### 4.2 环境和工具链边界

`./harness doctor --json` 显示：

- 必需的 `python3`、`git` 可用；
- 当前项目配置的 command 均可解析；
- smoke 数据集 8 cases、full 数据集 10 cases 均可加载；
- `ruff` 不可用，`pyright` 不可用；
- `pytest`、`uv`、`node` 可用，但没有被当前 `harness.toml` 的核心检查使用。

因此，本文将 `check` 描述为“当前配置下通过”，不会将它升级描述为“已通过 Ruff lint 和 Pyright typecheck”。

## 5. 主要风险与缺口

### R1：默认 `check` 工作流没有覆盖所有声明的质量阶段（中风险）

证据：[`harness.toml`](harness.toml) 中定义了 `format`、`lint`、`typecheck`、`test-unit`、`test-integration`，但 `check` 只执行 `lint` 和 `test-unit`。`typecheck = []` 也意味着类型检查当前明确未配置。

影响：开发者执行最常用的 `./harness run check` 时，不会得到格式化检查、类型检查或集成测试结果；若 CI 只复用 check，也可能形成质量门禁盲区。

建议：

1. 将 `check` 明确拆成 PR 快速检查和完整检查，或至少将真正需要的 format/typecheck 纳入；
2. 若 format/typecheck 允许为空，输出必须在 workflow 摘要中显式展示为 skipped 并由策略决定是否阻断；
3. 把 `format` 当前指向的 unittest 命令改成实际格式化工具，或将 stage 改名避免语义误导；
4. 对 Python 项目固定安装并执行 Ruff/formatter/type checker，避免“工具缺失但核心检查仍通过”的误判。

### R2：`max_cost_usd` 当前只是声明性字段（中风险）

`validate` 已正确发出 `PLANNED` 警告，说明实现没有把未执行的成本控制伪装成已执行。但 `harness.toml` 仍配置了 smoke `$2`、full `$50` 上限，普通使用者容易把阈值字段误解为硬门禁。

影响：接入真实 provider 后，若没有额外成本计量适配器，超预算不会被 harness 阻断。

建议：在 provider/result contract 中引入 tokens、price snapshot、currency 和 cost 字段；成本计算失败时对 high-risk/release workflow 默认 block；在此之前可考虑把字段命名为 `planned_max_cost_usd` 或要求显式 `enforce_cost = true`。

### R3：标准风险下外部安全扫描缺失只产生 warning（中风险）

内置 `security` check 当前通过，且高风险 workflow 对缺失 gitleaks/pip-audit 有阻断策略。但 `.github/workflows/security.yml` 对 standard risk 的外部扫描缺失是 warning，CI 仍可成功。

影响：当前项目虽有内置扫描和安全策略测试，但并没有证明 gitleaks 或 dependency audit 在 CI 中实际运行；第三方扫描覆盖范围不足时，标准风险项目仍可能合并。

建议：根据项目风险承诺选择其一：

- standard 也安装并强制执行固定版本扫描器；或
- 在合并门禁中把“缺少外部扫描器”升级为 failed，并对 prototype 单独保留 advisory；
- 对 `pip-audit` 使用可复现版本约束，减少动态安装带来的供应链不确定性。

### R4：离线 eval 不能证明真实模型行为（中风险，当前可接受）

smoke/full 使用仓库内 example dataset 的 fixture output，结果稳定且适合验证 harness 自身的 dataset/grader/threshold 协议；但它们不会调用真实模型，也不覆盖真实 prompt、工具调用、网络失败、token/cost、模型漂移或在线延迟。

因此“full 10/10”应准确解释为“离线回归协议 10/10”，不能解释为“AI 应用线上质量 10/10”。发布真实 AI 应用前仍需要脱敏 golden samples、provider runner、在线/回放 eval 和成本/延迟阈值。

### R5：baseline 内容与当前版本不完全同源（低风险）

`evals/baselines/latest.json` 的 git SHA 是 `9b3d25c`，当前新报告 SHA 是 `8ecbd02`。两者 pass rate 都是 1.0，因此 compare 得到 `unchanged`；但 baseline 的 case 结果与当前报告的可比性主要依赖相同 dataset/schema，不能替代“当前版本生成并审核过的 baseline”。

建议在发布流程中明确 baseline 更新审批，并在 baseline metadata 中记录 dataset revision、grader revision 和生成命令。

## 6. 分层质量评分

| 类别 | 评分 | 评语 |
|---|---:|---|
| 架构边界 | 8.5/10 | 控制面、adapter/profile、dataset/eval、security 分层清楚 |
| CLI 与结果契约 | 9/10 | JSON、退出码、skipped/failed 语义和 dry-run 覆盖较强 |
| 配置与可分发性 | 8.5/10 | profile、项目根目录和 vendor 初始化有回归；全局安装模型仍需文档化落地 |
| 测试质量 | 9/10 | 162 tests，边界和回归场景丰富；缺少真实第三方工具组合测试 |
| 安全与隐私 | 8/10 | 默认策略和脱敏扎实；外部扫描与标准风险门禁仍非强制 |
| Eval 能力 | 8/10 | 离线协议完整；真实 provider、成本和在线行为未闭环 |
| CI 门禁 | 7/10 | release-check 较完整，但默认 check 和工具可用性存在覆盖/解释差异 |
| 文档与可操作性 | 8/10 | README/architecture/评审文档较充分；应进一步标出 planned 与 enforced 的区别 |

**综合评分：8.25/10。** 该分数反映“当前实现质量较好但能力边界明确”，不是线上 AI 应用可靠性的承诺。

## 7. 是否建议合并

**建议：可以合并当前累计改动，但建议在发布/生产使用前完成 R1、R2、R3。**

合并理由：

- 当前工作树干净，核心测试和 release-check 全部通过；
- 新增回归测试覆盖了此前最容易出现的状态伪通过、runner 协议损坏、路径漂移、secret redaction 和风险策略问题；
- 未发现 P0/P1 级别的已证实功能错误；
- 已实现的缺口多数被代码通过 warning、skipped 或显式 policy 表达，没有被静默伪装为 passed。

合并限制：

- 不应把当前结果写成“完整 lint/typecheck 已通过”；
- 不应把离线 full 结果写成“真实模型/生产 AI 行为通过”；
- 不应把 `max_cost_usd` 写成已执行的成本硬阈值；
- standard risk 外部扫描缺失的 warning 需要在发布说明中保留。

## 8. 推荐后续顺序

1. **先修 R1：** 明确 `check`、`format`、`typecheck`、integration 的门禁层级和语义；
2. **再修 R2：** 接入 provider 成本统计，或者删除/改名当前未执行的成本字段；
3. **再修 R3：** 固定并强制标准风险的 gitleaks 与 dependency audit；
4. **补充真实 provider eval：** 保留离线 eval 作为协议回归，同时加入脱敏真实样本和可控 runner；
5. **刷新 baseline：** 以当前 SHA、dataset/grader revision 和审批记录生成新的 baseline；
6. **发布前复核：** 对高风险 profile 实际运行一次缺失 scanner、secret hit、approval gate 和 rollback 场景。

## 9. 证据索引

- 项目契约：[`AGENTS.md`](AGENTS.md)
- 项目说明：[`README.md`](README.md)
- 架构说明：[`docs/architecture.md`](docs/architecture.md)
- 当前配置：[`harness.toml`](harness.toml)
- 评测说明：[`evals/README.md`](evals/README.md)
- 评测配置：[`evals/eval.yaml`](evals/eval.yaml)
- 变更前后评审材料：[`HARNESS_FIFTH_REVIEW.md`](HARNESS_FIFTH_REVIEW.md)、[`HARNESS_SIXTH_REVIEW.md`](HARNESS_SIXTH_REVIEW.md)
- 当前 full 报告：[`evals/reports/full-20260810T033207Z-e903de7d.json`](evals/reports/full-20260810T033207Z-e903de7d.json)

## 10. 验收记录

- [x] 已读取仓库契约、README、架构说明、评测说明和覆盖相关区域的测试；
- [x] 已审查当前累计改动范围和工作树状态；
- [x] 已执行 `./harness validate`；
- [x] 已执行 `./harness run check`；
- [x] 已执行 `./harness eval smoke --offline`；
- [x] 已执行 `./harness eval full --offline`；
- [x] 已执行 baseline compare；
- [x] 已执行 `./harness run release-check --json`；
- [x] 已执行全量 unittest，共 162 个测试；
- [x] 文稿明确记录 passed、warning、未配置工具和离线评测边界；
- [ ] R1/R2/R3 尚未在本次任务中实施，属于后续改进项。

## 11. 第二次复评实测记录（2026-08-10）

> 本节为最新复评结果，覆盖并修正上文基于 `8ecbd02` 的旧状态描述。

### 11.1 新版本变更核对

当前版本为 `33dac33`。相对上一轮 `8ecbd02`，关键变化为：

- `220dc97`：将 format、Ruff lint、Pyright typecheck 纳入默认 `check`；
- `0e2149d`：增加 `enforce_max_cost` 与成本超限测试；
- `a4ee464`：standard risk 缺少 gitleaks/pip-audit 时改为阻断；
- `33dac33`：重新生成当前 SHA baseline，并修复 Ruff format drift。

### 11.2 本轮命令结果

| 命令 | 结果 | 证据 |
|---|---|---|
| `./harness doctor --json` | 通过 | ruff、pyright、pytest、uv、node 均可用，所有声明 command 可解析 |
| `./harness validate` | 通过（2 条 advisory） | smoke/full 无 runner，因此 max cost 明确为 `PLANNED (not enforced)` |
| `./harness run check --json` | 串行通过 | format、lint、typecheck、test-unit 全部 passed |
| `./harness eval smoke --offline --json` | 通过 | 8/8，pass rate 1.0，skipped 0 |
| `./harness eval full --offline --json` | 通过 | 10/10，pass rate 1.0，skipped 0 |
| `./harness baseline compare ...` | 通过 | pass-rate delta 0.0，regression 0.0，verdict `unchanged` |
| `./harness run release-check --json` | 串行通过 | check、integration、full、security 全部 passed |
| `python3 -m unittest discover -s tests/unit -p '*_test.py' -v` | 通过 | 156 tests；OK |

本次复评 full 报告为 [`evals/reports/full-20260810T042056Z-9d6fc3e4.json`](evals/reports/full-20260810T042056Z-9d6fc3e4.json)，记录 git SHA `33dac33`。

### 11.3 并发执行观察

首次将多个会读写 `evals/reports/` 的命令并行启动时，`check`/`release-check` 中的 unit stage 曾返回失败；随后单独运行 unit、再串行运行 `check` 和 `release-check` 均通过。当前没有足够证据认定为代码确定性缺陷，但这表明多个 harness 进程共享生成报告目录时应避免并发，或后续增加并发隔离/锁机制和对应回归测试。

该观察不影响本次串行门禁结论，但属于可维护性风险；评估报告生成目录应在并发场景下具备进程级隔离能力。

### 11.4 复评最终结论

**当前 `33dac33` 串行质量门禁通过，R1/R3 已验证修复，R2 已从“完全未实现”提升为显式可配置 enforcement；剩余主要限制是本仓库没有真实 provider runner，因此成本 enforcement 和真实 AI 行为仍未在仓库自身评估中生效。**

最新建议：可以合并；接入真实 provider 前，补充 `cost_usd` 端到端超预算阻断测试，并处理评测报告目录的并发隔离问题。

## 12. 第三次复评实测记录（2026-08-10）

> 本节为当前最新复评结果，覆盖第 11 节中关于成本端到端测试和报告并发隔离的后续项。

### 12.1 当前版本

当前 `HEAD=e5f4c70`。评估开始时无代码改动；当前工作树仅包含本次更新的评估文稿。本轮新增提交主题为：`Address §11.3 + §11.4: cost_usd e2e tests + concurrent report isolation`。

### 12.2 命令与证据

| 命令 | 结果 | 证据 |
|---|---|---|
| `./harness doctor --json` | 通过 | ruff、pyright、pytest、uv、node 可用；所有声明 command 可解析 |
| `./harness validate` | 通过（2 条 advisory） | 当前仓库 smoke/full 没有 runner，成本字段明确显示 `PLANNED (not enforced)` |
| `./harness run check --json` | 通过 | Ruff format、Ruff lint、Pyright、unit tests 全部通过 |
| `./harness eval smoke --offline --json` | 通过 | 8/8，pass rate 1.0，skipped 0，failed 0 |
| `./harness eval full --offline --json` | 通过 | 10/10，pass rate 1.0，skipped 0，failed 0 |
| `./harness baseline compare evals/baselines/latest.json <latest-full>` | 通过 | pass-rate delta 0.0，regression 0.0，verdict `unchanged` |
| `./harness run release-check --json` | 通过 | check、integration、full、security 全部 passed |
| `python3 -m unittest discover -s tests -p '*_test.py' -q` | 通过 | 172 tests；OK |

本轮 full 报告为 [`evals/reports/full-20260810T044608Z-4aafedb8.json`](evals/reports/full-20260810T044608Z-4aafedb8.json)，记录当前 SHA `e5f4c70`。

### 12.3 对上一轮遗留项的验证

- 成本控制：新增的 `cost_usd` runner 端到端测试已进入全量测试并通过，证明 enforcement 路径可被触发；当前仓库自身仍没有配置真实 runner，所以 `validate` 保留 advisory 是正确语义。
- 并发报告：新增并发报告隔离测试已进入全量测试并通过；本轮所有会写 `evals/reports/` 的命令均串行执行，未再出现上一轮的暂时性 unit failure。
- 门禁覆盖：format、lint、typecheck、unit、integration、offline eval、security 均有本轮通过证据。

### 12.4 第三次复评结论

**当前 `e5f4c70` 的串行质量门禁全部通过，上一轮已识别的 R1、R2、R3 及报告并发隔离问题均已有实现或测试证据。建议评级提升为 A；仍需在真实 provider 接入后补做在线模型行为、真实成本计量和第三方 scanner 的环境级验证。**

本轮文稿验收：

- [x] 重新核对最新 commit 与工作树；
- [x] 串行执行 doctor、validate、check、smoke、full、baseline compare、release-check；
- [x] 执行全量 172 tests；
- [x] 更新最新 full 报告路径、SHA、测试数量和剩余边界；
- [ ] 未执行真实 model provider eval、真实 gitleaks/pip-audit 下载执行和线上成本计量。
