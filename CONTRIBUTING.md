# 参与维护

欢迎通过 GitHub Issue 报告错译、漏译、链接失效或排版问题。准备提交修改时，请先按变更类型阅读 `docs/workflows/` 中对应的当前工作流。

仓库包含较多论文 PDF；首次克隆可使用 `git clone --filter=blob:none <仓库地址>`，Git 会在实际读取文件时按需下载 PDF 等对象。

提交修改时请保持范围明确：

- 元数据只使用 `paper.yaml` 已有字段和 `config/taxonomy.yaml` 的受控主题。
- 不手工编辑 `CATALOG.md`；元数据变化后运行 `make catalog`。
- `reading_status: translated` 论文的原文、译文或资源如需实质修改，先明确修复范围，再遵循 `docs/workflows/review.md` 的独立审阅与修复流程。Issue 或当前任务中的明确授权均可确定范围，不必重复确认。
- 保留无关文件和其他贡献者的修改。

提交前至少运行：

```bash
make check
make diff-check
```

只有依赖、策略或流程变更会影响论文内容解释、发布语义或全局校验器行为，
或明确进行全库审计时，才使用带原因的 `make deep-check` 替代 `make check`：

```bash
make deep-check DEEP_REASON=<content-semantics|publication-semantics|validator-semantics|full-audit>
```

Pages、文档、打包和发布流程等不影响这些语义的变更仍运行 `make check`，
再运行 `make diff-check`。

修改站点生成器、主题或 Pages 工作流时，另安装锁定的站点依赖并运行：

```bash
.venv/bin/python -m pip install --group site
make site-check
```

站点内容由权威元数据和 `reading_status: translated` 译文生成；不要提交 `site_src/`、`site/`
或 `site.generated.toml`，也不要在生成产物中手工修补论文页面。
