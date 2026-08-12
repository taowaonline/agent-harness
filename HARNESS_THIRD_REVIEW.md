# Harness 第三轮评估报告

评估对象：当前仓库的 Harness 实现。

对照报告：

- [HARNESS_EVALUATION_AND_IMPROVEMENTS.md](./HARNESS_EVALUATION_AND_IMPROVEMENTS.md)
- [HARNESS_SECOND_REVIEW.md](./HARNESS_SECOND_REVIEW.md)

## 本轮结论

本轮没有发现新的代码提交，当前实现与第二轮基本一致。核心本地路径仍然可运行，但上一轮识别的跨机器复用、跳过门禁、真实 Runner、Profile 加载和预算控制问题仍未关闭。

当前评分保持：**7.8/10**。

定位上，当前版本可以称为：

> 单仓库、本机可运行的 Harness 控制面原型。

还不能称为：

> 可直接复制到不同项目、不同机器并作为可信发布门禁的通用 Harness。

## 本轮实际验证

```text
python3 -m unittest discover -s tests -p '*_test.py'
→ exit 0，测试通过

./harness validate --strict --json
→ exit 0，status=passed

./harness eval smoke --offline --json
→ exit 0，8/8 passed，pass_rate=1.0

./harness run release-check --json
→ exit 0，status=passed

git diff --check
→ 通过
```

这些结果证明当前仓库回归稳定；它们没有证明跨机器分发和未配置阶段的安全语义。

## 仍未关闭的阻断问题

### P0-1：入口仍绑定本机绝对路径

`harness` 入口中的 `_CANONICAL_HOME` 仍是本机路径：

```python
_CANONICAL_HOME = "/Users/tommacmini4/Documents/code/harness"
```

`init` 只复制入口脚本和 Schema，不复制 `src/agent_harness`，也不保证目标项目已安装 `agent-harness` 包。

后果是：

- 当前机器可以正常运行，其他机器不一定能启动。
- CI 的源码仓库运行可能正常，但 `harness init` 生成的目标项目不自洽。
- 目标项目不能只提交初始化产物后在干净环境复现。

改进要求：选择并实现一种正式分发方式：

1. 可安装 CLI：目标项目声明固定版本，`harness` 只是薄 wrapper。
2. Vendored CLI：初始化时复制完整 `src/agent_harness` 和必要元数据。
3. Monorepo 引用：明确目标项目必须位于 Harness 源码树内。

必须增加一个没有源仓库路径的隔离测试，不能只依赖当前用户目录运行成功。

### P0-2：`skipped` 的成功语义仍然危险

当前 `_status_to_rc` 把 `skipped` 转成成功退出码；工作流含有部分跳过阶段时，顶层仍可能为 `passed`。例如可选的 `typecheck` 没有配置时，工作流可能继续通过；未配置的 Eval 也可能被视为成功完成。

这与文档中的“skipped 不应静默 claim passed”相矛盾。

建议：

- 默认 `skipped` 返回非零的专用退出码，例如 10。
- 工作流含 skipped 时顶层状态至少为 skipped。
- 只有显式 `--allow-skipped` 才允许 exit 0。
- dry-run 可返回 0，但状态应是 `planned` 或 `skipped`，不能是 `passed`。

### P0-3：离线 Eval 仍是 Fixture Grader，不是目标程序 Eval

`evals.py` 的离线路径直接读取 Case 内的 `input.output` 或 `metadata.output`。这能验证 grader，但没有验证一个真实目标程序的输入、输出、退出码、超时和工具轨迹。

因此“跨语言”目前只体现在命令 argv 可以写成不同语言的命令，不体现在 Eval Runner 协议上。

最低改进：支持配置一个语言无关的 Runner argv：

```toml
[evals.smoke]
dataset = "evals/datasets/smoke.example.jsonl"
runner = ["python3", "tests/fixtures/fake_provider.py"]
timeout_seconds = 120
```

Runner 使用 JSONL stdin/stdout：一行输入 Case，一行输出 Result；非零退出、超时和 malformed JSON 必须进入结构化报告。

## 重要但非阻断问题

### P1-1：Profiles 仍未接入运行时

`profiles/languages`、`profiles/workloads`、`profiles/risk` 当前是模板文件，代码没有加载、继承或合并逻辑。把 `language = "go"` 改成 `language = "python"` 不会自动改变 commands。

必须明确：

- 如果 Profiles 只是示例模板，就在 README 标记为 `[template]`。
- 如果是运行时适配器，就实现 `extends`、加载顺序、覆盖规则和来源追踪。

### P1-2：`--strict` 没有区别

CLI 注册了 `validate --strict`，但验证器没有 warnings 集合，也没有根据 `args.strict` 改变行为。当前 CI 使用这个参数，实际并未获得额外门禁。

应实现 warnings/strict，或删除该参数。

### P1-3：Eval 限制字段还只是报告字段

以下配置目前被解析或展示，但没有完整执行语义：

- `timeout_seconds`
- `max_cost_usd`
- `repetitions`
- `max_regression`

尤其是 baseline compare 没有读取 `max_regression`，任何正回退都可能失败，配置中的允许回退值不起作用。

### P1-4：Schema 与实现不一致

JSON Schema 要求 command 数组 `minItems: 1`，Python 实现却允许 `typecheck = []` 并将其解释为 skipped。需要统一为：

- Schema 允许空数组；或
- 改成显式 `disabled` 字段。

### P1-5：相对路径按 cwd 而非配置根解析

使用 `--config` 指向其他目录时，数据集、报告和安全扫描仍依赖当前 cwd。应以配置文件所在目录作为项目根，并增加从仓库外 cwd 调用的测试。

### P1-6：报告文件名秒级，存在覆盖风险

报告文件名由 Eval 名称和秒级时间戳组成，同一秒运行两次可能覆盖之前的报告。应加入 `run_id` 或毫秒精度，并采用临时文件原子写入。

### P1-7：安全扫描工具缺失时 CI 仍成功

gitleaks、pip-audit 等工具未安装时 Workflow 只输出 notice。prototype 可以接受，standard/high-risk 不应默认接受。应按 risk profile 决定缺失工具是 notice、warning 还是 blocked。

## 需要新增的回归测试

下一次修改后，至少新增这些测试：

- 复制入口到临时目录、移除源代码路径后仍可执行 `--help`。
- `init` 生成的项目在干净环境中可运行。
- 一个纯 skipped workflow 不会返回 passed/exit 0。
- 一个部分 skipped workflow 不会伪装成 passed。
- Eval 没有 runner 或 fixture 时返回明确的 skipped/blocked 语义。
- Runner 子进程 timeout 会阻断并记录原因。
- `max_regression = 0.02` 允许 0.01 回退但阻断 0.03 回退。
- `repetitions = 3` 实际执行三次并报告聚合结果。
- `--strict` 与普通 `validate` 的行为可观察地区分。
- 从非项目 cwd 使用 `--config` 时数据集路径正确。
- Schema 对空 command 的判断与 Python 解析器一致。

## 下一步顺序

```text
1. 先修复分发入口
2. 再修复 skipped/exit code 门禁
3. 加入真实 Runner 协议
4. 明确 Profiles 是模板还是运行时适配器
5. 实现 timeout/cost/repetitions/max_regression
6. 修复 strict、Schema 和路径解析
7. 最后再扩展 OTel、工具轨迹和生产发布适配
```

## 最终判断

当前实现已经足够作为 Harness 原型和单仓库开发工具继续迭代；但在 P0 问题关闭前，不建议：

- 把它复制给其他项目直接使用。
- 把 `release-check` 当作可信生产发布门禁。
- 宣称已支持跨语言 AI 应用 Eval。
- 将当前 `passed` 结果直接作为安全或质量证明。

