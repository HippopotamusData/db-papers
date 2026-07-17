---
paper_id: interleaved-multi-vectorizing
title: Interleaved Multi-Vectorizing
language: zh-CN
source: source.pdf
---

# Interleaved Multi-Vectorizing（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者

Zhuhe Fang、Beilei Zheng、Chuliang Weng

华东师范大学数据科学与工程学院；Chuliang Weng 为通讯作者。

## 摘要

SIMD 是主流处理器中的指令集，可提供数据级并行性以加速应用。然而，当应用遭遇大量缓存未命中时，SIMD 优势会削弱。为消除 SIMD 向量化中的缓存未命中，本文提出交错多向量化（interleaved multi-vectorizing，IMV）。IMV 交错执行多个向量化代码实例，用更多计算隐藏内存访问延迟。我们还提出 residual vectorized states，用于解决向量化中的控制流分歧。

IMV 可以同时充分利用 SIMD 的数据并行性，以及通过预取获得的内存级并行性。它减少缓存未命中、分支未命中和计算开销，从而显著加速 pointer-chasing 应用，并可应用于整个查询流水线执行。实验表明，相比纯标量实现和纯 SIMD 向量化，IMV 最高分别提升 4.23 倍和 3.17 倍。

## 1. 引言

SIMD（Single Instruction Multiple Data）是现代处理器上的指令集。通过 SIMD，一条指令可以并行作用于多个数据点，而不是执行多条指令。随着向量宽度增加，SIMD 提供更高数据并行性；最新 AVX-512 可达 512 位。数据库、图和其他领域已经广泛研究用 SIMD 加速 join、partitioning、sorting、Bloom filter、selection 和 compression 等操作。这些操作通过 SIMD 向量化降低计算开销和分支未命中。

但当操作频繁访问内存数据时，例如探测哈希表、探测 Bloom filter 和搜索树，SIMD 收益会下降。原因是这些操作在大数据集超过处理器缓存时受内存访问延迟主导。虽然 SIMD 可在一个向量中发出更多内存访问，但由于 SIMD lockstep 执行，即使向量中某些元素命中缓存，它们也必须等待其他元素的缓存未命中完成。CPU 与内存速度差距扩大也会使这个瓶颈更严重；SIMD 加速的是 CPU 处理而非数据访问本身。

我们用链式哈希表上的 hash join probe 展示内存访问影响。哈希表从 0.5MB 到 2GB，probe 表为 800MB，数据按 Zipf 因子 1 生成。随着哈希表增大，纯标量 probe 和 SIMD probe 吞吐都显著下降，直到哈希表超过缓存容量后受大量缓存未命中支配。在标量代码中，软件预取可有效减少这类未命中。GP、SPP 和 AMAC 是典型预取优化方法，其中 AMAC 可较好处理不规则数据访问，并能在大哈希表上将吞吐翻倍。

![图 1：链式哈希表 probe 在不同哈希表大小下的吞吐。](assets/figure-01-hash-probe-performance.png)

此前工作没有系统研究缓存未命中对 SIMD 操作的影响。一些工作调整数据布局以提高局部性并受益于硬件预取；另一些工作只是初步使用软件预取；ROF 在查询计划中连接 SIMD 优化代码和预取优化代码，但没有在单个算子内部完全结合二者。

把 GP、SPP、AMAC 与 SIMD 直接结合看似自然，但会遇到控制流分歧带来的向量 bubble。例如，一个向量中的多个元组并行探测不同哈希桶，其中部分元组可能因桶链较短提前结束，后续处理时相应 lane 空闲。完全向量化可以填满空闲 lane，但老元组和新元组为了保持同步可能重复某些步骤，仍浪费 lane；更严重的是，它难以处理一般 `if` 和循环语句中的多个有效分支。

因此，直接或完全地把 SIMD 与预取优化技术结合，既不能充分利用向量，也不能适用于一般情形。本文提出 IMV：以交错方式运行多个向量化代码实例。某个实例遇到即时内存访问时，发起数据预取并切换到其他运行实例，尝试用其他实例的计算覆盖内存访问。我们还引入 residual vectorized states：当某个状态中的向量不满时，它与该点的 residual state 合并，使向量变满后继续，或者变空后重启。这样分歧状态不会影响后续执行，所有实例可充分利用向量 lane。

本文贡献包括：系统研究如何减少 SIMD 向量化中的缓存未命中；直接和完全地把 SIMD 用于现有预取优化技术并分析其不足；提出 IMV 以结合 SIMD 与预取；提出 residual vectorized state 解决一般 `if` 和循环中的控制流分歧；在 CPU 和 Phi 协处理器上做全面实验。

后文第 2 节介绍 SIMD 向量化与预取背景；第 3 节分析如何把 SIMD 与既有预取优化技术结合；第 4 节给出 IMV 和用于处理控制流分歧的 residual vectorized state；第 5 节进行实验评测；第 6 节讨论复杂查询中的 IMV 与自动化；第 7 节介绍相关工作；第 8 节总结。

## 2. 背景

### 2.1 SIMD 向量化

现代处理器提供 SIMD 指令，让一条指令处理多个数据元素。AVX-512 中一个向量可有 8 个 64 位整数 lane。SIMD 不仅减少计算开销，还可在某些场景中把控制流转成数据流以避免分支。例如，对简单 `if`，SIMD 可以执行所有分支再按条件合并结果。

SIMD 还提供便于内存访问和数据重排的指令。`gather` 从非连续地址选择性读取数据到向量，`scatter` 执行反向操作。AVX512PF 支持 gather/scatter 的预取。`compress` 按 mask 把活跃元素连续打包到目标向量；`expand` 把连续元素存入另一个向量的指定位置。

![图 2：SIMD compress 操作。](assets/figure-02-compress.png)

![图 3：SIMD expand 操作。](assets/figure-03-expand.png)

已有工作给出完全向量化主存数据库操作的原则：若标量算法复杂度为 `O(f(n))`，则完全向量化实现应执行 `O(f(n)/W)` 条向量指令，其中 `W` 是向量长度。这个定义排除了随机内存访问，因为每周期执行 `W` 个缓存访问是不现实的硬件设计。因此，对内存密集型操作实现完全向量化很困难。

### 2.2 预取

处理器速度与内存速度差距不断扩大，形成 memory wall。缓存可缓解该问题，但缓存未命中成本高，通常约 80ns 到 200ns。Miss Status Holding Register（MSHR）或 Line Fill Buffer（LFB）等硬件结构用于跟踪未完成缓存未命中；一般每核有 6-10 个 L1 MSHR，允许 6-10 个 in-flight 内存请求，形成内存级并行性（MLP）。具体而言，Intel Skylake 有 10 个 L1 MSHR 和 16 个 L2 MSHR。但由于指令依赖，当前软件通常不能充分使用这些结构。

硬件预取能检测规则步长访问模式，但不擅长复杂和随机访问。推测执行可提前执行有限指令，但分支预测错误会浪费内存带宽。软件预取是充分利用 MLP 的实用方法：程序在数据需要前主动发出内存请求。若预取距离太短，数据还没进入缓存；若太长，数据可能已被逐出。

对 pointer-chasing 应用，如跳表、哈希表查找和树搜索，下一节点地址在当前节点处理前未知。知道地址到真正需要数据之间的时间远短于理想预取距离。本文把这种访问称为 immediate memory access。它只能通过任务间并行受益于软件预取：任务发出预取后不继续等待，而切换到其他任务，稍后再回来处理预取结果。

GP、SPP 和 AMAC 都基于这一思想。它们共同启动 `G` 个处理不同输入的相同任务，并把每个包含 `N` 次依赖内存访问的任务切成 `N+1` 个代码阶段；每个阶段消费上一阶段预取的数据，再为下一阶段发起新预取。三者的区别是如何交错这些阶段：group prefetching（GP）反复按阶段成组执行来自 `G` 个任务的同类阶段；software-pipelined prefetching（SPP）把 `G` 个任务放入软件流水线；asynchronous memory access chaining（AMAC）则把 `N+1` 个阶段编码成有限状态机（FSM），由 `G` 个 FSM 实例独立、循环交错推进。GP/SPP 把阶段耦合到 group 或 pipeline，面对不规则访问不够灵活；AMAC 更适合 pointer chasing 的 immediate memory access。

## 3. 结合预取与 SIMD

此前研究通常用 SIMD 或预取优化单个算子，而不是完全结合两者。在一个算子中结合 SIMD 与预取，理论上可同时降低分支误预测、计算开销和缓存未命中。直接方案是把 SIMD 应用于现有预取优化技术。预取技术包括 GP、SPP 和 AMAC；SIMD 可直接使用或完全使用，因此共有六种组合。论文重点以 AMAC 为例分析。

分析对象是 hash join probe，一个典型 pointer-chasing 应用。probe 使用链式哈希表，每个桶可能因冲突包含多个节点，每个节点由元组和 next 指针组成。probe 过程有两步：计算外侧元组 join key 的哈希，找到对应桶；然后迭代比较桶链中节点的 join key。对桶链的多次匹配导致随机访问，是性能瓶颈。

![图 4：链式哈希表 probe 及其 FSM。](assets/figure-04-hash-probe-fsm.png)

### 3.1 预取中的直接向量化

AMAC 把过程逻辑映射为 FSM，状态由 immediate memory access 分隔，然后交错多个 FSM 实例。直接向量化 AMAC（DVA）把每个 FSM 状态向量化。SIMD 处理的是一个元组 batch，batch 大小等于向量 lane 数 `W`。一个向量化状态只有在该状态中 batch 的所有元组都处理完时才结束；即使只剩一个元组未完成，该状态仍然活跃。

原文清单 1 的 DVA probe 结构如下（`G` 为交错实例数，`W` 为向量宽度）：

**代码清单 1：直接向量化的 AMAC probe。**

```c
struct fsm_t { v key, payload, ptr; state_t state; };

void dva_probe(tuple_t *tuple, hashtable_t *ht, table_t *out) {
    fsm_t fsm[G];
    int all_done = 0;
    while (all_done < G) {
        k = (k == G) ? 0 : k;
        switch (fsm[k].state) {
        case H:                         // 哈希输入 key，预取 bucket
            if (i < tuple_num) {
                fsm[k].key = load(tuple[i].key);
                v hashed = HASH(fsm[k].key);
                fsm[k].ptr = ht->buckets + hashed;
                v_prefetch(fsm[k].ptr);
                fsm[k].state = M;
                i += W;
            } else {
                fsm[k].state = D;
                ++all_done;
            }
            break;
        case M: {                       // 匹配 key，预取 next 节点
            m match = fsm[k].ptr->key == fsm[k].key;
            out[num] = store(fsm[k].ptr->payload, match);
            num += popcount(match);
            m valid = fsm[k].ptr->next != v_null;
            if (any(valid)) {
                v_prefetch(fsm[k].ptr->next, valid);
                fsm[k].ptr = select(fsm[k].ptr->next, valid);
            } else {
                fsm[k].state = H;
            }
            break;
        }}
        ++k;
    }
}
```

这种 lockstep 处理在哈希桶长度不同时产生 inactive lanes。某些元组提前完成匹配，其 lane 在后续匹配状态中空闲，形成 bubble。DVA 可以交错多个向量实例以覆盖部分内存访问，但仍浪费大量 lane。

图 5(a) 给出具体过程：group size 为 2、每个向量 4 个 lane，`a-h` 八个元组对应桶链长度依次为 1、2、1、3、1、1、2、1。到 `M6` 时，`a`、`b`、`c` 已完成，左侧向量只有 `d` 的 lane 仍活跃，另外三个 lane 成为 bubble。最坏情况下一个向量只剩一个活跃 lane，向量执行退化为标量，同时 inactive lane 也不再发出有用内存访问，DLP 与 MLP 都受损。直接向量化 GP/SPP 更严重：若某个实例提前结束，对应整个向量不能立即装入新元组；例如图中 GP 必须把 `H7` 推迟到下一轮，并让一个空向量继续 matching。

![图 5：三种交错方案在 hash join probe 上的执行模式。](assets/figure-05-execution-patterns.png)

GP 和 SPP 的直接向量化更糟，因为它们把多个阶段耦合成组或流水线。若某个运行实例提前结束，相应整个向量可能空闲，无法立即装载新元组继续。

### 3.2 预取中的完全向量化

完全向量化尝试通过把空闲 lane 填入新元组来避免 bubble。对 hash join probe，可把 FSM 从 `H M M ... M` 改写为重复的 `H M` 结构，使所有状态定期出现，并在 lane 空闲时引入新元组。这能保持向量占满。

完全向量化 AMAC（FVA）在每次 `M` 后总回到 `H`，由 `H` 只向无效 lane 装入新 key：

**代码清单 2：完全向量化的 AMAC probe。**

```c
struct fsm_t { v key, payload, ptr; state_t state; m valid; };

void fva_probe(tuple_t *tuple, hashtable_t *ht, table_t *out) {
    fsm_t fsm[G];
    int all_done = 0;
    while (all_done < G) {
        k = (k == G) ? 0 : k;
        switch (fsm[k].state) {
        case H:
            if (i < tuple_num) {
                m empty = !fsm[k].valid;
                fsm[k].key = load(tuple[i].key, empty);
                v hashed = HASH(fsm[k].key);
                v ptr = ht->buckets + hashed;
                fsm[k].ptr = select(ptr, empty, fsm[k].ptr);
                v_prefetch(fsm[k].ptr);
                fsm[k].state = M;
                i += popcount(empty);
                fsm[k].valid |= empty;
            } else {
                fsm[k].state = D;
                ++all_done;
            }
            break;
        case M: {
            m match = fsm[k].ptr->key == fsm[k].key;
            out[num] = store(fsm[k].ptr->payload, match);
            num += popcount(match);
            fsm[k].valid = fsm[k].ptr->next != v_null;
            fsm[k].ptr = select(fsm[k].ptr->next, fsm[k].valid);
            fsm[k].state = H;
            break;
        }}
        ++k;
    }
}
```

但完全向量化仍有两个问题。第一，新老元组可能处于不同逻辑阶段，为了同步，新元组或旧元组需要重复某些步骤，浪费计算。第二，它难以处理一般控制流，特别是存在多个有效分支的 `if` 和循环。完整填充 lane 并不等于充分使用 lane。

图 5(b) 中，`a`、`c` 在 `M2` 后结束，空出的 lane 被 `i`、`j` 填入，因此表面上没有 bubble；代价是每轮 match 后都重新执行 hash。元组 `d` 只有三次匹配，却执行三次 hash，后两次完全冗余。对更复杂的 FSM，问题还会递归放大：若串行状态 `ABCDEF` 在 `C`、`E` 都分歧，从 `E` 回到 `A` 填 lane 后再次到 `C` 又可能分歧，来自不同阶段的有效 lane 必须分别保护并重复步骤。一般多分支 `if` 也不能把进入其他合法分支的 lane 当作无效 lane 覆盖，因此无法真正填满单一分支。GP/SPP 的完全向量化同样能消除空 lane，却会引入相同冗余 hash，复杂 FSM 下的成组或流水线约束还更难处理。

## 4. 交错多向量化

IMV 的核心思想是把向量化程序划分为多个状态。状态边界出现在 immediate memory access 或控制流分歧处。多个运行实例交错执行这些状态：当某个实例即将等待内存时，它发出预取，然后 CPU 切换到其他实例继续执行。这样，某个实例的内存访问延迟可被其他实例的计算覆盖。

与 AMAC 相比，IMV 的状态内部是 SIMD 向量化的；与普通 SIMD 相比，IMV 利用预取和交错执行增加 MLP；与完全向量化相比，IMV 使用 residual vectorized state 处理分歧，避免重复步骤和 bubble。

### 4.1 交错执行

现代处理器用同时多线程（SMT/HT）在一个物理核上运行多个逻辑线程：一个线程因内存访问停顿时，另一个线程可以使用执行单元。然而主流 CPU 通常每核只有两个逻辑线程，对内存密集型应用不足以完全隐藏延迟；向量化线程虽然一次发出更多访问，也没有消除这个缺口。因此，IMV 在软件层再交错更多指令流。

交错执行要求能高效暂停和恢复指令流。一种选择是协程，但论文写作时协程尚未进入 C++ 标准，已有实验实现对 pointer-chasing 也没有超过 GP 或 AMAC。IMV 采用另一种方式：手工交错 FSM。程序在 immediate memory access 处分成状态；一个状态发出软件预取后，把上下文保存到循环数组并暂停，再从数组恢复另一个 FSM 实例的上下文。状态切换的成本低于一次内存停顿，因此不同实例的计算可覆盖未完成访问。

### 4.2 划分向量化程序的状态

按照交错 FSM 原则，每个向量化程序被拆成一系列状态，形成 vectorized FSM。一个状态以预取请求结束后，不立即运行自己的下一状态，而是切换到同组另一个实例。每个实例独立保存上下文。组规模必须足够大，使交错计算能覆盖内存延迟；其最佳值在第 5 节实验确定。

仅在内存访问处分割仍无法解决第 3 节的控制流分歧：不满的向量无论向前继续还是回退补充，都会降低 DLP 与 MLP。问题本质是当前不满向量污染后续处理。因此 IMV 还在每个分歧点把状态继续切小，并在状态内部用 residual vectorized state 消化分歧。这样任何分歧状态传给下一状态的向量都只会是满或空。

### 4.3 残余向量化状态（Residual Vectorized State）

控制流分歧会让向量中只有部分 lane 继续执行某个分支。IMV 为每个可能产生分歧的状态维护一个 residual vectorized state。当前运行实例进入分歧状态后，如果活跃 lane 不满，就把它们与该状态残留的 lane 合并。合并后若向量满，则继续执行该状态后续逻辑；若不满，则把当前 lane 保存在 residual state 中，等待其他实例后续填充。

原文算法可写为：

**代码清单 3：DVS 与 RVS 的整合。**

```text
if (DVS.active_lanes + RVS.active_lanes < vector_size) {
    DVS = compress(DVS);      // 将 DVS 的有效 lane 向左压紧
    RVS = expand(RVS, DVS);   // 把 DVS 的有效 lane 填入 RVS
    // 返回最近的数据源状态，重新装入数据
} else {
    DVS = expand(DVS, RVS);   // 用 RVS 填满 DVS
    RVS = compress(RVS);      // 压紧 RVS 中剩余的有效 lane
    // 进入 DVS 原本的下一状态
}
```

这种机制把分歧局部化。一个状态的分歧不会传播到后续状态；后续状态看到的仍是满向量或空向量。Residual state 在同一组运行实例之间共享，因此不需要为每个实例维护大量独立向量。

![图 6：加入 residual vectorized state 后更新的 FSM。](assets/figure-06-updated-fsms.png)

![图 7：IMV probe 的 FSM。](assets/figure-07-imv-probe-fsm.png)

对于一般 `if`，条件求值后可能有多个分支需要执行；进入每个分支前用 RVS 更新分歧状态。满向量继续，空向量返回最近的数据源状态。若分支内部又有复杂 `if` 或循环，可把填满的状态放入任务队列，交给空闲实例执行。对于一般循环，每次迭代后产生的分歧状态也以同样方式和 RVS 合并。RVS 的时空开销很小：每个分歧状态只有一个 RVS，由一组 FSM 实例共享；所有权随当前运行实例切换，读写仍是串行的，不会冲突，且合并只涉及寄存器向量操作。

### 4.4 示例分析

在链式哈希表 probe 中，IMV 把计算哈希、访问桶、匹配节点、访问 next 节点等步骤划分为状态。访问桶或 next 节点前发出预取，然后切换实例。匹配状态可能因桶链结束或匹配成功产生分歧；residual state 负责把仍需继续探测的 lane 打包成满向量。

IMV probe 的 FSM 包含 hashing 状态 `H`、matching 状态 `M` 和匹配状态的 RVS。`H` 装入一个向量的输入 key，计算哈希，得到 bucket 指针并预取；`M` 比较 key、输出匹配 payload，并读取 next 指针。匹配后在可能分歧的位置合并 RVS：若向量仍满，则预取下一批节点并继续 `M`；若变空，则直接切换回 `H` 装入新元组。若哈希表存在大量空 bucket，还应在 `H` 后增设检查有效 bucket 的状态，论文伪代码为简洁而省略。

清单 4 相比 DVA 只增加共享的 `RVS` 和 matching 后的 `integration`：

**代码清单 4：交错多向量化 probe。**

```c
struct fsm_t { v key, payload, ptr; state_t state; m valid; };

void imv_probe(tuple_t *tuple, hashtable_t *ht, table_t *out) {
    fsm_t fsm[G], RVS;
    int all_done = 0;
    while (all_done < G) {
        k = (k == G) ? 0 : k;
        switch (fsm[k].state) {
        case H:
            if (i < tuple_num) {
                fsm[k].key = load(tuple[i].key);
                v hashed = HASH(fsm[k].key);
                fsm[k].ptr = ht->buckets + hashed;
                v_prefetch(fsm[k].ptr);
                fsm[k].state = M;
                fsm[k].valid = full_mask;
                i += W;
            } else {
                fsm[k].state = D;
                ++all_done;
            }
            break;
        case M: {
            m match = fsm[k].ptr->key == fsm[k].key;
            out[num] = store(fsm[k].ptr->payload, match);
            num += popcount(match);
            fsm[k].valid = fsm[k].ptr->next != v_null;
            integration(fsm[k], RVS);
            if (fsm[k].state == M)
                v_prefetch(fsm[k].ptr->next, fsm[k].valid);
            else
                --k;                    // 直接切换到 H
            break;
        }}
        ++k;
    }
}
```

这样，IMV 同时减少三类开销：通过 SIMD 降低计算开销；通过将控制流转为向量 mask 和 residual state 降低分支未命中；通过预取和实例交错降低缓存未命中。

图 5(c) 展示了执行过程：`M2` 后只剩两个活跃任务，它们先移入 matching 状态的 RVS，完全空出的向量立即装入下一批元组；`M4`、`M10` 后同理。`M8` 后当前两个活跃 lane 与 RVS 中三个 lane 足以组成满向量，先前任务被重新装回并预取下一节点，随后执行 `M12`。相较图 5(a) 的 DVA 和图 5(b) 的 FVA，IMV 同时把 DLP 与 MLP 用满。

IMV 也能覆盖整个查询流水线。图 8 的示例是 `Scan -> Filter -> Probe -> Count`：过滤后的向量因选择率产生分歧，因此附加一个 RVS；哈希后的 matching 循环既访问内存又在每轮分歧，因此在匹配前放置预取状态、匹配后放置另一 RVS。只有预取状态触发跨 FSM 实例的交错切换，两个 RVS 则在当前实例内部转移状态。

![图 8：使用 IMV 的查询流水线示例。](assets/figure-08-pipeline-imv.png)

## 5. 实验评测

实验先在四个独立算子上比较 Naive 标量、纯 SIMD、AMAC、DVA、FVA 和 IMV，再在 Xeon Phi 上评测，最后把 IMV 用于完整查询并同三种查询执行模型比较。

### 5.1 实验设置

平台一是两颗 Skylake 架构 Intel Xeon Silver 4110（SKX），平台二是 Intel Knights Landing 7210（KNL）。代码由 GCC 6.4.0 以 `-O3` 编译，线程绑核以排除调度开销；软件预取使用 `_mm_prefetch(..., _MM_HINT_T0)`。实验代码公开在参考文献 [1]。

表 1：硬件配置细节（原文 Table 1）

| 项目 | SKX | KNL |
|---|---|---|
| 核心数 | 8 | 64 |
| 线程 | 2 threads/core | 4 threads/core |
| 频率 | 2.10 GHz | 1.05 GHz |
| L1d/L1i cache | 32 KB / 32 KB | 32 KB / 32 KB |
| L2 cache size | 1 MB | 1 MB |
| L3 cache size | 11 MB | NA |
| 内存容量 | 150 GB | 96 GB |
| 2 MB huge pages 的 L1 TLB entries | 32 | 128 |
| SIMD | 512 bits | 512 bits |

独立算子使用合成关系 `R`、`S`。每个元组含 8 字节整数 key 与 8 字节 payload；通过 Zipf 因子控制均匀或倾斜分布，记为 `[Z_R, Z_S]`，其中 `[0,0]` 表示均匀。`S` 的 key 落在 `R` 的范围内，保证存在等值 key。除第 5.5 节使用 MurmurHash3 外，默认使用取模哈希；默认启用 2MB huge pages，`R` 为 1M 元组、`S` 为 50M 元组。IMV/FVA/DVA 的最佳 group size 设为 5，AMAC 为 20；性能以每秒百万元组（Mtps）衡量。

### 5.2 Hash join probe 与二叉树搜索

Hash join probe（HJP）使用链式哈希表，每个 bucket 节点包含 1 字节同步 latch、16 字节元组和 8 字节 next 指针，并把匹配 payload 写入 batch 输出缓冲。二叉树搜索（BTS）使用由 `R` 构造、key 无重复的普通二叉搜索树；每个节点含 16 字节元组和两个 8 字节子指针，由 `S` 的元组查找相等 key，匹配后把双方 payload 组成新元组写入缓冲。二者都需要沿指针查找，但链式哈希的链长更受数据倾斜影响。

![图 9：数据分布对 hash join probe 和二叉树搜索的影响。](assets/figure-09-data-distribution.png)



表 2：IMV 相对其他方法的加速比（原文 Table 2；表头 DAV 对应正文中的 DVA）

| 配置 | Naive | SIMD | DAV | FVA | AMAC |
|---|---:|---:|---:|---:|---:|
| HJP, [0, 0], 1 thread | 1.62 | 1.91 | 1.01 | 1.15 | 0.93 |
| HJP, [0.5, 0.5], 1 thread | 2.79 | 2.76 | 1.48 | 1.22 | 1.33 |
| HJP, [1, 1], 1 thread | 3.34 | 3.17 | 2.39 | 1.27 | 1.97 |
| BTS, [0, 0], 1 thread | 4.23 | 2.62 | 1.15 | 1.27 | 2.10 |
| BTS, [0.5, 0.5], 1 thread | 3.76 | 2.30 | 1.14 | 1.25 | 2.21 |
| BTS, [1, 1], 1 thread | 2.39 | 1.66 | 1.14 | 1.22 | 2.34 |
| HJP, [0, 0], 32 threads | 1.62 | 1.37 | 1.01 | 1.14 | 1.00 |
| HJP, [0.5, 0.5], 32 threads | 2.09 | 1.71 | 1.31 | 1.11 | 1.15 |
| HJP, [1, 1], 32 threads | 1.66 | 1.79 | 1.89 | 1.49 | 1.54 |
| BTS, [0, 0], 32 threads | 2.76 | 1.86 | 1.15 | 1.26 | 1.85 |
| BTS, [0.5, 0.5], 32 threads | 2.31 | 1.52 | 1.13 | 1.23 | 1.83 |
| BTS, [1, 1], 32 threads | 1.52 | 1.22 | 1.14 | 1.26 | 1.97 |

![图 10：基于微架构分析的执行时间拆解。](assets/figure-10-time-breakdown.png)

Intel VTune 的 Top-down Microarchitecture Analysis 把周期分成 Front-End、Bad Speculation、Memory、Core 与 Retiring。图 10 显示，Naive 的 HJP/BTS 分别有 66%/48% 时间受内存约束；AMAC 虽降低访问成本，仍有 36%/42% 的 bad speculation；纯 SIMD 虽消除分支，却分别有 80%/56% 时间受内存约束。只消除分支或只减少缓存未命中都不够。DVA、FVA 与 IMV 同时结合向量化和预取，而 IMV 又因更好处理分歧而领先。

![图 11：数据规模影响。](assets/figure-11-data-size.png)

![图 12：group size 参数影响。](assets/figure-12-group-size.png)

#### 5.2.1 工作负载与技术参数

数据越倾斜，HJP 的桶链分歧越严重：均匀 `[0,0]` 时 AMAC 很少遇到分支误预测，额外处理分歧的 IMV/DVA/FVA 未必占优；到 `[1,1]` 时 AMAC 的 branch miss 明显上升，DVA 也因向量分歧落后，IMV 优势扩大。BTS 的树较为茂密、没有长链，分布影响较小。

图 11 把 `R` 从 16K 增至 64M 元组。超过 256K 后数据离开 cache，Naive 与 SIMD 吞吐快速下降；超过 1M 后各方法还受到更多 TLB miss。DVA 在数据位于 cache 时反而最慢，因为分歧处理与交错开销没有内存延迟可摊薄。BTS 中，各方法也随数据增大而因 branch miss、TLB miss 和计算开销下降。

Group size 决定预取距离，必须大到能用计算覆盖访问，又受每核 MSHR 数量限制。图 12 显示吞吐随 group size 增长到甜点后趋稳；向量交错方法在各配置下可统一取 5，相当于一组最多发出约 40 个 64 位元素访问，足以占用 MSHR；更大只会增加状态保存与恢复开销。AMAC 的最佳值为 20。

![图 13：huge pages 对吞吐的影响。](assets/figure-13-huge-pages.png)

![图 14：各方法的扩展性。](assets/figure-14-scalability.png)

#### 5.2.2 系统架构参数

默认 4KB 页会让大型随机访问工作集远超 TLB 容量。启用 2MB huge pages 后，HJP 与 BTS 都加速，数据越大收益越明显；IMV 在 64M HJP 上最高加速 2.05 倍，因为它消除 cache miss 与 branch miss 后，TLB miss 成为主要瓶颈。向量 gather/scatter 可能同时触及更多页，因此随着数据增大，IMV/FVA/DVA 相对 AMAC 的优势也会缩小。

从 1 到单 socket 的 8 个物理核，各方法近似线性扩展；超过 8 核后 HJP 受 NUMA 远程访问影响，尤其 IMV+SMT，BTS 因远程访问少仍近似线性。固定核数下启用 SMT 不会使吞吐翻倍，因为同核逻辑线程争用带宽、TLB、寄存器和 VPU。

### 5.3 Hash join build 与哈希聚合

![图 15：hash build 性能。](assets/figure-15-hash-build.png)

![图 16：hash aggregation 性能。](assets/figure-16-hash-aggregation.png)

这两个算子除随机访问外还包含大量写入。Build 先计算 key 的哈希、定位 bucket，再分配并写入新节点，最后把它插到 bucket 头部；随机访问 bucket head 会产生 cache miss。分组聚合先 probe bucket，匹配则更新聚合值，不匹配则在链尾插入节点；它还会产生内存分配和并发写入。

单线程 build 中，IMV 相对 Naive/SIMD 分别约快 1.77/1.76 倍，DVA、FVA、AMAC 也因预取而接近。32 线程时，内存带宽、TLB 与分配系统调用成为瓶颈，IMV 对 Naive 的优势降至 1.31-1.44 倍。Build 总在链头插入，对分布不敏感。

单线程聚合中，IMV 相对 Naive/SIMD 约快 1.7/2.3 倍；纯 SIMD 与 FVA 会为完全向量化重复聚合步骤，冗余较多。多线程时同样受带宽与 TLB 限制。高倾斜使重复 key 在 bucket 中合并、链反而变短，并导致插入或更新冲突；在 Zipf=1 时 AMAC 可超过 IMV。无冲突聚合不在本文范围内。

### 5.4 Knights Landing（Xeon Phi）

在 Knights Landing（Xeon Phi）上，硬件本身有 64-72 个核心、每核两个 512 位 VPU 和四个逻辑线程，能通过 SMT 隐藏部分内存访问延迟。为排除整体可扩展性影响，实验只使用一个核心并启用四个逻辑线程；AMAC 的 group size 降为 10，DVA、FVA、IMV 降为 2。结果显示，纯标量 Naive 和 AMAC 明显慢于 SIMD 类方法；AMAC 在某些低不规则性场景还因交错和预取开销慢于 Naive。DVA/FVA 有时也因开销慢于 SIMD。但 IMV 通过更好使用向量抵消开销，最高比 Naive 快 2.1 倍，比 SIMD 快 1.2 倍。Build 与 aggregation 的结果相似，原文因篇幅没有展示。这说明即使在具备硬件多线程的 Phi 上，软件交错仍有价值；在每核逻辑线程较少的 CPU 上价值更高。

![图 17：KNL 上 hash join probe 与 binary tree search 的性能。](assets/figure-17-knl-performance.png)

### 5.5 与其他执行模型比较

我们把 IMV 应用于完整查询执行，并与三种先进执行模型比较：以数据为中心的编译执行（data-centric compilation execution，DCE）、向量化执行（vectorized execution，VE）和 relaxed operator fusion（ROF）。查询基于 TPC-H：

```sql
SELECT count(*)
FROM orders, lineitem
WHERE o_orderkey = l_orderkey
  AND l_quantity < 50
  AND o_orderdate < '1996-1-1';
```

物理计划包含两个流水线：`scan -> filter -> build` 和 `scan -> filter -> probe -> count`。在 IMV 中，probe pipeline 被表示为 FSM，build pipeline 类似。IMV 也可用于加速 VE 和 ROF 中的 join 算子，分别称为 VE-IMV 和 ROF-IMV。

实验使用 TPC-H SF100 数据和全部 32 个线程。DCE、ROF、ROF-IMV、IMV 的 morsel size 为 10K；VE、VE-SIMD、VE-IMV 的 vector size 为 1K；ROF 各阶段之间的 buffer size 为 10K。这些参数既与既有工作一致，也在各自模型中表现良好。

结果显示，IMV 分别比 DCE、VE、ROF 快 1.92 倍、2.01 倍和 1.39 倍。用 IMV 加速 VE 和 ROF 的 join 算子分别带来 1.72 倍和 1.39 倍提升。DCE 慢是因为它既不能减少 join 中的缓存未命中，也不能避免 filter 中的分支未命中。VE 在阶段间物化中间结果，可能产生无用计算；即使用 SIMD 加速，仍受缓存未中主导。ROF 用 SIMD 优化 filter，并用 GP 实现 join，能减少大量缓存未命中，但 IMV 同时减少缓存未命中和分支未命中，因此更快。

![图 18：不同查询执行模型的对比。](assets/figure-18-engine-comparison.png)

ROF-IMV 与 IMV 接近。区别是 ROF-IMV 把 filter 与 build/probe 分成两个阶段并用 buffer 连接，引入物化开销；IMV 则把 filter 与 build/probe 合并。两者性能差距通常在 5% 内，因此把 IMV 应用于 ROF 也是加速完整查询执行的实际选择。

## 6. 讨论

### 复杂查询中的 IMV

TPC-H 这类复杂查询由多个 pipeline 组成，可从 IMV 中受益，减少缓存未命中、分支未命中和计算开销。可采用两种执行模型：用 IMV 实现整个 pipeline；或者像 ROF 一样，把 IMV 优化算子链接到 pipeline 中。第一种方法更复杂，需要 JIT 编译帮助融合 pipeline 中所有算子；同时融合过多算子可能干扰交错执行。我们认为第二种方法更实际。

对 pipeline 中具体算子，IMV 可处理复杂逻辑，因为 residual vectorized state 能解决一般 `if` 和循环中的分歧。算子主体逻辑通常固定，缓存未命中和控制流分歧位置也较明确，因此较容易决定在哪里插入预取和 residual 合并。变化部分，例如表达式和哈希函数，可通过运行时调用 SIMD 向量化 primitive 处理。这类似标量向量化执行，只是 primitive 面向 SIMD 向量而非标量 batch。

SIMD 不能直接计算涉及 `varchar`、`decimal` 等特殊类型或 `substr()` 等操作的复杂表达式。若复杂类型的唯一值数量有限，可先映射为小整数，加速相等性等操作；其他情况下，要用标量代码实现 SIMD-like primitive，使其与其他 SIMD 操作无缝连接。一个向量只有少量 tuple，primitive 调用开销未必能充分摊销，但 JIT 可以减少它；在 IMV 中，这部分调用开销还可能与内存访问重叠，因此整体仍能获得明显加速。

### IMV 自动化

本文手工实现交错执行，并用 residual vectorized state 解决控制流分歧。理想情况下，这两个过程应自动化。协程可提供暂停和恢复函数执行的方式，提高可读性和可维护性。但在向量化中，协程仍必须处理控制流分歧。若采用 residual state，协程需要自动识别分歧点、在运行时高效共享 residual state，并自动调度多个分支执行。这些要求对在 CPU 上自动解决 SIMD 分歧非常关键。

IMV 并非在所有工作集上都占优。当数据完全驻留 cache、控制流规则且分歧很少时，预取、状态保存和 residual 合并没有足够的内存延迟可以摊销，简单 SIMD 或 DVA 可能更快。Group size 过小无法覆盖延迟，过大又增加寄存器压力和上下文轮转；huge pages、MSHR 数量、SMT 和 NUMA 位置都会改变甜点。因而实现需要基于算子和硬件选择是否启用 IMV，而不是无条件替换所有向量代码。

论文的手工 FSM 还依赖开发者准确识别 immediate memory access 和分歧点。若预取地址过早不可知、状态之间计算量不足，或 pipeline 融合导致寄存器与 instruction cache 压力过高，交错收益会下降。我们因此把“在整个 pipeline 使用 IMV”和“只把 IMV 算子接入 ROF/VE”都保留为设计选项，后者通常更容易集成和调试。

## 7. 相关工作

SIMD 已被广泛用于数据库操作，包括 scan、index scan、join、aggregation、index operation 和 sort。已有工作也使用 SIMD 高效处理 cuckoo hash 或 linear hash 的 join probe。本文关注的是链式哈希表 probe，它有更多缓存未命中，并重点解决这些未命中。

关于分歧，GPU 有硬件支持，而 CPU 必须手工处理 SIMD 分歧。已有工作提出 partial consume 和 consume everything。后者缓冲分歧元组并延后处理，与 residual vectorized state 类似。但它会给缓冲算子引入更多嵌套 `if` 和循环，而 residual state 由 FSM 的分歧状态拥有，并在一组运行实例间共享。已有方法也主要考虑 active lane 与 inactive lane 的分歧，忽略 active lane 之间的多分支分歧，因此无法处理一般 `if` 和循环。

关于 SIMD 中的预取，GP、SPP 和 AMAC 可在标量代码中缓解缓存未命中，其中 AMAC 能处理不规则访问。向量化代码中，一些研究偏向调整数据布局以获得硬件预取收益，或把软件预取用于规则树遍历和顺序访问。ROF 把预取优化代码和 SIMD 优化代码链接到 pipeline 中，但没有在 SIMD 代码内部用预取解决缓存未命中。IMV 正是针对这一缺口。

用于等高树的 SPP 只能获得至多 `log2(W)` 而不是 `W` 倍加速，其中 `W` 是向量 lane 数；面向顺序数据访问的软件预取也只能略微减少 cache miss。与用 permutation lookup table 把新元素引入向量的方法不同，IMV 使用 `expand` load；并且本文实现彻底向量化，不像部分既有实现保留标量尾部。

协程和 Cimple 等工作同样通过暂停任务、交错独立访问来暴露 ILP/MLP，但主要面向标量指令流；IMV 还必须处理一个 SIMD 向量内部 lane 之间的分歧。GP、SPP、AMAC 解决的是任务切换时机，residual vectorized state 解决的是不满向量如何继续执行，这两层机制共同构成本文区别于既有预取方案的部分。

## 8. 结论

本文提出交错多向量化 IMV，用于突破 SIMD 向量化中的 memory wall。IMV 是一种新方法，可在具有不规则 immediate memory access 的 pointer-chasing 应用上同时充分利用 MLP 和 DLP。它把程序拆分为状态，这些状态位于 immediate memory access 或控制流分歧处；随后交错执行不同程序实例的状态，以隐藏内存访问延迟。

我们还提出 residual vectorized state，在每个状态内部解决控制流分歧，从而避免向量执行中的 bubble。实验表明，IMV 相比纯标量实现和纯 SIMD 向量化最高分别快 4.23 倍和 3.17 倍，因为它能同时减少缓存未命中、分支未命中和计算开销。IMV 不仅适用于 pointer-chasing 应用，也可应用到完整查询处理。未来工作将包括复杂查询中的 IMV 应用和 IMV 自动化。

## 致谢

该研究获得中国国家重点研发计划（No. 2018YFB1003400）和国家自然科学基金（No. 61772204、61732014）支持。本文作者感谢匿名审稿人和 shepherd 的建设性意见与指导。


## 参考文献

- [1] IMV Source Code. https://github.com/fzhedu/db-imv, 2019.
- [2] Intel Vtune TMAM. https://software.intel.com/en-us/vtune-amplifier-cookbook-top-down-microarchitecture-analysis-method, 2019.
- [3] M. Alam, K. S. Perumalla, and P. Sanders. Novel parallel algorithms for fast multi-GPU-based generation of massive scale-free networks. Data Science and Engineering, 4(1):61-75, 2019.
- [4] C. Balkesen, J. Teubner, G. Alonso, and M. T. Özsu. Main-memory hash joins on multi-core CPUs: Tuning to the underlying hardware. In ICDE, pages 362-373, 2013.
- [5] P. A. Boncz, M. Zukowski, and N. Nes. MonetDB/X100: Hyper-pipelining query execution. In CIDR, pages 225-237, 2005.
- [6] S. Chen, A. Ailamaki, P. B. Gibbons, and T. C. Mowry. Improving hash join performance through prefetching. ACM Trans. Database Syst., 32(3):17, 2007.
- [7] X. Cheng, B. He, X. Du, and C. T. Lau. A study of main-memory hash joins on many-core processor: A case with Intel Knights Landing architecture. In CIKM, pages 657-666, 2017.
- [8] J. Chhugani, A. D. Nguyen, V. W. Lee, W. Macy, M. Hagog, Y. Chen, A. Baransi, S. Kumar, and P. Dubey. Efficient implementation of sorting on multi-core SIMD CPU architecture. PVLDB, 1(2):1313-1324, 2008.
- [9] M. Dreseler, J. Kossmann, J. Frohnhofen, M. Uflacker, and H. Plattner. Fused table scans: Combining AVX-512 and JIT to double the performance of multi-predicate scans. In ICDE, pages 102-109, 2018.
- [10] Z. Fang, Z. He, J. Chu, and C. Weng. SIMD accelerates the probe phase of star joins in main memory databases. In DASFAA, pages 476-480, 2019.
- [11] T. Gubner and P. Boncz. Exploring query execution strategies for JIT, vectorization and SIMD. In ADMS, 2017.
- [12] T. D. Han and T. S. Abdelrahman. Reducing branch divergence in GPU programs. In GPGPU, page 3, 2011.
- [13] H. Inoue, M. Ohara, and K. Taura. Faster set intersection with SIMD instructions by reducing branch mispredictions. PVLDB, 8(3):293-304, 2014.
- [14] H. Inoue and K. Taura. SIMD- and cache-friendly algorithm for sorting an array of structures. PVLDB, 8(11):1274-1285, 2015.
- [15] S. Jha, B. He, M. Lu, X. Cheng, and H. P. Huynh. Improving main memory hash joins on Intel Xeon Phi processors: An experimental approach. PVLDB, 8(6):642-653, 2015.
- [16] C. Jonathan, U. F. Minhas, J. Hunter, J. J. Levandoski, and G. V. Nishanov. Exploiting coroutines to attack the "killer nanoseconds". PVLDB, 11(11):1702-1714, 2018.
- [17] T. Kersten, V. Leis, A. Kemper, T. Neumann, A. Pavlo, and P. A. Boncz. Everything you always wanted to know about compiled and vectorized queries but were afraid to ask. PVLDB, 11(13):2209-2222, 2018.
- [18] C. Kim, J. Chhugani, N. Satish, E. Sedlar, A. D. Nguyen, T. Kaldewey, V. W. Lee, S. A. Brandt, and P. Dubey. FAST: fast architecture sensitive tree search on modern CPUs and GPUs. In SIGMOD, pages 339-350, 2010.
- [19] V. Kiriansky, H. Xu, M. Rinard, and S. P. Amarasinghe. Cimple: instruction and memory level parallelism: a DSL for uncovering ILP and MLP. In PACT, pages 1-16, 2018.
- [20] Y. O. Koçberber, B. Falsafi, and B. Grot. Asynchronous memory access chaining. PVLDB, 9(4):252-263, 2015.
- [21] N. Kohout, S. Choi, D. Kim, and D. Yeung. Multi-chain prefetching: Effective exploitation of inter-chain memory parallelism for pointer-chasing codes. In PACT, pages 268-279, 2001.
- [22] H. Lang, A. Kipf, L. Passing, P. A. Boncz, T. Neumann, and A. Kemper. Make the most out of your SIMD investments: counter control flow divergence in compiled query pipelines. In DaMoN, pages 1-8, 2018.
- [23] H. Lang, L. Passing, A. Kipf, P. Boncz, T. Neumann, and A. Kemper. Make the most out of your SIMD investments: counter control flow divergence in compiled query pipelines. The VLDB Journal, 2019.
- [24] V. Leis, P. A. Boncz, A. Kemper, and T. Neumann. Morsel-driven parallelism: a NUMA-aware query evaluation framework for the many-core age. In SIGMOD, pages 743-754, 2014.
- [25] S. Manegold, P. A. Boncz, and M. L. Kersten. Optimizing database architecture for the new bottleneck: Memory access. The VLDB Journal, 9(3):231-246, 2000.
- [26] P. Menon, A. Pavlo, and T. C. Mowry. Relaxed operator fusion for in-memory databases: Making compilation, vectorization, and prefetching work together at last. PVLDB, 11(1):1-13, 2017.
- [27] T. Neumann. Efficiently compiling efficient query plans for modern hardware. PVLDB, 4(9):539-550, 2011.
- [28] O. Polychroniou, A. Raghavan, and K. A. Ross. Rethinking SIMD vectorization for in-memory databases. In SIGMOD, pages 1493-1508, 2015.
- [29] O. Polychroniou and K. A. Ross. Vectorized bloom filters for advanced SIMD processors. In DaMoN, pages 1-6, 2014.
- [30] O. Polychroniou and K. A. Ross. Towards practical vectorized analytical query engines. In DaMoN, pages 1-7. ACM, 2019.
- [31] G. Psaropoulos, T. Legler, N. May, and A. Ailamaki. Interleaving with coroutines: A practical approach for robust index joins. PVLDB, 11(2):230-242, 2017.
- [32] B. Ren, G. Agrawal, J. R. Larus, T. Mytkowicz, T. Poutanen, and W. Schulte. SIMD parallelization of applications that traverse irregular data structures. In CGO, pages 1-10, 2013.
- [33] K. A. Ross. Efficient hash probes on modern processors. In ICDE, pages 1297-1301, 2007.
- [34] W. A. Wulf and S. A. McKee. Hitting the memory wall: implications of the obvious. In Comp. Arch. News, pages 20-24, 1995.
- [35] J. Zhou and K. A. Ross. Implementing database operations using SIMD instructions. In SIGMOD, pages 145-156, 2002.
