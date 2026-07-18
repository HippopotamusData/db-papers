# 工作流：译文审阅、修复与验收

## 目标与权限

用 `source.pdf` 判断现有译文是否达到全文翻译标准。默认 audit/review 只读；只有用户明确授权 review-and-repair 或 accept 时，才能修复论文资产、修改状态或写入验收账本。

- **audit/review**：逐节核对并报告证据，不落盘；严重问题只建议 `translated -> draft`。
- **review-and-repair/accept**：先将实质修改或未通过论文置为 `draft`，修复并逐节验收；通过后用单一 accept 命令记录内容快照、审阅身份、固定基线和必要 waivers，并迁移到 `translated`。命令只接受 `draft`，失败不会留下部分账本或状态更新。

## 审阅范围与再次复审

默认采用增量审阅：完整处理新加入的论文；重新审阅源文、译文、资源或受审书目信息发生变化的论文；以及被新的确定性证据明确点名的论文。论文数量增长、普通校验器实现调整、依赖升级或工作流文案变化，本身都不构成全库内容复审授权。全库逐篇复审或批量修改历史译文，只能在用户当前请求明确授权时执行。

review receipt 记录生成时使用的翻译策略与审阅门禁快照，用于证明当时由哪套程序和标准验收；论文进入 `translated` 后，当前策略或门禁快照与 receipt 不同，不会单独使内容绑定的验收失效。源文、译文、资源或受审书目信息改变仍会立即使验收失效。receipt 生成后、accept 完成前发生任何绑定输入漂移也仍然拒绝验收。

维护校验器或工作流时先运行回归测试和适用的全库非破坏性检查，形成受影响 paper ID 与证据清单。检查发现具体论文违反既有质量底线时，先把这些论文列为范围复审候选；只有当前请求同时授权 `review-and-repair/accept` 时，才能将其转入 `draft` 并修复，否则只报告。无法机械定位的重大标准变化应先报告历史影响和成本，再由用户决定是否授权范围复审或全库复审。未获该授权时，既有验收保留，新加入和此后发生内容变化的论文按最新标准执行。

## 成功标准

- 摘要、正文、结论、附录、图、表、公式、算法、代码和参考文献均已对照原文。
- 首页作者/机构、分类信息、脚注、致谢、收稿记录和其他前后置材料已逐项盘点；不能因为不属于正文主线而静默省略。
- 漏译、摘要化、数值错误、错位资源、断链和过程残留已修复，或状态保持 `draft`。
- 机械覆盖信号只扩大人工抽查；确定性错误不能被 waiver 豁免。公式的静态兼容性错误在 `draft` 和 `translated` 状态下都直接失败，不得降级为质量告警。
- `translated` 的账本哈希与当前 `source.pdf`、`translation.md` 及全部非忽略 `assets/` 完全一致。
- `make check` 通过。

## 验收记录

`review_action` 必须从下列单一动作中选择：

- `section-review`：现有完整译文已逐节审阅；
- `full-translation-review`：新全文译文已交叉审阅；
- `repair-review`：实质修复后的译文已复审。

schema v4 不接受 `legacy-migration` 或 `pending-v3-re-review`。无法追溯实际审阅者的迁移期历史兼容记录只能使用已冻结的 `historical-v2-reviewer-unrecorded` 条目。所有 receiptless 兼容条目（含由 schema v3 迁移的普通 reviewer 条目）的论文 ID 和完整条目指纹都由代码逐项锁定，只允许通过真实重审把整条记录替换为带 receipt 的普通记录，不允许新增或改写 receiptless 证据。代码中的不可变全集必须精确分成仍活跃的 receiptless 条目和账本中的 `retired_legacy_entry_fingerprints`；accept 在同一事务里把旧条目指纹移入退役映射并写入新 receipt，回滚也同时恢复两者，不需要修改校验器源码。退役 ID 必须仍对应带 receipt 的当前条目，不能用退役标记隐藏未审债务。只有用户明确授权历史复审时，历史条目才在授权范围内通过 `review-queue` 排序；队列本身不授予复审或修改权限。任何新的或重新执行的 accept 都必须提供 receipt。

为避免校验器升级在没有 PDF 重审的情况下悄悄改写历史 waiver，receiptless `translated` 记录只重放其冻结时使用的旧参考文献边界、条目解析、Markdown 图片识别和正式资源配对，用来验证既有指纹，不能据此生成新 receipt。`draft`、验收预检和带当前 receipt 的记录必须使用证据支持的 References 起点、双栏/作者键条目恢复、正文引用核对、页边界截断和当前资源结构门禁。旧兼容路径不是质量证明；把历史记录迁移到新门禁的唯一方式仍是独立 PDF 复审、生成 receipt 并重新 accept。

只有机械候选已回到 PDF 逐项处置后，才能使用 `paper-check` 输出的 `WAIVER-EVIDENCE` 指纹。`--waiver` 必须写成 `category=fingerprint`。指纹绑定版本化的精确语义发现集合，即规则与受影响对象；receipt 生成和 accept 的同次事务要求集合精确一致，新增、删除或漂移都会阻止 accept。论文进入 `translated` 后，当前检测集合若只是已审集合的子集，表示校验器消除了保守误报，不否定历史内容验收；出现任何未审的新规则或新 Listing/资源/引用对象时，仍会点名该论文并硬失败。账本同时保存排序后的原始诊断（含便于审计的计数、比例与抽取器信息），但这些跨平台可能变化的测量值不参与指纹。未知诊断规则、同一语义发现的重复诊断和确定性错误始终失败。

审阅者在最终修改完成后，先独立执行两轮核对：

1. **源文清单轮**：先从 PDF 建立首页/脚注/章节/公式/图表/算法/代码/结论/参考文献清单，不看译文完整性声明；同时逐项列出作者性 `I/we/my/our/us` 及其上下文，先恢复 PDF 换行断词，并排除参考文献、代码和真正的第三方引语。
2. **逐项对照轮**：逐项回填译文位置，核对所有显式数字、单位、比较方向、故障边界、限定条件和结论；作者性自述必须逐项保持“我/我们”及其所有关系，中文共用同一主语时也要确认责任归属没有被无主语、“本文”“系统”或“团队”取代；图表密集页与抽取顺序可疑页必须渲染检查。

随后由未参与当前字节快照修改的审阅者用 `review-receipt` 显式确认命令列出的每个受控检查项。receipt 的 findings 应记录作者性叙述清单的源文有效项数、逐项通过数及任何同主语合并，不能只写原始正则计数；计数相等也不能替代语义与指代核对。若该审阅者发现问题，应把问题退回译者/修复者；修复后由同一审阅者重新核对。若审阅者亲自修改了 source、translation 或 assets，其身份立即转为本轮修复者，必须再换第三个独立身份完成最终复核和 receipt。译者/修复者与最终审阅者必须使用不同的 `namespace:value` 稳定身份；receipt 绑定源文、译文、资源、翻译策略、首页书目信息、验收门禁清单、固定基线、检查项、发现记录和逐项 waiver 证据。命令会再次运行单篇 `paper-check`，标准输出只包含可保存到临时文件的 YAML：

```bash
"$PYTHON" scripts/papers.py review-receipt \
  --id <paper-id> \
  --review-action <section-review|full-translation-review|repair-review> \
  --translator <stable-translator-or-repairer-identity> \
  --reviewer <stable-reviewer-identity> \
  --review-base-sha <40-character-fixed-batch-baseline> \
  --check front-matter \
  --check section-structure \
  --check technical-claims \
  --check numbers-and-units \
  --check formulas \
  --check figures-and-tables \
  --check algorithms-and-listings \
  --check footnotes-and-end-matter \
  --check conclusions-and-limitations \
  --check references \
  --check visual-layout \
  [--finding <location-and-disposition> ... | --no-findings] \
  [--waiver <abridgement|resources|listings>=<reviewed-sha256> ...] \
  > /tmp/<paper-id>-review.yaml

"$PYTHON" scripts/papers.py accept \
  --id <paper-id> \
  --review-receipt /tmp/<paper-id>-review.yaml
```

`review_base_sha` 必须是当前 `HEAD` 可见的真实祖先提交；同一批次使用预检时记录的固定基线，不使用审阅完成后的临时提交冒充基线。命令会比较 `paper-check` 前后的 metadata、source、translation、assets、翻译策略、验收门禁清单和 Git HEAD 快照，运行中发生漂移就拒绝生成 receipt。receipt 生成后再改动 source、translation、assets、首页书目信息、翻译策略或验收门禁都会使 accept 失败，禁止用新生成的哈希冒充旧审阅。waiver 必须在生成 receipt 时由最终审阅者明确确认，accept 不再接收第二份可漂移的 waiver 参数。

accept 先在未改写权威文件的 `draft` 上执行单篇深检和候选发现，要求发现指纹与命令行逐项一致，再用同一组证据执行 `translated` 级别复检，随后运行锁定 MathJax 与 GitHub Markdown 节点审计。两次本地预检不仅要求语义发现一致，也要求原始诊断逐字一致，以阻止同一进程中的测量漂移；只有不同受支持平台之间的等价语义发现才允许原始测量不同。预检覆盖只通过 accept 传入的显式内部参数生效；普通深检拒绝同名环境变量，始终读取权威账本。全部通过后才在跨进程锁内以 compare-and-swap 写入账本和状态；源文、译文、资源、元数据、账本或 Git HEAD 发生并发漂移，或进程被中断时，验收失败并回滚自身已尝试的写入。

账本和 `paper.yaml` 是两个权威文件。accept 在写入前创建并落盘一个内容带指纹的事务日志，两个文件和目录项均执行持久化同步。完成写入或完整回滚后，活动日志先原子改名为 cleanup marker 并同步目录，确认恢复锚点持久化后才删除；若删除后的最终目录同步失败，事务状态仍按已完成报告，并警告 cleanup marker 可能在崩溃重启后重新出现。若进程被不可捕获地强杀，任何验证都会因残留的活动日志或 cleanup marker 失败，必须在检查文件状态后显式恢复：

```bash
"$PYTHON" scripts/papers.py recover-acceptance --mode commit
# 或
"$PYTHON" scripts/papers.py recover-acceptance --mode rollback
```

恢复只接受事务记录中的原始或目标字节，并且活动日志与 cleanup marker 最多只能存在一个；每次写入前及删除 marker 前都会再次核对两个权威文件，commit 还会在写入前后重验 source、translation、assets、翻译策略、门禁和 Git HEAD。检测到外部改写、marker 指纹异常或绑定输入漂移时保留 marker 并拒绝覆盖。不要手工删除事务 marker 或拼接账本。

`config/acceptance.yaml` 是每篇论文当前已验收版本的快照，不是事件日志；新的验收项同时保存内容绑定的 review receipt，其中包含实际译者、独立审阅者、完整检查项和本轮发现。`retired_legacy_entry_fingerprints` 只记录被当前 receipt 原子取代的旧冻结指纹，不是第二份验收记录。重新验收会替换旧条目；更详细的逐段修改仍由 Git 历史保存。

历史 receipt 按自身 `schema_version` 的冻结检查项、受审元数据字段、受控动作和身份保证语义验证；新增标准使用新 schema，不能用最新常量重新解释或批量重算旧 receipt。未知 schema 必须失败。

历史 waiver 也按自身 `evidence_version` 的冻结诊断映射与指纹算法验证；新增诊断语义应使用新 evidence version 并继续支持旧版本，不能借解析器升级重释或批量改写旧 waiver。未知 evidence version 必须失败。

## 审校证据

以本地 PDF 为正文真相。旧日志、当前状态、译文长度或脚本绿灯都不能单独证明完整。receipt 证明哪组内容字节、策略、门禁和自报身份关联了哪些检查，不能替代 PDF 语义判断。`identity_assurance: self-attested` 明确表示身份字符串不是密码学签名：命令只强制稳定格式和译者/审阅者不同，根代理仍须从实际任务分派确认身份；需要对抗性身份不可否认性时必须另行引入签名机制。逐段修改仍通过 Git 历史追溯，不写入阅读元数据。

在用户已授权的历史复审范围内，运行 `"$PYTHON" scripts/papers.py review-queue` 可得到确定性的风险优先队列。无内容绑定 receipt、历史审阅者不可追溯、带 abridgement/listings/resources waiver、强数学代码跨度候选、资源密集或高阅读价值的论文优先；完成真实复审并重新 accept 后会自然退出相应高风险项。队列只负责排序，出现候选不要求自动清空，也不扩展当前授权范围。数学代码跨度只采用低误报强信号，未入队不表示其余反引号内容已通过语义核对。

资源审校遵循 `docs/translation-policy.md`，并额外确认：双栏抽取顺序正确；图像坐标轴、全部刻度、图例、子图标签、边界和正文 `(a)/(b)` 交叉引用可读且对应；表格数字、单位和结论对应；每个正式资源恰有一个完整表示；HTML 注释、占位围栏、空表和空白或近乎单色图片都没有被计入完成度。参考文献节的起点必须由相邻编号条目支持，并逐条检查 PDF 换行断词、页码范围与 URL；正文引用锚点必须与对应论断一起逐段核对，单篇深门禁列出的源文/译文编号差异只是候选，方括号区间或数组要回 PDF 消歧。目录、页眉和孤立标题不能缩小核对范围。编号扫描只生成候选，新增、删除、移动或重裁资源前必须回到渲染页确认。

任何变更译文都必须按 `docs/portable-math-maintainers.md` 通过限定文件范围的 GitHub Markdown 公式节点审计；accept 已把该审计和锁定 MathJax 结构门禁置于写入前。最终审阅者还必须逐个盘点行内代码节点：文件名、字段名、真实源码标识和字面数据可以保留代码格式，变量、下标、区间、集合、复杂度、关系式与希腊算子必须回到原文数学语义；强候选扫描未命中不能代替这一步。全库公式规则或安全修复器变更仍需运行全库审计，并在推送后的真实 GitHub 文件页检查最终显示。VS Code/KaTeX 仅为可选诊断；CI 对变更译文重复外部审计。

## 停止条件

audit/review 在证据报告完成时停止。写模式在译文通过并更新账本，或发现无法在当前范围可靠修复时停止；后一种情况保留 `draft` 并报告具体缺口。
