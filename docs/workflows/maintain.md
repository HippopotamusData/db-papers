# 工作流：项目维护

## 目标

在不破坏论文资产的前提下，维护 `paper.yaml` 契约、项目策略、分类法、当前
校验器和读者站。仓库只保存当前内容与当前规则；Git 保存历史，不建立平行的
发布版本数据库。

## 成功标准

- `paper.yaml` 保持七个必填字段，只允许评分工作流定义的可选 `rating`。
- `config/policy.yaml` 和 `config/taxonomy.yaml` 通过强类型 schema 校验。
- 目录或主题变化同步更新配置、文档、校验器和受影响记录。
- 原文、译文和资源不因结构调整而改变，相对资源链接仍有效。
- 生成文件由脚本重建，不手工修补。
- 普通变更通过 `make check` 和 `make diff-check`；改变内容解释、发布语义或
  全局校验器行为时改用带原因的 `make deep-check`。

## 持久数据边界

各类证据与存储位置统一见 [AGENTS.md](../../AGENTS.md#evidence-and-canonical-storage)。
维护时不新增平行版本账本、内容摘要注册表、per-paper waiver、流程日志或历史
schema reader；旧规则和旧证据从 Git 历史读取，不作为当前运行时输入。

## 规则设计

确定性约束和受控码以 `scripts/project_config.py` 及对应校验器为事实来源，不在
多个配置副本中重复。配置只保存真正可变的值；固定文件名、目标语言和质量底线
不是开关。

改变必填字段、评分结构、策略或分类法时，一次更新模板、文档、脚本、测试和
生成目录。不要为单篇论文增加临时字段。

校验分两类：

- **硬失败**：文件/状态不一致、不可读 PDF、坏资源路径、缺失读者载荷、非法
  Markdown 结构、公式静态错误等不存在合理例外的确定性问题。
- **warning**：覆盖率、引用编号差、资源或 Listing 数量差、人称计数、PDF
  抽取顺序等需要人工回到 PDF 判断的启发式信号。

`draft` 允许不完整载荷，过程残留和内容缺口以 warning 帮助继续工作；进入
`translated` 前须消除确定性缺陷。公式静态兼容错误在两种状态都失败，细节由
[公式维护指南](../portable-math-maintainers.md) 定义。某条规则需要逐篇例外才能
工作时应降为 warning；确定性规则误报应修实现，不添加永久 waiver。

摘要化候选的源文词数由仓库锁定版本的 pypdf 确定性抽取；计数和比例仅用于
诊断。Markdown 侧覆盖与结构统计先排除 HTML 注释；代码中的同形字符仍是
读者载荷。Poppler 布局抽取辅助 Listing、资源与参考文献扫描，平台布局差异
不得升级为确定性缺陷。机械信号只进入当前输出和审阅报告，不进入论文元数据。

修改全局解析器、章节边界或确定性启发式时，回归测试至少覆盖正例、负例和空
内容边界，并对当前论文全集运行只读影响扫描。不能只围绕触发修复的单篇样例
设计规则。

修复误报时先区分源文抽取、Markdown 关联与实际内容缺失：双栏/多栏参考文献
须按栏恢复阅读顺序；代码清单只取相邻代码载荷，不能把另一栏正文纳入比较；
连续图表须按图注与载荷的实际排列关联。回归同时保留真实缺项、重复编号、
不完整载荷的告警能力，不通过降低阈值或按论文 ID 豁免来消除告警。图内表名、
合法的分节式表格等无法可靠机械区分的情形，保留候选并回源处置。
跨页清单若无法可靠恢复完整代码，必须提示源窗口可能不完整；不得以截断窗口
的高重合率作为完整性证据。修改代码边界后同时回归大小写、续行和跨页情形。

## AI 工作文档维护

文档归属以 [AGENTS.md 的规则归属表](../../AGENTS.md#rule-ownership-and-document-updates)
为准。本节只规定更新流程；维护其他模块时无需预读文末的文档验收案例。

1. **定位**：写明本次改变的决策或交付行为，查找归属文档中的现有条款及调用位置。已有条款覆盖的新发现只留在任务报告；新边界优先合并到现有条款。
2. **修改**：在归属文档定义判据、适用范围和例外。调用文档仅说明本角色何时执行、交付什么，并链接具体小节；同步删除重复定义和过期表述。涉及多个关注点时分别落到各自归属文档，不把全文复制过去。
3. **核对**：对照修改前后，确认权限、证据、质量标准、状态和门禁没有意外变动；检查链接和按任务加载路径。给角色明确结果与证据，保留方法选择空间，不增加无依据的全篇重读或审批次数。
4. **验收**：选取受影响的任务情形，用最终文档逐步推演输入、动作、停止条件和交付。文末 [行为验收案例](#行为验收案例) 可按需选用；实际结果留在任务报告/PR。文案整理按顶层门禁选择验证，不为低影响文本增加复述实现的测试。

## Git 与发布模型

`reading_status: translated` 表示当前 Git revision 中的译文已经人工审阅并通过
当前确定性门禁。站点只按该状态选择译文；`main` 的 `check` 成功表示同一 SHA
已经通过归档检查和 push-side GitHub 公式审计。站点构建与归档检查并行，
部署等待两者成功，随后核验线上页面和静态资源与同 SHA 的构建产物一致。

内容变化不依赖额外摘要锁来确认发布状态。PR 或 push 的 Git diff 直接定位受影响
paper ID，并运行 `paper-check`；严格的独立身份要求应由 GitHub required reviewer
实现，而不是由提交者可同时填写的元数据模拟。

`pull_request_target` 公式审计及其受保护运行时代码属于 CI 信任边界。普通 PR
会拒绝这些文件的差异；只有用户明确授权信任边界更新时，维护者才可在完成本地
全库门禁后使用管理员 bypass 直接落地主分支，并继续等待同 SHA 的 `check` 和
Pages 部署。不得在同一 PR 中放宽保护来让自身通过。

批次 manifest 只允许放在 gitignored 的 `tmp/batches/`，仅用于当前任务分派和
恢复，不参与论文状态、校验或发布判断。

## 环境准备

`make doctor` 检查 Python 3.11+、pip 26.1.2、锁定的 dev dependency group、
Node.js/npm、MathJax、GNU Make、ripgrep、Poppler 和 Perl，但不安装依赖。
每个 worktree 独立拥有普通目录 `.venv/` 和 `node_modules/`，不得用符号链接
共享可写安装目录。新 worktree 或锁文件变化后显式运行：

```bash
make bootstrap
```

只构建 GitHub Pages 时使用精简的 site 环境：

```bash
make bootstrap-site
```

两个命令都可幂等重跑；`make check`、`make site-check` 和其他门禁不会隐式联网
安装依赖。

## GitHub Pages

`scripts/build_site.py` 从 `paper.yaml` 和 `config/taxonomy.yaml` 生成一次性的
`site_src/` 与 `site.generated.toml`，Zensical 构建到 `site/`。这些产物不得
提交或手工维护。

读者站发布 `reading_status: translated` 的译文、对应 `source.pdf` 和正式
资源；未完成译文、维护配置、脚本和测试不进入 artifact。

```bash
make site-serve   # 启动独立预览
make site-refresh # 修改源配置、样式或生成器后刷新预览源文件
make site-check   # 最终构建与链接验收
# 首次运行浏览器测试需显式准备环境：
npm ci
npx playwright install chromium
make site-test    # site-check + 读者交互回归
```

预览的源文件、生成配置、构建缓存和输出均位于 `.preview/`，与验收用的
`site_src/`、`site.generated.toml`、`site/` 隔离。刷新保留被监听的源目录，只同步
变化文件，避免删除目录导致持续预览停止响应。编辑迭代时使用预览刷新；
提交前再按变更范围运行最终门禁。预览不替代验收，也不保存跨提交的验收结果。

`check` workflow 的 `archive-check` 与 `site-build` 并行，PR 只构建不部署。
主分支每次推送都重新完整构建本站，不复用 PR artifact。`deploy` 只在主分支
且这两个 job 成功后运行。独立的 `pull_request_target` 公式审计保持受信任边界。
站点实现、前端依赖或浏览器测试变化时，PR 和主分支运行 Chromium 回归，覆盖筛选后直接点击、返回保留条件、PDF 链接和窄屏布局。

部署后，`scripts/site_smoke.py` 核验首页、目录、代表论文页及其本地 CSS/JS
的 SHA-256 与本次 artifact 相同，最多重试六轮，每轮间隔十秒。预期值只通过
当前运行的 job output 传递，不保存仓库版本账本。失败会使发布运行失败；成功
后在 Actions summary 记录 SHA 和核验数量。外部 CDN 依赖不属于本站 artifact。
站点故障优先 revert 导致故障的仓库提交，不直接修改 artifact。

仓库可启用 auto-merge；仅对已获发布授权的具体 PR 设置，等待 required checks
与分支规则满足后合并。合并后仍须等待该 SHA 的检查、部署和线上核验。

## CI 范围

- 每次 PR 和默认分支推送运行完整单测、元数据、标题和目录门禁。
  普通变更使用 `make check`；全库深检触发时以
  `make test _deep-validate-check _catalog-check` 替代快速扫描，不重复运行两遍。
- 同一次译文检查批量准备读者可见 Markdown、叙述提示和标题检查，减少重复解析；
  临时结果只供当次调用使用，深检、单篇检查与公式渲染仍保留各自门禁。
- `source.pdf`、`translation.md`、`assets/` 或影响发布语义的 `paper.yaml`
  变化时，对相应 paper ID 运行 `paper-check`。
- 仅 `title_zh`、`topics` 或 `rating` 变化时，运行快速元数据、目录和站点检查。
- 变更译文运行限定文件公式门禁；公式 profile 或实现变化时升级为全库检查。
- 差异基线无法可信确定时直接失败，不猜测范围。

## 验证

```bash
make doctor
make python-compile
node --check scripts/render_mathjax.cjs
make check
# 改变内容解释、发布语义或全局校验器时改用：
# make deep-check DEEP_REASON=<content-semantics|publication-semantics|validator-semantics|full-audit>
make diff-check
# 站点生成器、主题或 Pages workflow 变化时：
make site-check
```

深检是 `make check` 的替代项，不叠加运行。机械全库检查不授权全库内容复审；
报告实际检查范围和发现；是否扩大历史内容复审仍由用户授权决定。

## 行为验收案例

仅在修改相关指导时按需使用。下表检验既有归属规则如何被调用，不另设权限或
质量标准；案例通过也不构成翻译正确性的证明。

| 输入情形 | 依据与期望行为 |
| --- | --- |
| 又发现一处 `and/or` 误译，现有质量标准已经覆盖 | 按顶层归属规则记录实际缺陷和修复，不在 policy、translate、review 各追加一条提醒 |
| 发现现有规则未说明的跨公式编号问题 | 在 policy 的结构要求中补充边界；translate/review 通过既有调用检查，不复制判据 |
| 审阅者称原文无 `not`，但 PDF 和提取结果都有 | review 要求修改者独立核源、驳回错误发现；若字形证据冲突，按 policy 放大重取证，不猜原文异常 |
| 新论文、已有基线的一处限定修复、仅 EOF 空行三种任务 | review 风险表分别要求首次完整两轮、改动及关联论证复核、diff 与相关呈现检查；不互相替代或一律重审全文 |
| 只抽查一个证明分支，或用户要求重大问题优先且有条件修复 | 按 review 报告实际范围和严重程度；按顶层权限与已有约定决定是否写入，不因完成抽样擅自修复或声称全篇通过 |
| 完整处理新论文，当前刚开始入库 | 按顶层路由依次加载 ingest、translate、review、rating，已有授权下不中断交接 |
| 批次中一篇停止写入、另一篇仍在翻译 | batch 允许前一篇进入独立审阅；共享生成、仓库级检查和提交等待写入者全部停止 |
| 最后一轮交付、随后 squash 发布 | 按 batch 提交最终候选后运行 clean-HEAD 门禁，不预先重复同套检查；按授权交付分支，合并与部署成功后再快进本地 main |

### 设计参考

本组提示词依据 OpenAI 官方 [GPT-6 Astra：Prompting best practices](https://developers.openai.com/api/docs/guides/latest-model#prompting-best-practices)
和 [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
（2026-09-19 核验）。官方建议审查指令冲突、按任务加载资料、明确分工与完成边界，
并让验证规模匹配实际风险。项目的 PDF 核源和复核划分是本项目的工程决策，
不是 OpenAI 对论文翻译的专门规定，也不保证模型不再误读。
