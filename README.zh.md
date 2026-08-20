# AI Development Harness（agent_harness）

[English](README.md) | 中文

面向 AI 辅助软件开发与 AI 应用生命周期管理的**厂商中立、语言无关控制面**。

无论目标语言、模型供应商或 AI 框架是什么，harness 给每个项目一个稳定的入口：

```
需求 / 验收标准
  -> Agent 获取受控上下文
  -> 规划与小步实现
  -> 格式化、静态检查、类型检查、测试
  -> AI smoke eval、完整回归、对抗评测
  -> PR 门禁与人工评审
  -> 灰度发布与回滚
  -> 线上 Trace 回流为新回归样本
```

## 为什么需要它

两类工作通常被当成不相干的事：

1. **AI 辅助软件开发** —— 让编码 Agent 理解项目、规划修改、执行检查、提交可审查的变更。
2. **AI 应用生命周期** —— 管理 Prompt、模型、工具、数据集、评测、Tracing、安全门禁和发布回滚。

本 harness 把两者统一到一组命令后面，让*使用* AI 的项目也能*用* AI 开发，不用同时维护两套工具链。

## 稳定命令面

| 命令 | 含义 |
|---|---|
| `doctor` | 检查 Harness、配置和项目工具链是否可用 |
| `validate` | 校验配置、数据集和策略文件 |
| `list` | 显示阶段、工作流和配置来源 |
| `run <stage-or-workflow>` | 运行一个阶段或工作流 |
| `run <...> --dry-run` | 只打印将执行的阶段和安全转义后的 argv，不执行 |
| `run <...> --json` | 输出稳定的机器可读结果 |
| `eval <smoke\|full> --offline` | 离线确定性评测（replay 模式别名） |
| `eval <...> --snapshot-mode diff` | 跑 runner 并与录制的 fixture 逐例对比，不写数据集 |
| `eval <...> --snapshot-mode record` | 跑 runner 并把输出写回数据集作为 fixture |
| `gen-schema` / `verify-schema` | 从 config.py 生成 / 校验 harness.schema.json |

阶段名映射到各语言的具体工具（Ruff、ESLint、`tsc`、`go vet`、Clippy、
`dotnet format`……），但**命令名和结果语义保持稳定**。

完整心智模型见 `docs/architecture.md` 与 `docs/development-workflow.md`。

## 快速开始

```bash
./agent_harness doctor
./agent_harness validate
./agent_harness list
./agent_harness run check --dry-run
./agent_harness run check
./agent_harness eval smoke --offline
```

控制面只用 Python 3.11+ 标准库实现——零运行时第三方依赖。测试用内置
`unittest` 运行。

## 以 Agent Skill 形式安装（npm）

以
[`@taowaonline/agent-harness`](https://www.npmjs.com/package/@taowaonline/agent-harness)
分发——一个包，覆盖所有编码 Agent CLI：

```bash
npm install -g @taowaonline/agent-harness
agent-harness-setup            # 把 skill 接入各个 CLI
agent-harness-setup --list     # 查看全部目标
```

| 目标 | 标志 | 安装位置 |
|---|---|---|
| Claude Code | `--claude` | `~/.claude/skills/agent_harness` |
| Z.ai ZCode | `--zcode` | `~/.zcode/skills/agent_harness` |
| Kimi Code CLI | `--kimi` | `~/.kimi-code/skills/agent_harness` |
| 跨工具共享目录 | `--agents-shared` | `~/.agents/skills/agent_harness` |
| Deep Code | `--deepcode` | `~/.deepcode/skills/agent_harness`（尽力而为） |
| Codex | `--codex` | `~/.codex/AGENTS.md` 托管块 |
| Cursor | `--cursor --project <目录>` | `.cursor/rules/agent-harness.mdc` |

SKILL.md 目标是指向安装包的符号链接，`npm update -g` 后即时生效、无需重跑。
Python CLI 需要 Python 3.11+（仅标准库）。卸载用
`agent-harness-setup --uninstall`。

## 目录

- `agent_harness` —— 可执行入口
- `harness.toml` —— 本仓库自身配置
- `harness.schema.json` —— 配置契约（由 `gen-schema` 从 config.py 生成）
- `src/agent_harness/` —— 控制面实现
- `tests/` —— 单元、集成与 fixture 驱动测试
- `evals/` —— 数据集、评分器、基线与生成报告
- `profiles/` —— 语言 / 工作负载 / 风险等级的可复制覆盖片段
- `prompts/` —— Prompt manifest 示例
- `docs/` —— 架构、安全模型、观测、发布策略、评测策略、测试策略、复盘、决策日志
- `examples/` —— 跨语言参考项目
- `.github/` —— CI、评测与安全 workflow 及模板

## 设计原则

1. **稳定内核，可替换适配器。** CLI 契约不依赖任何目标语言、模型供应商或 AI 框架。
2. **无意外副作用。** 外部命令一律 argv 数组；绝不 `shell=True`；高风险写入需要显式人工批准门禁。
3. **可复现。** Prompt、工具、模型、数据集、评分器、阈值全部版本化。离线 fixture 产生稳定结果。
4. **渐进式采用。** 没有模型密钥时，`doctor`、`validate`、harness 自测与离线评测照常运行。
   未配置的可选阶段如实报告 `skipped` 及原因——绝不静默当作 `passed`。

## 状态

参考实现骨架，持续迭代中。设计取舍见 `docs/adr/` 与 `docs/notes/`。
