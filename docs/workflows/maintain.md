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

- `paper.yaml` 保存当前阅读元数据和 `reading_status`。
- `config/policy.yaml` 保存当前页数策略、单篇授权例外和 skipped 原因。
- `config/taxonomy.yaml` 保存当前受控领域与主题。
- `source.pdf`、`translation.md` 和 `assets/` 保存读者内容。
- Git commit 保存内容版本；PR、提交和任务报告保存审阅过程。

不要新增平行版本账本、内容摘要注册表、per-paper waiver、流程日志或历史
schema reader。旧规则和旧证据需要时从 Git 历史读取，不作为当前运行时输入。

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

不保存永久 waiver。某条规则需要逐篇例外才能工作时，应降为 warning；确定性
规则出现误报时，应修正规则本身。

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

本组提示词依据 OpenAI 官方 [GPT-6 Astra：Prompting best practices](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#prompting-best-practices)
和 [Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
（2026-09-16 核验）。官方建议审查指令冲突、按任务加载资料、明确分工与完成边界，
并让验证规模匹配实际风险。下面的 PDF 核源和复核划分是本项目的工程决策，
不是 OpenAI 对论文翻译的专门规定，也不保证模型不再误读。

- `AGENTS.md` 保留路由、权限和证据底线；policy 定义翻译质量，translate 定义
  交稿条件，review 定义发现采纳与复核，batch 只负责协调。修改时同步移除冲突
  规则，不把同一段提示重复塞入每份文件。
- 给角色明确的结果和可核验证据：审阅者提出可复现的发现，修改者独立核源，
  复核者验证最终内容。保留方法选择空间，不用增加“必须全篇重读”的次数代替
  检查具体误读。已有授权覆盖后续步骤时继续完成，不新增审批节点。
- 将真实风险与文风偏好分开；用上下文判断作者视角，不用代词数量或逐词补齐
  模拟忠实度。报告实际检查范围和未决证据，避免无依据的“全部通过”。

修改提示词时，用以下情形检查规则是否给出清楚、一致的行动；这些是行为验收
案例，不是机械测试通过即可证明翻译正确的断言。实际回放结果留在任务报告/PR。

| 输入情形 | 期望行为 |
| --- | --- |
| `we can see` 译作“可以看到”，上下文主体明确 | 接受自然省略，不为补“我们”返工 |
| 连续作者自述被改成“作者认为／作者提出” | 检查并修复系统性的第三人称转述 |
| 审阅者称原文无 `not`，PDF 与提取文本都有 `not` | 修改者驳回该发现，保持否定；复核证据而非投票 |
| 图像识读、提取文本或表格标识符相互矛盾 | 放大具体区域并重取证据；未解决前不宣称原文异常 |
| 原文确有可确认的公式或数字矛盾 | 忠实保留，必要时用短注隔离，不擅自修正 |
| 仅 EOF 空行或等价换行格式变化 | 交审前发现并修复；按格式变化验证，不重审全文 |
| 只核对了一个证明分支 | 报告该范围，不能声称完成全篇审阅 |
| 图注全文在图片 alt 中，图片正常显示时看不到 | 移到相邻可见正文并核验渲染；已有独立图注则不重复添加 |
| 原文 similar/with 被译成“相同／只有……才能” | 回源核对限定强度，不批量替换所有相同词语 |
| 性能数字正确，但默认配置或调优条件遗漏 | 恢复实验条件，并核对关联性能结论 |
| 比较三个系统，原文 `both` 仅指后述两个商业系统 | 沿上下文确定指代，不把关闭锁或日志等配置推广到三个系统 |
| 译文增加一段合理的架构总结，原文没有对应段落 | 删除补写，回查相关章节，确认没有以总结替换源文细节 |

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
只报告被确定性证据点名的 paper ID，是否扩大修复范围仍由用户决定。
