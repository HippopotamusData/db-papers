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
- 逐节对照通过后由 review/accept 绑定源文、译文、非忽略资源、审阅者、固定基线和精确机械候选，再把 `reading_status` 改为 `translated`。
- 新论文的完整处理在 accept 后继续执行 `docs/workflows/rating.md`；评分写入并重新生成目录后才进入最终提交。
- `make check` 通过。

## 约束

正文证据只来自当前目录的 `source.pdf`。不要用模型记忆补写模糊段落、实验数字、参考文献或图表内容。保留原文结构和主张，不添加论文未提出的解释性结论。

单篇新论文若被要求“完整处理”，本工作流只拥有
`source_only -> draft` 和论文目录内的译文资产；随后必须按 review workflow
独立审阅并 accept，再按 rating workflow 评分并重建目录。未获 accept 权限
时交付 `draft`，不得把“翻译完成”误报为 `translated`。

完整质量要求见 `docs/translation-policy.md`。可以选择高效的提取、分栏、裁图和校对路径，但合并前必须检查编号、引用和顺序。

`draft` 是允许不完整的工作状态：TODO、低覆盖、Listing/表格/资源缺口会由校验器报告为 warning，便于继续工作；同样的问题在 `translated` 中必须失败。不要为了让草稿通过而隐藏标记或调低阈值。

## 停止条件

译文达到 `translated` 标准，或出现无法可靠读取的内容、缺失原文、页数超限或范围外依赖。未通过验收时保留 `draft`，不猜测完成。
