# 工作流：中文全文翻译

## 目标

依据本地 `source.pdf` 生成结构完整、术语一致、可直接阅读且可复核的中文全文译文。

## 成功标准

- 开工前运行 `make source-check PAPER_ID=<paper-id>`；缺少原文或身份/可读性门禁失败时保持 `unavailable` 并停止。
- 页数超限时停止翻译并报告。单篇译者不修改共享策略或状态；由 maintain workflow 同步受控 `skip_reason` 与 `source_only -> skipped`。只有用户显式授权后，维护者才能在 `config/policy.yaml` 为单篇记录更高上限和授权依据。
- 开始形成译文后使用 `draft`。
- `translation.md` 以 `templates/translation.md` 的 YAML frontmatter 开头；`paper_id` 与目录名一致，`title` 与 `paper.yaml` 一致，`language` 固定为 `zh-CN`，`source` 固定为 `source.pdf`。
- `translation.md` 覆盖原文全部实质章节、公式、图表、算法、代码、附录和完整参考文献。
- 图表资源精确裁剪、链接有效、位置正确，主阅读路径无整页截图和工作残留。
- 翻译者完成草稿自检并交付审阅材料；批次中的翻译子代理运行 `make paper-check PAPER_ID=<paper-id>`，仓库级门禁由根代理负责。
- 完整处理新论文时，根代理继续安排 review workflow；审阅通过后更新状态并重新运行单篇门禁，再执行 `docs/workflows/rating.md`、重建目录和最终仓库级门禁。

## 约束

正文证据只来自当前目录的 `source.pdf`。不要用模型记忆补写模糊段落、实验数字、参考文献或图表内容。保留原文结构和主张，不添加论文未提出的解释性结论。

翻译阶段只拥有 `source_only -> draft` 和论文目录内的译文资产；翻译子代理
交付 `draft` 不表示完整任务结束。用户要求完整处理新论文时，根代理已有继续
安排独立审阅、按审阅结果更新为 `translated`、评分和重建目录的授权，无需在
工作流切换时重新确认。用户只要求草稿时交付 `draft`；不得把草稿完成误报为
`translated`。提交和发布仍遵循任务已有的授权范围。

完整质量要求见 `docs/translation-policy.md`。可以选择高效的提取、分栏、裁图和校对路径，但合并前必须检查编号、引用和顺序。

## 交审前自检

按段确认作者观点与责任归属，允许自然省略“我们”；检查是否出现连续的第三人称
改写或把作者观察变成普遍事实。将否定、必要/充分、上下界、公式标识符和表格
数据作为优先核源项。疑似原文异常也要查证，不能留给审阅者默认接受。

按 translation policy 同时检查解释句、比较强度和实验条件；默认配置不能只在脑中作为背景。逐图确认完整中文图注位于可见正文，alt 只作替代说明。对照源图注后，在渲染结果中检查编号、单位和工作负载定义是否能直接读到。

对目录、算法和条件列表，子列表每层使用四空格缩进，并在本地阅读页面确认子项仍属于相应父项、主步骤编号未被子项挤占。数字和公式正确但步骤层级变平，也属于内容错误。结论和解释逐段对应源文，不添加译者自行归纳的机制总结；原文存在冲突时按 policy 保留证据并加必要短注。

Markdown 表格普通文字中的字面 `|` 必须转义为 `\|`。类型联合、位运算等
行内代码中的竖线使用 `<code>str &#124; float</code>`，避免不同渲染器把
反引号内的竖线拆列或显示多余反斜杠。检查渲染后的列数与单元格完整性，不能
只看 Markdown 源码。

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

`draft` 是允许不完整的工作状态：过程残留和内容缺口会由校验器报告为 warning，便于继续工作。进入 `translated` 前必须消除确定性错误；低覆盖、数量差等启发式 warning 必须人工回到 PDF 处置，但不会转成永久例外记录。不要为了让草稿通过而隐藏标记或调低阈值。

## 停止条件

翻译阶段在草稿自检和交审材料完成时结束；根代理按用户要求继续后续流程。
出现无法可靠读取的内容、缺失原文、页数超限或范围外依赖时，报告具体阻塞和
受影响论文。未通过审阅时保留 `draft`，不猜测完成；批次中不受阻塞影响的论文
可继续处理。
