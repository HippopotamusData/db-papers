# 参与维护

欢迎通过 GitHub Issue 报告错译、漏译、链接失效或排版问题。准备提交修改时，请先按变更类型阅读 `docs/workflows/` 中对应的当前工作流。

仓库包含较多论文 PDF；首次克隆可使用 `git clone --filter=blob:none <仓库地址>`，Git 会在实际读取文件时按需下载 PDF 等对象。

提交修改时请保持范围明确：

- 元数据只使用 `paper.yaml` 已有字段和 `config/taxonomy.yaml` 的受控主题。
- 不手工编辑 `CATALOG.md`；元数据变化后运行 `make catalog`。
- 已验收论文的原文、译文或资源如需实质修改，先通过 Issue 确认修复范围，再遵循 `docs/workflows/review.md` 的独立复核与验收流程。
- 保留无关文件和其他贡献者的修改。

提交前至少运行：

```bash
make check
make diff-check
```

若改动校验器、项目级翻译策略或其他全局门禁，使用 `make deep-check`
替代 `make check`，再运行 `make diff-check`。
