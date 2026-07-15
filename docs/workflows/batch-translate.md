# 工作流：Codex 批量中文全文翻译

## 目标

用一个隔离工作树承载一个翻译批次。批次可以包含多轮并行翻译；每轮只并行修改互斥论文目录，由异人交叉审阅，根代理串行处理验收和共享状态。每轮可形成本地检查点，整个批次只在结束时集成一次 `main`。

## 批次、轮次与授权

- **批次**对应一个固定基线、一个 `codex/` 分支和一个工作树；同一批次的所有轮次复用该工作树，不为每轮创建新工作树。
- **轮次**是一组同时翻译的论文。根代理根据实时并发槽位决定规模，并保留自身协调槽位。
- 启动时根代理明确处理模式：`draft-only`，或已获用户授权的 `review-and-repair/accept`。
- 启动时根代理明确交付范围：仅保留工作树、允许本地检查点、合并本地 `main`，或进一步推送。提交、合并和推送权限不得互相推断。
- 多轮批次应在开始前取得一次性的本地检查点提交授权；未获授权时只保持工作树改动，不创建提交。

若独立 Codex 任务各自创建了工作树，应视为不同批次并串行集成；不得让多个工作树并行写入或手工拼接 `config/acceptance.yaml` 和 `CATALOG.md`。

## 启动预检

1. 从包含当前 `AGENTS.md` 和本工作流的固定提交启动；优先使用 Codex-managed worktree。Local 任务优先 Handoff，若当前产品不能 Handoff 自身，则在生成写入型子代理前创建独立 `codex/` 工作树。
2. 在实际批次工作树中确认没有未归属改动，并记录 `git rev-parse HEAD`。进行中的批次不得静默换基线。
3. 根代理选择一个可用的 Python 绝对路径并传给全部子代理。生成子代理前运行：

   ```bash
   PYTHON=/absolute/path/to/python
   PYTHON="$PYTHON" make doctor
   PYTHON="$PYTHON" make check
   make diff-check
   ```

   环境检查失败时先停止，不让每个子代理分别发现相同依赖问题。
4. 只选择 `reading_status: source_only`、`source.pdf` 可读且不超过该篇有效页数上限的论文。已是 `draft`、`translated`、`skipped` 或 `unavailable` 的论文不得自动加入。

## 角色与写入边界

- **根代理**：维护队列和基线，检查写入范围，串行执行 accept、评分、catalog、检查点和最终集成。只有根代理可以修改共享配置和生成目录或执行 Git 写操作。
- **翻译子代理**：每轮只负责一个 paper ID；先读 `docs/workflows/translate.md` 和 `docs/translation-policy.md`。只修改该论文目录中的 `paper.yaml`、`translation.md` 和必要 `assets/`，不得修改 `source.pdf`、共享状态、其他论文或执行 Git 写操作。交付状态只能是 `draft`。
- **审阅子代理**：不得审阅自己翻译的论文；先读 `docs/workflows/review.md` 和 `docs/translation-policy.md`。只核对或修复当前分配目录，不执行 accept、Git 写操作或共享文件更新。

子代理不得继续生成子代理。长译文和日志保留在文件中，只返回 paper ID、状态、修改文件、门禁、warning 和 blocker 的短摘要。

根代理在任务状态中记录 paper ID、译者、审阅者，以及 `queued`、`translating`、`draft-ready`、`reviewing`、`accepted`、`rated`、`blocked` 之一。版本库真相仍以文件、评分字段和验收账本为准。

## 每轮执行

1. 根代理为互斥论文目录生成直接翻译子代理。子代理运行期间，根代理不修改仓库文件，不执行 accept、catalog、commit、merge 或 rebase。
2. 翻译子代理形成完整草稿并使用根代理提供的 Python 运行真正的单篇门禁：

   ```bash
   PYTHON=/absolute/path/to/python
   PYTHON="$PYTHON" make paper-check PAPER_ID=<paper-id>
   ```

   `paper-check` 只校验目标论文和共享配置，不应读取其他代理尚未完成的译文。warning 必须逐项报告，不得通过处置码、隐藏标记或降低阈值消除。
3. 子代理只发送两个中间里程碑：
   - `source-inventory-ready`：页数、章节、图表、算法、代码和参考文献候选已盘点；
   - `draft-ready`：全文、资源和单篇门禁已完成。
4. 根代理等待本轮全部译者返回，再确认改动只位于获分配目录。越界改动、同篇并发写入或基线漂移将该项置为 `blocked`，不得自动覆盖。
5. 若当前模式授权验收，根代理轮换已完成的子代理交叉 review-and-repair，且不得让译者审阅自己的论文。审阅至少核对：
   - 图像标签、坐标轴、图例、子图边界和裁图安全留白；
   - 裁图是否带入相邻正文、图注、表格或算法；
   - Figure/Algorithm 以代码块表示时是否完整且恰有一个表示；
   - Input/Require、步骤编号、表格数字与单位、双栏参考文献是否完整。
6. 根代理等待全部审阅结束，再逐篇串行运行 `scripts/papers.py accept`。失败项保持或恢复为 `draft`，不回滚其他成功论文。
7. 根代理对本轮每篇新验收论文串行执行 `docs/workflows/rating.md`。评分必须读取 `source.pdf` 并核验外部传播或落地证据，不得把翻译质量计入分值。证据不足时不编造 `rating`，将该项标为 `blocked` 并报告具体证据缺口；此时译文可保持 `translated`，但不得计入“完整处理完成”。
8. 每轮结束由根代理运行：

   ```bash
   make catalog
   make check
   make diff-check
   ```

9. 若已获本地检查点授权且本轮全绿，根代理创建一个只包含本轮成果的 checkpoint commit；不在轮次边界合并 `main`。

## 批次关闭与集成

1. 最后一轮形成检查点后，确认批次分支工作区干净，并读取当前 `main`。不得在活动子代理仍写入时关闭批次。
2. 若 `main` 已从批次基线前进，在批次分支上受控 rebase 最新本地 `main`；发生冲突时停止，不手工覆盖验收条目或生成目录。
3. 在最终集成状态重新生成目录并运行快速仓库门禁：

   ```bash
   make catalog
   make check
   make diff-check
   ```

4. 用户已授权本地集成且 `main` 检出干净时，使用 `git merge --ff-only <batch-branch>`。不能 fast-forward、`main` 有未归属改动或工作树占用不安全时停止。
5. 推送属于单独的外部发布授权。只有合并和验证成功后才能清理批次工作树与分支。

普通翻译批次不运行全库 `deep-check`。每篇最终 accept 已强制运行该篇深度门禁；重复扫描全部历史论文会增加线性成本而不增加本批次的有效覆盖。只有本批次同时修改了校验器、改变了可能影响历史论文判定的全局翻译策略，或用户明确要求全库审计时，根代理才在最终集成状态额外运行一次 `make deep-check`。

## 工作树清理与残留审计

批次关闭时总是运行 `git worktree list --porcelain`，记录批次工作树的绝对路径、分支和 HEAD。清理前必须同时满足：没有活动子代理、工作区干净、最终检查点存在、分支已按获授权的交付范围完成集成，并且用户已授权清理。尚未集成、仅要求保留工作树或清理未获授权时，不删除任何内容，在完成报告中列出保留路径、分支和原因。

满足前置条件后，从批次工作树之外执行：

```bash
git worktree remove <absolute-batch-worktree>
git worktree list --porcelain
git worktree prune --dry-run
```

不得使用 `git worktree remove --force`。只有 `prune --dry-run` 确认存在已消失目录对应的陈旧管理项时才运行 `git worktree prune`。删除批次分支前，先确认没有工作树仍使用它，并用 `git merge-base --is-ancestor <batch-branch> <integrated-target>` 证明已集成；随后只使用 `git branch -d <batch-branch>`，不得使用 `-D`。最终再次审计工作树列表，并在完成报告中分别列出已删除和仍保留的路径、分支及原因。

## Dry run

工作流或校验命令变化后，使用一篇已验收论文执行不写文件的演练：

```bash
PYTHON=/absolute/path/to/python
PYTHON="$PYTHON" make doctor
PYTHON="$PYTHON" make paper-check PAPER_ID=<translated-paper-id>
make diff-check
make check
git status --short
```

Dry run 不执行 accept、catalog、commit、merge 或 push；输出必须证明环境可用、单篇门禁只处理一个 record、工作区无意外改动。

## 恢复与停止

- 暂停或恢复时，从 checkpoint commits、任务队列、`paper.yaml`、工作区差异和验收账本重建状态。
- 单篇失败不阻塞其他论文；失败项使用同一 paper ID 重新分派。
- 不从其他任务复制 `acceptance.yaml`，不手工合并哈希，不用 `translated` 掩盖未完成审阅。
- 当来源不可读、超出策略、授权不足、范围冲突、环境失败、基线漂移或无法 fast-forward 时停止并报告具体 blocker。

## 完成报告

报告批次基线、处理和交付模式、轮次数、accepted/rated/draft/blocked paper ID、最终评分、译者与审阅者分工、检查点提交、单篇 warning、未解决阅读或评分证据缺口、实际门禁，以及最终分支是否已提交、合并或推送。只有账本哈希匹配且状态为 `translated` 的论文计入译文验收数；只有进一步具有有效 `rating` 的新论文计入完整处理数。报告还必须列出工作树和批次分支的清理或保留结果。
