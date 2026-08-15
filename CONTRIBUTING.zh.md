# 贡献指南

[English](CONTRIBUTING.md) | 中文

感谢帮助改进 harness。先读 [AGENTS.md](AGENTS.md)——它是任何贡献者（人类或
模型辅助）的约束契约。

## 完成标准（Definition of Done）

一项改动只有满足以下全部条件才算完成：

1. 验收标准已满足且可演示。
2. 相关文档与决策记录（`docs/notes/`）已更新。
3. 格式化、Lint、类型检查和相关测试通过。
4. AI 行为变更已新增或更新评测样本。
5. 没有未说明的质量、成本或延迟回退。
6. 没有泄漏秘密，也没有扩大工具权限。
7. 可观测性足以在生产中定位失败。
8. 发布与回滚路径明确。

如果某条无法满足，在 PR 里明确说明，不要近似完成。

## 工作流

1. 认领或新建 Issue，并在 PR 描述中链接。
2. 从 `main` 拉分支，保持 diff 小而可审查。
3. 本地运行 `./agent_harness validate` 和 `./agent_harness run check`。
4. 使用 `.github/pull_request_template.md` 开 PR。
5. 在评审意见处逐条回复。除非被要求，不要 force-push 评审者正在读的历史。
6. 合并前必需的 CI 检查必须全绿（或显式豁免）。

## 分支保护与必需检查

对 `main` 推荐的分支保护：

- 合并前要求 pull request。
- 合并前要求以下状态检查通过：
  - `harness checks`（来自 `ci.yml`）
  - `secret scanning`（来自 `security.yml`）
- 合并前要求分支是最新的。
- 有新提交时撤销过期的批准。
- 限制 force-push 和删除。

禁止使用会导致必需检查永远 Pending 的路径过滤——每个 PR 的每个必需检查
都必须产生终态。

## 沟通规范

- 优先书面异步沟通，而非实时打断。
- 区分事实（测试结果、评测报告）与观点。
- 有建设性地表达分歧：提出替代方案，而不是只投否决票。

## 双语文档

`README.md` / `README.zh.md`、`CONTRIBUTING.md` / `CONTRIBUTING.zh.md`
成对维护：改了英文版就要在同一个 PR 里更新中文版（反之亦然），由
`verify-bilingual-pairs` 测试在 CI 强制。段落不必逐字对应，但事实、命令和
表格行必须一致。
