# 工作流：原文入库

## 目标

创建一个可发现、可追溯、可直接阅读的论文记录；无法取得合格 PDF 时保留 `unavailable`，不伪造完成。

## 成功标准

- 路径为 `papers/<area>/<paper-id>/`，ID 全库唯一。
- `paper.yaml` 只有六个字段；未知作者和年份分别为 `[]`、`null`。
- `source_url` 是一个权威原文入口，`topics` 来自受控词表。
- 成功取得且验证 PDF 时保存为 `source.pdf`，状态改为 `source_only`。
- 未取得 PDF 时不创建占位文件，保持 `reading_status: unavailable`。
- `make check` 通过且目录已重新生成。
- 若当前策略跳过该论文，在 `config/policy.yaml` 的对应 paper ID 下记录 `skip_reason`；不要把原因塞进 `paper.yaml`。

可先用脚手架创建最小记录：

```bash
make paper-new \
  PAPER_ID=<paper-id> \
  TITLE="<title>" \
  AREA=<area> \
  TOPICS="<topic> [<topic> ...]" \
  URL=<url>
```

命令不会联网或猜测作者与年份。

## 原文验证闭环

先把下载结果放在忽略目录，而不是直接让未经验证的字节成为
`source.pdf`。例如候选文件可放在 `tmp/ingest/<paper-id>.pdf`，随后运行：

```bash
make source-check \
  PAPER_ID=<paper-id> \
  SOURCE_PDF=tmp/ingest/<paper-id>.pdf
```

该门禁检查 PDF 签名、加密状态、页数、首尾页文本可抽取性，并将首页
标题和作者 token 与 `paper.yaml` 对照。代理还必须确认下载入口就是
`paper.yaml.source_url` 所指向或跳转到的同一篇原文；脚本不把“URL 看起来
相似”当作论文身份。门禁或人工身份核对任一失败时，不安装候选文件，不把
状态改成 `source_only`。

两项都通过后，才把候选安装为同目录的 `source.pdf`，再次执行
`make source-check PAPER_ID=<paper-id>`，并按 metadata workflow 将状态从
`unavailable` 改为 `source_only`。随后运行 `make catalog` 和 `make check`。
完成报告必须列出 paper ID、最终 `source_url`、`source-check` 结果和任何
人工消歧；这样“取得 PDF”“PDF 可读”“PDF 确为目标论文”和状态迁移形成
一个闭环。

若合格 PDF 超过有效页数上限，ingest 只完成原文身份验证；不要开始翻译。
由 maintain workflow 在同一变更中记录受控 `skip_reason` 并执行
`source_only -> skipped`，或在已有用户明确授权时记录单篇页数例外。

## 约束与证据

优先使用出版方、作者主页、机构仓库、DOI 或 arXiv 等可归因来源。不要把 HTML、登录页或错误页保存成 PDF。不要根据标题猜作者或年份。

下载付费内容、绕过访问控制或扩大检索范围前停止并请求确认。冲突信息不进入元数据，保持未知即可。

## 停止条件

PDF 已验证并可阅读，或合理的直接来源无法提供 PDF。不要为了把状态变成成功而无限搜索。
