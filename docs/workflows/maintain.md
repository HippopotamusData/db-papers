# 工作流：项目维护

## 目标

在不破坏论文资产的前提下，维护六个必填字段、可选评分、目录分类、主题词表、校验器和生成目录。

## 成功标准

- `paper.yaml` 仍严格保持六个必填字段，并且只允许评分工作流定义的可选 `rating`。
- 目录或主题变化同时更新配置、文档、校验器和受影响记录。
- 生成文件由脚本重建，不手工修补统计。
- `config/project.yaml`、`config/taxonomy.yaml`、`config/paper-policy.yaml` 与 `config/acceptance.yaml` 都通过版本化强类型 schema 校验。
- 已有原文、译文正文和资源不因结构调整而改变；相对资源链接仍有效。
- `make check` 通过，`make diff-check` 对 tracked、staged 和 untracked 文件均无格式错误。

## 变更规则

确定性约束优先进入脚本，不通过更长提示词反复提醒。只有会被多篇论文复用并改善阅读的概念才进入分类法。

若要改变必填字段或可选评分结构，必须由用户明确选择，并一次性更新模板、文档、脚本和生成目录。不要为单篇论文添加临时字段。`docs/` 只保留当前规则和工作流；旧规则、迁移记录和审校过程通过 Git 历史追溯，不得作为当前状态输入。

页数例外、skipped 原因和验收记录属于项目级治理数据。单篇页数例外必须包含 paper ID、允许页数和用户授权原因；`over-page-limit`、`out-of-scope`、`explicit-user-skip` 是当前 reason code。源文或译文发生实质变化时先迁移到 `draft`，旧账本哈希不得继续支持 `translated`。

## 环境准备

`make doctor` 检查项目所需工具及版本。维护环境需要 Python 3.11+、pip 25.1+ 和 `pyproject.toml` 的 `dev` dependency group、GNU Make 3.81+、ripgrep、Poppler（`pdfinfo`、`pdftotext`、`pdftoppm`）、Perl 5.30+，以及兼容 POSIX 选项的 `sed`、`awk`、`find`、`sort`、`mktemp`。

macOS 可执行 `brew install make ripgrep poppler perl`，再执行 `python3 -m pip install --upgrade "pip>=25.1"` 和 `python3 -m pip install --group dev`。读者可见标题约定变化时使用 `make normalize-headers` 做机械迁移；`make check` 会检查规范标题和译者说明。

## 验证

```bash
make doctor
python3 -m py_compile scripts/*.py
make check
make deep-check  # 修改校验器或全局翻译策略时
make diff-check
```
