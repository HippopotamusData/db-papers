# 工作流：译文审阅、修复与验收

## 目标与权限

用 `source.pdf` 判断现有译文是否达到全文翻译标准。默认 audit/review 只读；只有用户明确授权 review-and-repair 或 accept 时，才能修复论文资产、修改状态或写入验收账本。

- **audit/review**：逐节核对并报告证据，不落盘；严重问题只建议 `translated -> draft`。
- **review-and-repair/accept**：先将实质修改或未通过论文置为 `draft`，修复并逐节验收；通过后用单一 accept 命令记录内容快照、审阅身份、固定基线和必要 waivers，并迁移到 `translated`。命令只接受 `draft`，失败不会留下部分账本或状态更新。

## 成功标准

- 摘要、正文、结论、附录、图、表、公式、算法、代码和参考文献均已对照原文。
- 漏译、摘要化、数值错误、错位资源、断链和过程残留已修复，或状态保持 `draft`。
- 机械覆盖信号只扩大人工抽查；确定性错误不能被 waiver 豁免。公式的静态兼容性错误在 `draft` 和 `translated` 状态下都直接失败，不得降级为质量告警。
- `translated` 的账本哈希与当前 `source.pdf`、`translation.md` 及全部非忽略 `assets/` 完全一致。
- `make check` 通过。

## 验收记录

`review_action` 必须从下列单一动作中选择：

- `section-review`：现有完整译文已逐节审阅；
- `full-translation-review`：新全文译文已交叉审阅；
- `repair-review`：实质修复后的译文已复审。

schema v3 不接受 `legacy-migration` 或 `pending-v3-re-review`。无法追溯实际审阅者的迁移期历史兼容记录只能使用已冻结的 `historical-v2-reviewer-unrecorded` 条目；其论文 ID、全部证据字段和基线指纹由代码逐项锁定，只允许通过真实重审把整条记录替换为普通 reviewer，不允许新增或改写历史标记。

只有机械候选已回到 PDF 逐项处置后，才能使用 `paper-check` 输出的 `WAIVER-EVIDENCE` 指纹。`--waiver` 必须写成 `category=fingerprint`；同一类别内新增、删除或改写任一候选都会改变指纹并阻止 accept。账本保存排序后的完整候选和内容指纹；确定性错误始终失败。

```bash
python3 scripts/papers.py accept \
  --id <paper-id> \
  --review-action <section-review|full-translation-review|repair-review> \
  --reviewer <stable-reviewer-identity> \
  --review-base-sha <40-character-fixed-batch-baseline> \
  [--waiver <abridgement|resources|listings>=<reviewed-sha256>]
```

`review_base_sha` 必须是当前 `HEAD` 可见的真实祖先提交；同一批次使用预检时记录的固定基线，不使用审阅完成后的临时提交冒充基线。`reviewer` 记录实际执行本次 PDF 对照审阅的稳定身份。

accept 先在未改写权威文件的 `draft` 上执行单篇深检和候选发现，要求发现指纹与命令行逐项一致，再用同一组证据执行 `translated` 级别复检，随后运行锁定 MathJax 与 GitHub Markdown 节点审计。预检覆盖只通过 accept 传入的显式内部参数生效；普通深检拒绝同名环境变量，始终读取权威账本。全部通过后才在跨进程锁内以 compare-and-swap 写入账本和状态；源文、译文、资源、元数据、账本或 Git HEAD 发生并发漂移，或进程被中断时，验收失败并回滚自身已尝试的写入。

`config/acceptance.yaml` 是每篇论文当前已验收版本的快照，不是事件日志；每项绑定源文、译文、非忽略资源清单、审阅动作、审阅者、固定基线和精确候选证据。重新验收会替换旧条目，详细审校过程由 Git 历史保存。

## 审校证据

以本地 PDF 为正文真相。旧日志、当前状态、译文长度或脚本绿灯都不能单独证明完整；详细过程通过 Git 历史追溯，不写入阅读元数据或验收账本。

资源审校遵循 `docs/translation-policy.md`，并额外确认：双栏抽取顺序正确；图像坐标轴、图例、标签和边界可读；表格数字、单位和结论对应；每个正式资源恰有一个完整表示。编号扫描只生成候选，新增、删除、移动或重裁资源前必须回到渲染页确认。

任何变更译文都必须按 `docs/portable-math-maintainers.md` 通过限定文件范围的 GitHub Markdown 公式节点审计；accept 已把该审计和锁定 MathJax 结构门禁置于写入前。全库公式规则或安全修复器变更仍需运行全库审计，并在推送后的真实 GitHub 文件页检查最终显示。VS Code/KaTeX 仅为可选诊断；CI 对变更译文重复外部审计。

## 停止条件

audit/review 在证据报告完成时停止。写模式在译文通过并更新账本，或发现无法在当前范围可靠修复时停止；后一种情况保留 `draft` 并报告具体缺口。
