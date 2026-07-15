---
paper_id: permutable-compiled-queries-dynamically-adapting-without-recompiling
title: 'Permutable Compiled Queries: Dynamically Adapting Compiled Queries without Recompiling'
language: zh-CN
source: source.pdf
---

# Permutable Compiled Queries: Dynamically Adapting Compiled Queries without Recompiling（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

**作者：** Prashanth Menon、Amadou Ngom、Lin Ma、Todd C. Mowry、Andrew Pavlo（卡内基梅隆大学）

## 摘要

即时查询编译是一种提升数据库管理系统（DBMS）分析查询性能的技术。然而，相对于查询本身的执行时间，逐查询编译的成本可能非常显著。这一开销使 DBMS 难以采用成熟的自适应查询处理方法：当真实数据分布与优化器估计不符时，系统无法低成本地为查询生成新计划。优化器也可以预先生成多个子计划，但每加入一个备选都会增加编译时间，因此实际只能容纳少量替代方案。

本文提出 PCQ，用以弥合 JIT 编译与 AQP 之间的鸿沟。PCQ 允许 DBMS 修改已经编译的查询，既不需要重新编译，也不要求在查询开始前包含全部可能变体。PCQ 在查询代码中设置间接层，使 DBMS 甚至能在查询运行过程中改变计划。我们在一个内存 DBMS 中实现 PCQ，并用微基准将其与非自适应计划比较，又与先进分析型 DBMS 比较。实验表明，PCQ 相对静态计划可获得超过 4 倍的性能，在分析基准上相对其他 DBMS 可获得超过 2 倍的性能。

**PVLDB 引用信息：** Prashanth Menon, Amadou Ngom, Lin Ma, Todd C. Mowry, Andrew Pavlo. *Permutable Compiled Queries: Dynamically Adapting Compiled Queries without Recompiling*. PVLDB 14(2): 101-113, 2021. DOI: 10.14778/3425879.3425882。

## 1. 引言

内存 DBMS 假定数据库主要存储在 DRAM，因此磁盘 I/O 不再构成查询瓶颈。研究者转而从减少执行指令数与降低每条指令周期数（CPI）两方面提升 OLAP 性能 [9]。即时查询编译 [10, 21, 39] 把 SQL 转为查询专用机器码；相比解释式执行，它能专门化访问方法和哈希表等中间结构，还可改善紧循环局部性，使元组更可能通过 CPU 寄存器直接在算子间传递 [27, 28]。

但编译只能加速既定计划，无法补救优化器选错操作顺序、误估数据结构大小或未为热键优化代码路径。这些错误来自指数级搜索空间，以及以直方图、草图和样本等摘要为基础、无法捕捉相关性的代价模型 [23]。AQP [12] 用动态反馈环观察执行行为；若真实数据与估计偏差过大，系统可为后续调用改用策略，或停止当前查询，把执行中收集的信息交给优化器生成新计划 [6]。

AQP 对编译式 DBMS 有两项困难。复杂查询重新编译常需数百毫秒 [20]；运行环境和数据分布还可能在一次查询中持续变化，重编译一次并不够。例如同一表不同数据块的最佳谓词顺序会变化；同一缓存计划的不同调用也几乎总有不同并发负载和参数。

PCQ 的关键是“只编译一次”：不反复调用编译器，也不预编译多个物理计划，而把一个计划组织成日后可排列的形式。例如五个合取过滤项有 120 种顺序，PCQ 只编译每项一次，就能按观测选择率在 120 种顺序间切换。其实现融合预编译向量原语 [9] 与 HyPer 风格流水线 JIT [28]，并在底层代码中嵌入轻量钩子，用于观察且在运行中修改流水线；一条流水线的指标也可在其他流水线编译前用于优化它们。

我们在编译式内存 DBMS NoisePage [4] 中实现 PCQ。对商业优化器生成的计划最高提升约 4 倍；与 Tableau HyPer [3] 和 Actian Vector [1] 相比，启用 PCQ 的 NoisePage 最高快 2 倍。

动机实验扫描含 1,000 万元组、六个 64 位整数列的表 A：

```sql
SELECT * FROM A
WHERE col1 = δ1 AND col2 = δ2 AND ... AND col6 = δ6;
```

总体选择率固定，但每个谓词的选择率随数据块变化。实验比较优化器选择固定顺序的最佳静态计划、事先知道每块最佳顺序的“最优”计划和 PCQ。图 1(a) 中，低选择率时静态计划最多慢 4.4 倍；选择率升高时因处理元组增多，差距缩小。PCQ 在所有选择率下距最优不超过 10%。图 1(b) 为 `col1` 再加过滤项形成范围谓词：少于三项时三种方案代码生成时间相近，超过三项后最优方案需生成 $O(n!)$ 个计划；PCQ 从一项增至七项仅增加约 20% 代码生成时间。

![图 1：重新优化已编译查询。PCQ 通过运行时自适应接近最优执行时间，同时避免为所有可能过滤顺序预编译代码。](assets/manual-figure-01-reoptimizing-compiled-queries.png)

## 2. 背景

### 2.1 查询编译

新查询到达时，优化器生成表示关系算子数据流的计划树。解释式 DBMS 遍历计划树执行查询，要反复追踪指针和经过条件分支；磁盘不再是瓶颈时，这种开销尤其不利。查询编译将计划树转换为针对查询硬编码的例程，减少条件判断和其他检查。

DBMS 有两种主要编译方式。其一是输出源代码，再调用 gcc 等外部编译器生成机器码 [19, 21]，早期 MemSQL 和 Amazon Redshift 使用此法。其二是在进程内生成 IR，再由 LLVM 等嵌入式库编译 [28]；HyPer、后期 MemSQL [32]、Peloton [27]、Hekaton 和 Splice Machine 属于此类。

编译时间本身是主要问题：外部编译器每查询可能耗时数秒 [21]，进程内编译器也可能耗时数百毫秒，重量级优化遍还会增加时间。三种缓解办法分别是尽量预编译；分阶段编译以降低启动延迟，但编译器一次只见计划局部，优化效果可能下降；或先解释同一 IR，在后台编译完成后无缝切换到本机代码 [20]。

### 2.2 自适应查询处理

规划时遍历整个数据库代价过高，因此优化器用代价模型近似计划成本；执行时可能发现近似错误，例如低估连接输出基数并选错连接顺序或缓冲区大小 [23]。并发查询对内存通道和 CPU cache 的干扰等环境因素更不可能预知。

AQP 不再严格“先规划、后执行”，而让优化与执行互相反馈 [6]。执行中可丢弃计划并用新估计重新优化 [26]，也可只修改尚未执行的流水线 [40]。重启的代价必须与继续错误计划权衡：若已处理大量必要数据，重启并不明智。为避免重启，一些优化器为单查询生成整流水线 [11, 16] 或流水线内部 [7] 的备选子计划，并插入 `change`、`switch` 等特殊算子在运行时选择。

### 2.3 重新优化已编译查询

为编译式系统重新生成计划很昂贵；即使预先算出一条流水线的全部变体，把额外流水线纳入计划也会增加编译时间。后台编译 [20] 又会与查询执行争用 CPU。细粒度优化更加困难：若想把表扫描中最有选择性的谓词放在最前面，每种顺序都生成流水线会造成组合爆炸；按需编译也未必赶得上数据和环境在执行中的变化。

过滤表达式规范化为析取范式后，若有 $M$ 个析取项，每项含 $N$ 个合取因子，则顺序数为：

$$
R = M!N!
$$

PCQ 要在不枚举这 $M!N!$ 种排列的情况下保留运行时可变性。

## 3. PCQ 概览

PCQ 让 JIT DBMS 在运行中改变已编译查询策略，同时不重启、不重复工作、不预编译替代流水线。它与主动式重新优化 [7] 都无需回到优化器或重复处理元组；区别是 PCQ 不预计算全部子计划，也不预设切换阈值，而在运行时探索能改善延迟或资源利用率的策略。该框架虽为 NoisePage 的 LLVM 环境设计，也适用于其他支持查询编译的引擎。

图 2 给出系统生命周期：优化器先生成物理计划；Translator 把计划转成带 PCQ 构造的 TPL；Compiler 把 TPL 编成 bytecode；执行阶段收集 samples、更新 stats，并通过 policies 改变过滤顺序。

![图 2：系统概览。SQL 被翻译成含间接层的 DSL，再编译成紧凑 bytecode；运行时根据采样统计调整执行策略。](assets/manual-figure-02-system-overview.png)

### 3.1 阶段 1：翻译

优化器生成物理计划后，翻译器把它分解为流水线，并转换成名为 TPL 的数据库 DSL。TPL 结合 VectorWise 风格预编译原语 [9] 与 HyPer 以数据为中心的代码生成 [28]，比 C/C++ 更易应用数据库专用优化，且编译延迟低。

翻译器加入两类 PCQ 构造。第一类是可开关的指标钩子，按策略收集流水线底层操作的运行时性能。第二类是参数化运行时结构，以间接层替换执行策略。算子逻辑可分查询无关与查询特定部分；后者由 DBMS 生成不同版本并用指针切换。间接性有两级：一级中算子无需知道查询特定实现，二级要求运行时与代码生成器协作。图 2 的过滤数组每项指向生成函数，排列只需交换指针。

```text
fun a_eq_1() { ... }
fun b_eq_2() { ... }
fun c_eq_3() { ... }
fun query() {
  var filters = {[a_eq_1, b_eq_2, c_eq_3]}
  for (v in foo) { filters.Run(v) }
}
```

### 3.2 阶段 2：编译

编译器把含钩子和间接结构的 TPL 转成紧凑 CISC 字节码。除算术、内存和分支指令外，还包括带 NULL 语义的 SQL 值比较、表/索引迭代器、哈希表构造和并行任务。图 2 用 `FilterInit`、`FilterInsert`、`RunFilters` 构造可排列过滤器；过滤器的函数指针数组顺序就是实际求值顺序。

### 3.3 阶段 3：执行

DBMS 先解释字节码，同时用 LLVM 异步编译本机代码；完成后自动切换函数实现 [20]。运行时结构的策略决定何时采样，以及收到新指标后如何适应。图 2 以固定概率收集各过滤项选择率和耗时，构造使当前分布下执行时间最小的排名。线程处理不相交表片段，可能看到不同分布，故独立决策；策略还须容纳线程同时运行字节码/本机实现且耗时不同。

NoisePage 是推送式面向批引擎，以类似宽松算子融合 [27] 的方式结合向量化与一次一元组执行。批处理摊销 PCQ 间接开销，并让 LLVM 自动向量化生成代码。

## 4. 支持的查询优化

### 4.1 过滤条件重排

多个过滤谓词的最佳顺序取决于选择率和计算成本。DBMS 先把表达式规范化为 DNF：$M$ 个 disjunctive summand，每个含 $N$ 个 conjunctive factor；summand 之间和 factor 内都可重排，共 $R=M!N!$ 个顺序。每 factor 生成接收 tuple vector 的函数；简单项调用约 250 个预编译 vector primitive，复杂算术用融合 tuple code，避免中间物化。示例查询为：

最佳顺序需要平衡选择率与求值时间：高选择性过滤器能尽早丢弃元组，但自身可能昂贵；最快过滤器又可能丢弃太少元组，使后续过滤浪费周期。将因子拆成函数有两项收益：交换函数指针即可探索顺序；复杂表达式用生成代码、简单表达式用向量原语，各取所长。

```sql
SELECT * FROM A
WHERE col1 * 3 = col2 + col3 AND col4 < 44;
```

Translator 把过滤表达式拆成可调用的过滤函数，并在执行函数中通过 `filters.Run(v)` 进入可排列过滤器。图 3 中，策略模块根据 profile 中的选择率、成本和 rank 重排过滤函数。

![图 3：过滤重排。Translator 把查询转成 TPL；右侧 policy 根据运行时 profile 重排过滤执行顺序。](assets/manual-figure-03-filter-reordering.png)

图 3 的核心生成代码为：

```text
fun query() {
  var filters = {[p1, p2]}
  for (v in A) { filters.Run(v) }
}
fun p1(v:*Vec) { @selectLT(v.col4, 44) }
fun p2(v:*Vec) {
  for (t in v) {
    if (t.col1 * 3 == t.col2 + t.col3) { v[t] = true }
  }
}
```

运行时每批决定是否重采样。若不采样，函数按当前顺序短路；若采样，每个谓词必须对全部输入执行，记录真实选择率与调用时间，再刷新内存统计表并排序。本文用固定概率 $p$ 随机采样，并在第 5 节研究 $p$。由于采样禁用短路而产生冗余工作，策略必须在响应倾斜与采集成本之间权衡。

过滤因子的 rank 按选择率和单元组开销计算：

$$
\mathrm{rank}(p)=\frac{1-s_p}{c_p}
$$

其中 $s_p$ 是谓词 $p$ 的选择率，$c_p$ 是该谓词的单元组求值成本。若不采样，就按当前顺序 short-circuit；若重采样，每个 predicate 必须在全部输入上执行以得到真实选择率和调用时间，产生冗余工作。Profile 存入内存统计表，policy 结合 rank 重排。因此 sampling policy 必须在快速响应 skew 与额外工作间平衡。

### 4.2 自适应聚合

Hash aggregation 分 hashing、probing、key equality、initialization、update 五个 batch step；parallel 还需 merge thread-local partial。Translator 为 query-specific 的 init/update/merge 生成代码，其余使用 vector primitive。若 key skew，PCQ 把 $N$ 个 hot key 抽入专用 JIT 路径，避免 hash probe。示例查询为：

哈希、探测、键相等检查、初始化和更新是五个面向批步骤；并行聚合还需将线程局部部分结果合并到全局表。初始化、更新和合并计算密集且查询特定，故生成定制代码，其余步骤调用向量原语。

```sql
SELECT col1, COUNT(*)
FROM A
GROUP BY col1;
```

图 4 展示 Translator 生成的三个函数：`aggregateHot` 处理 hot key，`aggregateMerge` 合并部分结果，`aggregateRun` 在主路径中分派 hot/cold 路径。策略通过估计 distinct key 数和 hot-set 命中率决定是否启用 hot-set 优化。

`N` 是编译期常量，故 hot equality branch、merge 都可 unroll/inline。每 batch 计算 hash 时还用紧凑 HyperLogLog 估计 distinct；若少于 `N`，分配 hot aggregate array，以 batch 前 `N` 个 unique key 初始化并运行 hot function，再 merge 回 table。HLL 有误差，未命中 tuple 还需 cold pass；可通过误差参数控制风险。Parallel thread 各自执行同样 thread-local 流程，无需额外生成代码。

![图 4：自适应聚合。PCQ 把聚合拆成 hot 路径、cold 路径和 merge 逻辑，并用 policy 决定是否使用 hot set。](assets/manual-figure-04-adaptive-aggregations.png)

```text
fun query() {
  var aggregator = {[..., aggregateHot, aggregateMerge]}
  for (v in A) { aggregator.Run(v) }
}
fun aggregateHot(v:*Vec, hot:[*]Agg) {
  for (t in v) {
    if (t.col1 == hot[0].col1) { hot[0].c++ }
    elif (t.col1 == hot[1].col1) { hot[1].c++ }
  }
}
fun aggregateMerge(hot:[*]Agg, ht:*HashTable) {
  ht[hot[0].col1] = hot[0]
  ht[hot[1].col1] = hot[1]
}
```

热数组每项保存分组键和正在累积的值。$N$ 是编译期常量，因此翻译器生成 $N$ 个条件分支，并完全展开、内联合并逻辑。运行时在计算批内哈希值时用紧凑 HLL [15] 估计不同键数；少于 $N$ 才进入优化路径。热键识别可取前 $N$ 个唯一键或随机采样，本文采用前者，因其性能/成本权衡最好。HLL 误差可能让未命中元组再走冷路径，系统通过误差参数降低额外扫描风险；并行线程仍独立做局部聚合，无需新代码。

### 4.3 自适应连接

PCQ 对 hash join 同时做 runtime hash-table specialization 与 right/left-deep join permutation。Build 首先把 tuple 与 hash 物化到 thread-local row buffer，并用 HLL 估计 unique key；若预计 table 小于 L3，就选 concise hash table，否则选 pointer-tagging bucket-chain，并一次精确 sizing，避免 resize。第二阶段各线程扫描 buffer：bucket chain 用 CAS 插入 pointer，CHT 用 partitioned build。示例查询为：

本文约定左输入为构建侧、右输入为探测侧。构建分两阶段：先把左输入元组和哈希值按行物化到线程局部缓冲区并用 HLL 估计唯一键数；左输入耗尽后，小于 L3 cache 选 CHT [31]，否则选带指针标记的桶链表 [22]，从而一次精确设置大小。随后各线程扫描缓冲区：桶链表通过原子 CAS 插入指针，CHT 按 [31] 分区构造。

```sql
SELECT * FROM A
INNER JOIN B ON A.col1 = B.col1
INNER JOIN C ON A.col2 = C.col1;
```

图 5 展示两种可能的 join ordering，以及 `joinExec.Run(v)` 如何通过 policy 在执行时切换探测顺序。系统先计算 hash，再对多个 hash table 执行 probe；profile 记录每个 join 的选择率和耗时，并驱动 permute。

Optimizer 只对连续 right-deep join 启用，指定含全部 join key 的 driver table。每 join 生成 key-check function，接收 input vector 与 candidate vector，可调用 SIMD gather/select primitive 或 tuple bytecode。Runtime 先为 batch 算 hash，再按 policy 决定采样；probe 分“hash table 内嵌 Bloom filter 的 lookup/filter”和“key equality 排除 false positive”两步，后续 join 只处理此前通过的 tuple。最终 profile 记录每步 selectivity/time 并重排。

![图 5：自适应连接。DBMS 为多个 join 生成可排列执行结构，运行时根据 profile 改变 join 应用顺序。](assets/manual-figure-05-adaptive-joins.png)

优化器面向连续右深连接指定一张驱动表；哈希/索引连接、内/外连接均可排列，因为每个驱动元组独立，中间状态只在一批内短暂存在。NoisePage 额外要求驱动表含所有连接键列。翻译器为每个连接生成键检查函数，输入是元组向量和候选向量；它可调用 SIMD gather/select 原语，也可直接用字节码一次处理一个元组。`joinExec` 中每个连接保存哈希表指针、连接键属性下标和键检查函数指针。

```text
fun query() {
  var joinExec = {[{ht_B, joinB}, {ht_C, joinC}]}
  for (v in A) { joinExec.Run(v) }
}
fun joinB(v:*Vec, m:[*]Entry) {
  for (t in v) { if (t.col1 == m[t].col1) { v[t] = true } }
}
fun joinC(v:*Vec, m:[*]Entry) { @gatherSelectEq(v.col2, m, 0) }
```

探测分两步：先利用哈希表内嵌 Bloom filter，以已计算的哈希值完成合并查找/过滤；再调用键相等函数排除假阳性。后续连接只处理通过前序连接的元组。最终 profile 保存各步选择率和时间，写入内部目录并驱动重排。

## 5. 评估

### 5.1 工作负载

我们在 NoisePage 中实现 PCQ。NoisePage 是 PostgreSQL-compatible HTAP DBMS，在 Apache Arrow in-memory columnar data 上使用 HyPer-style MVCC，并用 LLVM 9 把 bytecode JIT 到机器码。实验机器是 2×10-core Intel Xeon Silver 4114（2.2 GHz、25 MB L3、AVX512）、128 GB DRAM，用 `numactl` 把数据库放入同一 NUMA region。Google Benchmark 自动迭代到稳定时间。

前三组微基准以单线程运行，尽量减少调度干扰；最终系统比较为多线程。合成数据库有 A-F 六张表，每表六个 64 位有符号整数列、300 万元组、144 MB；我们改变列分布和相关性，分别隔离扫描、聚合和多路连接。TPC-H 是八张 3NF 表的决策支持负载 [37]，使用 Microsoft 倾斜生成器 [5]，九条查询覆盖从计算到内存/连接密集型 choke point [8]。SSB 将 `LINEITEM` 与 `ORDERS` 反规范化为 `LINEORDER`，删除 `PARTSUPP` 并增加 `DATE` 维表 [30]。

微基准表含 3 million tuple、占 144 MB，分别隔离三项优化。TPC-H 用 Microsoft skew generator、SF=10（约 10 GB），选 9 条覆盖 choke point 的查询；SSB 同为 SF=10、uniform，含 13 条 join-heavy 查询。系统对比包括 Actian Vector 与 Tableau HyPer。

图 6 的顺序扫描实验显示，三个静态过滤顺序分别只在数据分布的某个区间最优；当选择率在 block #500 和 #1000 变化时，PCQ 通过采样和重排快速接近当前最优顺序。

每段让一个 predicate 约 2% 选择率、另外两个 98%。PCQ 采样率 10%，分布切换后约 10 个 block 内重采样并换到最优，整体比任一 static plan 快约 2.5 倍。

![图 6：随时间变化的性能。三种静态过滤顺序只在局部区间最优，PCQ 能在分布变化后重新排列。](assets/manual-figure-06-performance-over-time.png)

### 5.2 过滤适应性

过滤微基准使用单表顺序扫描：

```sql
SELECT * FROM A
WHERE col1 < 1000 AND col3 < 1000 AND col3 < 3000;
```

原文在此确实两次印作 `col3`；后续描述明确实验有三个轮流成为最优者的谓词。

当过滤选择率与优化器估计不符时，静态计划可能把低选择性或高成本谓词放在前面，导致额外工作。图 7 显示，在整体选择率较低时，PCQ 明显优于静态顺序；当选择率接近 100% 时，所有顺序差异变小，PCQ 的采样开销也更容易显现。

PCQ 全范围距离预知每块最优的 upper bound 不超过 20%。0% 时 PCQ/optimal 比 static 快 2.7/3.6 倍；100% 时无需 adaptivity，PCQ 因 sampling 最慢。所有配置在 100% 反而比 90% 快，因为 full vector 触发专门优化。

![图 7：改变谓词选择率。PCQ 在低选择率区间显著优于静态顺序，并接近按真实分布选择的最优顺序。](assets/manual-figure-07-varying-predicate-selectivity.png)

随后考察重采样频率的开销。频率为 0 时没有 metrics 开销，但无法响应数据分布变化；频率为 1 时每个 block 都采样，适应最快但执行开销更高。论文后续实验采用 0.1 的采样率作为折中。

禁用采样相对可排列过滤慢约 1.7 倍；100% 采样额外增加 15%，0.1 最优。

![图 8：过滤排列开销。重采样频率越高，越能快速适应分布变化，但采样和 profile 更新也会增加开销。](assets/manual-figure-08-filter-permutation-overhead.png)

### 5.3 聚合适应性

聚合实验使用：

```sql
SELECT col1, SUM(col2), SUM(col3), SUM(col4)
FROM A
GROUP BY col1;
```

图 9 改变唯一 aggregate key 数量。当 key 数较少且 hot-set 能覆盖足够多输入时，PCQ 的 hot 路径能减少哈希表访问并提升性能；当 key 数超过缓存友好范围后，PCQ 会回退到混合向量化/JIT 路径，仍优于静态实现。

固定提取 5 个 hot key。少于 5 key 时 hot path 提升 1.5 倍；超过后 hybrid vector/JIT 比 static 快 1.6 倍。约 256k key 时 hash table 超 LLC，data-independent random access 与 auto-vectorization 令 PCQ 快 3 倍。

![图 9：改变 aggregate 数量。PCQ 在 hot key 数较少时收益明显，在 key 数扩大后仍能避免静态计划的高开销。](assets/manual-figure-09-varying-number-aggregates.png)

另一实验固定唯一 key 数并改变 Zipfian skew。随着 skew 增大，hot-set 分支命中率上升，抽出更多 hot key 的配置更有利；低 skew 时额外分支可能带来开销，收益较小。

固定 200k key，比较 0/1/2/4/8 hot。低 skew 各配置差 3% 内，`None` 因无未命中 branch 最快；skew 2.4 时 Hot-8 比 None 快 18 倍。Skew 1.6 时 Hot-1/Hot-8 命中 45%/82%，skew 2.4 时范围为 72%-98%。

![图 10：改变聚合倾斜度。上图为执行时间，下图为 hot 分支命中率；skew 越高，hot-set 优化越有效。](assets/manual-figure-10-varying-aggregation-skew.png)

### 5.4 连接适应性

连接实验使用三表 hash join，并改变整体 join 选择率：

```sql
SELECT * FROM A
INNER JOIN B ON A.col1 = B.col1
INNER JOIN C ON A.col2 = C.col1;
```

图 11 显示，在低选择率时 PCQ 能快速发现更优 join 顺序，避免静态顺序的无效探测；随着选择率提高，所有 tuple 都更可能匹配，重排收益下降。

0% 时 PCQ 在 10 block 内找到最优，比 static 快约 14 倍；100% 时仍因 vectorized hash/probe/equality 小幅领先。

![图 11：改变 join 选择率。低选择率下 PCQ 通过重排 join 避免无效探测，高选择率下差距缩小。](assets/manual-figure-11-varying-join-selectivity.png)

最后改变 join 数量并保持整体选择率为 10%。当 join 数增加时，静态计划的错误顺序会放大无效工作，而 PCQ 通过运行时重排保持更低执行时间。

单 join 无需排列，NoisePage 实际会消除间接层；图中 PCQ 仍因 vectorized hash/probe 与 LLVM auto-vectorized equality 快 1.15 倍。两 join 快 3 倍，超过三 join约快 2.5 倍。

![图 12：改变 join 数量。PCQ 在多步 join 中通过重排最有选择性的 join 获得更大收益。](assets/manual-figure-12-varying-number-joins.png)

### 5.5 系统比较

在 skewed TPC-H 上，我们比较 Vector、HyPer、NoisePage 无 PCQ 和 NoisePage 启用 PCQ 的执行时间。图 13 展示总体执行时间，表 1 展示逐步启用过滤、聚合、连接三类 PCQ 优化带来的相对 speedup。

Vector 9.2 是基于 MonetDB/X100 [9] 的列式向量引擎，使用 SIMD 优化原语；我们调整配置以充分利用内存和 CPU 线程。HyPer 5.1 用 LLVM 生成可解释或 JIT 的一次一元组计划，且支持 SIMD 谓词求值；依 Tableau 工程师建议未改配置。各系统载入数据后执行统计收集与优化，预热一次，再报告连续五次平均。我们人工检查计划并尽力保证等价；NoisePage 使用 HyPer 优化器生成的计划。

#### 5.5.1 倾斜 TPC-H 逐查询分析

Microsoft 生成器倾斜度为 2.0。表 1 中每格表示在此前 PCQ 优化基础上再启用本项的相对加速；接近 1.0 表示影响小，空白表示不适用。

- **Q1：** 四个分组键上计算五个聚合。最热键对接收的更新从无倾斜时 49% 增至高倾斜时 86%，触发聚合优化并提升 1.7 倍。PCQ NoisePage 比 Vector 快 4.8 倍、比 HyPer 慢 1.2 倍；我们归因于 HyPer 的定点运算快于 NoisePage 浮点运算。
- **Q4：** 五个分组键上一个聚合，`ORDERS` 上有可排列过滤；`o_orderdate` 范围谓词选择率 0.08% 且高度倾斜。翻转范围谓词并优化聚合后，相对 NoisePage 基线和商业系统均提升约 2 倍，主要收益来自聚合。
- **Q5：** 六表连接但仅两个连接可排列；最终在两个分组键上求和。过滤收益有限，聚合提升 1.33 倍；两个可排列连接未重排，连接项为 1.00。总体比 HyPer 快 3 倍、比 Vector 快 5 倍。
- **Q6：** `LINEITEM` 上过滤选择率 0.05%。倾斜不改变谓词顺序，固定概率重采样反使 PCQ 比基线慢 4%；更高级采样策略可避免。各系统 SIMD 过滤性能接近。
- **Q7：** HyPer 选择的 bushy 连接计划比右深计划慢 4 倍。虽无元组进入最终聚合，PCQ 翻转 `l_shipdate` 范围谓词仍提升 1.2 倍。
- **Q11：** 五个连接均不可排列；两个聚合基数不触发优化；向量化谓词都只有单项。无 PCQ 优化触发，说明框架空载开销可忽略。NoisePage 与 HyPer 接近，比 Vector 快 4 倍。
- **Q16：** 以 `PARTSUPP` 为驱动的右深流水线，`PART` 上有多项过滤和哈希聚合。过滤重排提升近 1.2 倍；按构建表大小重排连接以使用 SIMD gather 又提升 1.2 倍。总体比 HyPer 快 7.4 倍、比 Vector 快 3 倍；HyPer 高倾斜下错选左反连接而非右反连接。
- **Q18：** 以 `ORDERS` 为驱动的右深流水线；聚合基数超过阈值。PCQ 重排连接，使小表使用 SIMD gather，提升 1.19 倍。HyPer 错用右半连接而非左半连接，比 PCQ 慢 2.6 倍。
- **Q19：** `PART` 与 `LINEITEM` 内连接后接复杂析取过滤和静态聚合。重排 `LINEITEM` 谓词提升 1.2 倍。HyPer 分别比 NoisePage、Vector 快 1.2 倍和 2.5 倍；NoisePage 损失来自一次一元组与向量过滤并用时“已选元组”内部表示间的转换。

![图 13：skewed TPC-H 系统比较。NoisePage 启用 PCQ 后在多条查询上明显降低执行时间。](assets/manual-figure-13-system-comparison-tpch.png)

表 1：TPC-H speedup。数值表示在已有前序 PCQ 优化基础上再启用对应优化后的增益；`-` 表示该优化未适用。

| Query | +Filters (§4.1) | +Aggregations (§4.2) | +Joins (§4.3) |
|---|---:|---:|---:|
| Q1 | - | 1.71 | - |
| Q4 | 1.05 | 1.54 | - |
| Q5 | 1.08 | 1.33 | 1.00 |
| Q6 | 0.96 | - | - |
| Q7 | 1.02 | 1.40 | 1.00 |
| Q11 | - | 1.02 | - |
| Q16 | 1.18 | 1.00 | 1.00 |
| Q18 | - | 1.00 | 1.19 |
| Q19 | 1.21 | - | - |

在 SSB 上，所有系统都先收集统计信息并执行必要优化。图 14 展示端到端执行时间；表 2 表明，SSB 中最主要收益来自 join permutation，尤其是 Q2/Q3 类查询。

![图 14：Star Schema Benchmark 系统比较。SSB 上 PCQ 对 join-heavy 查询提升更明显。](assets/manual-figure-14-system-comparison-ssb.png)

表 2：SSB speedup。数值表示逐步启用 PCQ 优化后的相对增益。

| Query | +Filters (§4.1) | +Aggregations (§4.2) | +Joins (§4.3) |
|---|---:|---:|---:|
| Q1.1 | 1.00 | 1.00 | 1.00 |
| Q1.2 | 1.02 | 1.00 | 1.00 |
| Q1.3 | 1.06 | 1.00 | 1.00 |
| Q2.1 | 0.96 | 1.00 | 1.32 |
| Q2.2 | 0.99 | 1.00 | 1.56 |
| Q2.3 | 1.00 | 1.00 | 1.60 |
| Q3.1 | 1.00 | 1.00 | 1.20 |
| Q3.2 | 1.01 | 1.00 | 1.42 |
| Q3.3 | 1.03 | 1.00 | 1.69 |
| Q3.4 | 1.00 | 1.00 | 0.92 |
| Q4.1 | 1.03 | 1.00 | 1.19 |
| Q4.2 | 1.02 | 1.00 | 1.33 |
| Q4.3 | 1.02 | 1.00 | 0.98 |

#### 5.5.2 SSB 分组分析

十三条查询分四组，组内结构等价，只是过滤和聚合项不同。为展示自适应收益，PCQ NoisePage 从随机初始计划开始，而无 PCQ 版本使用 HyPer 生成的最优计划。

- **Q1.*：** 最小表与最大表之间只有一个连接，两表都有选择性多项过滤。连接不可排列，过滤重排只带来小幅收益。HyPer 在压缩数据上执行 SIMD 向量过滤，CPI 更好，分别比 NoisePage 和 Vector 快 1.7 倍、3.7 倍。
- **Q2.*：** 三个连接和一个聚合。PCQ 从随机连接顺序出发，按选择率和运行条件排列，平均比基线快约 1.5 倍。过滤探索有轻微负收益，因为最佳顺序始终不变；可调采样策略能避免。总体比 HyPer 快 1.4 倍、比 Vector 快 2.2 倍。
- **Q3.*：** 与 Q2 类似但替换一张基表，仅 Q3.4 触发聚合优化。连接探索平均提升 1.3 倍；Q3.4 因最佳排名稳定后仍探索其他顺序而退化，探索开销大于收益。总体比基线和 HyPer 快 1.3 倍、比 Vector 快 3.2 倍。
- **Q4.*：** 连接全部五张表。除 Q4.3 外均找到最优连接和过滤顺序，相对基线约提升 1.26 倍；Q4.3 同样因强制探索退化。平均比基线快 1.2 倍，比 HyPer、Vector 分别快 1.9 倍、3.4 倍。

总体来看，与非自适应静态计划相比，PCQ 在微基准中最高超过 4 倍；在分析基准中，相对其他先进 DBMS 也有超过 2 倍的性能优势。重要结论是：少量间接开销通常小于错误编译计划带来的损失。

## 6. 相关工作

Deshpande 等综述了 2000 年代后期以前的 AQP [12]。AQP 监控查询运行行为，判断优化器基数估计是否越过阈值，然后用新估计重新优化，或在物化点切换备选子计划；前者因重编译成本不适合 JIT DBMS。

与 PCQ 最相关的是参数化优化 [11, 16] 和主动式重新优化 [7]。Volcano 为一条流水线生成多个计划，以 `choose-plan` 算子按观测基数选择。Rio 在流水线内加入 `switch` 算子并收集运行统计。Plan Bouquets [14] 生成运行时切换且有最坏情况界的“参数化最优计划集”。它们面向解释式 DBMS，只在执行前粗粒度选择不可排列子计划；PCQ 可在流水线执行中切换策略。Perron 等也表明现代代价优化器对部分查询仍会失效 [33]，PCQ 在执行期处理许多相同问题。

IBM 的 AQP 可动态重排流水线连接 [24]，但针对 OLTP，难以推广到分析查询。SkinnerDB 用强化学习近似最优连接顺序 [38]，却需为所有索引预计算哈希表，且只支持单线程。HyPer 的自适应编译 [20] 与 NoisePage 一样先解释专用字节码，但其字节码源自 LLVM IR；HyPer 只在解释/编译模式间切换，不修改高层计划或进行第 4 节的流水线内优化。

Vector [9] 拼接按数据类型专门化的预编译原语。其“微自适应”用不同编译器生成原语，并以多臂老虎机按性能选择 [34]；它只能改变编译器，不能依据观测数据做全计划优化。Zeuch 等用 CPU 硬件计数器建立代价模型，估计多表选择率并调整执行顺序。

Apache Spark 的方法动态推测优化数据文件解析代码 [35]。Grizzly [17] 先生成带 profiling 的通用 C++，再重编译优化变体并用硬件计数器验证；它支持谓词重排和域值专门化，但 PCQ 无需重编译且支持更多优化。

早期 Postgres 谓词迁移 [18] 收集谓词完成时间，供优化器为未来查询权衡选择率与求值成本；DB2 的 LEO [36] 同样把运行信息反馈给优化器。PCQ 则修改当前正在执行的查询。Dreseler 等将 TPC-H choke point 分为计划级、逻辑算子级和引擎效率级 [13]，认为谓词放置和子查询扁平化最重要；PCQ 在执行引擎支持前者，后者仍由优化器负责。

## 7. 结论

本文提出 PCQ，一种弥合 JIT 编译与 AQP 之间鸿沟的查询处理架构。PCQ 在生成代码中加入带间接层的动态运行时结构，使 DBMS 能在查询运行期间安全、原子地切换计划。为摊销切换开销，生成代码依赖面向批的处理。

我们为三类关系算子提出了 PCQ 优化。对于扫描，系统使用自适应过滤器，高效发现能缩短执行时间的过滤顺序。对于基于哈希的聚合，系统动态识别并利用 grouping key 的倾斜，把重键抽入哈希表之外的专用路径。最后，对于 hash join，系统既可按构建侧数据定制哈希表实现，也可在运行时重排多个 join，以最大化性能。实验表明，NoisePage 启用 PCQ 后，在合成工作负载上最高获得 4 倍性能提升，在 TPC-H 和 SSB 基准上最高获得 2 倍性能提升。

## 致谢

本文工作部分由 National Science Foundation (IIS-1846158, IIS-1718582, SPX-1822933)、Google Research Grants 和 Alfred P. Sloan Research Fellowship program 支持。

## 参考文献

- [1] [n.d.]. Actian Vector. http://esd.actian.com/product/Vector.
- [2] [n.d.]. Google Benchmark. https://github.com/google/benchmark.
- [3] [n.d.]. HyPer. https://hyper-db.de.
- [4] [n.d.]. NoisePage. https://noise.page.
- [5] [n.d.]. Skewed TPC-H. https://www.microsoft.com/en-us/download/details.aspx?id=52430.
- [6] Shivnath Babu and Pedro Bizarro. 2005. Adaptive Query Processing in the Looking Glass. In CIDR. 238–249.
- [7] Shivnath Babu, Pedro Bizarro, and David DeWitt. 2005. Proactive Re-optimization. In SIGMOD. 107–118.
- [8] Peter Boncz, Thomas Neumann, and Orri Erling. 2014. TPC-H Analyzed: Hidden Messages and Lessons Learned from an Influential Benchmark.
- [9] Peter Boncz, Marcin Zukowski, and Niels Nes. 2005. MonetDB/X100: Hyper- pipelining query execution. In CIDR.
- [10] Donald D. Chamberlin, Morton M. Astrahan, Michael W. Blasgen, James N. Gray, W. Frank King, Bruce G. Lindsay, Raymond Lorie, James W. Mehl, Thomas G. Price, Franco Putzolu, Patricia Griffiths Selinger, Mario Schkolnick, Donald R. Slutz, Irving L. Traiger, Bradford W. Wade, and Robert A. Yost. 1981. A history and evaluation of System R. Commun. ACM 24 (October 1981), 632–646. Issue 10.
- [11] Richard L. Cole and Goetz Graefe. 1994. Optimization of Dynamic Query Evalua- tion Plans. In Proceedings of the 1994 ACM SIGMOD International Conference on Management of Data (SIGMOD ’94). 150–160.
- [12] Amol Deshpande, Zachary G. Ives, and Vijayshankar Raman. 2007. Adaptive Query Processing. Foundations and Trends in Databases 1, 1 (2007), 1–140.
- [13] Markus Dreseler, Martin Boissier, Tilmann Rabl, and Matthias Uflacker. 2020. Quantifying TPC-H Choke Points and Their Optimizations. PVLDB 13, 8 (2020), 1206–1220.
- [14] Anshuman Dutt and Jayant R. Haritsa. 2014. Plan Bouquets: Query Process- ing without Selectivity Estimation. In Proceedings of the 2014 ACM SIGMOD International Conference on Management of Data (SIGMOD ’14). 1039–1050.
- [15] Philippe Flajolet, Éric Fusy, Olivier Gandouet, and Frédéric Meunier. 2007. Hy- perLogLog: the analysis of a near-optimal cardinality estimation algorithm. In AofA: Analysis of Algorithms (DMTCS Proceedings). 137–156.
- [16] G. Graefe and K. Ward. 1989. Dynamic Query Evaluation Plans. SIGMOD Rec. 18, 2 (June 1989), 358–366.
- [17] Philipp M Grulich, Sebastian Breß, Steffen Zeuch, Jonas Traub, Janis von Bleichert, Zongxiong Chen, Tilmann Rabl, and Volker Markl. 2020. Grizzly: Efficient Stream Processing Through Adaptive Query Compilation (SIGMOD).
- [18] Joseph M. Hellerstein and Michael Stonebraker. 1993. Predicate Migration: Opti- mizing Queries with Expensive Predicates. In SIGMOD. 267–276.
- [19] Yannis Klonatos, Christoph Koch, Tiark Rompf, and Hassan Chafi. 2014. Building efficient query engines in a high-level language. PVLDB 7, 10 (2014), 853–864.
- [20] André Kohn, Viktor Leis, and Thomas Neumann. 2018. Adaptive Execution of Compiled Queries. In ICDE. 197–208.
- [21] Konstantinos Krikellas, Stratis D Viglas, and Marcelo Cintra. 2010. Generating code for holistic query evaluation. In Data Engineering (ICDE), 2010 IEEE 26th International Conference on. IEEE, 613–624.
- [22] Viktor Leis, Peter Boncz, Alfons Kemper, and Thomas Neumann. 2014. Morsel- driven Parallelism: A NUMA-aware Query Evaluation Framework for the Many- core Age. In SIGMOD. 743–754.
- [23] Viktor Leis, Andrey Gubichev, Atanas Mirchev, Peter A. Boncz, Alfons Kemper, and Thomas Neumann. 2015. How Good Are Query Optimizers, Really? PVLDB 9, 3 (2015), 204–215.
- [24] Q. Li, M. Shao, V. Markl, K. Beyer, L. Colby, and G. Lohman. 2007. Adaptively Re- ordering Joins during Query Execution. In 2007 IEEE 23rd International Conference on Data Engineering. 26–35. https://doi.org/10.1109/ICDE.2007.367848
- [25] Tianyu Li, Matthew Butrovich, Amadou Ngom, Wes McKinney, and Andrew Pavlo. 2019. Mainlining Databases: Supporting Fast Transactional Workloads on Universal Columnar Data File Formats. Under Submission.
- [26] Volker Markl, Vijayshankar Raman, David Simmen, Guy Lohman, Hamid Pira- hesh, and Miso Cilimdzic. 2004. Robust Query Processing through Progressive Optimization. In Proceedings of the 2004 ACM SIGMOD International Conference on Management of Data (SIGMOD ’04). 659–670.
- [27] Prashanth Menon, Todd C. Mowry, and Andrew Pavlo. 2017. Relaxed Opera- tor Fusion for In-Memory Databases: Making Compilation, Vectorization, and Prefetching Work Together At Last. Proceedings of the VLDB Endowment 11 (September 2017), 1–13. Issue 1.
- [28] Thomas Neumann. 2011. Efficiently Compiling Efficient Query Plans for Modern Hardware. PVLDB 4, 9 (2011), 539–550.
- [29] Thomas Neumann, Tobias Mühlbauer, and Alfons Kemper. 2015. Fast Serializ- able Multi-Version Concurrency Control for Main-Memory Database Systems (SIGMOD).
- [30] Patrick O’Neil, Elizabeth O’Neil, Xuedong Chen, and Stephen Revilak. 2009. The star schema benchmark and augmented fact table indexing. In Technology Conference on Performance Evaluation and Benchmarking. Springer, 237–252.
- [31] R Barber G Lohman I Pandis, V Raman R Sidle, G Attaluri N Chainani S Lightstone, and D Sharpe. 2014. Memory-Efficient Hash Joins. Proceedings of the VLDB Endowment 8, 4 (2014).
- [32] Drew Paroski. 2016. Code Generation: The Inner Sanctum of Database Per- formance. http://highscalability.com/blog/2016/9/7/code-generation-the-inner- sanctum-of-database-performance.html.
- [33] M. Perron, Z. Shang, T. Kraska, and M. Stonebraker. 2019. How I Learned to Stop Worrying and Love Re-optimization. In 2019 IEEE 35th International Conference on Data Engineering (ICDE).
- [34] Bogdan Raducanu, Peter A. Boncz, and Marcin Zukowski. 2013. Micro adaptivity in Vectorwise. In SIGMOD. 1231–1242.
- [35] Filippo Schiavio, Daniele Bonetta, and Walter Binder. 2020. Dynamic Speculative Optimizations for SQL Compilation in Apache Spark. Proc. VLDB Endow. 13, 5 (Jan. 2020), 754–767. https://doi.org/10.14778/3377369.3377382
- [36] Michael Stillger, Guy M. Lohman, Volker Markl, and Mokhtar Kandil. 2001. LEO - DB2’s LEarning Optimizer. In VLDB. 19–28.
- [37] The Transaction Processing Council. 2013. TPC-H Benchmark (Revision 2.16.0). http://www.tpc.org/tpch/.
- [38] Immanuel Trummer, Junxiong Wang, Deepak Maram, Samuel Moseley, Saehan Jo, and Joseph Antonakakis. 2019. SkinnerDB: Regret-Bounded Query Evaluation via Reinforcement Learning. CoRR abs/1901.05152 (2019). arXiv:1901.05152 http://arxiv.org/abs/1901.05152
- [39] Stratis D. Viglas. 2013. Just-in-time Compilation for SQL Query Processing. PVLDB 6, 11 (2013), 1190–1191.
- [40] Jianqiao Zhu, Navneet Potti, Saket Saurabh, and Jignesh M. Patel. 2017. Looking Ahead Makes Query Plans Robust. PVLDB 10, 8 (2017), 889–900.
