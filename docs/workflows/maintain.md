# 工作流：项目维护

## 目标

在不破坏论文资产的前提下，维护 `paper.yaml` 契约、项目策略、分类法、当前
校验器和读者站。仓库只保存当前内容与当前规则；Git 保存历史，不建立平行的
发布版本数据库。

## 成功标准

- `paper.yaml` 保持七个必填字段，只允许评分工作流定义的可选 `rating`。
- `config/policy.yaml` 和 `config/taxonomy.yaml` 通过强类型 schema 校验。
- 目录或主题变化同步更新配置、文档、校验器和受影响记录。
- 原文、译文和资源不因结构调整而改变，相对资源链接仍有效。
- 生成文件由脚本重建，不手工修补。
- 普通变更通过 `make check` 和 `make diff-check`；改变内容解释、发布语义或
  全局校验器行为时改用带原因的 `make deep-check`。

## 持久数据边界

- `paper.yaml` 保存当前阅读元数据和 `reading_status`。
- `config/policy.yaml` 保存当前页数策略、单篇授权例外和 skipped 原因。
- `config/taxonomy.yaml` 保存当前受控领域与主题。
- `source.pdf`、`translation.md` 和 `assets/` 保存读者内容。
- Git commit 保存内容版本；PR、提交和任务报告保存审阅过程。

不要新增平行版本账本、内容摘要注册表、per-paper waiver、流程日志或历史
schema reader。旧规则和旧证据需要时从 Git 历史读取，不作为当前运行时输入。

## 规则设计

确定性约束和受控码以 `scripts/project_config.py` 及对应校验器为事实来源，不在
多个配置副本中重复。配置只保存真正可变的值；固定文件名、目标语言和质量底线
不是开关。

改变必填字段、评分结构、策略或分类法时，一次更新模板、文档、脚本、测试和
生成目录。不要为单篇论文增加临时字段。

校验分两类：

- **硬失败**：文件/状态不一致、不可读 PDF、坏资源路径、缺失读者载荷、非法
  Markdown 结构、公式静态错误等不存在合理例外的确定性问题。
- **warning**：覆盖率、引用编号差、资源或 Listing 数量差、人称计数、PDF
  抽取顺序等需要人工回到 PDF 判断的启发式信号。

不保存永久 waiver。某条规则需要逐篇例外才能工作时，应降为 warning；确定性
规则出现误报时，应修正规则本身。

## Git 与发布模型

`reading_status: translated` 表示当前 Git revision 中的译文已经人工审阅并通过
当前确定性门禁。站点只按该状态选择译文；`main` 的 `check` 成功表示同一 SHA
已经通过归档检查和 push-side GitHub 公式审计，Pages 随后对该 SHA 完整构建并
部署。

内容变化不依赖额外摘要锁来确认发布状态。PR 或 push 的 Git diff 直接定位受影响
paper ID，并运行 `paper-check`；严格的独立身份要求应由 GitHub required reviewer
实现，而不是由提交者可同时填写的元数据模拟。

`pull_request_target` 公式审计及其受保护运行时代码属于 CI 信任边界。普通 PR
会拒绝这些文件的差异；只有用户明确授权信任边界更新时，维护者才可在完成本地
全库门禁后使用管理员 bypass 直接落地主分支，并继续等待同 SHA 的 `check` 和
Pages 部署。不得在同一 PR 中放宽保护来让自身通过。

批次 manifest 只允许放在 gitignored 的 `tmp/batches/`，仅用于当前任务分派和
恢复，不参与论文状态、校验或发布判断。

## 环境准备

`make doctor` 检查 Python 3.11+、pip 26.1.2、锁定的 dev dependency group、
Node.js/npm、MathJax、GNU Make、ripgrep、Poppler 和 Perl。依赖只安装到项目
虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade "pip==26.1.2"
.venv/bin/python -m pip install --group dev
npm ci
```

维护 GitHub Pages 时另安装 site dependency group：

```bash
.venv/bin/python -m pip install --group site
```

## GitHub Pages

`scripts/build_site.py` 从 `paper.yaml` 和 `config/taxonomy.yaml` 生成一次性的
`site_src/` 与 `site.generated.toml`，Zensical 构建到 `site/`。这些产物不得
提交或手工维护。

读者站发布 `reading_status: translated` 的译文、对应 `source.pdf` 和正式
资源；未完成译文、维护配置、脚本和测试不进入 artifact。

```bash
make site-serve
make site-check
```

PR 只构建不部署。默认分支的 `check` workflow 在同一 SHA 完成归档检查和
push-side GitHub 公式审计后，Pages workflow 检出该 SHA、完整运行
`make site-check` 并部署。站点故障优先 revert 导致故障的仓库提交，不直接修改
artifact。

## CI 范围

- 每次 PR 和默认分支推送都运行 `make check`。
- `source.pdf`、`translation.md`、`assets/` 或影响发布语义的 `paper.yaml`
  变化时，对相应 paper ID 运行 `paper-check`。
- 仅 `title_zh`、`topics` 或 `rating` 变化时，运行快速元数据、目录和站点检查。
- 变更译文运行限定文件公式门禁；公式 profile 或实现变化时升级为全库检查。
- 差异基线无法可信确定时直接失败，不猜测范围。

## 验证

```bash
make doctor
make python-compile
node --check scripts/render_mathjax.cjs
make check
# 改变内容解释、发布语义或全局校验器时改用：
# make deep-check DEEP_REASON=<content-semantics|publication-semantics|validator-semantics|full-audit>
make diff-check
# 站点生成器、主题或 Pages workflow 变化时：
make site-check
```

深检是 `make check` 的替代项，不叠加运行。机械全库检查不授权全库内容复审；
只报告被确定性证据点名的 paper ID，是否扩大修复范围仍由用户决定。
