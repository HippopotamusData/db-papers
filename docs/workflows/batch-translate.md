# 工作流：Codex 批量全文翻译与历史译文修复

## 目标

一个批次使用固定 Git 基线、`codex/` 分支和隔离工作树。子代理只并行修改互斥
论文目录；独立审阅者负责 PDF 复核；根代理负责范围、共享生成文件、检查点和
集成。批次状态是临时编排信息，不是论文发布元数据。

## 授权与启动

启动前明确：

- 模式是 `draft-only` 还是用户已授权的 `review-and-repair`；
- 交付到工作树、检查点、本地 `main`，还是进一步推送；
- 多轮批次是否已有检查点提交授权。

根代理在批次外创建分支和工作树。本流程不自动创建、删除或修复它们。进入批次
工作树后运行：

```bash
make doctor
make diff-check
make check

BASE=$(git rev-parse HEAD)
BATCH_MANIFEST=tmp/batches/<batch-id>.yaml
make batch-start \
  BATCH_MANIFEST="$BATCH_MANIFEST" \
  MODE=<draft-only|review-and-repair> \
  BASE="$BASE" \
  PAPER_IDS="<paper-id> ..."
```

清单只在 gitignored 的 `tmp/batches/` 保存当前 branch、worktree、`base_sha`、
论文范围和队列状态；它不进入提交，不参与 `reading_status`、校验或发布判断。

## 角色

- **根代理**：维护范围和基线；管理 catalog、检查点及集成；只有根代理可改
  共享配置、生成目录或执行 Git 写操作。
- **翻译/修复子代理**：每次只负责一个 paper ID，只改该目录中的
  `paper.yaml`、`translation.md` 和必要 `assets/`；不得改 `source.pdf`、
  共享文件或其他论文；未完成时交付 `draft`。
- **审阅子代理**：不以机械扫描代替 PDF 核对。需要身份隔离时，不审阅自己的
  最后一次内容修改；若亲自修改内容，修改后重新安排最终复核。

子代理不得继续生成子代理。长正文和日志留在文件中，只返回 paper ID、状态、
修改文件、门禁、warning 和 blocker 的短摘要。

临时状态为：

```text
queued -> translating -> draft-ready -> reviewing -> reviewed -> rated
```

任一步都可进入 `blocked` 并按状态机恢复。`draft-only` 不得进入 `reviewed`
或 `rated`。

```bash
make batch-state \
  BATCH_MANIFEST="$BATCH_MANIFEST" \
  PAPER_ID=<paper-id> \
  STATE=<queued|translating|draft-ready|reviewing|reviewed|rated|blocked>
```

## 每轮执行

1. 运行 `make batch-check BATCH_MANIFEST="$BATCH_MANIFEST"`，为互斥论文目录
   分派子代理并迁移到 `translating`。
2. 翻译/修复完成后运行
   `make paper-check PAPER_ID=<paper-id>`。报告全部 warning，不隐藏候选或降低
   阈值。
3. 根代理等待本轮全部子代理结束，确认没有越界、同篇并发写入或基线漂移。
4. `review-and-repair` 模式下，由审阅者按 review workflow 完成源文清单轮和
   逐项对照轮。缺陷退回修复者；未通过项保持 `draft`。
5. 审阅通过后将 `reading_status` 改为 `translated`，再次运行当前论文的
   `paper-check`，并把临时状态改为 `reviewed`。审阅范围和结论写入任务报告、
   PR 或提交，不生成额外 hash、waiver 或共享账本。
6. 只给本批新增论文执行 rating workflow。证据不足时不写 `rating`，标为
   `blocked`；历史修复保留原 rating，除非另有授权。
7. 每轮运行 `make catalog`、`make check`、`make diff-check`。全绿且已授权时
   创建 checkpoint commit。

不同论文没有共享发布状态文件，可以自然并行；同一论文禁止并发修改。发现范围
重叠、基线外变化或未经分派的论文改动时停止，由根代理重新分派。批次运行期间
不要 merge 或 rebase。

## 关闭与集成

1. 等待全部子代理停止，核对清单、最终状态、检查点和分支。
2. 运行 `make catalog`、`make check`、`make diff-check`。若本批修改校验器或
   影响全局内容解释，用带原因的 `make deep-check` 替代 `make check`。
3. 公式规则、profile 或全库迁移按公式维护工作流完成；普通论文变更使用 scoped
   公式门禁和 CI。
4. 已授权本地集成且 `main` 干净时，执行
   `git merge --ff-only <batch-branch>`；不能 fast-forward 或存在未归属改动时
   停止。
5. 推送需要独立授权；本地门禁未通过时不得推送。

普通批次不运行全库 deep-check。全库机械扫描不授权扩大历史复审范围。

## 恢复与清理

根据 checkpoint、临时 manifest、论文文件和工作区差异恢复，再运行
`make batch-check`。不存在共享发布事务 marker 或恢复协议；普通 Git 状态和门禁
足以暴露部分完成的工作。

只有全部子代理停止、工作区干净、分支已按授权集成且用户授权清理时，才从工作树
外执行 `git worktree remove`。不得使用 `--force` 或 `git branch -D`；删除分支
前用 `git merge-base --is-ancestor` 证明已集成。

## 完成报告

报告清单路径、固定基线、模式、reviewed/rated/draft/blocked paper ID、评分、
分工、检查点、warning、证据缺口、实际门禁、提交/合并/推送和清理状态。只有
当前 revision 处于 `translated` 且门禁通过的论文计入完成数；具有有效 rating
的新论文才计入端到端完成数。
