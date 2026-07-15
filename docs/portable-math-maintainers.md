# GitHub-first 公式维护指南

## 契约

GitHub 正确解析和渲染是唯一硬平台要求。仓库仍采用 `$...$`、独占行 `$$` 和标准自包含 TeX，使 VS Code、Obsidian、Typora、GitLab 等主流阅读器通常可直接显示；这些平台只做 best-effort 抽查，不得驱动有损的数学改写。

`docs/translation-policy.md` 只保留 AI 代理和译者必须遵守的最小规则。本文面向维护工具，平台细节不得复制回主翻译规范。

## 工具分层

1. `scripts/validate_github_math.py` 只读解析 Markdown 与公式，执行 GitHub 边界、容器、分隔符、TeX profile 和表格检查。
2. `scripts/fix_portable_math.py` 只在显式 `fix --safe` 下插入少量 opening `$` 前的 ASCII 空格。
3. `scripts/verify_math_rendering.py` 使用仓库锁定的 MathJax 做本地 TeX 结构门禁，并负责 GitHub Markdown 公式节点审计；KaTeX 模式仅用于可选的编辑器兼容诊断。

扫描器使用 `markdown-it-py` 识别 fenced/indented code、列表和引用容器、HTML code block、链接、图片与强调；代码跨度继续按精确反引号长度屏蔽。验证、修复与外部审计共享同一个公式提取实现。

## 安全修复证明

自动修复只允许：在已识别的普通行内公式前，且前一字符属于汉字或白名单中的中英文结束/分隔标点时，插入一个 ASCII 空格。全角左括号、其他 Unicode 字母、数学符号和 emoji 不属于安全前驱字符。

每个文件写入前必须同时满足：

- 输出只包含预先声明的插入区间；
- TeX 载荷、公式顺序和 inline/display 类型逐字不变；
- Markdown token 结构不变；
- 公式所在的非兼容容器集合不变；
- 第二次运行无差异。

多文件修复先读取并验证全部文件，再把所有候选写入同目录临时文件；单文件替换使用原子 rename，批次中途失败则回滚已替换文件。以下内容永不自动修改：

- TeX 载荷、分隔符或块缩进；
- 数学、LaTeX 或 TeX fence；
- 强调、链接、脚注、图片说明和代码；
- `paper.yaml` 与验收账本。

粗体公式 `**$x$**` 属于允许写法，但修复器不会触碰其强调标记。`*$x$*`、`Top-$k$`、未闭合 fence、列表内 display math 等歧义结构则只报告，不修复。

## GitHub profile

静态门禁包含以下层次：

- opening/closing 边界、成对美元符号和独占行 display delimiter；
- `F1@ $k$`、`Top- $k$` 等因边界修复而被可见空格拆开的 ASCII 标签；这类标签必须按原义整体写入同一公式；
- `** $x$-标签**` 等因插入空格而失效的强调；删除错误插入的空格以恢复允许的 `**$x$-标签**`，或人工改写标签，不得留下裸露的 Markdown 标记；
- 斜体、链接文字、脚注定义、图片 alt 与 raw HTML 等 GitHub 不解析公式的容器；
- GFM table delimiter row 建立的表格上下文，外侧管道可省略且容器边界不可跨越；
- GitHub Markdown 会消费的 TeX 转义、裸 `<`/`>`、反引号、`~~`、`\operatorname`、宏配置和未验证命令；
- GitHub Markdown 会当作强调语法的裸 `*`，以及可与同段其他下划线配对的 `_`；ASCII 字母数字两侧的 intraword `_` 可保留，其他下标运算符写成 ` _ `，使其既不能打开也不能关闭 emphasis；
- GitHub 会优先识别的 URL 和邮箱 autolink；这类内容应移出公式；
- GitHub 会先于公式节点处理的脚注引用、实际成立的 Markdown 链接或图片，以及 HTML entity；
- GitHub 会抑制公式节点的已知 token。

仓库内的 TeX command allowlist 是 GitHub 已验证 profile，不是完整 LaTeX。新增命令必须先加入最小失败/成功测试，再在 GitHub 页面 canary 中确认最终显示，随后才能扩展 profile。类似 `selec{}t` 或 `\char` 的编码只能用于保持原字符含义的人工修复；不得自动生成，也不得用于改变变量、大小写、下标归属或运算关系。

## 命令与审计

```bash
npm ci
make math-check
make fix-math FILES='papers/<area>/<paper-id>/translation.md'

# 需要已登录 gh 和网络；单篇或一批变更必须限定 FILES
make math-audit-github FILES='papers/<area>/<paper-id>/translation.md'

# 全库 profile/迁移才省略 FILES
make math-audit-github

# 可选，不是验收门禁
make math-audit-katex KATEX_MODULE='/path/to/katex'
```

`make check` 和 `make deep-check` 都包含只读 `math-check`：静态解析后，用 `package-lock.json` 锁定的 MathJax 对每个 TeX 载荷做结构渲染。该本地门禁捕获括号、命令参数、`\left`/`\right` 与环境配对等错误，但不代替 GitHub 自身的 Markdown 解析。

GitHub 的链接化和 Markdown 规则会随上下文组合，无法靠静态规则穷举。每个变更译文在验收或提交前必须运行限定 `FILES` 的 GitHub Markdown API 审计；CI 根据 Git diff 重复这项检查。公式 profile、扫描器、审计器、MathJax 锁或工作流发生变化时，CI 自动升级为全库审计；全库迁移也运行不带 `FILES` 的审计。

普通 `pull_request` 检查不接收 API token。带只读 token 的外部审计由默认分支上的受信任脚本运行；PR worktree 只作为 Markdown 数据读取，禁止执行其中的脚本、依赖或配置，并拒绝符号链接和非普通输入。该审计只信任仓库既定的 `$`/`$$` 边界提取，不信任 PR 自己修改的 TeX allowlist；PR 内的新静态规则仍由无 token 的普通 CI 验证。

GitHub Markdown API 审计证明 GitHub 为每个公式创建节点且未改写载荷；它不执行网页端最终渲染。因此 profile 或全库迁移发生变化时，还必须在推送后的真实 GitHub 文件页检查错误提示。KaTeX 失败不能单独成为改写数学语义的理由。

## 变更要求

每个解析差异先落最小回归用例，再修改实现。测试至少覆盖：代码与 HTML code、列表/引用 fence、跨行 code span、链接 destination 与文字、斜体/粗体、脚注、图片 alt、带与不带外侧管道的表格、容器边界、安全修复字节范围与幂等性。

修改 profile、扫描器、修复器或全库公式后运行：

```bash
make doctor
python3 -m py_compile scripts/*.py
node --check scripts/render_mathjax.cjs
# 仅当 render_katex.cjs 或可选 KaTeX 审计路径变化时运行：
node --check scripts/render_katex.cjs
make check
make deep-check
make diff-check
make math-audit-github
```
