# 工作流：Codex 批量中文全文翻译与历史译文修复

## 目标

一个翻译或已授权历史修复批次使用一个固定基线、一个 `codex/` 分支和一个隔离工作树。多轮只并行修改互斥论文目录；异人交叉审阅，根代理串行处理验收、评分、共享状态和最终集成。

## 授权与预检

启动前明确：

- 处理模式是 `draft-only`，还是已授权的 `review-and-repair/accept`；
- 交付范围是保留工作树、允许本地检查点、合并本地 `main`，还是进一步推送；提交、合并和推送权限不得互相推断；
- 多轮批次是否已获一次性的本地检查点提交授权。

工作树和分支由根代理在批次外按授权创建；本工作流不会自动创建、删除或
修复它们。进入批次工作树后，先准备维护环境并运行适用的 doctor：

```bash
make doctor          # draft-only
make doctor-accept   # review-and-repair/accept；替代上一行
make diff-check
make check
```

随后以当前 `HEAD` 冻结基线，并创建一个位于 gitignored
`tmp/batches/` 的持久操作清单：

```bash
BASE=$(git rev-parse HEAD)
BATCH_MANIFEST=tmp/batches/<batch-id>.yaml
make batch-start \
  BATCH_MANIFEST="$BATCH_MANIFEST" \
  MODE=<draft-only|review-and-repair/accept> \
  BASE="$BASE" \
  PAPER_IDS="<paper-id> ..."
```

`batch-start` 只创建操作清单，不创建 worktree 或分支。它会拒绝主工作树、
detached HEAD、非 `codex/` 分支、脏工作树、不是当前 `HEAD` 的基线、重复或
不存在的 paper ID，以及残留的 acceptance transaction marker。任一项失败
时停止，不让各子代理重复发现同一环境问题。操作清单固定记录 branch、
worktree、`review_base_sha`、模式、目标及其队列状态；它不进入 Git，也不
替代论文文件、评分或验收记录。

新增翻译队列只包含 `source_only`、已通过 `source-check` 且不超过有效页数
上限的论文；其他状态不得自动加入。已验收译文的批量修复使用下述独立规则。

## 已验收译文的确定性批量修复

历史译文批量修复必须由用户明确授权 `review-and-repair/accept`，并以固定 `review_base_sha` 冻结确定性扫描得到的 paper ID、内容位置、旧模式和目标模式；不得用 `review-queue` 或后续扫描结果自动扩大范围。根代理在修改任何受绑定论文内容前先把目标论文置为 `draft`。修复者每次只改获分配的论文目录并运行 `paper-check`；共享校验器、文档和验收账本仍只由根代理修改。

每篇论文仍须由未修改当前字节快照的审阅者完整执行 review workflow，以 `repair-review` 生成独立 receipt，再由根代理串行 accept。批次级规范化证明、全库 `math-check`、GitHub API 审计或网页 canary 只能界定迁移与显示结果，不能代替单篇 PDF 审阅和 receipt。失败项保持 `draft`，不回滚或冒充其他已通过项。

## 写入边界

- **根代理**：维护队列和基线，串行执行 accept、评分、catalog、检查点及集成。只有根代理可改共享配置、生成目录或执行 Git 写操作。
- **翻译子代理**：每次只负责一个 paper ID；读取 translate workflow 与 translation policy；只改该论文的 `paper.yaml`、`translation.md` 和必要 `assets/`，不得改 `source.pdf`、共享状态或其他论文，交付状态只能为 `draft`。
- **审阅子代理**：不得审阅自己的译文；读取 review workflow 与 translation policy；先独立建立 PDF 内容清单，再逐项核对当前论文；不执行 accept、Git 写操作或共享文件更新。发现缺陷时退回原译者/修复者，待其修改后重新核对。若审阅子代理亲自修改论文内容，它就成为修复者，必须另换第三个独立审阅者。只有未参与当前字节快照修改的最终审阅者才能在临时目录生成 review receipt，并返回 receipt 路径、指纹、检查项和发现摘要。

子代理不得继续生成子代理。长正文和日志留在文件中，只返回 paper ID、状态、修改文件、门禁、warning 和 blocker 的短摘要。根代理用下列命令把 `queued`、`translating`、`draft-ready`、`reviewing`、`accepted`、`rated`、`blocked` 状态持久化到批次清单：

```bash
make batch-state \
  BATCH_MANIFEST="$BATCH_MANIFEST" \
  PAPER_ID=<paper-id> \
  STATE=<next-state>
```

命令拒绝越级状态迁移；`draft-only` 不能进入 `accepted` 或 `rated`。版本库
真相仍以论文文件、评分和验收记录为准，批次清单只用于工作恢复和分派核对。

## 每轮执行

1. 每轮开始先运行 `make batch-check BATCH_MANIFEST="$BATCH_MANIFEST"`；根代理为互斥论文目录生成翻译子代理，并把各项迁移到 `translating`。子代理运行期间不写共享文件，不 accept、catalog、commit、merge 或 rebase。
2. 翻译子代理完成原文资源盘点和全文草稿后运行：

   ```bash
   make paper-check PAPER_ID=<paper-id>
   ```

   warning 必须报告，不得靠 waiver、隐藏标记或降低阈值消除。
3. 根代理等待本轮全部译者结束，确认改动只在获分配目录；越界、同篇并发写入或基线漂移均停止该项。
4. 已授权验收时，由不同子代理按 review workflow 交叉复核。审阅发现先退回原译者/修复者，修复后必须再次交给未修改当前快照的审阅者；审阅者必须与译者/修复者使用不同稳定身份，并在最后一次修改后生成 review receipt。根代理记录 receipt、`paper-check` 输出的逐类别证据指纹，并对所有论文使用清单中的同一个 `review_base_sha`。每篇开始验收前先把清单状态迁移到 `reviewing`，再运行：

   ```bash
   make accept-preflight \
     PAPER_ID=<paper-id> \
     BASE="$BASE" \
     BATCH_MANIFEST="$BATCH_MANIFEST"
   ```

   该只读预检要求目标仍为 `draft`、基线仍是 `HEAD` 祖先、清单归属当前
   branch/worktree、命令行 `BASE` 与清单 `review_base_sha` 完全相同、目标
   状态为 `reviewing`、无事务 marker，并执行
   `doctor-accept` 与 `paper-check`。存在机械候选时，最终审阅者把逐项确认过
   的指纹作为 `review-receipt --waiver category=fingerprint` 生成到 receipt
   中；accept 本身不接收 waiver。receipt 必须使用 `mktemp` 创建并在单篇
   accept 后删除，不能复用可预测的 `/tmp/<paper-id>-review.yaml`：

   ```bash
   PYTHON=$(make -s python-path)
   receipt=$(mktemp "${TMPDIR:-/tmp}/db-papers-review.XXXXXX")
   trap 'rm -f "$receipt"' EXIT HUP INT TERM
   "$PYTHON" scripts/papers.py review-receipt \
     --id <paper-id> \
     --review-action <full-translation-review|repair-review> \
     --translator <stable-translator-or-repairer-identity> \
     --reviewer <stable-reviewer-identity> \
     --review-base-sha "$BASE" \
     --check front-matter \
     --check section-structure \
     --check technical-claims \
     --check numbers-and-units \
     --check formulas \
     --check figures-and-tables \
     --check algorithms-and-listings \
     --check footnotes-and-end-matter \
     --check conclusions-and-limitations \
     --check references \
     --check visual-layout \
     --finding "<one concrete PDF-verified disposition>" \
     --authorial-voice-source-items <count> \
     --authorial-voice-verified-items <same-count> \
     --authorial-voice-shared-subject-merges <count> \
     > "$receipt"
   "$PYTHON" scripts/papers.py accept \
     --id <paper-id> \
     --review-receipt "$receipt"
   rm -f "$receipt"
   trap - EXIT HUP INT TERM
   ```

   receipt 与当前 source、translation、assets、首页书目信息、翻译策略、
   验收门禁或身份不匹配时停止该项。失败项保持 `draft`，迁移到 `blocked`
   或退回 `draft-ready`，不回滚其他成功项。
5. 根代理仅对本批新增论文执行 rating workflow。证据不足时保持无 `rating`、标为 `blocked`；译文可为 `translated`，但不得计入完整处理。历史译文修复保留原 rating，除非用户另行授权评分。
6. 每轮运行 `make catalog`、`make check`、`make diff-check`。`draft-only`
   还必须运行 `make math-audit-github-worktree BASE="$BASE"`；该目标同时覆盖
   相对固定基线的 staged、unstaged 和未跟踪译文，避免尚未 accept 的草稿
   绕过限定范围的 GitHub Markdown 公式审计。获授权且全绿时创建只包含本轮
   成果的 checkpoint commit。

## 关闭与集成

1. 等待所有子代理停止，确认最终检查点和批次分支状态。
2. 生成本批第一份 v2 receipt 前必须再次确认本地 `main` 没有前进；若已前进，
   只能在尚未生成 receipt、尚未 accept 时先受控 rebase，再重新运行单篇门禁
   和独立最终复核。任何 v2 receipt 或 accept 完成后都禁止 rebase、amend 或
   其他历史重写，因为 `review_head_sha` 必须继续存在并保持为当前 `HEAD` 的
   祖先；若此后 `main` 又前进，停止集成并报告，不得为了 fast-forward 静默
   改写历史或手工拼接验收账本。
3. 重新运行 `make catalog`、`make check`、`make diff-check`。
4. 推送始终需要单独的外部发布授权。涉及公式 profile 或全库公式迁移时，先提交最终候选并推送候选分支，再按 `docs/portable-math-maintainers.md` 检查固定 commit 的真实 GitHub 文件页。逐篇覆盖本批次所有变更译文及每个被修改的公式，确认公式主体保持横向或原有多行结构、编号可见且没有错误提示、纵向堆叠、截断或异常溢出；GitHub Markdown API 节点审计不能替代该页面检查。完成报告记录候选 commit、逐篇 URL、公式编号和结果；页面检查未通过时不得合并或推送到 `main`。
5. 普通批次完成第 3 步，公式批次完成第 4 步的真实页面检查后，已授权本地集成且 `main` 干净时才使用 `git merge --ff-only <batch-branch>`；不能 fast-forward、存在未归属改动或工作树占用不安全时停止。
6. 只有另获主分支推送授权且相关页面检查已通过，才推送 `main`。

普通批次不运行全库 `deep-check`：每篇 accept 已在任何写入前强制执行双轮单篇深度门禁、锁定 MathJax 和 GitHub 节点审计。只有同时修改校验器、需要评估历史影响的全局策略，或用户明确要求全库审计时，最终额外运行一次 `make deep-check`。该命令是非破坏性的影响扫描，不自动授权逐篇复审或修改全部历史译文；未获用户明确授权时，只处理被具体结果点名且位于当前范围内的论文。

只有用户明确授权历史质量复审批次时，才从 `make review-queue` 的最高优先级开始；论文数量增长或队列仍有候选都不自动扩展授权范围。不要把抽样绿灯外推为其余论文通过。每轮只在 receipt 已生成且根代理确认之后计入 reviewed，直到历史空 findings 或 waiver 风险按用户授权范围收敛。

## 恢复与清理

从 checkpoint、`BATCH_MANIFEST`、`paper.yaml`、工作区差异和验收记录恢复；
先运行 `make batch-check BATCH_MANIFEST="$BATCH_MANIFEST"`，再按权威文件核对
清单状态；不从其他任务复制验收记录，不手工合并哈希。若
`config/.acceptance-transaction.yaml` 存在，先停止后续验收，按 review
workflow 检查后执行 `recover-acceptance --mode commit|rollback`；不得手工
删除日志。单篇失败可用同一 paper ID 重新分派，不阻塞其他论文。

仅在没有活动子代理、工作区干净、分支已按授权完成集成且用户授权清理时，才从工作树外执行 `git worktree remove`。不得使用 `--force` 或 `git branch -D`；删除分支前用 `git merge-base --is-ancestor` 证明已集成。条件不满足时保留工作树并报告路径、分支和原因。

## 完成报告

报告批次清单路径、固定基线、处理和交付模式、accepted/rated/draft/blocked paper ID、最终评分、分工、检查点、warning、证据缺口、实际门禁、提交/合并/推送状态及工作树清理结果。只有哈希匹配的 `translated` 计入验收数；进一步具有有效 `rating` 的新论文才计入完整处理数。
