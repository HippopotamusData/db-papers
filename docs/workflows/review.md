# 工作流：译文审阅、修复与验收

## 目标与权限

用 `source.pdf` 判断现有译文是否达到全文翻译标准。默认 audit/review 只读；只有用户明确授权 review-and-repair 或 accept 时，才能修复论文资产、修改状态或写入验收账本。

- **audit/review**：逐节核对并报告证据，不落盘；严重问题只建议 `translated -> draft`。
- **review-and-repair/accept**：先将实质修改或未通过论文置为 `draft`，再修复并逐节验收。通过后用 accept 记录内容快照、审阅身份、固定基线和必要 waivers，并迁移到 `translated`。命令只接受 `draft`；失败不留下部分更新。

## 审阅范围与再次复审

默认采用增量审阅：完整处理新论文；重新审阅内容或受审书目信息已变化的论文；处理被新确定性证据点名的论文。论文数量增长、普通校验器调整、依赖升级或工作流文案变化，不构成全库内容复审授权。全库复审或历史批量修改必须由用户明确授权。

历史 v1 receipt 直接记录策略与门禁哈希；v2 记录正式 Git `review_head_sha`，并从该提交重建策略和门禁。两者都证明当时使用的程序和标准。当前策略或门禁变化不单独否定已绑定内容的验收；内容或受审书目信息变化，以及 receipt 到 accept 之间的输入漂移，仍会使验收失败。

维护校验器或工作流时，先运行回归测试和适用的非破坏性全库检查，列出受影响 paper ID 和证据。只有当前请求同时授权 `review-and-repair/accept`，才能把具体失败论文转入 `draft` 并修复；否则只报告。无法机械定位影响的重大标准变化应先报告历史成本，由用户决定复审范围。未获授权时保留既有验收，新增和后续变更论文按新标准执行。

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

`config/acceptance.yaml` 保存每篇论文当前已验收的 receipt。历史 receipt 和 waiver 始终按自身 schema 与 evidence version 验证；未知版本直接失败，禁止用新规则重算旧指纹。
历史 v1 的空 findings 和早期通用 findings 会由 `review-queue` 分别标记，只有真实 PDF 复审才能用具体的 v2 receipt 替换。

只有把机械候选逐项核回 PDF 后，才能使用 `paper-check` 输出的 `WAIVER-EVIDENCE` 指纹。`--waiver` 写成 `category=fingerprint`；指纹绑定版本化的规则和受影响对象。receipt 与 accept 看到的集合必须完全一致，新增、删除或漂移都会阻止验收。
进入 `translated` 后，当前发现只是已审集合的子集不使历史验收失效；任何未审的新发现仍会点名该论文并失败。确定性错误不能 waiver。

审阅者在最终修改完成后，先独立执行两轮核对：

1. **源文清单轮**：从 PDF 建立首页、脚注、章节、公式、图表、算法、代码、结论和参考文献清单，不依赖译文声明。恢复 PDF 换行断词后，逐项列出作者性 `I/we/my/our/us` 及其上下文；排除参考文献、代码和真正的第三方引语。
2. **逐项对照轮**：回填每项译文位置，核对数字、单位、比较方向、故障边界、限定条件和结论。逐项保持“我/我们”及其所有关系，不得改成无主语、“本文”“系统”或“团队”。图表密集页和抽取顺序可疑页必须渲染检查。

## 历史高频、脚本难发现的语义缺陷

以下问题在历史译文复审中反复出现，属于最终审阅者的强制人工清单。`paper-check`、字符比例、标题数量、资源数量或公式节点全部通过，都不能替代这些核对；扫描器未报警也不表示该项通过。

- **叙述者和责任归属漂移**：原文 `I/we/my/our/us` 被改成“本文”“系统”“结果表明”或无主语，导致提出、实现、观察和限制的责任主体消失；反方向也常见，即把原文被动句或客观陈述擅自改成“我们”。
  必须逐项核对第一人称、所有关系和动作主体，不能用中英文词频相等代替。
- **语气、强度和逻辑关系改变**：重点检查否定、双重否定、`may/can/must`、`only/at least/at most`、近似量、比较级、因果与相关、必要与充分、例外、故障边界及实验适用条件。
  不得把“实践中几乎不发生”强化成“不会发生”，也不得省略“在某配置、数据集或硬件下”之类限定语。
- **摘要化和源文不存在的补写**：逐段检查贡献列表、机制步骤、实验解释、结论、限制、附录和参考文献前后顺序。合并句段时最容易静默丢掉条件、反例或次要贡献。
  自行增加“总结”“启示”“因此可见”等原文没有的结论同样不合格。译文长度接近或超过原文不能证明不存在漏译或幻觉。
- **技术指代和标识符失真**：变量、算子、函数、类型、代码标识符、算法阶段、集合嵌套关系以及“该方法/前者/后者”的指代必须回到相邻原文确认。
  不要把多个相近实现统称为一个泛化术语，也不要因中文顺畅而改变算法执行顺序。
- **数字正确但上下文错误**：每个显式数字除数值外，还要绑定单位、指标、分母、基线、数据集、硬件、并发度和“高/低更好”的方向。
  表格数字抄对但列错实验、把相对提升写成绝对提升，仍是实质错误。
- **图表存在但论断缺失**：图片或 Markdown 表存在只证明有载荷；还要检查图注、坐标轴、图例、子图标签、空值/异常条件、正文交叉引用，以及作者从图表得出的具体结论。
  原图、图注和正文自身不一致时应忠实保留并明确说明“原文如此”，不能静默替作者修正或自拟解释。
- **结构完整但阅读顺序错误**：双栏抽取可能串栏；结论、致谢、参考文献和附录可能都存在却顺序错位。
  必须按渲染页确认章节边界、脚注归属、参考文献完整区间及附录位置，不能只比较标题集合。

最终审阅报告不能只写笼统的“语义通过”。须对上述七类缺陷逐类给出“已核对、无发现”或具体处置，再汇总 `source-inventory`、`authorial-voice` 和 `semantic-fidelity` 的通过或阻塞结论，并列出缺陷的原文页码与译文位置。
原文自身的数值、图注、署名或拼写异常单列为 `source-native-anomaly`，说明如何忠实保留。receipt 的 `findings` 只保存简洁结论；逐行定位留在任务报告和 Git 历史，不扩充 `paper.yaml`。

若真实复审在至少两篇论文中再次发现脚本难以可靠判定的新缺陷，或单次发现会系统性改变论文结论，应在维护任务中把缺陷族及核对方法补入本节。逐篇事件、完整日志和临时计数不进入本节，也不新增元数据文件。

随后由未参与当前字节快照修改的审阅者生成 receipt。译者/修复者和最终审阅者必须使用不同的 `namespace:value` 稳定身份。若审阅者修改了 source、translation 或 assets，其身份就转为修复者，必须另换审阅者完成最终复核。

`findings` 至少写一条经 PDF 核对的修复或通过结论，最多 8 条；每条不得超过 500 字符且必须单行。逐行日志留在任务报告和 Git 历史。
作者性叙述的有效项、逐项通过数和同主语合并写入 `authorial_voice`。有效项与通过项必须相等，同主语合并不得超过通过项；计数不能替代语义核对。

v2 receipt 绑定内容和受审元数据哈希、动作、身份、固定基线、`review_head_sha`、findings、作者性叙述计数及逐项 waiver。schema 冻结固定检查清单和身份保证；策略与门禁由 `review_head_sha` 重建。
命令运行一次单篇 `paper-check`，标准输出是可写入临时文件的 YAML：

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

`review_base_sha` 必须是当前 `HEAD` 可见的真实祖先；批次内使用清单固定的基线。`review_head_sha` 取当前 `HEAD`，因此门禁、依赖、策略和 review 程序必须先提交。论文内容可以留在工作树，receipt 用哈希绑定确切字节。
任何绑定输入或 HEAD 在 receipt 前后变化，都必须重新审阅并生成 receipt。waiver 只由最终审阅者写入 receipt，accept 不接收第二份 waiver 参数。

accept 使用 receipt 中的 waiver 记录执行一次 `translated` 级别最终深检，再运行锁定 MathJax 和 GitHub Markdown 节点审计。发现集合、绑定哈希、身份、基线或 HEAD 不匹配时，命令失败且不留下部分更新。全部通过后才更新账本和 `paper.yaml`。

若验收被强制中断并留下 transaction marker，所有后续验证都会停止。检查工作区与 marker，再选择恢复到目标状态或原状态：

```bash
PYTHON=$(make -s python-path)
"$PYTHON" scripts/papers.py recover-acceptance --mode commit
# 或
"$PYTHON" scripts/papers.py recover-acceptance --mode rollback
```

恢复命令只接受 marker 记录的原始或目标字节；外部改写、指纹异常或绑定输入漂移都会阻止覆盖。不要手工删除 marker、改写 receipt 或拼接账本。账本是当前快照，不是事件日志；重新验收替换旧 entry，详细历史由 Git 保留。

## 审校证据

以本地 PDF 为正文真相；旧日志、状态、译文长度或脚本绿灯都不能单独证明完整。receipt 只证明特定内容字节、运行时和自报身份完成了 schema 检查，不能替代语义判断。`self-attested` 不提供密码学身份保证；根代理仍须根据实际分派确认译者和审阅者不同。逐段修改由 Git 历史追溯，不进入阅读元数据。

在已授权的历史复审范围内，`make review-queue` 生成确定性的风险队列。历史 v1 空或通用 findings、带 abridgement/listings/resources waiver、强数学代码跨度候选、资源密集或高阅读价值的论文优先。真实复审并重新 accept 后会退出相应风险项。队列只排序，不扩大授权；未入队也不代表其余内容已通过语义核对。

资源审校遵循 `docs/translation-policy.md`。另须确认双栏顺序；图像坐标轴、刻度、图例、子图标签、边界和正文交叉引用；表格数字、单位与结论；以及每个资源只有一个完整表示。过程残留、空表和无效图片不计入完成度。

参考文献起点必须由相邻编号条目证明。逐条修复 PDF 换行断词、页码范围和 URL，并把正文引用与对应论断一起核对。编号差异只是候选，区间或数组必须回 PDF 消歧。目录、页眉或孤立标题不能缩小范围；移动或重裁资源前必须查看渲染页。

`make paper-check` 覆盖单篇公式结构门禁，accept 还会审计 GitHub Markdown 公式节点。最终审阅者须盘点行内代码：文件名、字段名、真实源码标识和字面数据可保留代码格式；变量、下标、区间、集合、复杂度、关系式与希腊算子必须回到原文语义。
扫描未命中不能代替人工核对。公式专项修复、规则或安全修复器变更按 `AGENTS.md` 的独立任务路由执行。

## 停止条件

audit/review 在证据报告完成时停止。写模式在译文通过并更新账本，或发现无法在当前范围可靠修复时停止；后一种情况保留 `draft` 并报告具体缺口。
