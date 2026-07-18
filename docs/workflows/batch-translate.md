# 工作流：Codex 批量中文全文翻译

## 目标

一个翻译批次使用一个固定基线、一个 `codex/` 分支和一个隔离工作树。多轮只并行修改互斥论文目录；异人交叉审阅，根代理串行处理验收、评分、共享状态和最终集成。

## 授权与预检

启动前明确：

- 处理模式是 `draft-only`，还是已授权的 `review-and-repair/accept`；
- 交付范围是保留工作树、允许本地检查点、合并本地 `main`，还是进一步推送；提交、合并和推送权限不得互相推断；
- 多轮批次是否已获一次性的本地检查点提交授权。

在批次工作树记录基线并运行：

```bash
PYTHON=/absolute/path/to/python
git rev-parse HEAD
PYTHON="$PYTHON" make doctor          # draft-only
PYTHON="$PYTHON" make doctor-accept   # review-and-repair/accept；替代上一行
PYTHON="$PYTHON" make check
make diff-check
```

失败时停止，不让各子代理重复发现同一环境问题。队列只包含 `source_only`、原文可读且不超过有效页数上限的论文；其他状态不得自动加入。

## 写入边界

- **根代理**：维护队列和基线，串行执行 accept、评分、catalog、检查点及集成。只有根代理可改共享配置、生成目录或执行 Git 写操作。
- **翻译子代理**：每次只负责一个 paper ID；读取 translate workflow 与 translation policy；只改该论文的 `paper.yaml`、`translation.md` 和必要 `assets/`，不得改 `source.pdf`、共享状态或其他论文，交付状态只能为 `draft`。
- **审阅子代理**：不得审阅自己的译文；读取 review workflow 与 translation policy；先独立建立 PDF 内容清单，再逐项核对当前论文；不执行 accept、Git 写操作或共享文件更新。发现缺陷时退回原译者/修复者，待其修改后重新核对。若审阅子代理亲自修改论文内容，它就成为修复者，必须另换第三个独立审阅者。只有未参与当前字节快照修改的最终审阅者才能在临时目录生成 review receipt，并返回 receipt 路径、指纹、检查项和发现摘要。

子代理不得继续生成子代理。长正文和日志留在文件中，只返回 paper ID、状态、修改文件、门禁、warning 和 blocker 的短摘要。根代理记录 `queued`、`translating`、`draft-ready`、`reviewing`、`accepted`、`rated`、`blocked` 状态，但版本库真相仍以论文文件、评分和验收账本为准。

## 每轮执行

1. 根代理为互斥论文目录生成翻译子代理；子代理运行期间不写共享文件，不 accept、catalog、commit、merge 或 rebase。
2. 翻译子代理完成原文资源盘点和全文草稿后运行：

   ```bash
   PYTHON="$PYTHON" make paper-check PAPER_ID=<paper-id>
   ```

   warning 必须报告，不得靠 waiver、隐藏标记或降低阈值消除。
3. 根代理等待本轮全部译者结束，确认改动只在获分配目录；越界、同篇并发写入或基线漂移均停止该项。
4. 已授权验收时，由不同子代理按 review workflow 交叉复核。审阅发现先退回原译者/修复者，修复后必须再次交给未修改当前快照的审阅者；审阅者必须与译者/修复者使用不同稳定身份，并在最后一次修改后生成 review receipt。根代理记录 receipt、`paper-check` 输出的逐类别证据指纹，并对所有论文使用同一个预检基线 `review_base_sha`。存在机械候选时，最终审阅者把逐项确认过的指纹作为 `review-receipt --waiver category=fingerprint` 生成到 receipt 中；accept 本身不接收 waiver。根代理逐篇串行执行 `accept --review-receipt <path>`；receipt 与当前 source、translation、assets、首页书目信息、翻译策略、验收门禁或身份不匹配时停止该项。失败项保持 `draft`，不回滚其他成功项。
5. 根代理对每篇新验收论文执行 rating workflow。证据不足时保持无 `rating`、标为 `blocked`；译文可为 `translated`，但不得计入完整处理。
6. 每轮运行 `make catalog`、`make check`、`make diff-check`；获授权且全绿时创建只包含本轮成果的 checkpoint commit。

## 关闭与集成

1. 等待所有子代理停止，确认最终检查点和批次分支状态。
2. 若本地 `main` 已前进，在批次分支受控 rebase；冲突时停止，不手工拼接验收账本或生成目录。
3. 重新运行 `make catalog`、`make check`、`make diff-check`。
4. 已授权本地集成且 `main` 干净时使用 `git merge --ff-only <batch-branch>`；不能 fast-forward、存在未归属改动或工作树占用不安全时停止。
5. 推送是单独的外部发布授权。

普通批次不运行全库 `deep-check`：每篇 accept 已在任何写入前强制执行双轮单篇深度门禁、锁定 MathJax 和 GitHub 节点审计。只有同时修改校验器、需要评估历史影响的全局策略，或用户明确要求全库审计时，最终额外运行一次 `make deep-check`。该命令是非破坏性的影响扫描，不自动授权逐篇复审或修改全部历史译文；未获用户明确授权时，只处理被具体结果点名且位于当前范围内的论文。

只有用户明确授权历史质量复审批次时，才从 `python3 scripts/papers.py review-queue` 的最高优先级开始；论文数量增长或队列仍有候选都不自动扩展授权范围。不要把抽样绿灯外推为其余论文通过。每轮只在 receipt 已生成且根代理确认之后计入 reviewed，直到 receiptless/historical/waiver 风险按用户授权范围收敛。

## 恢复与清理

从 checkpoint、队列、`paper.yaml`、工作区差异和验收账本恢复；不从其他任务复制 `acceptance.yaml`，不手工合并哈希。若 `config/.acceptance-transaction.yaml` 存在，先停止后续验收，按 review workflow 检查后执行 `recover-acceptance --mode commit|rollback`；不得手工删除日志。单篇失败可用同一 paper ID 重新分派，不阻塞其他论文。

仅在没有活动子代理、工作区干净、分支已按授权完成集成且用户授权清理时，才从工作树外执行 `git worktree remove`。不得使用 `--force` 或 `git branch -D`；删除分支前用 `git merge-base --is-ancestor` 证明已集成。条件不满足时保留工作树并报告路径、分支和原因。

## 完成报告

报告批次基线、处理和交付模式、accepted/rated/draft/blocked paper ID、最终评分、分工、检查点、warning、证据缺口、实际门禁、提交/合并/推送状态及工作树清理结果。只有哈希匹配的 `translated` 计入验收数；进一步具有有效 `rating` 的新论文才计入完整处理数。
