# 工作流：译文审阅、修复与验收

## 目标与权限

用 `source.pdf` 判断现有译文是否达到全文翻译标准。默认 audit/review 只读；只有用户明确授权 review-and-repair 或 accept 时，才能修复论文资产、修改状态或写入验收账本。

- **audit/review**：逐节核对并报告证据，不落盘；严重问题只建议 `translated -> draft`。
- **review-and-repair/accept**：先将实质修改或未通过论文置为 `draft`，修复并逐节验收；通过后用单一 accept 命令记录哈希、审阅动作和必要 waivers，并迁移到 `translated`。命令只接受 `draft`，失败会回滚账本和状态。

## 成功标准

- 摘要、正文、结论、附录、图、表、公式、算法、代码和参考文献均已对照原文。
- 漏译、摘要化、数值错误、错位资源、断链和过程残留已修复，或状态保持 `draft`。
- 机械覆盖信号只扩大人工抽查；确定性错误不能被 waiver 豁免。公式的静态兼容性错误在 `draft` 和 `translated` 状态下都直接失败，不得降级为质量告警。
- `translated` 的账本哈希与当前 `source.pdf`、`translation.md` 完全一致。
- `make check` 通过。

## 验收记录

`review_action` 必须从下列单一动作中选择：

- `section-review`：现有完整译文已逐节审阅；
- `full-translation-review`：新全文译文已交叉审阅；
- `repair-review`：实质修复后的译文已复审。

`legacy-migration` 只兼容读取 schema v1 迁移来的历史条目，普通 `accept` 不接受该值，也不能用它验收新的文件哈希。

只有机械候选已回到 PDF 逐项处置后，才能按需添加 `--waiver abridgement`、`--waiver resources` 或 `--waiver listings`。深度校验要求记录的 waiver 与当前候选逐项相等：候选缺 waiver 或 waiver 没有对应候选都会失败；确定性错误始终失败。

```bash
python3 scripts/papers.py accept \
  --id <paper-id> \
  --review-action <section-review|full-translation-review|repair-review> \
  [--waiver <abridgement|resources|listings>]
```

`config/acceptance.yaml` 是每篇论文当前已验收版本的快照，不是事件日志；重新验收会替换旧条目，详细审校过程由 Git 历史保存。

## 审校证据

以本地 PDF 为正文真相。旧日志、当前状态、译文长度或脚本绿灯都不能单独证明完整；详细过程通过 Git 历史追溯，不写入阅读元数据或验收账本。

资源审校遵循 `docs/translation-policy.md`，并额外确认：双栏抽取顺序正确；图像坐标轴、图例、标签和边界可读；表格数字、单位和结论对应；每个正式资源恰有一个完整表示。编号扫描只生成候选，新增、删除、移动或重裁资源前必须回到渲染页确认。

任何变更译文在验收前都必须按 `docs/portable-math-maintainers.md` 运行限定文件范围的 GitHub Markdown 公式节点审计；全库公式规则或安全修复器变更运行全库审计，并在推送后的真实 GitHub 文件页检查最终显示。仓库内的静态门禁和锁定版本 MathJax 结构门禁同样必跑；VS Code/KaTeX 仅为可选诊断，外部核验不加入离线 `make check`，由 CI 对变更译文重复执行。

## 停止条件

audit/review 在证据报告完成时停止。写模式在译文通过并更新账本，或发现无法在当前范围可靠修复时停止；后一种情况保留 `draft` 并报告具体缺口。
