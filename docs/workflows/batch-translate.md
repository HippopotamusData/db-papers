# 工作流：Codex 批量中文全文翻译与历史译文修复

## 目标

一个批次使用一个固定基线、一个 `codex/` 分支和一个隔离工作树。子代理只并行
修改互斥论文目录；独立审阅者负责 PDF 复核，根代理串行处理验收、评分、共享
状态和集成。

## 授权与启动

启动前明确三件事：

- 模式是 `draft-only`，还是用户已授权的 `review-and-repair/accept`；
- 交付到工作树、检查点、本地 `main`，还是进一步推送；这些权限不能互相推断；
- 多轮批次是否已获一次性检查点提交授权。

根代理按授权在批次外创建分支和工作树。本流程不自动创建、删除或修复它们。
进入批次工作树后运行：

```bash
make doctor          # draft-only
make doctor-accept   # review-and-repair/accept；替代上一行
make diff-check
make check

BASE=$(git rev-parse HEAD)
BATCH_MANIFEST=tmp/batches/<batch-id>.yaml
make batch-start \
  BATCH_MANIFEST="$BATCH_MANIFEST" \
  MODE=<draft-only|review-and-repair/accept> \
  BASE="$BASE" \
  PAPER_IDS="<paper-id> ..."
```

`batch-start` 只在 gitignored 的 `tmp/batches/` 创建操作清单。它要求：当前工作树
干净且不是主工作树；分支以 `codex/` 开头；`BASE` 就是当前 `HEAD`；paper ID
存在且不重复；没有残留验收事务。失败时停止。

清单固定 branch、worktree、`review_base_sha`、模式、论文范围和队列状态。
它只用于恢复和分派，不替代论文文件、评分或验收账本。新增翻译只接收
`source_only`、已通过 `source-check` 且未超过有效页数上限的论文。

## 已验收译文的批量修复

历史批量修复必须有明确的 `review-and-repair/accept` 授权。根代理以固定基线
保存确定性扫描得到的 paper ID、位置、旧模式和目标模式；不得用
`review-queue` 或后续扫描结果扩展范围。修改绑定内容前，根代理先把目标置为
`draft`。

每篇论文都由未修改当前字节快照的审阅者完整执行 review workflow，并以
`repair-review` 生成独立 receipt。批次扫描、全库公式检查或页面 canary 不能
替代单篇 PDF 审阅。失败项保持 `draft`，不回滚其他已通过项。

## 角色与状态

- **根代理**：维护范围和基线；串行 accept、评分、catalog、检查点及集成。只有
  根代理可改共享配置、生成目录或执行 Git 写操作。
- **翻译/修复子代理**：每次只负责一个 paper ID，只改该目录中的
  `paper.yaml`、`translation.md` 和必要 `assets/`；不得改 `source.pdf`、
  共享状态或其他论文；交付状态只能为 `draft`。
- **审阅子代理**：不审阅自己的修改，不执行 accept、Git 写操作或共享文件更新。
  它独立建立 PDF 清单并按 review workflow 逐项核对。若亲自修改论文内容，
  身份就转为修复者，必须另换审阅者完成最终复核。

子代理不得继续生成子代理。长正文和日志留在文件中，只返回 paper ID、状态、
修改文件、门禁、warning 和 blocker 的短摘要。根代理记录状态：

```bash
make batch-state \
  BATCH_MANIFEST="$BATCH_MANIFEST" \
  PAPER_ID=<paper-id> \
  STATE=<queued|translating|draft-ready|reviewing|accepted|rated|blocked>
```

命令拒绝越级迁移；`draft-only` 不能进入 `accepted` 或 `rated`。

## 每轮执行

1. 运行 `make batch-check BATCH_MANIFEST="$BATCH_MANIFEST"`。根代理为互斥
   论文目录分派子代理，并把目标迁移到 `translating`。子代理运行期间不得
   accept、catalog、commit、merge 或 rebase。
2. 翻译/修复子代理完成草稿后运行
   `make paper-check PAPER_ID=<paper-id>`。报告全部 warning；不得靠隐藏标记、
   waiver 或降低阈值消除。
3. 根代理等待本轮全部子代理结束，确认修改没有越界、同篇并发写入或基线漂移。
4. 已授权验收时，把论文交给不同身份的审阅者。缺陷退回原译者/修复者；最后
   一次修改后再由未修改当前快照的审阅者完成复核。
5. 根代理把目标迁移到 `reviewing`，然后运行只读预检：

   ```bash
   make accept-preflight \
     PAPER_ID=<paper-id> \
     BASE="$BASE" \
     BATCH_MANIFEST="$BATCH_MANIFEST"
   ```

   预检只核对状态、清单归属、固定基线、环境和事务 marker，不重复内容深检。
   审阅者随后按 `docs/workflows/review.md` 的唯一权威命令生成 receipt；该命令
   运行一次新鲜的 `paper-check`。机械候选必须由审阅者逐项核回 PDF，并以
   `--waiver category=fingerprint` 写入 receipt。根代理使用同一 receipt
   串行 accept；accept 再执行一次最终 `translated` 级别深检。任何绑定输入、
   身份、基线、发现集合或 HEAD 不匹配都会停止该项。失败项保持 `draft`，
   转为 `blocked` 或退回 `draft-ready`，不影响其他成功项。
6. 根代理只给本批新增论文执行 rating workflow。证据不足时不写 `rating`，
   标为 `blocked`；译文可以是 `translated`，但不计为端到端完成。历史修复
   保留原 rating，除非另有授权。
7. 每轮运行 `make catalog`、`make check`、`make diff-check`。`draft-only`
   还运行 `make math-audit-github-worktree BASE="$BASE"`，覆盖相对基线的
   staged、unstaged 和未跟踪译文。获授权且全绿时创建本轮 checkpoint commit。

## 关闭与集成

1. 等待全部子代理停止，并核对清单、最终检查点和分支状态。
2. 生成第一份 v2 receipt 前再次确认本地 `main` 未前进。若已前进，只能在
   尚无 receipt、尚未 accept 时受控 rebase，然后重跑单篇门禁和独立复核。
   一旦生成 receipt 或完成 accept，禁止 rebase、amend 或其他历史重写。
   此后 `main` 再前进时停止并报告。
3. 运行 `make catalog`、`make check`、`make diff-check`。若本批同时修改校验器
   或可能影响历史论文的全局策略，用 `make deep-check` 替代 `make check`。
   深检只产生影响清单，不授权全库内容复审。
4. 公式规则、profile 或全库公式迁移按 `AGENTS.md` 的公式任务路由完成真实
   GitHub 页面检查。普通批次无需额外读取公式维护指南。
5. 已授权本地集成且 `main` 干净时，使用
   `git merge --ff-only <batch-branch>`。不能 fast-forward 或存在未归属改动
   时停止。
6. 推送需要独立授权；只有本地检查和适用的 GitHub 页面检查通过后才能推送。

普通批次不运行全库 `deep-check`。每篇已有译者反馈、receipt 取证和 accept
最终验证三次单篇深检。只有校验器变更、全局策略影响分析或明确的全库审计
才使用 `deep-check`。

仅在用户授权历史质量复审时，才从 `make review-queue` 选择范围。队列候选不
自动扩大授权，也不能用抽样结果外推未审论文。

## 恢复与清理

先根据 checkpoint、`BATCH_MANIFEST`、论文文件、工作区差异和验收账本恢复，
再运行 `make batch-check BATCH_MANIFEST="$BATCH_MANIFEST"`。不要复制 receipt
或手工合并哈希。若存在 acceptance transaction marker，停止后续验收并按
review workflow 执行 `recover-acceptance --mode commit|rollback`；不得手工
删除 marker。单篇失败可重新分派，不阻塞其他论文。

只有全部子代理停止、工作区干净、分支已按授权集成且用户授权清理时，才从
工作树外执行 `git worktree remove`。不得使用 `--force` 或 `git branch -D`；
删除分支前用 `git merge-base --is-ancestor` 证明已集成。否则保留并报告。

## 完成报告

报告清单路径、固定基线、模式、accepted/rated/draft/blocked paper ID、评分、
分工、检查点、warning、证据缺口、实际门禁、提交/合并/推送和清理状态。只有
哈希匹配的 `translated` 计入验收数；具有有效 rating 的新论文才计入端到端
完成数。
