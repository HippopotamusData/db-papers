# 工作流：项目维护

## 目标

在不破坏论文资产的前提下，维护六个必填字段、可选评分、项目策略、分类法、验收账本、校验器和生成目录。

## 成功标准

- `paper.yaml` 仍严格保持六个必填字段，并且只允许评分工作流定义的可选 `rating`。
- 目录或主题变化同时更新配置、文档、校验器和受影响记录。
- 生成文件由脚本重建，不手工修补统计。
- `config/policy.yaml`、`config/taxonomy.yaml` 与 `config/acceptance.yaml` 都通过版本化强类型 schema 校验。
- 已有原文、译文正文和资源不因结构调整而改变；相对资源链接仍有效。
- 普通变更通过 `make check`；校验器或全局策略变更改用 `make deep-check`。所有变更都通过 `make diff-check`。

## 变更规则

确定性约束和受控码以 `scripts/project_config.py` 为事实来源，不在提示词或多个配置副本中重复。配置只保存真正可变的值；固定文件名、目标语言和质量底线不是开关。只有可被多篇论文复用且改善阅读的概念才进入分类法。

改变必填字段或评分结构必须由用户明确选择，并一次更新模板、文档、脚本和生成目录。不要为单篇论文增加临时字段。`docs/` 只保留当前规则和工作流；旧规则、迁移及审校过程由 Git 历史追溯，不作为当前状态输入。

默认页数上限、单篇例外和 skipped 原因集中在 `config/policy.yaml`。单篇页数例外必须包含高于默认值的 `max_source_pages` 和用户授权依据 `authorization`；跳过原因使用代码定义的受控值。

`config/acceptance.yaml` 是当前验收快照，不是事件日志。每个 entry 都是可验证 receipt。当前 v2 保存内容和元数据哈希、动作、译者与独立审阅者、固定基线、`review_head_sha`、非空 findings、作者性叙述计数及 waiver 证据。
固定检查清单和身份保证由 schema 定义，策略与门禁从 `review_head_sha` 重建。详细迁移和逐段修改只由 Git 历史保留，不另建索引或日志。

评分总分和五个分项只保存在对应论文的 `paper.yaml.rating` 中，不另建评分 sidecar、registry 或 receipt。评分工作流仍要求核验原文和外部证据，但这些依据只在当前任务的完成报告中简述，不扩充单篇元数据结构。

验收绑定脚本、依赖锁、策略和 review/batch-review 程序。它们必须与 `review_head_sha` 指向的提交一致；receipt 之后这些输入或 HEAD 改变，就必须重新生成 receipt。源文、译文、资源或受审书目信息改变时，论文先回到 `draft`。
运行时或策略变化本身不否定历史验收；只处理被新证据明确点名的论文，扩大历史复审范围仍需用户授权。

receipt schema 冻结检查项、受审字段、动作和身份保证；waiver evidence version 冻结诊断语义和指纹算法。历史记录按自身版本验证，未知版本 fail closed。不得用当前解析器重释、猜测或批量重算历史证据。
历史 v1 的空或通用 findings 只作为冻结证据读取，并由 `review-queue` 标记。新 v2 receipt 必须有 PDF 核对结论、完整作者性叙述计数和精确 waiver 指纹。

不同分支不得并行维护验收状态；批次由根代理串行 accept。任一 acceptance transaction marker 都是硬失败。按 review workflow 执行 `recover-acceptance --mode commit|rollback`，不要手工删除、改写或提交 marker。

## 环境准备

`make doctor` 检查项目工具和版本。维护环境需要 Python 3.11+、pip 26.1.2、精确锁定的完整 `dev` dependency group、Node.js/npm、锁定的 MathJax、GNU Make 3.81+、ripgrep、Poppler、Perl 5.30+ 及兼容 POSIX 选项的基本文本工具。
CI 固定使用 Ubuntu 24.04。锁定的 pypdf 提供跨平台正文计数；Poppler 布局文本只生成候选，不定义 waiver 身份。

macOS 执行 `brew install make ripgrep poppler perl node`，再在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade "pip==26.1.2"
.venv/bin/python -m pip install --group dev
npm ci
```

依赖只装入项目虚拟环境。标题约定变化时用 `make normalize-headers` 机械迁移。公式专项修复按 `docs/portable-math-maintainers.md` 限定文件，并显式运行 `make fix-math FILES='...'`；`make check` 只读。

`scripts/validate_ci_trust.py` 是 `pull_request_target` 从默认分支执行的信任根，并绑定其调用的公式审计脚本。普通 PR 不得修改这些文件。更新信任基线需要明确授权的管理员变更、定向测试、`make deep-check` 和 `make diff-check`。

## 验证

```bash
make doctor
make python-compile
node --check scripts/render_mathjax.cjs
make check       # 普通变更
# 或 make deep-check  # 校验器、全局翻译策略或明确的全库审计
make diff-check
```

`make deep-check` 是 `make check` 的深检替代项，不叠加运行。两者都包含锁定 MathJax 的本地 TeX 结构门禁；accept 还会在写入前审计当前译文的 GitHub 节点。
未 accept 的公式专项变更、公式校验器或全局公式策略变更按公式维护指南执行限定范围或全库审计。外部审计依赖 `gh` 和网络，由 CI 重复执行；结果必须写入完成报告。

校验器、依赖或流程实现变化时，`make deep-check` 扫描全库并列出受影响论文，但不授权全库复审。无确定性历史影响时保留既有验收；有明确影响时按 paper ID 修复和复审。只有用户明确要求时才扩展为全库逐篇内容复审。

CI 的 `archive-check` 保持同一个必需检查名：

- 每次运行都执行 `make check`，CI 不执行 `make deep-check`；
- 论文内容或元数据变化时，再对受影响 paper ID 运行 `paper-check`；
- acceptance entry 的局部变化按可信 base/head 精确计算 paper ID；
- acceptance 差异无法可靠定位时直接失败，不猜测 paper ID。

`make deep-check` 只在本地用于校验器、依赖锁、policy、全局翻译策略、CI 选域逻辑变更或明确的全库审计；不要把它加入 CI。
