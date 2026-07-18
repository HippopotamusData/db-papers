# 工作流：项目维护

## 目标

在不破坏论文资产的前提下，维护六个必填字段、可选评分、项目策略、分类法、验收账本、校验器和生成目录。

## 成功标准

- `paper.yaml` 仍严格保持六个必填字段，并且只允许评分工作流定义的可选 `rating`。
- 目录或主题变化同时更新配置、文档、校验器和受影响记录。
- 生成文件由脚本重建，不手工修补统计。
- `config/policy.yaml`、`config/taxonomy.yaml` 与 `config/acceptance.yaml` 都通过版本化强类型 schema 校验。
- 已有原文、译文正文和资源不因结构调整而改变；相对资源链接仍有效。
- `make check` 通过，`make diff-check` 对 tracked、staged 和 untracked 文件均无格式错误。

## 变更规则

确定性约束和受控码以 `scripts/project_config.py` 为事实来源，不通过更长提示词或多个配置副本反复声明。配置只保存真正可变的值；固定文件名、目标语言和质量底线不是开关。只有会被多篇论文复用并改善阅读的概念才进入分类法。

若要改变必填字段或可选评分结构，必须由用户明确选择，并一次性更新模板、文档、脚本和生成目录。不要为单篇论文添加临时字段。`docs/` 只保留当前规则和工作流；旧规则、迁移记录和审校过程通过 Git 历史追溯，不得作为当前状态输入。

默认页数上限、单篇例外和 skipped 原因集中在 `config/policy.yaml`。单篇页数例外必须包含高于默认值的 `max_source_pages` 和用户授权依据 `authorization`；跳过原因使用代码定义的受控值。schema v4 验收账本是当前已验收版本的快照，保存源文/译文哈希、非忽略资源清单哈希、一个受控 `review_action`、实际 `reviewer`、固定祖先基线 `review_base_sha`，以及与当前机械候选逐项匹配的受控 `waivers`；新的或重新验收的条目还必须保存内容绑定的 `review_receipt`，记录独立译者/审阅者自报身份、身份保证级别、翻译策略哈希、首页书目信息哈希、验收门禁清单哈希、完整受控检查项、发现摘要、逐项 waiver 证据和 receipt 指纹。账本顶层的 `retired_legacy_entry_fingerprints` 保存已被当前 receipt 取代的旧冻结指纹，并与条目替换处于同一原子事务。验收门禁清单同时绑定执行脚本、依赖锁、策略配置和当前 review/batch-review 程序，用于记录本次审阅的可复现运行时；receipt 生成后、accept 完成前这些输入发生变化必须重新生成 receipt。进入 `translated` 后，运行时或策略快照漂移本身不自动否定内容绑定的历史验收；维护者应运行回归测试和非破坏性全库检查，只把被具体新证据影响的论文转入 `draft`。无法机械定位的重大标准变化必须先给出影响分析，未经用户明确授权不得据此启动全库内容复审或批量历史修改。每项 waiver 同时保存证据版本、语义发现集合及其指纹和原始诊断。语义发现用于跨平台匹配，原始诊断用于审计和同次 accept 的漂移检测；历史验收后若当前检测集合只是已审语义发现的子集，表示保守候选被消除，不使内容失效，只有新增语义发现才点名该论文重新处置。重新验收会替换旧条目。源文、译文、资源或受审书目信息发生实质变化时先迁移到 `draft`，旧账本不得继续支持 `translated`。

review receipt 的 schema 版本必须冻结该版本的检查项、受审元数据字段、受控动作和身份保证语义；读取历史 receipt 时按其自身 schema 解释，不能用最新常量重释旧证据。未来确需改变这些语义时新增 schema 版本并继续支持旧版本，未知版本 fail closed；不得为了迁移而批量重算旧 receipt 指纹。

waiver 的 `evidence_version` 同样冻结原始诊断到语义发现的映射和指纹算法；历史记录必须按自身 evidence version 验证。新增候选语义时新增并并行支持新的 evidence version，未知版本 fail closed，不能用当前解析器重新解释旧 waiver。

从不含审阅者和资源快照的旧账本迁移时，不得猜测历史审阅身份。schema v4 对全部 receiptless 兼容条目冻结论文 ID 和完整条目指纹，其中 `historical-v2-reviewer-unrecorded` 还受独立历史 allowlist 约束；代码中的冻结全集不可增长，必须精确分成仍活跃的 receiptless 条目和账本中已有当前 receipt 支撑的退役条目，不能保留未归属 ID 作为未来新增入口。schema v3 迁移的普通 receiptless 条目也只能在真实 PDF 对照后由带 receipt 的普通 accept 原子替换并退役旧指纹。`pending-v3-re-review` 与 `legacy-migration` 均不是有效的当前账本值。在用户已授权的历史复审范围内，用 `scripts/papers.py review-queue` 对 receiptless、历史和 waiver 项按风险排序；队列不授予复审权限，也不用批量伪造 receipt 消除债务。代码内冻结清单、账本退役映射和 schema 属于受 Git 评审约束的维护权限边界，不是密码学签名；对抗恶意维护者需要仓库外签名或受保护分支机制。

accept 用带指纹的 `config/.acceptance-transaction.yaml` 协调账本和 `paper.yaml` 两个权威文件，并对文件和目录项执行持久化同步。事务完成时先把活动日志原子改名为 `config/.acceptance-transaction.cleanup.yaml` 并同步目录，形成删除前的持久恢复锚点；随后才删除 cleanup marker。任一事务 marker 残留都是硬失败；只能按 review workflow 使用 `recover-acceptance --mode commit|rollback` 恢复，不得手工删除、改写或纳入提交。

## 环境准备

`make doctor` 检查项目所需工具及版本。维护环境需要 Python 3.11+、pip 25.1+ 和 `pyproject.toml` 的 `dev` dependency group（Markdown 解析器及其 URL 依赖、用于摘要化风险指标的 pypdf 均锁定精确版本，另含 PyYAML、Pillow）、Node.js 与 npm、`package-lock.json` 锁定的 MathJax、GNU Make 3.81+、ripgrep、Poppler（`pdfinfo`、`pdftotext`、`pdftoppm`）、Perl 5.30+，以及兼容 POSIX 选项的 `sed`、`awk`、`find`、`sort`、`mktemp`。CI 固定使用 Ubuntu 24.04；pypdf 6.14.2 提供跨平台一致的正文词数，Poppler 的布局文本继续用于 Listing、资源和参考文献等候选发现，其原始测量不作为跨平台 waiver 身份。

macOS 可执行 `brew install make ripgrep poppler perl node`，再执行 `python3 -m pip install --upgrade "pip>=25.1"`、`python3 -m pip install --group dev` 和 `npm ci`。读者可见标题约定变化时使用 `make normalize-headers` 做机械迁移。公式修复必须按 `docs/portable-math-maintainers.md` 限定文件范围，并显式运行 `make fix-math FILES='...'`；`make check` 只读，不修改译文。

## 验证

```bash
make doctor
python3 -m py_compile scripts/*.py
node --check scripts/render_mathjax.cjs
make check
make deep-check  # 修改校验器或全局翻译策略时
make diff-check
```

`make check` 内含锁定版本 MathJax 的本地 TeX 结构门禁。accept 对当前译文额外执行 GitHub 节点审计后才允许写入；未运行 accept 的其他变更译文仍须按 `docs/portable-math-maintainers.md` 执行限定文件范围的审计。公式校验器或全局公式策略变更执行全库 `make math-audit-github`，并在推送后的真实 GitHub 文件页检查最终显示。外部审计依赖已登录的 `gh` 和网络，因此不纳入无网络的 `make check`，由 CI 对变更译文重复执行；VS Code/KaTeX 仅为可选诊断，不能驱动有损公式改写。审计结果必须在完成报告中明确列出。

校验器、依赖或流程实现变化时，`make deep-check` 可以扫描整个仓库以识别实际受影响论文，但该只读检查不等于全库复审授权。无确定性历史影响时保留既有验收；存在确定性影响时按 paper ID 做范围修复与复审；只有用户明确要求时才把影响范围扩展为全库逐篇内容复审。

CI 的 `archive-check` 保持同一个必需检查名，但按差异选择最小安全范围：普通文档、目录和配置快照变更运行 `make check`；论文的 `paper.yaml`、`source.pdf`、`translation.md` 或 `assets/` 变化再对现存的受影响 paper ID 逐篇运行 `make paper-check`；只有深度校验器、依赖锁、`config/policy.yaml`、全局翻译策略、CI 范围选择逻辑发生变化，无法取得可信比较基线，或维护者手动触发时才运行全库 `make deep-check`。不得把 `config/acceptance.yaml` 的正常单篇验收更新或测试文件变化升级为全库扫描。
