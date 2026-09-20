# 工作流：中文全文翻译

## 目标

依据本地 `source.pdf` 生成结构完整、术语一致、可直接阅读且可复核的中文全文译文。

## 成功标准

- 开工前运行 `make source-check PAPER_ID=<paper-id>`；缺少原文或身份/可读性门禁失败时停止，按 [原文验证闭环](ingest.md#原文验证闭环) 和 [状态与文件](metadata.md#状态与文件) 处理，不把失败文件当作可译原文。
- 页数超限时停止翻译并报告。单篇译者不修改共享策略或状态；由 maintain workflow 同步受控 `skip_reason` 与 `source_only -> skipped`。只有用户显式授权后，维护者才能在 `config/policy.yaml` 为单篇记录更高上限和授权依据。
- 开始形成译文后使用 `draft`。
- `translation.md` 以 `templates/translation.md` 的 YAML frontmatter 开头；`paper_id` 与目录名一致，`title` 与 `paper.yaml` 一致，`language` 固定为 `zh-CN`，`source` 固定为 `source.pdf`。
- 译文及资源满足 [translation policy](../translation-policy.md) 的内容、结构与呈现要求。
- 翻译者完成草稿自检并交付审阅材料；批次中的翻译子代理运行 `make paper-check PAPER_ID=<paper-id>`，仓库级门禁由根代理负责。
- 完整处理新论文时，根代理继续安排 review workflow；审阅通过后更新状态并重新运行单篇门禁，再执行 `docs/workflows/rating.md`、重建目录和最终仓库级门禁。

## 约束

翻译阶段只拥有 `source_only -> draft` 和论文目录内的译文资产；翻译子代理
交付 `draft` 不表示完整任务结束。用户要求完整处理新论文时，根代理已有继续
安排独立审阅、按审阅结果更新为 `translated`、评分和重建目录的授权，无需在
工作流切换时重新确认。用户只要求草稿时交付 `draft`；不得把草稿完成误报为
`translated`。提交和发布仍遵循任务已有的授权范围。

## 交审前自检

1. 对照 policy 的 [内容与语义](../translation-policy.md#内容与语义)，完成源文与译文双向对照。
2. 对照 [结构与读者呈现](../translation-policy.md#结构与读者呈现) 和 [公式语法](../translation-policy.md#可移植公式语法)，检查资源、编号、引用及顺序。
3. 按 [核源与呈现核验](../translation-policy.md#核源与呈现核验) 处理字形、原文疑点和实际页面显示，不把疑点默认交给下一阶段。
4. 完成下列门禁，交付 paper ID、实际修改、源文定位、检查结果、已处置告警和未决证据。后续进入 [审阅工作流](review.md)。

## 格式与公式门禁

本节也供 review 中的译文修复复用；检查对象为最后一次修改后的译文。

送独立审阅前，对本篇完成格式和公式检查，避免审阅后再返工：

```bash
.venv/bin/python scripts/normalize_translation_headers.py --check --paper-id <paper-id>
paper_whitespace=$(git diff --no-index --check /dev/null papers/<area>/<paper-id>/translation.md 2>&1 || true)
test -z "$paper_whitespace" || { printf '%s\n' "$paper_whitespace"; exit 1; }
make paper-check PAPER_ID=<paper-id>
make math-check-files FILES='papers/<area>/<paper-id>/translation.md'
make math-audit-github FILES='papers/<area>/<paper-id>/translation.md'
```

首条检查也会检查 EOF 空行；目前报错可能统称 header 不规范，先查看实际差异。
空白检查沿用 `scripts/check_diff.sh` 对未跟踪文件的处理：检查诊断输出，不把
`git diff --no-index` 仅表示存在差异的退出码 1 当成空白错误。
不要盲目运行全库规范化。显式换行可用 `<br>`，避免双空格行尾触发 whitespace
门禁。单篇检查只处理本篇；根代理保留最终仓库级门禁，不让并行中的其他草稿
阻塞本篇交审。已通过的检查只因后续改动影响其检查对象、失败或具体疑点而重跑。

状态按 [元数据工作流](metadata.md#状态与文件) 管理。草稿中尚未解决的缺口必须随交审材料交付；告警按 [审阅工作流](review.md#告警处置) 核源，不隐藏标记或调低阈值来让草稿通过。

## 停止条件

翻译阶段在草稿自检和交审材料完成时结束；根代理按用户要求继续后续流程。
出现无法可靠读取的内容、缺失原文、页数超限或范围外依赖时，报告具体阻塞和
受影响论文。未通过审阅时保留 `draft`，不猜测完成；批次中不受阻塞影响的论文
可继续处理。
