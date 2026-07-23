# 工作流：阅读元数据

## 目标

让 `paper.yaml` 用最少字段准确支持论文发现、原文跳转和阅读状态判断，不扩展为书目数据库或流程日志。可选 `rating` 只由评分工作流管理。

## 数据契约

每份 `paper.yaml` 必须包含且只包含以下六个基础字段；完成评分后可额外包含一个完整的 `rating`：

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `title` | string | 原文正式标题 |
| `authors` | string list | 仅填写有可靠证据的作者；未知时为 `[]` |
| `year` | integer/null | 仅填写可靠发表年份；未知时为 `null` |
| `source_url` | string | 一个权威 HTTP(S) 原文入口 |
| `topics` | string list | 一个或多个 `config/taxonomy.yaml` 受控主题；顺序无语义 |
| `reading_status` | enum | `unavailable`、`source_only`、`draft`、`translated` 或 `skipped` |

论文 ID 和一级领域由目录表达；原文、译文和资源可用性由 `source.pdf`、`translation.md`、`assets/` 表达。文件名、中文目标语言和质量底线是代码不变量；默认页数上限、单篇例外与 skipped 原因属于 `config/policy.yaml`，验收内容快照、内容绑定 review receipt、固定基线和必要 waivers 属于 `config/acceptance.yaml`。这些信息不得在 `paper.yaml` 中重复。

`rating` 的字段、证据和计算规则只由 `docs/workflows/rating.md` 定义。本工作流不得创建、删除或修改 `rating`。

## 状态与文件

| `reading_status` | `source.pdf` | `translation.md` | 进入条件 |
| --- | --- | --- | --- |
| `unavailable` | 无 | 无 | 当前没有可读原文 |
| `source_only` | 有 | 无 | 已通过 ingest 的原文身份与可读性闭环，尚无译文 |
| `draft` | 有 | 有 | 译文尚未逐节验收 |
| `translated` | 有 | 有 | 验收快照与当前文件匹配；新的或重新验收的条目还必须有独立 review receipt，且受审 title/authors/year/source_url 未漂移 |
| `skipped` | 有 | 无 | 项目策略已有对应 reason code |

状态与文件不一致、`translated` 缺少匹配的验收条目或 `skipped` 缺少项目级原因时，`make check` 必须失败。`draft` 允许存在显式工作缺口，不表示译文接近验收完成。

## 决策规则

标题、作者和年份只来自论文首页或可靠原文入口；证据冲突且无法解决时保持未知。分类依据核心研究问题和主要贡献，不依据标题关键词、来源清单小节、处理批次或工作优先级。主题按 `config/taxonomy.yaml` 的定义选择；其列表视为无序集合，生成目录按分类法声明顺序稳定展示。

不要添加 venue、DOI/arXiv 独立字段、文档类型、PDF 页数、摘要、版权、下载记录、审校说明、评分证据或自由备注。确有跨论文的新需求时转入 `docs/workflows/maintain.md`，不要只为一篇论文增加字段。

状态迁移由对应工作流拥有：ingest 在 `source-check` 与人工来源身份核对都通过后负责 `unavailable -> source_only`，translate 负责 `source_only -> draft`，review/accept 负责 `draft -> translated`；源文或译文实质变化及复审失败时先 `translated -> draft`。translate 只检测页数超限并停止；页数或范围策略变化时，由 maintain 在同一变更中同步 `source_only <-> skipped` 与项目级 reason code，单篇译者不得单独修改共享策略。

## 验证

修改后运行 `make catalog` 和 `make check`；不要手工修补 `CATALOG.md`。
