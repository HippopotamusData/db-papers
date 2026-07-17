---
paper_id: generating-code-holistic-query-evaluation
title: Generating code for holistic query evaluation
language: zh-CN
source: source.pdf
---

# Generating code for holistic query evaluation（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 摘要

本文介绍定制化代码生成在数据库查询求值中的应用。核心思想是使用一组高效代码模板，并在运行时实例化这些模板，生成面向查询和硬件的源代码。生成的源代码被编译并动态链接到数据库服务器中执行。代码生成消除了当前通用解释式 SQL 查询引擎中实现高层抽象所带来的膨胀，同时生成代码还能针对运行硬件进行定制。我们称这种方法为整体查询求值（holistic query evaluation）。我们介绍采用这些方案的原型系统 HIQUE，即 Holistic Integrated Query Engine，并对系统性能进行详细实验。结果表明，HIQUE 达到了设计目标，效率超过了成熟和新兴的查询处理技术。

## I. 引言

本文把定制化代码生成用于高效数据库查询处理。方法源自 template-based programming：为各种查询处理算法准备代码模板，在运行时实例化这些模板，并把它们组合成一段求值完整查询的 source code。动态模板实例化消除了当前查询引擎为实现 generic query evaluator 而必需的高层抽象缺陷；由于代码是动态生成的，还能按执行它的硬件架构特征定制。我们称之为 holistic query evaluation，因为核心前提是同时从整体上看待待求值查询和 host hardware。主存执行的性能优势非常大，例如 TPC-H Q1 相对成熟数据库技术达到 167 倍。我们主张的创新在于，template-based code generation 可以泛化到高效处理任意类型的查询，而不影响数据库系统的正交部分。

**动机。**传统查询处理算法一直优先减少磁盘 I/O，把内存内执行效率放在次要位置。现代服务器具有大量内存，大部分乃至整个磁盘数据库都可能装入主存；此时，processor register 与 main memory 的访问延迟差成为性能瓶颈 [1]。要优化这种负载，就必须精心构造执行代码，尽量减少 query execution 中的 processor stall time。

已有工作把 data layout 识别为主要瓶颈，认为它妨碍具有多级 cache 的现代处理器在数据库负载中发挥全部潜力。我们认为改变 storage layer 会彻底偏离既有设计；query engine 更大的问题，是把 SQL query 编译成 operator plan，以及公共 operator interface——iterator model——过于通用。后者使 CPU resource 利用率不佳：抽象实现和频繁 function call 增加查询求值所需的 instruction 与 memory access；generic code 又不能根据具体查询与硬件平台的特征定制。不过，主存中的 SQL 和 query processing 很适合 just-in-time compilation，因此我们把这个思路推到极致。

**用于查询求值的代码生成。**理想的查询处理代码既应最优利用 cache hierarchy，又应减少求值所需的 instruction，同时还要保留 iterator model 的可组合性，并且不影响独立系统模块。为此，我们提出 holistic query evaluation：在传统查询求值流程中插入 source-code generation。系统从完整查询出发整体优化，生成 query-specific、hardware-specific source code，再编译并执行。

该方法有多项收益：（a）最小化查询求值期间的 function call；（b）generated code 具有更好的 data locality，能最优利用 cache-resident data；（c）代码生成和编译允许对每个查询应用 compiler optimization，在传统 query optimization 之上增加一层优化；（d）generated code 的性能接近 hard-coded evaluation plan。同时，该模型保持灵活，不影响 storage management、concurrency control 等正交系统部分。

在此框架下，我们实现了 holistic query engine 原型，并把它与 iterator-based solution 和既有数据库系统比较。实验结果一方面量化 per-query code generation 相对 generic query operator implementation 的优势，另一方面表明整体方法在一部分 TPC-H 查询上优于 iterator-based 和 hardware-conscious 系统，证明它可作为另一种 query engine 设计。

本文其余部分安排如下：第 II 节介绍当前 processor/compiler 技术和传统 query engine 设计；第 III 节回顾相关工作；第 IV 节介绍采用整体求值的系统设计；第 V 节给出 code generation 方法和 query evaluation algorithm；第 VI 节实验评估该模型；第 VII 节总结并指出未来研究方向。

## II. 背景

### A. 硬件概览

现代 CPU 通过流水线、超标量和乱序执行并行处理多条指令 [14]。乱序执行可让等待数据的指令暂时让位，但数据库常有连续内存请求与长数据/控制依赖链，能隐藏的 stall 有限。多级 cache 用固定长度 cache line 缓解主存延迟：L1 最小最快并分 I1/D1，L2 更大较慢，部分处理器还有 L3；它们利用时间和空间局部性。Non-blocking cache 可维持多个未完成请求，但 data-intensive workload 很快令控制器饱和，剩余 cache miss 成为瓶颈。

现代处理器还使用多个与 cache 层次紧密耦合的硬件 prefetcher [10]：简单单元识别顺序模式，更高级单元则记录少量高频地址的历史，并跟踪连续取数之间的距离（stride）。我们在 1.86 GHz Core 2 Duo 6300 上用 RightMark Memory Analyser [22] 测得：D1 顺序/随机访问均为 3 cycles；L2 顺序 9、随机 14 cycles；主存顺序 28、随机至少 77 cycles。因而随机访问应尽量限制在 D1，跨更低层级时顺序性至关重要。

![图 1：现代 CPU 架构示意图](assets/embedded-p02-xref63.jpeg)

图 1：现代 CPU 的取指、调度、执行单元、cache 层次与多个硬件预取器。

### B. Iterator 的缺点

大多数引擎采用 iterator 模型 [11]，用 `open()` 初始化、`get_next()` 逐 tuple 传播、`close()` 清理，形成 pipeline operator tree。每条 tuple 至少触发 caller 请求和 callee 返回两次调用；为动态绑定类型，字段访问和比较也可能是 virtual call。调用要更新 stack pointer、保存/恢复数十个寄存器，还会跳转到新 instruction stream，限制 superscalar execution。

每个 iterator 还维护内部状态，反复读写可能引发 cache miss，并打断本应顺序的数据流，削弱 prefetcher。不同算子独立控制访问，pipeline 中多个 working set 可能互相驱逐，导致 cache thrashing。

### C. 编译器优化

编译器可通过调度独立指令、寄存器重用、聚合同一数据的访问来减少 stall [16]。但 iterator 的跨函数控制流阻止它看见完整循环；跨过程分析弱于过程内分析，函数调用中的条件和 jump 又缩小可联合优化的范围。谓词类型、tuple offset 等直到运行时才知道，也使常量传播、内联和地址计算专用化无法充分应用。

## III. 相关工作

早期研究 [23] 已用响应时间和硬件性能指标表明，处理器并不适合数据库访问模式，并提出改善现代处理器上 join 行为的修改。NSM 在只访问少数字段时浪费带宽；DSM [9] 以垂直分区改善数组计算，却要求重写算子并影响并发控制等正交部分。PAX [2] 在页内垂直分区，既保留 tuple-level 接口又改善 cache locality，是 NSM 与 DSM 的折中。

在 iterator 范式内，buffer operator [25] 把算子间粒度提升为 tuple block，减少 pipeline 调用，却没有减少算子内部求值函数；block-oriented aggregation [20] 可共享表达式并用 array computation。MonetDB [3], [18] 用 DSM 和完整数组物化，仍是 operator-based 且失去跨算子 cache reuse；MonetDB/X100 [4], [26] 结合列存与 compound vectorized primitive，达到接近手写实现的性能。

软件 prefetch [7], [8] 可改善 hash join，但合适距离依赖 CPU 频率、cache 延迟和运行负载；太近来不及，太远污染 cache，且控制器可忽略 hint。HIQUE 因此不采用它。System R [5] 已使用原始形式的代码生成；Daytona [13] 动态生成查询代码，却把 buffering、concurrency control 等大部分传统 DBMS 功能交给操作系统；JVM 查询编译原型 [21] 仍用 iterator 通信与执行，只用 generator 消除 iterator 主体中的 virtual function，join 也完全依赖预建索引。

## IV. 系统概览

本节介绍以代码生成为高效查询求值基本原则的查询引擎。系统名为 HIQUE（Holistic Integrated Query Engine），用 C/C++ 实现，在 GNU/Linux 上由 GNU GCC 编译，采用多个客户端与查询引擎通信的传统 client-server 模型。

#### 存储层

原型使用 NSM，tuple 连续存入 4096-byte page；但系统并不绑定 NSM，换用 DSM 或 PAX 时本文方案仍然适用。每张表各存于一个磁盘文件；storage manager 维护 table/file 对应关系和 schema。采用 LRU replacement policy 的 buffer manager 负责缓冲磁盘页并提供 concurrency control。除普通文件外，系统还使用节省内存的 fractal B+-tree 索引 [6]，每个物理页切成四个 1024-byte tree node。

#### 查询处理

图 2 展示查询经过系统的路径。第一个模块是 SQL parser。SQL grammar 支持带 equi-join 的合取查询，以及任意 grouping 和 sort order；它不支持聚合值中的统计函数和 nested query，但我们认为这两项都是直接扩展，不限制整体求值模型的一般性。

![图 2：HIQUE 整体查询引擎概览](assets/precise-manual-figure-02-engine-overview.png)

图 2 展示 HIQUE 的端到端路径：Parser 结合 DB catalog 产生内部查询表示，Optimizer 结合 DB statistics 输出 scheduled plan，Generator 根据 templates、data staging 和 holistic algorithms 生成 source code，再由 compiler 生成 shared-library file，Executor 动态加载并在 DB tables 上执行。

SQL parser 根据 system catalogue 检查查询是否合法，并向 optimizer 输出内部查询表示。Optimizer 采用以最小化中间结果规模为目标的 greedy approach 选择最优求值计划；它还为每个算子选择最优求值算法，并设置实例化 code generator 模板所需的参数，详见第 V 节。

Optimizer 输出按拓扑排序的 operator descriptor 列表 `O`。每个 `o_i` 的输入是 base table，或者 `o_j`（`j<i`）的输出；descriptor 包含实现该算子所用的算法，以及初始化该算法代码模板所需的附加信息。由于只有一个 root operator，这个列表实际上描述了一棵已经调度的物理算子树。列表开头依次是查询中的 join，后面是 aggregation 和 sorting；后两者是一元算子，各至多有一个 descriptor。Optimizer 跟踪 interesting order [5] 和 join team [12]，把 join 操作组合在一起，并尽量避免重复排序。

Code generator 遍历拓扑有序列表，为每个算子分两步生成代码：

1. **Data staging：**扫描全部输入表，应用全部 selection predicate，并丢弃输入中不再需要的字段，以缩小 tuple、提高后续处理的 cache locality。后继算子所需的 sorting、partitioning 等预处理与 scan code 交织执行。输出随后被物化；若 staging 后的输入足以放入主存，则不写入磁盘。
2. **Holistic algorithm instantiation：**生成实现该算子的 source code；该代码是第 V-B 节所述相应整体算法模板的一次实例化。

Code generator 根据各算子的输入关系组合其实现，产生一个供 query engine 调用、求值完整查询的最终函数；随后把所有生成函数写入新的 C source file。Source code 生成后，系统调用 compiler，把文件编译成面向该具体查询、可应用激进 compiler optimization 的 shared library。Query executor 动态链接并加载这个文件，调用其中的函数求值查询，再把输出发送给客户端。

## V. 代码生成

### A. 实现

Code generator 的输入是 optimizer 输出的、按拓扑排序的 operator descriptor 列表 `O`，输出是一个包含 query-specific code 的 C source file。每个 descriptor 包含待实现的算法和实例化代码模板所需的参数，包括 predicate data type、算子输入是 base table 还是 intermediate result，以及 output schema。完整生成算法见图 3。

**图 3：代码生成算法。**

```text
Input:
  1. Topologically sorted list of operators O.
  2. Code templates for data staging (TS),
     join evaluation (TJ), and aggregation (TA).

Output:
  Query-specific C source file.

1.  for each join operator j_m in O
2.    retrieve code template ts_m in TS to stage j_m's inputs
3.    for each input i_n of j_m
4.      instantiate ts_m for i_n
5.      generate C function c_ts,m,n for staging i_n
6.    retrieve code template t_jm in TJ for j_m's algorithm
7.    instantiate t_jm for j_m
8.    generate C function c_jm to evaluate join
9.  if aggregate operator a in O
10.   retrieve code template ts_a in TS to stage a's input
11.   instantiate ts_a for a
12.   generate C function c_ts,a for staging a
13.   retrieve code template t_a in TA for a's algorithm
14.   instantiate t_a for a
15.   generate C function c_a to compute aggregate values
16. if ordering operator s in O
17.   retrieve code template ts_s in TS for sorting
18.   instantiate ts_s and generate C function c_s
19. traverse O to compose the function cm calling all functions
20. for all generated functions c, write source file F
21. return F
```

Descriptor 同时带有 predicate 类型、base/intermediate input 和 output schema。生成器先处理 join（第 1-8 行），再处理 aggregation（9-15）与 ordering（16-18）；每个算子分别生成各输入的 staging function 与算法 function。最后 composing function 按 `O` 连接调用、分配/释放资源并输出结果。

### B. 算法与代码模板

整体算法的目标，是用代码生成把成熟的数据处理算法定制为对硬件更高效的实现。查询级已知的 attribute type 让 data access 和 predicate evaluation 分别从单独 function call 退化为 pointer cast 和 primitive comparison；页内定长 tuple 可通过 pointer arithmetic 和直接引用当作数组访问。系统知道各层 memory hierarchy 的访问延迟：D1 之外从顺序访问切换为随机访问，延迟甚至可能翻倍；每向下一层，延迟又增加一个数量级。因此，生成代码会让输入 block 适配 D1 或 L2，在 cache-resident data 上执行多项操作以最大化复用，并尽量只在 D1 内出现随机访问，因为唯有 D1 的顺序与随机取数代价相同。

代码清单 1 给出优化后的 scan-select 模板：

**代码清单 1：优化后的 table scan-select。**

```c
// loop over pages
for (int p = start_page; p <= end_page; p++) {
  page_str *page = read_page(p, table);
  // loop over tuples
  for (int t = 0; t < page->num_tuples; t++) {
    void *tuple = page->data + t * tuple_size;
    int *value = tuple + predicate_offset;
    if (*value != predicate_value) continue;
    add_to_result(tuple); // inlined
  }
}
```

Listing 1 只保留不可避免的 page load 与结果输出调用；inner loop 直接求地址、读取整数、比较并内联输出。数组形式既减少指令，也让 superscalar CPU 暴露更多独立操作，且编译器可跨循环分配寄存器。

代码清单 2 给出 join evaluation 的 nested-loops 模板：

**代码清单 2：用于 join evaluation 的 nested-loops 模板。**

```c
/* Inlined code to hash-partition or sort inputs */

hash join:
for (k = 0; k < M; k++) {
  // update page bounds for both k-th partitions

hybrid hash-sort-merge join:
  // sort partitions

  for (p_1 = start_page_1; p_1 <= end_page_1; p_1++) {
    page_str *page_1 = read_page(p_1, partition_1[k]);
    for (p_2 = start_page_2; p_2 <= end_page_2; p_2++) {
      page_str *page_2 = read_page(p_2, partition_2[k]);
      for (t_1 = 0; t_1 < page_1->num_tuples; t_1++) {
        void *tuple_1 = page_1->data + t_1 * tuple_size_1;
        for (t_2 = 0; t_2 < page_2->num_tuples; t_2++) {
          void *tuple_2 = page_2->data + t_2 * tuple_size_2;
          int *value_1 = tuple_1 + offset_1;
          int *value_2 = tuple_2 + offset_2;
          if (*value_1 != *value_2) {
            // merge join: update bounds for all loops
            continue;
          }
          add_to_result(tuple_1, tuple_2); // inlined
        }
      }
    }
  }
}
```

#### 输入 staging

排序先对适合 L2 的 partition 做优化 quicksort 再 merge。Fine partition 用有序 value directory 和 binary search 映射到分区，适合 distinct value 少、目录能驻 cache；目录太大时改用 hash/modulo 的 coarse partition。粗分区包含多个 value，可再排序形成 hybrid hash-sort；若最大 partition 能放入 L2，后续处理复用效果好。

Staging 在扫描输入的同一遍中完成 selection、丢弃后续不需要的属性，并把剩余 tuple 写入目标分区或排序缓冲，避免先生成完整中间关系再二次整理。分区粒度由 cache 决定：fine partition 让同分区 tuple 直接满足 join 条件，但 value directory 必须足够小；coarse partition 降低目录成本，却需要在分区内部继续比较或排序。优化器在两种开销之间选择。

#### Join

所有 join 共用 Listing 2 的 nested-loop 骨架，区别主要由 staging 决定。模板以类似数组的顺序模式访问数据：第一次遍历每页 tuple 时有利于硬件 prefetcher，之后的 tuple 迭代则在 cache-resident page 上完成，不再发生 cache miss。Merge join 预排序后线性扫描输入；系统持续更新各表起止 page 和各页起止 tuple 的 loop bound。Condition variable 有三种值，分别表示当前 tuple 不匹配、已经找到至少一个匹配因而继续扫描 inner tuple，以及 inner matching group 已耗尽因而推进 outer tuple 并回溯到 inner group 开头。每个 outer tuple 至多匹配一次时，两侧访问均为线性；回溯小型 inner group 通常命中 L2 乃至 D1。

Partition join 建立在 Grace hash join [17] 之上，先把两张输入表细分或粗分为 `M` 个 partition。Fine partition 的对应 tuple 全匹配；coarse partition 不建随机访问 hash table，而是临时排序对应分区，再 merge，形成 hybrid hash-sort-merge。若每个 partition 小于 L2 的一半，在 join 前才排序每对对应 partition，可确保两侧在 join evaluation 时同时驻留 L2。

传统 hash join 在 probe 时随机访问 bucket 和 collision chain；HIQUE 的 hybrid 方案刻意把随机访问限制在较小目录，把实际 tuple 处理转成 cache-resident partition 内的顺序排序和 merge。排序被推迟到某对 partition 即将 join 时，使刚排好的两侧仍留在 L2。这个安排解释了为何它在主存数据库中愿意付出局部排序成本。

Nested-loop 模板还能为 join team 增加 loop nesting，在多表公共 key、star schema 或 key-foreign-key join 中不物化中间结果。各表先正确排序/分区，再按表顺序先生成 page loop、后生成 tuple loop，布局类似 loop blocking [16]。

#### Aggregation

Sort aggregation 在线性扫描已排序输入时识别 group；hybrid aggregation 先按首个 group attribute hash partition，再按全部 group attribute 排序各分区。若所有 group directory 能驻 cache，map aggregation 无需 staging，只扫描一次。

Aggregation 使用 group directory 把多维 grouping key 映射为一维 aggregate array offset。图 4 的例子中，`R.a = 200`、`R.b = C`、`R.c = Asia` 对应 offset 为 `1 * 3 * 4 + 2 * 4 + 1 = 21`。

![图 4：聚合的 group directory 与 offset 计算](assets/precise-manual-figure-04-group-directories.png)

一般地，若 `M_i[v]` 是第 `i` 个属性值 `v` 的 id，group `(v_1,...,v_n)` 映射为：

$$
\mathrm{offset}(v_1,\ldots,v_n)=\sum _ {i=1}^{n}\left(M_i[v_i]\prod _ {j=i+1}^{n}|M_j|\right).
$$

每个 aggregate function 维护长度为 $\prod_i |M_i|$ 的数组。每条 tuple 查目录得到 offset，再更新对应 aggregate slot。Group 识别和 aggregate expression 都内联，编译器可复用寄存器、消除公共算术并避免 stack interaction。

Map aggregation 的代价是目录和稠密 aggregate array 可能随 distinct 值笛卡尔积迅速膨胀；只有当目录与数组能有效驻留 cache 时才适合。基数较高时，优化器改用 sort 或 hybrid aggregation，把工作限制在较小 partition。

### C. 开发经验

工程难点有三项：抽取不同算法之间的公共代码模板；在不再存在公共接口时连接不同算子；验证全部受支持操作所生成代码的正确性。整体求值模型缓解了这些问题，因为其算法对所有操作使用通用代码模板。Data staging 采用 Listing 1 的模板，sorting 和 partitioning 可以交织进其中。Join evaluation 均采用 Listing 2 的 nested-loops 模板，算法差异要么由 staging 处理，要么由 loop 内的附加步骤处理。例如，hash join 包含 Listing 2 第 3-5 行对应的片段，排除第 6、21 行；再包含后两段就得到 hybrid hash-sort-merge join。Aggregation 通过向 Listing 1 模板注入跟踪不同 group 和计算 aggregate function 的代码来实现。算子之间则在 buffer pool 内把 intermediate result 物化成 temporary table，再把它们流向后继算子。

开发 HIQUE 的经验验证了这些主张。加入新算法乃至新算子时，扩展 parser 和 optimizer 所需的工作比扩展 generator 更多。通常先建立新算法的 model implementation，并与现有模板比较；多数情况下，新算法相对现有求值算法只差几行代码，随后再扩展模板与 code generator。Generator 输出 C source file 也有助于这个过程：compiler 能帮助开发者快速定位 generated code 中的错误，减少完整支持新算法所需的迭代次数。

## VI. 实验研究

为检验代码生成作为通用查询求值方案的可行性，我们从多个方面进行实验，目标是测量：（a）整体模型相对传统 iterator-based approach 的优势；（b）compiler optimization 对 HIQUE generated code 的影响；（c）系统在标准 benchmark query 上相对研究系统和商业系统的竞争力；（d）运行时生成、编译并链接 query-specific code 的代价。

实验采用当时占主导地位的 x86-64 架构。机器配备 1.86 GHz Intel Core 2 Duo 6300 双核处理器和 2 GB 物理内存，运行 Ubuntu 8.10 64-bit、Linux kernel 2.6.27。HIQUE generated code 使用 GNU compiler 4.3.2 和 `-O2` 编译；更详细的平台信息见表 I。Cache latency 使用 RightMark Memory Analyser [22] 测量。

表 I 是实验机器的 Intel Core 2 Duo 6300 配置：

| 指标 | 数值 |
| --- | --- |
| Number of cores | 2 |
| Frequency | 1.86GHz |
| Cache line size | 64B |
| I1-cache | 32KB per core |
| D1-cache | 32KB per core |
| L2-cache | 2MB shared |
| L1-cache miss latency, sequential | 9 cycles |
| L1-cache miss latency, random | 14 cycles |
| L2-cache miss latency, sequential | 28 cycles |
| L2-cache miss latency, random | 77 cycles |
| RAM type | 2x1GB DDR2 667MHz |

**指标与方法。**所有查询均彼此隔离地运行，每个查询重复十次。每个查询运行在自己的 thread 中，只使用一个 processor core。任何实验都不物化输出，因为 materialization penalty 对所有系统和配置相近。下文报告各系统的平均响应时间，所有结果的偏差均小于 3%。

我们还把 hardware performance event 用作指标，并用 OProfile [19] 从 CPU performance event counter 收集 sampling data。Execution time 被分解为 instruction execution、D1-cache miss stall、L2-cache miss stall 和其他 pipeline resource stall；这里“其他”指并非由 D1/L2 cache miss 引起的 resource stall [15]。为计入 hardware prefetching，对已 prefetched cache line 使用 sequential access latency，对所有其他 cache miss 使用 random access latency。由于 non-blocking cache 允许 CPU 在取数期间继续执行指令，这只能近似计算实际 cache-miss stall time，但仍是良好估计。

除 execution time breakdown 外，我们还计算 CPI（Cycles Per Instruction）；Intel Core 2 Duo 的理论最小值为 0.25，即每个 CPU cycle 并行执行四条指令。我们还采样 retired instruction、function call 和 D1-cache access，并针对每个查询，以所有被比较配置中的最大值做归一化。最后报告 prefetch efficiency，即 prefetched cache line 数量与全部 missed cache line 数量之比。

### A. Iterator 与整体代码

为量化 iterator 模型相对整体模型的不足，我们比较五种实现：（a）用 generic function 求值 predicate 的 iterator 实现；（b）使用 type-specific iterator 并内联 predicate evaluation 的版本；（c）以 generic function 做 predicate evaluation 和 tuple access 的 hard-coded 实现；（d）通过 pointer arithmetic 直接访问 tuple 的改进 hard-coded 版本；（e）进一步内联 predicate evaluation 的 HIQUE generated code。我们对 generic 实现作了有利处理：分别编译每个查询的代码，并包含实例化 statically pipelined iterator 的全部参数，让 compiler 能够进一步优化。

Join evaluation 使用两个查询：（a）两个各有 10,000 条、每条 72 bytes 的表执行 merge join，每个 outer tuple 匹配 1,000 个 inner tuple；（b）两个各有 1,000,000 条、每条 72 bytes 的表执行 hybrid join，每个 outer tuple 匹配 10 个 inner tuple。Aggregation 使用一个包含 1,000,000 条 72-byte tuple 的表和两个 sum function；grouping attribute 分别有 100,000 个和 10 个 distinct value，前者用 hybrid aggregation，后者用 map aggregation。全部 join attribute 和 grouping attribute 都是 integer。指标同时采用 response time 和 hardware performance event；join 结果见图 5，aggregation 结果见图 6。

![图 5：Join 查询的执行时间分解和硬件指标](assets/precise-manual-figure-05-join-profiling.png)

图 5 对两类 join 查询分解 execution time，并给出 CPI、retired instructions、function calls、D1-cache accesses 和 prefetch efficiency 等硬件指标。HIQUE 在 Join Query #1 上通过减少函数调用和指令数获得明显优势；Join Query #2 中 staging 成本占比更高，收益相对缩小。

Join Q1 是 inflationary query：两张各 10,000 条的表产生 10,000,000 条输出。所有版本的 memory stall 都很少，HIQUE 比 iterator 快近 5 倍，差异完全来自 function call 消失、retired instruction 减少和 resource stall 消除。相对 generic iterator，它只需 26.22% 的指令、36.67% 的 data access、1.08% 的 function call；CPI 改善 22.5%，接近理想值 0.25。随着代码越来越 query-specific，D1/L2 hardware prefetch efficiency 均增加一倍以上。

Join Q2 的输入更大、selectivity 更低，大部分时间用于 hash partition 和 partition sorting。所有版本使用相同算法、相同 type-specific quicksort 和近似访问模式，因此差距缩小，但 HIQUE 仍比 iterator 版本快近 2 倍。Retired instruction、data access 和 function call 仍明显减少，但幅度不及 Q1。Hard-coded 版本的 CPI 反而升高，是因为总 retired instruction 更少，昂贵 memory operation 在 CPI 中的占比因而更大。D1 prefetch efficiency 约翻倍，所有版本的 L2 prefetch efficiency 均约为 90%。

![图 6：Aggregation 查询的执行时间分解和硬件指标](assets/precise-manual-figure-06-aggregation-profiling.png)

图 6 对 aggregation 查询做同样 profiling。Aggregation Query #1 中 HIQUE 仍保持优势；Aggregation Query #2 的 map-based aggregation 减少中间 staging，HIQUE 的 function calls 显著下降。

Aggregation Q1 使用 hybrid hash-sort：staging 主导 execution time，后续只需单趟扫描已排序 partition。由于各版本采用相同 partitioning 和 sorting 实现，memory stall cost 相近；HIQUE 仍比 iterator 快 1.61 倍，差异来自 instruction、data access 和 function call 减少。D1 prefetch efficiency 提高约 3 倍，所有实现的 L2 prefetch efficiency 接近 90%。

Aggregation Q2 使用 map-based algorithm，单趟扫描输入且无需 intermediate staging，因此 generator 可以把 group tracking 和 aggregate calculation 全部内联到一个 code segment。HIQUE 比 generic iterator 快近 2 倍。由于每条 tuple 的 aggregate calculation 只需少量指令，memory stall 主导 HIQUE 的 execution time，不过 non-blocking cache 可能缓解其影响。随着代码越来越 query-specific，function call 逐步减少，在 HIQUE 中降至 4.95%。线性扫描使 D1 prefetch efficiency 超过 70%，所有实现的 L2 prefetch efficiency 接近 95%。

随后关闭 compiler optimization（GNU compiler 使用 `-O0`）并重跑这些 join 与 aggregation query，结果见表 II。没有 compiler optimization 时，各版本之间的差异更明显，因为 compiler 会完成部分 code generation 已包含的优化，例如内联 predicate evaluation function，使最后两个实现之间的差距在 `-O2` 下缩小。Join Q1 的 compiler speedup 为 2.67-4.85 倍，其他查询接近 2 倍。由于我们为每个查询编译全部实现，iterator 版本同样得到显著收益；hard-coded source 已经很精简，并包含 loop blocking、function inlining 等优化，compiler 可发挥的空间较少，但简洁控制流和较少 function call 仍带来显著加速。

表 II：Compiler optimization 的影响（响应时间，单位：秒）。

| Implementation | Join Q1 -O0 | Join Q1 -O2 | Join Q2 -O0 | Join Q2 -O2 | Agg Q1 -O0 | Agg Q1 -O2 | Agg Q2 -O0 | Agg Q2 -O2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Generic iterators | 0.802 | 0.235 | 1.953 | 0.995 | 1.225 | 0.527 | 0.136 | 0.060 |
| Optimized iterators | 0.618 | 0.231 | 1.850 | 0.990 | 1.199 | 0.509 | 0.113 | 0.055 |
| Generic hard-coded | 0.430 | 0.118 | 1.421 | 0.688 | 0.586 | 0.344 | 0.095 | 0.051 |
| Optimized hard-coded | 0.267 | 0.055 | 1.225 | 0.622 | 0.554 | 0.333 | 0.080 | 0.038 |
| HIQUE | 0.178 | 0.054 | 1.138 | 0.613 | 0.543 | 0.326 | 0.070 | 0.033 |

### B. 整体算法的性能

![图 7：Join 与 aggregation 微基准性能](assets/precise-manual-figure-07-join-aggregation-performance.png)

图 7 比较本文算法的 optimized iterator 版本和 HIQUE 为各查询生成的代码，覆盖 join scalability、multi-way join、join predicate selectivity 和 grouping attribute cardinality。

Join scalability 实验采用每条 72 bytes 的两张表和 integer join attribute，每个 outer tuple 匹配 10 个 inner tuple；outer cardinality 固定为 1,000,000，inner cardinality 从 1,000,000 增至 10,000,000。所有算法均线性扩展，iterator-based hash-sort-merge 与 HIQUE merge join 性能相近，而 HIQUE generated hash-sort-merge 在整个 cardinality 范围内都明显更快。

Multi-way 实验把一张含 1,000,000 条 tuple 的表与 2-8 张各含 100,000 条 tuple 的表按单一 join attribute 连接；所有 tuple 都是 72 bytes，输出 cardinality 恒为 1,000,000。比较对象包括 binary iterator merge join、HIQUE 生成的对应 binary 版本，以及启用 join team 后的 HIQUE merge/hybrid join。即使 binary HIQUE 也大幅优于 iterator；join team 又通过避免 intermediate result materialization 显著缩短时间，连接 8 张表时差距达到 3.32 倍。

Join selectivity 实验连接两张各有 1,000,000 条 72-byte tuple 的表，每个 outer tuple 的 inner match 数量从 1 增至 1,000。随着 iterator call 增多、join evaluation cost 超过所有实现共同承担的 input staging，差距迅速扩大，在每个 outer tuple 匹配 1,000 条时达到 5 倍。

Aggregation 实验采用 1,000,000 条 72-byte tuple、两个 sum function 和一个 grouping attribute，把 distinct value 数量从 10 调到 100,000。Group 很少时，map aggregation 的 iterator 与 holistic 版本都很高效；sort 和 hybrid aggregation 对 group 数量只受中等程度影响。当 map 的 value directory 和 aggregate array 跨出 L2 后，sort/hybrid 反而更快，100,000 个 group 时差距接近 2 倍。

### C. TPC-H benchmark

最后一组实验采用标准且更真实的 TPC-H benchmark [24]。我们把 HIQUE 与三个数据库系统比较：（a）PostgreSQL 8.2.7，广泛使用的高性能开源 DBMS，采用 NSM 和 iterator model；（b）匿名商业系统 System X，同样采用 NSM 和 iterator，但用 software prefetch instruction 减少 cache-miss stall；（c）MonetDB 5.8.2，采用 DSM storage layer 和 column-wise evaluation algorithm 的 architecture-conscious DBMS。这个组合分别代表传统 I/O-optimized 设计、用 software prefetch 衔接 I/O-bound 与 CPU-bound execution 的设计，以及面向 main-memory execution 优化的设计。

我们用 benchmark generator 生成 scaling factor 1 的数据集。导入各系统前未对表作排序等任何修改；不含索引的 raw data 约 1.3 GB，能放入实验机器主存。所有系统都建立索引、以最高详细级别收集统计信息，并把内存参数设置为允许 in-memory execution。实验使用 TPC-H Q1、Q3 和 Q10。后两者含有不能作为 join team 求值的高选择性 join predicate，并包含 grouping attribute 和 aggregate function 数量不一的 aggregation。TPC-H tuple 很宽、跨越多个 cache line，而每个查询实际只需要少数字段；因此预期 MonetDB 会从 vertical partitioning 获益，优于 NSM 系统。

![图 8：TPC-H 查询性能对比](assets/precise-manual-figure-08-tpch-queries.png)

图 8 比较 TPC-H Q1、Q3、Q10 上 PostgreSQL、System X、MonetDB 与 HIQUE 的响应时间。

Q1 对几乎整张 `lineitem` 表（约 5,900,000 条 tuple）做 aggregation，输出 4 个 group。两个 grouping attribute 的 distinct value cardinality 乘积仅为 6，因此最合适的整体算法是 map aggregation。HIQUE 把 selection、grouping 和 aggregation 全部内联到一个无 function call、面向高效 register utilization 的紧凑 code block 中。HIQUE 用时 0.356 s，MonetDB 1.376 s、System X 37.185 s、PostgreSQL 59.353 s；即比 MonetDB 快约 4 倍，比 PostgreSQL 快 167 倍。实测 662.16 million CPU cycles，与 MonetDB/X100 的 DSM 方案相当，并比其 NSM 方案快 30% [26]。因此，我们认为 HIQUE 生成的代码等同于 hard-coded implementation，至少在 NSM 系统的 aggregation 上达到最高效率。

Q3/Q10 同时测试 join、aggregation 和 sorting。Holistic optimizer 在进一步处理前先 stage 全部输入；TPC-H tuple 很宽而查询只使用其中一小部分，这一步代价较高，恰好有利于只取所需字段的 DSM 系统。HIQUE 相对 MonetDB 在 Q3 上快 34.5%，在 Q10 上慢 18.1%；但相对两个 NSM 系统仍快 2.2-11.1 倍。

这些结果证明整体求值在真实查询负载中可行：整体模型简化代码并提高执行时的 cache locality，减少求值所需的 instruction 和 data access，因而降低 processor 和 memory subsystem 压力、显著加速查询。这使采用 NSM 的 HIQUE 达到了此前通常只能由 vertical-partitioning 系统实现的性能。

### D. 代码生成成本

表 III 给出 TPC-H 查询准备成本：

| TPC-H Query | Parse ms | Optimize ms | Generate ms | Compile -O0 ms | Compile -O2 ms | Source bytes | Shared library bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| #1 | 21 | 1 | 1 | 121 | 274 | 17,733 | 16,858 |
| #3 | 11 | 1 | 2 | 160 | 403 | 33,795 | 24,941 |
| #10 | 15 | 1 | 4 | 213 | 619 | 50,718 | 33,510 |

Parse/optimize/generate 合计低于 25 ms；C 编译 O0 为 121-213 ms，O2 为 274-619 ms，source/shared library 均小于约 50 KB。短查询应避免收益无法摊销的高优化；频繁或近期查询可缓存小型 binary。此外，在多数情况下，performance benefit 仍然超过代码生成成本。

## VII. 结论与未来工作

我们已经论证了整体查询求值。该方法生成查询专用代码，把多个查询操作集成到简洁、连续的代码结构中；生成过程使用每个查询算子的代码模板，构造以三项目标为导向的查询专用代码：尽量减少函数调用、减少指令和内存访问、增强 cache locality。该模型在基于 NSM 的存储层之上取得显著性能优势，同时不影响并发控制与恢复等 DBMS 正交模块。为验证这些优势，我们实现了整体集成查询引擎 HIQUE；在多种数据集和查询负载上的广泛实验表明，每查询代码生成在主存执行中具有明显潜力和很高效率。

下一步是把该方法扩展到多线程处理。现代处理器集成多个核心并共享最低层片上 cache；这种设计扩大了并行机会，也带来资源争用。代码生成尤其适合这种架构，因为生成器可以精确指定哪些代码段并行执行，从而降低同步开销和内存带宽需求。

## 参考文献

- [1] Anastassia Ailamaki et al. DBMSs on a Modern Processor: Where Does Time Go? In The VLDB Journal, 1999.
- [2] Anastassia Ailamaki et al. Weaving Relations for Cache Performance. In The VLDB Journal, 2001.
- [3] P. A. Boncz. Monet: A Next-Generation DBMS Kernel For Query-Intensive Applications. PhD thesis, Universiteit van Amsterdam, 2002.
- [4] P. A. Boncz, M. Zukowski, and N. Nes. MonetDB/X100: Hyper-Pipelining Query Execution. In CIDR, 2005.
- [5] Donald D. Chamberlin et al. A history and evaluation of System R. Commun. ACM, 24(10), 1981.
- [6] Shimin Chen et al. Fractal prefetching B+-Trees: optimizing both cache and disk performance. In SIGMOD, 2002.
- [7] Shimin Chen et al. Improving hash join performance through prefetching. In ICDE, 2004.
- [8] Shimin Chen et al. Inspector Joins. In VLDB, 2005.
- [9] George P. Copeland and Setrag Khoshafian. A Decomposition Storage Model. In SIGMOD, 1985.
- [10] Jack Doweck. Inside Intel Core Microarchitecture and Smart Memory Access, 2005. White paper.
- [11] Goetz Graefe. Query Evaluation Techniques for Large Databases. ACM Comput. Surv., 25(2), 1993.
- [12] Goetz Graefe et al. Hash Joins and Hash Teams in Microsoft SQL Server. In VLDB, 1998.
- [13] Rick Greer. Daytona And The Fourth-Generation Language Cymbal. In SIGMOD, 1999.
- [14] John Hennessy and David Patterson. Computer architecture: a quantitative approach. Morgan Kaufmann, 2006.
- [15] Intel Corporation. Intel 64 and IA-32 Architectures Software Developer’s Manual, 2008.
- [16] Ken Kennedy and John R. Allen. Optimizing compilers for modern architectures: a dependence-based approach. Morgan Kaufmann Publishers Inc., 2002.
- [17] Masaru Kitsuregawa et al. Application of Hash to Data Base Machine and Its Architecture. New Generation Comput., 1(1), 1983.
- [18] S. Manegold et al. What happens during a Join? - Dissecting CPU and Memory Optimization Effects. In VLDB, 2000.
- [19] OProfile. A System Profiler for Linux, 2008. http://oprofile.sourceforge.net/.
- [20] Sriram Padmanabhan et al. Block Oriented Processing of Relational Database Operations in Modern Computer Architectures. In ICDE, 2001.
- [21] Jun Rao et al. Compiled Query Execution Engine using JVM. In ICDE, 2006.
- [22] RightMark. RightMark Memory Analyser, 2008. http://cpu.rightmark.org/products/rmma.shtml.
- [23] Ambuj Shatdal et al. Cache Conscious Algorithms for Relational Query Processing. In VLDB, 1994.
- [24] Transaction Processing Performance Council. The TPC-H benchmark, 2009. http://www.tpc.org/tpch/.
- [25] Jingren Zhou and Kenneth A. Ross. Buffering database operations for enhanced instruction cache performance. In SIGMOD, 2004.
- [26] Marcin Zukowski et al. DSM vs. NSM: CPU performance tradeoffs in block-oriented query processing. In DaMoN, 2008.
