# 工作流：译文审阅、修复与验收

## 目标与权限

用 `source.pdf` 判断现有译文是否达到全文翻译标准。默认 audit/review 只读；只有用户明确授权 review-and-repair 或 accept 时，才能修复论文资产、修改状态或写入验收账本。

- **audit/review**：逐节核对并报告证据，不落盘；严重问题只建议 `translated -> draft`。
- **review-and-repair/accept**：先将实质修改或未通过论文置为 `draft`，修复并逐节验收；通过后用单一 accept 命令记录内容快照、审阅身份、固定基线和必要 waivers，并迁移到 `translated`。命令只接受 `draft`，失败不会留下部分账本或状态更新。

## 审阅范围与再次复审

默认采用增量审阅：完整处理新加入的论文；重新审阅源文、译文、资源或受审书目信息发生变化的论文；以及被新的确定性证据明确点名的论文。论文数量增长、普通校验器实现调整、依赖升级或工作流文案变化，本身都不构成全库内容复审授权。全库逐篇复审或批量修改历史译文，只能在用户当前请求明确授权时执行。

历史 v1 review receipt 直接记录翻译策略与审阅门禁哈希；新的 v2 receipt 记录正式 Git `review_head_sha`，策略和门禁从该提交重建。两者都用于证明当时由哪套程序和标准验收；论文进入 `translated` 后，当前策略或门禁变化不会单独使内容绑定的验收失效。源文、译文、资源或受审书目信息改变仍会立即使验收失效。receipt 生成后、accept 完成前发生任何绑定输入漂移也仍然拒绝验收。

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

schema v5 的每个 entry 都必须能物化为完整且指纹可验证的 receipt；不再接受 receiptless entry、退役指纹映射或迁移身份。历史 v1 entry 通过共享 `review_snapshots` 压缩重复的策略、门禁和基线字段，固定检查项与身份保证由冻结的 v1 schema 补回；新 v2 entry 直接保存，不使用共享快照。历史 v1 的空 findings 仍可按原 schema 验证，但 `review-queue` 会将其标记为 `legacy-empty-findings`；只有真实 PDF 复审才能用非空 findings 的 v2 receipt 替换，禁止猜测历史结论。

只有机械候选已回到 PDF 逐项处置后，才能使用 `paper-check` 输出的 `WAIVER-EVIDENCE` 指纹。`--waiver` 必须写成 `category=fingerprint`。指纹绑定版本化的精确语义发现集合，即规则与受影响对象；receipt 生成和 accept 的同次事务要求集合精确一致，新增、删除或漂移都会阻止 accept。论文进入 `translated` 后，当前检测集合若只是已审集合的子集，表示校验器消除了保守误报，不否定历史内容验收；出现任何未审的新规则或新 Listing/资源/引用对象时，仍会点名该论文并硬失败。账本同时保存排序后的原始诊断（含便于审计的计数、比例与抽取器信息），但这些跨平台可能变化的测量值不参与指纹。未知诊断规则、同一语义发现的重复诊断和确定性错误始终失败。

审阅者在最终修改完成后，先独立执行两轮核对：

1. **源文清单轮**：先从 PDF 建立首页/脚注/章节/公式/图表/算法/代码/结论/参考文献清单，不看译文完整性声明；同时逐项列出作者性 `I/we/my/our/us` 及其上下文，先恢复 PDF 换行断词，并排除参考文献、代码和真正的第三方引语。
2. **逐项对照轮**：逐项回填译文位置，核对所有显式数字、单位、比较方向、故障边界、限定条件和结论；作者性自述必须逐项保持“我/我们”及其所有关系，中文共用同一主语时也要确认责任归属没有被无主语、“本文”“系统”或“团队”取代；图表密集页与抽取顺序可疑页必须渲染检查。

## 历史高频、脚本难发现的语义缺陷

以下问题在历史译文复审中反复出现，属于最终审阅者的强制人工清单。
`paper-check`、字符比例、标题数量、资源数量或公式节点全部通过，都不能替代
这些核对；扫描器未报警也不表示该项通过。

- **叙述者和责任归属漂移**：原文 `I/we/my/our/us` 被改成“本文”“系统”
  “结果表明”或无主语，导致提出、实现、观察和限制的责任主体消失；反方向也
  常见，即把原文被动句或客观陈述擅自改成“我们”。必须逐项核对第一人称、
  所有关系和动作主体，不能用中英文词频相等代替。
- **语气、强度和逻辑关系改变**：重点检查否定、双重否定、`may/can/must`、
  `only/at least/at most`、近似量、比较级、因果与相关、必要与充分、例外、
  故障边界及实验适用条件。不得把“实践中几乎不发生”强化成“不会发生”，
  也不得省略“在某配置、数据集或硬件下”之类限定语。
- **摘要化和源文不存在的补写**：逐段检查贡献列表、机制步骤、实验解释、
  结论、限制、附录和参考文献前后顺序。合并句段时最容易静默丢掉条件、
  反例或次要贡献；自行增加“总结”“启示”“因此可见”等原文没有的结论同样
  不合格。译文长度接近或超过原文不能证明不存在漏译或幻觉。
- **技术指代和标识符失真**：变量、算子、函数、类型、代码标识符、算法阶段、
  集合嵌套关系以及“该方法/前者/后者”的指代必须回到相邻原文确认。不要把
  多个相近实现统称为一个泛化术语，也不要因中文顺畅而改变算法执行顺序。
- **数字正确但上下文错误**：每个显式数字除数值外，还要绑定单位、指标、
  分母、基线、数据集、硬件、并发度和“高/低更好”的方向。表格数字抄对但
  列错实验、把相对提升写成绝对提升，仍是实质错误。
- **图表存在但论断缺失**：图片或 Markdown 表存在只证明有载荷；还要检查
  图注、坐标轴、图例、子图标签、空值/异常条件、正文交叉引用，以及作者从
  图表得出的具体结论。原图、图注和正文自身不一致时应忠实保留并明确说明
  “原文如此”，不能静默替作者修正或自拟解释。
- **结构完整但阅读顺序错误**：双栏抽取可能串栏；结论、致谢、参考文献和
  附录可能都存在却顺序错位。必须按渲染页确认章节边界、脚注归属、参考文献
  完整区间及附录位置，不能只比较标题集合。

最终审阅报告不能只写笼统的“语义通过”：须对上述七类缺陷逐类给出
“已核对、无发现”或具体处置，再分别汇总为 `source-inventory`、
`authorial-voice` 和 `semantic-fidelity` 的通过或阻塞结论，并列出发现缺陷的
原文页码与译文位置。若原文自身存在数值、图注、署名或拼写异常，再单列
`source-native-anomaly` 说明如何忠实保留。receipt 的 `findings` 只保存可审计
的简洁结论；逐行定位留在当前任务报告和 Git 历史中，不扩充 `paper.yaml`。

若后续真实复审在两篇及以上论文中再次发现一种脚本难以可靠判定的新缺陷，
或单次发现会系统性改变论文结论的严重缺陷，应在维护任务中把该缺陷族及其
核对方法补入本节。逐篇事件、完整审阅日志和临时计数不进入本节，也不为此
新增元数据文件。

随后由未参与当前字节快照修改的审阅者用 `review-receipt` 显式确认命令列出的每个受控检查项。作者性叙述清单的源文有效项数、逐项通过数及任何同主语合并分别写入受控的 `authorial_voice` 计数；有效项与通过项必须相等，同主语合并不能超过通过项。`findings` 至少记录一条经 PDF 核对的修复或通过结论，不能再用空列表表示“无问题”；新 receipt 最多 8 条，每条必须是最多 500 字符的单行简洁结论，不能粘贴逐行日志。计数相等也不能替代语义与指代核对。若审阅者发现问题，应把问题退回译者/修复者；修复后由同一审阅者重新核对。若审阅者亲自修改了 source、translation 或 assets，其身份立即转为本轮修复者，必须再换第三个独立身份完成最终复核和 receipt。译者/修复者与最终审阅者必须使用不同的 `namespace:value` 稳定身份。v2 receipt 直接绑定内容与受审元数据哈希、动作、身份、固定基线、`review_head_sha`、findings、作者性叙述计数和逐项 waiver；固定检查清单与自报身份语义由 schema 冻结，策略和门禁由 `review_head_sha` 重建。命令会再次运行单篇 `paper-check`，标准输出只包含可保存到临时文件的 YAML：

```bash
PYTHON=$(make -s python-path)
receipt=$(mktemp "${TMPDIR:-/tmp}/db-papers-review.XXXXXX")
trap 'rm -f "$receipt"' EXIT HUP INT TERM
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
  --finding <location-and-disposition> \
  --authorial-voice-source-items <count> \
  --authorial-voice-verified-items <count> \
  --authorial-voice-shared-subject-merges <count> \
  [--waiver <abridgement|resources|listings>=<reviewed-sha256> ...] \
  > "$receipt"

"$PYTHON" scripts/papers.py accept \
  --id <paper-id> \
  --review-receipt "$receipt"
rm -f "$receipt"
trap - EXIT HUP INT TERM
```

`review_base_sha` 必须是当前 `HEAD` 可见的真实祖先提交；同一批次使用预检时记录的固定基线，不使用审阅完成后的临时提交冒充基线。v2 的 `review_head_sha` 由命令取当前 `HEAD`；门禁实现、依赖、策略和 review/batch-review 程序必须先提交，使工作树门禁能从该 Git 提交逐路径重建。论文内容可以仍在工作树中，receipt 用内容哈希绑定其确切字节。命令会比较 `paper-check` 前后的 metadata、source、translation、assets、翻译策略、验收门禁和 Git HEAD 快照，运行中发生漂移就拒绝生成 receipt；accept 还要求 receipt 的 `review_head_sha` 等于当前 HEAD。waiver 必须在生成 receipt 时由最终审阅者明确确认，accept 不再接收第二份可漂移的 waiver 参数。

accept 先在未改写权威文件的 `draft` 上执行单篇深检和候选发现，要求发现指纹与命令行逐项一致，再用同一组证据执行 `translated` 级别复检，随后运行锁定 MathJax 与 GitHub Markdown 节点审计。两次本地预检不仅要求语义发现一致，也要求原始诊断逐字一致，以阻止同一进程中的测量漂移；只有不同受支持平台之间的等价语义发现才允许原始测量不同。预检覆盖只通过 accept 传入的显式内部参数生效；普通深检拒绝同名环境变量，始终读取权威账本。全部通过后才在跨进程锁内以 compare-and-swap 写入账本和状态；源文、译文、资源、元数据、账本或 Git HEAD 发生并发漂移，或进程被中断时，验收失败并回滚自身已尝试的写入。

账本和 `paper.yaml` 是两个权威文件。accept 在写入前创建并落盘一个内容带指纹的事务日志，两个文件和目录项均执行持久化同步。完成写入或完整回滚后，活动日志先原子改名为 cleanup marker 并同步目录，确认恢复锚点持久化后才删除；若删除后的最终目录同步失败，事务状态仍按已完成报告，并警告 cleanup marker 可能在崩溃重启后重新出现。若进程被不可捕获地强杀，任何验证都会因残留的活动日志或 cleanup marker 失败，必须在检查文件状态后显式恢复：

```bash
PYTHON=$(make -s python-path)
"$PYTHON" scripts/papers.py recover-acceptance --mode commit
# 或
"$PYTHON" scripts/papers.py recover-acceptance --mode rollback
```

恢复只接受事务记录中的原始或目标字节，并且活动日志与 cleanup marker 最多只能存在一个；每次写入前及删除 marker 前都会再次核对两个权威文件，commit 还会在写入前后重验 source、translation、assets、翻译策略、门禁和 Git HEAD。检测到外部改写、marker 指纹异常或绑定输入漂移时保留 marker 并拒绝覆盖。不要手工删除事务 marker 或拼接账本。

`config/acceptance.yaml` 是每篇论文当前已验收版本的快照，不是事件日志。entry 本身就是 review receipt；历史 v1 的重复环境字段通过共享快照规范化，新 v2 只保存每篇独有或必须显式留存的证据。重新验收会替换旧 entry；更详细的逐段修改和迁移记录仍由 Git 历史保存。

历史 receipt 按自身 `schema_version` 的冻结检查项、受审元数据字段、受控动作和身份保证语义验证；新增标准使用新 schema，不能用最新常量重新解释或批量重算旧 receipt。未知 schema 必须失败。

历史 waiver 也按自身 `evidence_version` 的冻结诊断映射与指纹算法验证；新增诊断语义应使用新 evidence version 并继续支持旧版本，不能借解析器升级重释或批量改写旧 waiver。未知 evidence version 必须失败。

## 审校证据

以本地 PDF 为正文真相。旧日志、当前状态、译文长度或脚本绿灯都不能单独证明完整。receipt 证明哪组内容字节、审阅运行时和自报身份关联了本 schema 的检查，不能替代 PDF 语义判断。`self-attested` 是 schema 冻结的身份保证语义；v2 不在每篇 entry 重复保存该常量。命令只强制稳定身份格式和译者/审阅者不同，根代理仍须从实际任务分派确认身份；需要对抗性身份不可否认性时必须另行引入签名机制。逐段修改仍通过 Git 历史追溯，不写入阅读元数据。

在用户已授权的历史复审范围内，运行 `make review-queue` 可得到确定性的风险优先队列。历史 v1 空 findings、带 abridgement/listings/resources waiver、强数学代码跨度候选、资源密集或高阅读价值的论文优先；完成真实复审并重新 accept 后会自然退出相应高风险项。队列只负责排序，出现候选不要求自动清空，也不扩展当前授权范围。数学代码跨度只采用低误报强信号，未入队不表示其余反引号内容已通过语义核对。

资源审校遵循 `docs/translation-policy.md`，并额外确认：双栏抽取顺序正确；图像坐标轴、全部刻度、图例、子图标签、边界和正文 `(a)/(b)` 交叉引用可读且对应；表格数字、单位和结论对应；每个正式资源恰有一个完整表示；HTML 注释、占位围栏、空表和空白或近乎单色图片都没有被计入完成度。参考文献节的起点必须由相邻编号条目支持，并逐条检查 PDF 换行断词、页码范围与 URL；正文引用锚点必须与对应论断一起逐段核对，单篇深门禁列出的源文/译文编号差异只是候选，方括号区间或数组要回 PDF 消歧。目录、页眉和孤立标题不能缩小核对范围。编号扫描只生成候选，新增、删除、移动或重裁资源前必须回到渲染页确认。

任何变更译文都必须按 `docs/portable-math-maintainers.md` 通过限定文件范围的 GitHub Markdown 公式节点审计；accept 已把该审计和锁定 MathJax 结构门禁置于写入前。最终审阅者还必须逐个盘点行内代码节点：文件名、字段名、真实源码标识和字面数据可以保留代码格式，变量、下标、区间、集合、复杂度、关系式与希腊算子必须回到原文数学语义；强候选扫描未命中不能代替这一步。全库公式规则或安全修复器变更仍需运行全库审计，并在推送后的真实 GitHub 文件页检查最终显示。VS Code/KaTeX 仅为可选诊断；CI 对变更译文重复外部审计。

## 停止条件

audit/review 在证据报告完成时停止。写模式在译文通过并更新账本，或发现无法在当前范围可靠修复时停止；后一种情况保留 `draft` 并报告具体缺口。
