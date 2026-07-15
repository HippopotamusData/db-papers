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
python3 scripts/papers.py new --id <paper-id> --title "<title>" --area <area> --topic <topic> --url <url>
```

命令不会联网或猜测作者与年份。

## 约束与证据

优先使用出版方、作者主页、机构仓库、DOI 或 arXiv 等可归因来源。不要把 HTML、登录页或错误页保存成 PDF。不要根据标题猜作者或年份。

下载付费内容、绕过访问控制或扩大检索范围前停止并请求确认。冲突信息不进入元数据，保持未知即可。

## 停止条件

PDF 已验证并可阅读，或合理的直接来源无法提供 PDF。不要为了把状态变成成功而无限搜索。
