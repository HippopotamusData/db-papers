# GitHub-first 公式维护指南

## 契约

GitHub 正确解析和渲染是唯一硬平台要求。仓库仍采用 `$...$`、独占行 `$$` 和标准自包含 TeX，使 VS Code、Obsidian、Typora、GitLab 等主流阅读器通常可直接显示；这些平台只做 best-effort 抽查，不得驱动有损的数学改写。

`docs/translation-policy.md` 只保留 AI 代理和译者必须遵守的最小规则。本文面向维护工具，平台细节不得复制回主翻译规范。

## 工具分层

1. `scripts/validate_github_math.py` 只读解析 Markdown 与公式，执行 GitHub 边界、容器、分隔符、TeX profile 和表格检查。
2. `scripts/fix_portable_math.py` 只在显式 `fix --safe` 下插入少量 opening `$` 前的 ASCII 空格。
3. `scripts/verify_math_rendering.py` 使用仓库锁定的 MathJax 做本地 TeX 结构门禁，并负责 GitHub Markdown 公式节点审计；KaTeX 模式仅用于可选的编辑器兼容诊断。

扫描器使用 `pyproject.toml` 锁定版本的 `markdown-it-py` 与 `mdurl`，识别 fenced/indented code、列表和引用容器、HTML code block、链接、图片与强调；代码跨度按精确反引号长度屏蔽，不把其中的字节冒充公式节点。活跃 `draft` 另启用窄范围 `GHM029` 风险门禁：数学运算符、完整渐近复杂度或下标向量若被放进代码跨度会直接失败；字段名和单变量等歧义内容留给 PDF 语义审阅。验证、修复与外部审计共享同一个公式提取实现。

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

## 受控全库公式迁移

改写 TeX 载荷的批量迁移不属于 `fix-math --safe`。对于 `\tag{N}` 迁移，迁移投影中允许的唯一变化是 `\tag{N}` 到 `\qquad \text{(N)}`。写入前冻结固定基线及 paper ID、公式位置和原编号清单；写入后逐文件重建固定基线的仅迁移投影，并要求其与仅迁移候选逐字节一致，同时核对公式数量、顺序、inline/display 类型、编号集合和正文引用未变。若完整 PDF 复核又发现当前授权范围内的独立非公式缺陷，应把这些修复另列清单；最终候选仍须按提取顺序逐项匹配仅迁移投影中的全部公式载荷，不得借附带修复改变公式。该证明只界定修改范围，不能替代逐篇 PDF 语义复核。

新规则、回归测试、文档和全部受影响论文必须出现在同一最终候选中。最终全库扫描不得残留旧语法，并运行不限定 `FILES` 的 GitHub 审计、完整全库门禁，以及推送后固定 commit 文件页的逐公式检查。

## GitHub profile

静态门禁包含以下层次：

- opening/closing 边界、成对美元符号和独占行 display delimiter；
- `F1@ $k$`、`Top- $k$` 等因边界修复而被可见空格拆开的 ASCII 标签；这类标签必须按原义整体写入同一公式；
- `** $x$-标签**` 等因插入空格而失效的强调；删除错误插入的空格以恢复允许的 `**$x$-标签**`，或人工改写标签，不得留下裸露的 Markdown 标记；
- 斜体、链接文字、脚注定义、图片 alt 与 raw HTML 等 GitHub 不解析公式的容器；
- GFM table delimiter row 建立的表格上下文，外侧管道可省略且容器边界不可跨越；表格发现只在表头遮蔽成对行内公式的载荷，正文持续到空行或新的 Markdown 块，再从原载荷报告会破坏表格结构的裸管道；表格中的 display math 直接失败；
- GitHub Markdown 会消费的 TeX 转义、裸 `<`/`>`、反引号、`~~`、`\operatorname`、宏配置和未验证命令；
- 任何公式中的 `\tag`：`GHM020` 无条件拒绝该命令。GitHub 文件页的 MathJax 会为它生成带 `mtable`/`mlabeledtr` 的 MathML 标签表，浏览器可能把公式内容挤进窄列并逐项纵向堆叠；本地 MathJax 和 GitHub Markdown 公式节点审计都可能通过，因此必须改用 `\qquad \text{(编号)}`，并在真实文件页检查最终布局；
- GitHub Markdown 会当作强调语法的裸 `*`，以及可与同段其他下划线配对的 `_`；ASCII 字母数字两侧的 intraword `_` 可保留，其他下标运算符写成 ` _ `，使其既不能打开也不能关闭 emphasis；
- GitHub 会优先识别的 URL 和邮箱 autolink；这类内容应移出公式；
- GitHub 会先于公式节点处理的脚注引用、实际成立的 Markdown 链接或图片，以及 HTML entity；
- GitHub 会抑制公式节点的已知 token。

仓库内的 TeX command allowlist 是 GitHub 已验证 profile，不是完整 LaTeX。新增命令必须先加入最小失败/成功测试，再在 GitHub 页面 canary 中确认最终显示，随后才能扩展 profile。GitHub 会消费公式源码中单个 `\_`、`\%` 和 `\#` 的反斜杠，双重转义虽然能把标准 TeX 转义送入公式节点，却会让可信节点审计无法逐字比较未信任的 PR 数据。仓库因此只允许 `\verb0_0`、`\verb0%0` 和 `\verb0#0` 三种完整形式来表示这些字面标点；数字 `0` 分隔符既不破坏 Markdown 表格，也能防止 GFM 把同一行多个字面下划线配成强调。它们会原样进入公式节点并由 GitHub MathJax 精确渲染。`\char` 会通过节点审计却在网页端渲染失败，属于确定性错误并被静态门禁禁止。类似 `selec{}t` 的拆词只可用于保持原字符含义的人工修复；不得自动生成，也不得用于改变变量、大小写、下标归属或运算关系。

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

GitHub 的链接化和 Markdown 规则会随上下文组合，无法靠静态规则穷举。accept 在写入账本和状态前自动对当前译文运行 GitHub Markdown API 审计；其他未经过 accept 的变更译文在提交前必须运行限定 `FILES` 的同一审计。CI 根据 Git diff 重复这项检查。公式 profile、扫描器、审计器、MathJax 锁或工作流发生变化时，CI 自动升级为全库审计；全库迁移也运行不带 `FILES` 的审计。

普通 `pull_request` 检查不接收 API token。带只读 token 的外部审计由默认分支上的受信任脚本运行；PR worktree 只作为 Markdown 数据读取，禁止执行其中的脚本、依赖或配置，并拒绝符号链接和非普通输入。该审计只信任仓库既定的 `$`/`$$` 边界提取，不信任 PR 自己修改的 TeX allowlist；PR 内的新静态规则仍由无 token 的普通 CI 验证。

GitHub Markdown API 审计证明 GitHub 为每个公式创建节点且未改写载荷；它不执行网页端最终渲染。因此 profile 或全库迁移完成后，先推送固定候选 commit，再逐篇打开 `blob/<40-character-sha>/.../translation.md` 的真实 GitHub 文件页。检查必须覆盖全部变更译文和每个被修改的公式，确认公式主体保持横向或原有多行结构、编号可见且与原文及正文引用一致，并且没有渲染错误、纵向堆叠、截断或异常溢出；完成报告记录候选 SHA、逐篇 URL、公式编号和结果。任何失败项必须重新进入 `draft -> repair-review -> accept`，不得合并或推送到 `main`。KaTeX 失败不能单独成为改写数学语义的理由。

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
