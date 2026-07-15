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

默认页数上限、单篇例外和 skipped 原因集中在 `config/policy.yaml`。单篇页数例外必须包含高于默认值的 `max_source_pages` 和用户授权依据 `authorization`；跳过原因使用代码定义的受控值。验收账本是当前已验收版本的快照，只保存文件哈希、一个受控 `review_action` 和与当前机械候选精确匹配的受控 `waivers`；重新验收会替换旧条目。源文或译文发生实质变化时先迁移到 `draft`，旧账本哈希不得继续支持 `translated`。

## 环境准备

`make doctor` 检查项目所需工具及版本。维护环境需要 Python 3.11+、pip 25.1+ 和 `pyproject.toml` 的 `dev` dependency group、GNU Make 3.81+、ripgrep、Poppler（`pdfinfo`、`pdftotext`、`pdftoppm`）、Perl 5.30+，以及兼容 POSIX 选项的 `sed`、`awk`、`find`、`sort`、`mktemp`。

macOS 可执行 `brew install make ripgrep poppler perl`，再执行 `python3 -m pip install --upgrade "pip>=25.1"` 和 `python3 -m pip install --group dev`。读者可见标题约定变化时使用 `make normalize-headers` 做机械迁移；可移植公式规则变化时使用 `make normalize-math`。`make check` 会同时检查规范标题、译者说明和公式规范化漂移。

## 验证

```bash
make doctor
python3 -m py_compile scripts/*.py
make check
make deep-check  # 修改校验器或全局翻译策略时
make diff-check
```

公式校验器或全局公式策略变更还应按 `docs/translation-policy.md` 执行 VS Code 同版 KaTeX 与 GitHub Markdown API 实际渲染审计。外部审计依赖本机 VS Code 运行时、已登录的 `gh` 和网络，因此不纳入无网络的 `make check`；审计结果必须在完成报告中明确列出。
