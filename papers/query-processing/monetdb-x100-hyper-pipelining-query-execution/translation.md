---
paper_id: monetdb-x100-hyper-pipelining-query-execution
title: 'MonetDB/X100: Hyper-Pipelining Query Execution'
language: zh-CN
source: source.pdf
---

# MonetDB/X100: Hyper-Pipelining Query Execution（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者

Peter Boncz、Marcin Zukowski、Niels Nes

## 摘要

在决策支持、OLAP 和多媒体检索等计算密集型应用中，数据库系统在现代 CPU 上往往只能达到很低的 IPC（instructions per cycle，每周期指令数）效率。本文首先深入研究其原因，重点关注 TPC-H 基准。我们对多种关系数据库系统和 MonetDB 的分析，导出了一组新的查询处理器设计准则。

论文第二部分描述 MonetDB 系统中新 X100 查询引擎的架构。表面上，它类似经典 Volcano 风格引擎；关键区别在于所有执行都基于向量处理（vector processing）概念，因此具有很高的 CPU 效率。我们在 100GB 规模的 TPC-H 上评估 MonetDB/X100，显示其原始执行能力相比此前技术高出一到两个数量级。

## 1. 引言

现代 CPU 每秒能执行大量计算，但前提是能找到足够多独立工作来利用其并行执行能力。过去十年的硬件发展显著扩大了满吞吐和低吞吐之间的速度差，差距可轻松达到一个数量级。按直觉，决策支持、OLAP、数据挖掘和多媒体检索等查询密集型数据库负载包含许多独立计算，应能让现代 CPU 接近最优 IPC。

然而研究表明，在这些应用领域中，数据库系统通常只能达到很低的 IPC 效率。我们质疑这种情况是否必然。除缓存感知查询处理这一重要话题外，本文详细研究关系数据库系统如何在查询密集型负载，特别是 TPC-H 决策支持基准中，与现代超标量 CPU 互动。

主要结论是：大多数 DBMS 采用的架构阻碍编译器使用最关键的性能优化技术，导致 CPU 效率低。特别是，流行的 Volcano 迭代器模型通常实现为 tuple-at-a-time 执行。这既带来高解释开销，也把 CPU 并行机会隐藏在编译器之外。

我们还分析了 MonetDB/MIL 的 CPU 效率。MonetDB 是我们团队开发的主存数据库，论文发表时已经开源，入口为 `monetdb.cwi.nl`。MonetDB/MIL 使用 column-at-a-time 执行模型，因此没有 tuple-at-a-time 解释产生的问题。但它的整列物化策略会在执行中产生大型数据流。在决策支持负载上，MonetDB/MIL 受到内存带宽强约束，CPU 效率急剧下降。

因此，我们主张结合 MonetDB 的列式执行与 Volcano 风格流水线提供的增量物化。为此，我们从头设计并实现了 MonetDB 的新查询引擎 X100，采用向量化查询处理模型。除高 CPU 效率外，MonetDB/X100 还旨在扩展到非纯内存的数据集，即磁盘数据。

### 1.1 论文结构

第 2 节介绍现代超标量（或超流水线）CPU，重点说明与查询求值性能最相关的问题。第 3 节把 TPC-H Query 1 作为 CPU 效率微基准，依次考察标准关系数据库、MonetDB，以及用于建立最大可达原始性能基线的独立手写实现。第 4 节介绍新 X100 查询处理器的架构，重点讨论查询执行，同时概述数据布局、索引和更新。第 5 节在 TPC-H 上比较 Monet 系统中的 MIL 与 X100，第 6 节讨论相关工作，第 7 节总结。

## 2. CPU 如何工作

现代 CPU 性能提升来自制造工艺缩小和流水线加深。更小的制造尺度带来更多、更小的晶体管，以及更短的连线距离和信号延迟。理论上，CPU 频率应随信号延迟降低而提升；实际频率提升更大，主要靠流水线：把 CPU 指令工作切成更多阶段。每阶段工作更少，频率就可以更高。

![图 1：十年 CPU 性能趋势。](assets/figure-01-cpu-performance.png)

流水线引入两个风险。第一，若某条指令需要前一条指令结果，它不能立刻进入流水线，必须等待结果可用。第二，遇到 `if a then b else c` 这类分支时，CPU 必须预测 `a` 的结果。如果预测错，必须清空流水线并重新开始。流水线越长，清空代价越高。对应到数据库系统，选择算子中那些依赖数据且选择率不极端的分支几乎无法预测，会显著拖慢查询执行。

超标量 CPU 还可以在多条独立指令之间并行执行。也就是说，CPU 不是一条流水线，而是多条流水线。若每周期都能向每条流水线送入独立指令，IPC 可以大于 1。现代处理器在这方面的平衡不同：Itanium2 是 VLIW 处理器，有多条并行流水线、流水线较短、频率较低；Pentium4 频率更高、流水线更深，但每周期可执行指令数较少。Intel 曾把“hyper-pipelined”作为“super-scalar”的同义营销用语来宣传 Pentium4。要达到理论最大吞吐，CPU 需要在任意时刻找到大量独立指令。

流水线深度的增长十分具体：1988 年 Intel 80386 用一个或多个周期完成一条指令；1993 年 Pentium 已有 5 级流水线；1999 年 Pentium III 增至 14 级；2004 年 Pentium4 达到 31 级。1.5GHz Itanium2 的流水线只有 7 级、每周期最多执行 6 条指令，因此在任意时刻需要 `7 × 6 = 42` 条相互独立的指令才能达到理论峰值；3.6GHz Pentium4 每周期最多执行 3 条，需要 `31 × 3 = 93` 条独立指令。程序通常找不到这么多并行工作，所以尽管 Pentium4 时钟高得多，两者在基准中的实际性能仍相近。

程序员通常不会显式标注哪些指令独立，因此编译器优化对 CPU 利用率至关重要。最重要的技术之一是循环流水化（loop pipelining）：把对数组每个元素依次执行多个依赖操作，重排成先对多个元素执行第一步，再对这些元素执行下一步。这样，当后续操作需要第一个元素的结果时，该结果已经从流水线中出来。

Itanium2 还提供分支谓词化（branch predication），可以并行执行 then 和 else，并在条件结果确定后丢弃其中一个结果。我们用选择查询微基准说明：普通 CPU 在 50% 选择率附近分支预测最差；把分支改写成布尔计算后，性能不再依赖选择率但平均成本更高；Itanium2 上编译器可把分支转换为硬件谓词化代码，因此性能也较稳定。

![图 2：Itanium 硬件谓词化消除分支误预测。](assets/figure-02-branch-predication.png)

片上缓存同样关键。大量 CPU 指令是内存 load/store，而主存位于 CPU 芯片外，物理延迟下界约 50ns。对 3.6GHz CPU 而言，这已经是约 180 个等待周期。只有绝大多数内存访问命中片上缓存，现代 CPU 才可能接近最大吞吐。数据库研究已经证明，缓存未命中严重损害 DBMS 性能；缓存对齐 B-tree、PAX/DSM 列式布局、radix 分区哈希连接等技术能显著改善性能。

总之，CPU 是复杂设备。其指令吞吐可因缓存命中率、分支可预测性/谓词化，以及编译器和 CPU 能发现的平均独立指令数量而相差几个数量级。商业 DBMS 查询执行常见 IPC 只有约 0.7，而科学计算或多媒体处理可达到更高 IPC。我们认为，数据库系统在大规模分析任务上不应如此低效，因为数百万元组和表达式计算本身包含大量独立工作。目标是改造数据库架构，把这些独立性暴露给编译器和 CPU。

## 3. 微基准：TPC-H Query 1

我们首先聚焦表达式计算，暂时排除 Join 等复杂关系操作。TPC-H Query 1 是一个很合适的微基准：它扫描 `lineitem` 表，选择几乎所有元组，计算多个定点 decimal 表达式和聚合。group-by 只作用于两个单字符列，产生 4 个唯一组合，可用小哈希表高效完成，不需要额外 I/O，甚至不需要因访问哈希表而产生 CPU 缓存未命中。

![图 3：TPC-H Query 1 的 SQL 形态。](assets/figure-03-tpch-query-1.png)

我们依次分析 Query 1 在传统关系数据库系统、MonetDB/MIL 和手写程序中的表现。

### 3.1 关系数据库系统中的 Query 1

自 RDBMS 早期以来，查询执行通常通过物理关系代数实现，并遵循 Volcano 流水线模型。然而，关系代数算子的参数自由度很高。即使简单的 `ScanSelect(R, b, P)`，也只有在查询时才知道输入关系格式、布尔选择表达式和投影表达式列表。为了处理所有可能情况，DBMS 实现者实际上需要实现一个能处理任意复杂表达式的解释器。

这种解释器的危险在于，尤其当解释粒度是元组时，真正工作，即执行查询表达式，只占总执行成本的一小部分。MySQL 4.1 在 TPC-H Query 1 上的 gprof trace 显示，真正做算术工作的函数只占总时间约 10%。约 28% 时间花在聚合哈希表的创建和查找；剩余约 62% 分散在记录表示导航、字段读取和复制等函数中。锁和 buffer 页分配在这个决策支持查询中影响较小。

原文还说明，我们使用的 Linux 测试平台当时没有可用的多线程 profiling 工具，因此这里的 trace 只来自单线程执行。

表 1 的关键性能数据如下，单位为秒；`(#CPU)/SF` 表示 CPU 数与 scale factor 归一化项。

| 系统 | 时间 | SF | CPU / 平台 | SPECCpu int/fp |
| --- | ---: | ---: | --- | --- |
| DBMS “X” | 28.1 | 1 | 1 AthlonMP 1533MHz | 609/547 |
| MySQL 4.1 | 26.6 | 1 | 1 AthlonMP 1533MHz | 609/547 |
| MonetDB/MIL | 3.7 | 1 | 1 AthlonMP 1533MHz | 609/547 |
| MonetDB/MIL | 3.4 | 1 | 1 Itanium2 1.3GHz | 1132/1891 |
| hand-coded | 0.22 | 1 | 1 AthlonMP 1533MHz | 609/547 |
| hand-coded | 0.14 | 1 | 1 Itanium2 1.3GHz | 1132/1891 |
| MonetDB/X100 | 0.50 | 1 | 1 AthlonMP 1533MHz | 609/547 |
| MonetDB/X100 | 0.31 | 1 | 1 Itanium2 1.3GHz | 1132/1891 |
| MonetDB/X100 | 0.30 | 100 | 1 Itanium2 1.3GHz | 1132/1891 |

即便是 Item 操作本身，`Item_func_plus::val` 的一次加法也要执行 38 条指令，远多于机器层面的几条 load/add/store。该 trace 采自 SGI MIPS R12000：它每周期可执行三条整数或浮点指令及一条 load/store，平均操作延迟约 5 个周期。一个简单的 `+(double src1, double src2)` 在 RISC 指令中只需：

```text
LOAD src1,reg1
LOAD src2,reg2
ADD  reg1,reg2,reg3
STOR dst,reg3
```

解释器的函数调用、类型处理、记录格式处理和不可见的控制流共同放大了每个元组的成本。

**表 2：MySQL 4.1 在 TPC-H Q1 上的 gprof trace。** `cum.` 与 `excl.` 是累计与独占时间百分比，`calls` 是调用次数，`ins.` 是每次调用指令数。

| cum. % | excl. % | calls | ins. | IPC | function |
| ---: | ---: | ---: | ---: | ---: | --- |
| 11.9 | 11.9 | 846M | 6 | 0.64 | `ut_fold_ulint_pair` |
| 20.4 | 8.5 | 0.15M | 27K | 0.71 | `ut_fold_binary` |
| 26.2 | 5.8 | 77M | 37 | 0.85 | `memcpy` |
| 29.3 | 3.1 | 23M | 64 | 0.88 | `Item_sum_sum::update_field` |
| 32.3 | 3.0 | 6M | 247 | 0.83 | `row_search_for_mysql` |
| 35.2 | 2.9 | 17M | 79 | 0.70 | `Item_sum_avg::update_field` |
| 37.8 | 2.6 | 108M | 11 | 0.60 | `rec_get_bit_field_1` |
| 40.3 | 2.5 | 6M | 213 | 0.61 | `row_sel_store_mysql_rec` |
| 42.7 | 2.4 | 48M | 25 | 0.52 | `rec_get_nth_field` |
| 45.1 | 2.4 | 60 | 19M | 0.69 | `ha_print_info` |
| 47.5 | 2.4 | 5.9M | 195 | 1.08 | `end_update` |
| 49.6 | 2.1 | 11M | 89 | 0.98 | `field_conv` |
| 51.6 | 2.0 | 5.9M | 16 | 0.77 | `Field_float::val_real` |
| 53.4 | 1.8 | 5.9M | 14 | 1.07 | `Item_field::val` |
| 54.9 | 1.5 | 42M | 17 | 0.51 | `row_sel_field_store_in_mysql` |
| 56.3 | 1.4 | 36M | 18 | 0.76 | `buf_frame_align` |
| 57.6 | 1.3 | 17M | 38 | 0.80 | `Item_func_mul::val` |
| 59.0 | 1.4 | 25M | 25 | 0.62 | `pthread_mutex_unlock` |
| 60.2 | 1.2 | 206M | 2 | 0.75 | `hash_get_nth_cell` |
| 61.4 | 1.2 | 25M | 21 | 0.65 | `mutex_test_and_set` |
| 62.4 | 1.0 | 102M | 4 | 0.62 | `rec_get_1byte_offs_flag` |
| 63.4 | 1.0 | 53M | 9 | 0.58 | `rec_1_get_field_start_offs` |
| 64.3 | 0.9 | 42M | 11 | 0.65 | `rec_get_nth_field_extern_bit` |
| 65.3 | 1.0 | 11M | 38 | 0.80 | `Item_func_minus::val` |
| 65.8 | 0.5 | 5.9M | 38 | 0.80 | `Item_func_plus::val` |

### 3.2 MonetDB/MIL 中的 Query 1

MonetDB/MIL 避免了 tuple-at-a-time 解释。它把列作为整体处理：每个 MIL primitive 接收列作为输入，产生新列作为输出。这样，表达式求值的循环更紧凑，解释开销在整列上摊销，编译器和 CPU 也更容易优化。

但问题转移到内存带宽。MonetDB/MIL 在每个操作后物化完整中间列，导致大量中间结果被写入和读出主存。对于 Query 1 这类表达式和聚合，整列物化使系统受限于 RAM 带宽。也就是说，MonetDB/MIL 消除了 tuple-at-a-time 解释，却因 column-at-a-time 的全量物化而变成内存带宽瓶颈。

**表 3：MonetDB/MIL 的 TPC-H Q1 trace。** SF=1 列给出主存工作集，SF=0.001 列给出可驻 cache 的缩小工作集；带宽单位为 MB/s。

| SF=1 ms | SF=1 BW | SF=.001 us | SF=.001 BW | 总 MB | 结果大小 | MIL statement |
| ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 127 | 352 | 150 | 305 | 45 | 5.9M | `s0 := select(l_shipdate).mark` |
| 134 | 505 | 113 | 608 | 68 | 5.9M | `s1 := join(s0,l_returnflag)` |
| 134 | 506 | 113 | 608 | 68 | 5.9M | `s2 := join(s0,l_linestatus)` |
| 235 | 483 | 129 | 887 | 114 | 5.9M | `s3 := join(s0,l_extprice)` |
| 233 | 488 | 130 | 881 | 114 | 5.9M | `s4 := join(s0,l_discount)` |
| 232 | 489 | 127 | 901 | 114 | 5.9M | `s5 := join(s0,l_tax)` |
| 134 | 507 | 104 | 660 | 68 | 5.9M | `s6 := join(s0,l_quantity)` |
| 290 | 155 | 324 | 141 | 45 | 5.9M | `s7 := group(s1)` |
| 329 | 136 | 368 | 124 | 45 | 5.9M | `s8 := group(s7,s2)` |
| 0 | 0 | 0 | 0 | 0 | 4 | `s9 := unique(s8.mirror)` |
| 206 | 440 | 60 | 1527 | 91 | 5.9M | `r0 := [+](1.0,s5)` |
| 210 | 432 | 51 | 1796 | 91 | 5.9M | `r1 := [-](1.0,s4)` |
| 274 | 498 | 83 | 1655 | 137 | 5.9M | `r2 := [*](s3,r1)` |
| 274 | 499 | 84 | 1653 | 137 | 5.9M | `r3 := [*](s12,r0)` |
| 165 | 271 | 121 | 378 | 45 | 4 | `r4 := {sum}(r3,s8,s9)` |
| 165 | 271 | 125 | 366 | 45 | 4 | `r5 := {sum}(r2,s8,s9)` |
| 163 | 275 | 128 | 357 | 45 | 4 | `r6 := {sum}(s3,s8,s9)` |
| 163 | 275 | 128 | 357 | 45 | 4 | `r7 := {sum}(s4,s8,s9)` |
| 144 | 151 | 107 | 214 | 22 | 4 | `r8 := {sum}(s6,s8,s9)` |
| 112 | 196 | 145 | 157 | 22 | 4 | `r9 := {count}(s7,s8,s9)` |
| **3724** | — | **2327** | — | — | — | **TOTAL** |

### 3.3 手写实现

我们还用手写 C 程序实现 Query 1，用作最大可达原始性能基线。手写程序知道所有数据类型、表达式和聚合结构，因此可以把循环写得非常紧凑，并让编译器进行充分优化。这个基线比传统 DBMS 快一个到两个数量级，也明显快于 MonetDB/MIL，说明硬件本身有能力以很高效率执行这类分析工作；低效主要来自执行模型。

![图 4：TPC-H Query 1 的手写 C UDF。](assets/figure-04-hard-coded-udf.png)

手写代码的局限是不可作为通用查询引擎直接使用。数据库系统必须处理任意查询、类型和表达式。因此，X100 的目标是在保持通用性的同时，尽可能接近手写代码的 CPU 效率。

## 4. MonetDB/X100 架构

X100 的目标有三项：以很高 CPU 效率执行大数据量查询；能扩展到数据挖掘、多媒体检索等领域，并让扩展代码达到同样效率；随着最低层存储（磁盘）的容量扩展。为此它在整个存储层次上逐层消除瓶颈：

- **磁盘**：ColumnBM I/O 子系统面向顺序访问，使用垂直分片布局，并在适用时加入轻量压缩来减少带宽。
- **RAM**：用显式 memory-to-cache/cache-to-memory 例程搬运数据，例程可含平台专用的 SSE 预取或汇编数据移动；RAM 中保留与磁盘一致的垂直、压缩布局。
- **Cache**：使用类似 Volcano 的流水线，但单位是约 1000 个值、驻留 cache 的垂直小块，即向量。压缩/解压发生在 RAM 与 cache 的边界，算子把大数据集切成 cache chunk，并把随机访问限制在这些小块内。
- **CPU**：向量化 primitive 明确告诉编译器，相邻元组互相独立，使其可以循环流水化。X100 还可为整个表达式子树生成 compound primitive，减少指令流中的 load/store；当前由构建期静态指定，未来可由优化器在运行时触发。

因此，X100 在 Volcano 和 MonetDB/MIL 之间取得平衡：它使用流水线算子避免整列物化，但每次 `next()` 返回小型向量而非一个元组。解释开销按向量大小摊销，中间结果也不会膨胀为主存带宽瓶颈。论文中的 ColumnBM 尚在开发，实验实际以 MonetDB 的内存 BAT 作为存储管理器。

![图 5：X100 软件架构。](assets/figure-05-x100-architecture.png)

### 4.1 查询语言

X100 使用相当标准的关系代数。它不沿用一次处理一列的 MIL，因为关系算子需要同时处理多个列，使一个表达式产生的向量能在仍位于 CPU cache 时直接成为下一个表达式的输入。算子之间通过 `next()` 形成流水线，但每次调用返回一批垂直向量。

#### 4.1.1 示例

图 6 用简化的 TPC-H Query 1 展示执行：

```text
Aggr(
  Project(
    Select(
      Table(lineitem),
      <(shipdate, date('1998-09-03'))),
      [discountprice = *(-(flt('1.0'), discount), extendedprice)]),
    [returnflag],
    [sum_disc_price = sum(discountprice)])
```

![图 6：简化 TPC-H Query 1 在 MonetDB/X100 中的执行方案。](assets/figure-06-execution-scheme.png)

执行以向量（例如 1000 个值）为粒度。Scan 每次从 Monet BAT 取回一个向量，且只扫描查询真正用到的属性。Select 生成 selection vector，其中存放通过谓词的元组位置。Project 计算聚合需要的表达式；`discount`、`extendedprice` 不会在选择后复制压紧，map primitive 读取 selection vector，只计算相关位置，并把结果写回输出向量的相同位置。因此 selection vector 一直传到 Aggr。Aggr 为每个元组计算哈希表位置、更新聚合值，并在新组出现时保存分组属性；下层算子耗尽后，哈希表内容即为结果。

这种模型有几个好处。算子解释和函数调用开销按向量大小摊销；primitive 循环规则、类型固定，编译器可进行循环流水化和寄存器分配；中间结果只以 cache-resident 向量在相邻算子间传递，避免 MonetDB/MIL 的整列物化；垂直向量布局也适合 cache 和 SIMD。

#### 4.1.2 X100 代数

X100 代数支持常规算子，如 Scan、Select、Project、Aggregation、Join 等。表达式被分解为 primitive 调用；primitive 针对操作、类型和输入格式组合实现。例如 map primitive 对输入向量执行加减乘除，select primitive 生成 selection vector，aggregation primitive 在 group id 上更新聚合状态。

![图 7：X100 查询代数。](assets/figure-07-query-algebra.png)

`Table` 表示物化关系，`Dataflow` 表示在流水线中流动的元组。`Order`、`TopN` 和 `Select` 保持输入 dataflow 的 shape，其余算子可定义新 shape。`Project` 只做表达式计算，不负责消重；消重用只有 group-by 列的 `Aggr` 完成。`Array` 产生表示 N 维整数空间的 dataflow，可用于生成索引位置。`Fetch1Join`/`FetchNJoin` 按 row id 从垂直列取值；`OrdAggr`、`DirectAggr`、`HashAggr` 是按输入性质选择的聚合实现。

聚合有三个物理算子：直接聚合、哈希聚合和有序聚合。如果源 dataflow 中同组成员连续到达，选择有序聚合；若 group id 的 bit 表示限制在已知的小域内，可像手写方案一样使用小数组直接聚合；其他情况使用哈希聚合。

当前 X100 只支持 left-deep join。默认物理实现是上方带 `Select` 的 `CartProd`，即嵌套循环连接；若检测到外键谓词且有 join index，就改用 `Fetch1Join` 或 `FetchNJoin`。这些 fetch join 也承担垂直分片中的“位置连接”：X100 为每张表赋予从 0 递增的虚拟 `#rowId`，`Fetch1Join` 可按该位置取回某列的值。这相当于 MonetDB 中把 OID positional-join 到 void 列，能高效完成垂直列的重新组合。

### 4.2 向量化 Primitive

X100 把大量实际计算下沉到预编译 primitive。垂直数据模型使 primitive 只需知道所操作的列，不必知道整条记录的 offset 或 layout；固定 shape 的独立数组又允许 C 编译器激进循环流水化。向量浮点加法的生成代码形态如下：

```c
map_plus_double_col_double_col(
    int n,
    double *__restrict__ res,
    double *__restrict__ col1,
    double *__restrict__ col2,
    int *__restrict__ sel)
{
    if (sel) {
        for (int j = 0; j < n; j++) {
            int i = sel[j];
            res[i] = col1[i] + col2[i];
        }
    } else {
        for (int i = 0; i < n; i++)
            res[i] = col1[i] + col2[i];
    }
}
```

`sel` 可以为空，也可以指向 `n` 个选中位置。所有 X100 primitive 都接受这种 selection vector。选择后保留子算子原向量，通常比把所有选中值复制到新的连续向量更快。

X100 有数百个 primitive，但不手写维护，而是由 pattern 生成。例如：

```text
any::1 +(any::1 x, any::1 y) plus = x + y
```

表示两个同类型值可用 C 的中缀 `+` 实现，结果同类型，标识名为 `plus`；后续类型专用 pattern 可以覆盖它。另一个文件请求要生成的签名：

```text
+(double*, double*)
+(double,  double*)
+(double*, double)
+(double,  double)
```

星号表示列，从而生成列/标量的所有组合。只允许单值 UDF 的可扩展数据库会隐藏循环，妨碍编译器流水化；X100 让扩展作者提供源码 pattern，因而抽象数据类型（ADT）也能获得与内置类型相同的执行待遇。

原文指出，X100 二进制当时小于 1 MB；若部署在资源受限环境，可省略某些 primitive 的列版本进一步缩小体积。X100 仍能以 vector size 为 1 的方式执行这些 primitive，只是速度较慢。

X100 还能请求 compound primitive，例如：

```text
/(square(-(double*, double*)), double*)
```

这是多媒体检索中的 Mahalanobis 距离表达式。实验中 compound primitive 常比逐函数 primitive 快约 2 倍。普通二元 primitive 每做一次算术要装入两个参数并存一个结果，即 1 条工作指令配 3 条内存指令，而现代 CPU 每周期通常只能执行 1-2 次 load/store。compound primitive 在表达式图边界才访问内存，中间结果通过寄存器传递，改善指令配比。论文实现的生成器仍只是 make 流程中的宏展开脚本，未来计划由优化器要求动态编译。

对返回布尔值的 pattern，`select_*` primitive 不产生完整布尔向量，而是填充选中位置数组并返回数量。`aggr_*` primitive 则计算 `count`、`sum`、`min`、`max`，每种聚合由初始化、更新和收尾 pattern 生成不同 X100 聚合实现所需例程。

### 4.3 数据存储

MonetDB/X100 以垂直分片形式存储所有表。无论使用新的 ColumnBM buffer manager，还是 MonetDB 的 BAT 存储，存储方案相同。MonetDB 将每个 BAT 存为单个连续文件；ColumnBM 则把这些文件划分为大块。

垂直存储的一个缺点是更新成本较高：单行更新或删除可能需要对每列执行一次 I/O。X100 通过把垂直分片视为不可变对象来规避这一点。更新写入 delta 结构。删除通过把 tuple id 加入删除列表处理；插入则追加到独立 delta 列。ColumnBM 把所有 delta 列一起存储在一个块中，类似 PAX。因此删除和插入都只需一次 I/O。更新可视为先删除再插入。随着 delta 增长，当其大小超过总表大小的某个较小百分比时，系统应重组数据存储，使垂直存储重新最新并清空 delta。

![图 8：垂直存储与更新处理。](assets/figure-08-storage-updates.png)

垂直存储的优势是，访问大量元组但不访问所有列的查询可以节省带宽。这既适用于 RAM 带宽，也适用于 I/O 带宽。X100 还使用轻量压缩进一步降低带宽需求。枚举类型可把列存为一字节或二字节整数，该整数引用映射表的 row id。当查询使用这些列时，X100 自动加入 Fetch1Join 操作取回未压缩值。由于垂直分片不可变，更新只进入未压缩 delta 列，不会使压缩方案复杂化。

X100 还支持简单 summary index，用于近似有序的列。这些索引以较粗粒度存储 row id、到该位置的 running maximum 以及反向 running minimum，可快速为范围谓词推导 row id 边界。由于垂直分片不可变，这些索引几乎不需要维护；小型内存 delta 列不建索引，始终直接访问。

## 5. TPC-H 实验

我们比较了 MonetDB/MIL 和 MonetDB/X100 在完整 TPC-H 查询上的表现。SQL 基准查询在开箱即用的 MonetDB/MIL 上运行；我们还手工把所有 TPC-H 查询翻译为 X100 algebra 后运行。结果显示 X100 明显超过 MonetDB/MIL。

在配置上，MonetDB/MIL 和 X100 都在所有外键路径上使用 join index。X100 还按日期排序 `orders` 表，并让 `lineitem` 与之聚簇；对两个表所有日期列使用 summary index；还按 region/country 排序 supplier 和 customer。SF=1 时，MonetDB/MIL 总磁盘存储约 1GB，X100 约 0.8GB，降低来自枚举类型压缩。

我们还在 1.3GHz Itanium2（3MB cache、12GB RAM）上运行 SF=1 和 SF=100，并与四颗 1.5GHz Itanium2、32GB RAM 的 DB2 8.1 官方 power test 比较。需要注意的是，MonetDB 数字全是内存内结果；DB2 包含 I/O，但其平台使用 112 块 SCSI 磁盘，很可能已经加盘到 CPU-bound。DB2 的 CPU 配置强四倍以上，X100 的结果仍很稳健。

原文表 4 的完整执行时间如下（秒）：

| Q | MonetDB/MIL SF=1 | X100 Athlon SF=1 | X100 Itanium SF=1 | X100 Itanium SF=100 | DB2 4CPU SF=100 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 3.72 | 0.50 | 0.31 | 30.25 | 229 |
| 2 | 0.46 | 0.01 | 0.01 | 0.81 | 19 |
| 3 | 2.52 | 0.04 | 0.02 | 3.77 | 16 |
| 4 | 1.56 | 0.05 | 0.02 | 1.15 | 14 |
| 5 | 2.72 | 0.08 | 0.04 | 11.02 | 72 |
| 6 | 2.24 | 0.09 | 0.02 | 1.44 | 12 |
| 7 | 3.26 | 0.22 | 0.22 | 29.47 | 81 |
| 8 | 2.23 | 0.06 | 0.03 | 2.78 | 65 |
| 9 | 6.78 | 0.44 | 0.44 | 71.24 | 274 |
| 10 | 4.40 | 0.22 | 0.19 | 30.73 | 47 |
| 11 | 0.43 | 0.03 | 0.02 | 1.66 | 20 |
| 12 | 3.73 | 0.09 | 0.04 | 3.68 | 19 |
| 13 | 11.42 | 1.26 | 1.04 | 148.22 | 343 |
| 14 | 1.03 | 0.02 | 0.02 | 2.64 | 14 |
| 15 | 1.39 | 0.09 | 0.04 | 14.36 | 30 |
| 16 | 2.25 | 0.21 | 0.14 | 15.77 | 64 |
| 17 | 2.30 | 0.02 | 0.02 | 1.75 | 77 |
| 18 | 5.20 | 0.15 | 0.11 | 10.37 | 600 |
| 19 | 12.46 | 0.05 | 0.05 | 4.47 | 81 |
| 20 | 2.75 | 0.08 | 0.05 | 2.45 | 35 |
| 21 | 8.85 | 0.29 | 0.17 | 17.61 | 428 |
| 22 | 3.07 | 0.07 | 0.04 | 2.30 | 93 |

### 5.1 Query 1 性能

我们进一步分析 X100 上 TPC-H Query 1。X100 提供基于底层 CPU 计数器的 tracing 和 profiling。trace 的 primitive 级统计显示，X100 能以很低的每元组周期数运行 primitive。即使相对复杂的聚合 primitive，也约为每元组 6 个周期；乘法 map primitive 约为每元组 2.2 个周期，远好于 MySQL 中约 49 周期的乘法。

![图 9：TPC-H Query 1 的 X100 Algebra 计划。](assets/figure-09-x100-algebra.png)

另一个观察是，因为 primitive 处理的大部分数据来自 CPU cache 中的向量，X100 能维持很高带宽。MonetDB/MIL 中乘法受约 500MB/s RAM 带宽限制，而 X100 在 Itanium2 的同一算子上超过 7.5GB/s（AthlonMP 约 5GB/s）。此外，Query 1 的 `l_discount`、`l_tax`、`l_quantity` 以枚举类型存储，X100 自动插入三个 Fetch1Join 恢复原值，每个都低于 2 cycles/tuple。

原文表 5 的 primitive 级 trace 如下；输入计数中的 6M/5.9M 分别表示过滤前后约 600 万/590 万行：

| 输入 | 数据量 MB | 时间 us | 带宽 MB/s | cycles/tuple | Primitive |
| ---: | ---: | ---: | ---: | ---: | --- |
| 6M | 30 | 8518 | 3521 | 1.9 | `map fetch uchr_col flt_col` |
| 6M | 30 | 8360 | 3588 | 1.9 | `map fetch uchr_col flt_col` |
| 6M | 30 | 8145 | 3683 | 1.9 | `map fetch uchr_col flt_col` |
| 6M | 35.5 | 13307 | 2667 | 3.0 | `select lt usht_col usht_val` |
| 5.9M | 47 | 10039 | 4681 | 2.3 | `map sub flt_val flt_col` |
| 5.9M | 71 | 9385 | 7565 | 2.2 | `map mul flt_col flt_col` |
| 5.9M | 71 | 9248 | 7677 | 2.1 | `map mul flt_col flt_col` |
| 5.9M | 47 | 10254 | 4583 | 2.4 | `map add flt_val flt_col` |
| 5.9M | 35.5 | 13052 | 2719 | 3.0 | `map uidx uchr_col` |
| 5.9M | 53 | 14712 | 3602 | 3.4 | `map directgrp uidx_col uchr_col` |
| 5.9M | 71 | 28058 | 2530 | 6.5 | `aggr sum flt_col uidx_col` |
| 5.9M | 71 | 28598 | 2482 | 6.6 | `aggr sum flt_col uidx_col` |
| 5.9M | 71 | 27243 | 2606 | 6.3 | `aggr sum flt_col uidx_col` |
| 5.9M | 71 | 26603 | 2668 | 6.1 | `aggr sum flt_col uidx_col` |
| 5.9M | 71 | 27404 | 2590 | 6.3 | `aggr sum flt_col uidx_col` |
| 5.9M | 47 | 18738 | 2508 | 4.3 | `aggr count uidx_col` |

### 5.1.1 向量大小影响

X100 默认向量大小为 1024，但用户可覆盖。理想情况下，所有向量合计应舒适地放入 CPU 缓存，因此不能太大；但若向量太小，利用 CPU 并行性的机会消失，X100 algebra `next()` 方法的解释开销也会增大。

实验显示，当向量大小为 1，即 tuple-at-a-time 处理时，解释开销对 X100 也很严重。随着向量大小增加，执行时间迅速改善。对该查询和平台而言，最佳值约为 1000，128 到 8K 都表现良好。Query 1 所有向量的合计宽度略高于每元组 40 字节；AthlonMP 的 L1+L2 合计 320KB，因此超过 8K 后 cache 需求越界，性能开始下降。Itanium2 有 16KB L1、256KB L2、3MB L3，退化稍早开始，随后持续到 64K × 40 字节也越过 L3。极端向量大小为 4M 时，中间结果都物化到主存，X100 行为接近 MonetDB/MIL，但仍因不需要 MIL 为投影选中元组所做的额外 join 而更快。

![图 10：Query 1 性能随 vector size 的变化。](assets/figure-10-vector-size.png)

## 6. 相关工作

本文在经典 Volcano 迭代器模型和 MonetDB 列式查询处理模型之间架桥。Volcano 不仅形式化了查询处理迭代器模型，也概括了多种并行查询处理形式，例如为每个查询算子分配单独进程。X100 的不同之处在于，它通过让进程在每次查询处理迭代中在同一算子内处理一个元组向量，而不是单个元组，来减少开销。

与本文最接近的是 DB2 中的 blocked execution path。不同于从一开始就为向量化执行设计的 X100，DB2 工作只用这种方法增强 aggregation 和 projection，且元组布局仍是 NSM。另一些工作在算子流水线中插入 Buffer 算子，让其连续调用子算子多次以缓解指令缓存问题；X100 认为，如果查询算子本身就以块/向量为单位工作，可以自然获得这类指令缓存收益。

在数据存储方面，X100 的更新方案结合了 DSM 和 PAX。PAX 块可看作一组垂直向量，因此 X100 可以在这种表示上直接运行而无需转换。

## 7. 结论与未来工作

本文研究了关系数据库系统为何在现代 CPU 上 CPU 效率较低。结论是，Volcano 风格的一次一个元组执行架构引入解释开销，并阻碍编译器使用最关键的优化技术，例如循环流水化。

我们还分析了 MonetDB 主存数据库的 CPU 效率。MonetDB 不受 tuple-at-a-time 解释影响，但采用 column-at-a-time 物化策略，导致系统受内存带宽限制。

因此，本文提出在 Volcano 和 MonetDB 执行模型之间取得平衡：流水线算子之间传递小的、缓存驻留的垂直数据片段，即向量。基于这一原则，我们提出 MonetDB 的新查询引擎 X100。它使用向量化 primitive 高效完成大部分查询处理工作。在 100GB TPC-H 决策支持基准上，MonetDB/X100 可比既有 DBMS 技术快一到两个数量级。

未来工作包括继续为 MonetDB/X100 增加更多向量化查询处理算子，把 MonetDB/MIL SQL 前端移植到 X100，并配备基于直方图的查询优化器。我们还计划让 ColumnDB buffer manager 支持从主存扩展到磁盘数据，同时在从磁盘顺序流入数据时尽量保持高 CPU 效率，包括研究轻量压缩和多查询磁盘访问优化。最后，我们考虑把 X100 用作低功耗环境中的高能效查询处理系统，因为它占用小，并且能用尽可能少的 CPU 周期完成尽可能多的工作。


## 参考文献

- [1] The STREAM Benchmark: Computer Memory Bandwidth. http://www.streambench.org.
- [2] A. Ailamaki, D. DeWitt, M. Hill, and M. Skounakis. Weaving Relations for Cache Performance. In Proc. VLDB, Rome, Italy, 2001.
- [3] A. Ailamaki, D. J. DeWitt, M. D. Hill, and D. A. Wood. DBMSs on a Modern Processor: Where Does Time Go? In Proc. VLDB, Edinburgh, 1999.
- [4] P. A. Boncz. Monet: A Next-Generation DBMS Kernel For Query-Intensive Applications. Ph.d. thesis, Universiteit van Amsterdam, Amsterdam, The Netherlands, May 2002.
- [5] P. A. Boncz and M. L. Kersten. MIL Primitives for Querying a Fragmented World. VLDB J., 8(2):101- 119, 1999.
- [6] Q. Cao, J. Torrellas, P. Trancoso, J.-L. Larriba-Pey, B. Knighten, and Y. Won. Detailed characterization of a quad pentium pro server running tpc-d. In Proc. ICCD, Austin, USA, 1999.
- [7] S. Chen, P. B. Gibbons, and T. C. Mowry. Improving index performance through prefetching. In Proc. SIGMOD, Santa Barbara, USA, 2001.
- [8] G. P. Copeland and S. Khoshafian. A Decomposition Storage Model. In Proc. SIGMOD, Austin, USA, 1985.
- [9] R. Cornacchia, A. van Ballegooij, and A. P. de Vries. A case study on array query optimisation. In Proc. CVDB, 2004.
- [10] G. Graefe. Volcano - an extensible and parallel query evaluation system. IEEE Trans. Knowl. Data Eng., 6(1):120-135, 1994.
- [11] S. Manegold, P. A. Boncz, and M. L. Kersten. Optimizing Main-Memory Join On Modern Hardware. IEEE Transactions on Knowledge and Data Eng., 14(4):709-730, 2002.
- [12] G. Moerkotte. Small Materialized Aggregates: A Light Weight Index Structure for Data Warehousing. In Proc. VLDB, New York, USA, 1998.
- [13] G. Moore. Cramming more components onto integrated circuits. Electronics, 38(8), Apr. 1965.
- [14] S. Padmanabhan, T. Malkemus, R. Agarwal, and A. Jhingran. Block oriented processing of relational database operations in modern computer architectures. In Proc. ICDE, Heidelberg, Germany, 2001.
- [15] R. Ramamurthy, D. J. DeWitt, and Q. Su. A case for fractured mirrors. In Proc. VLDB, Hong Kong, 2002.
- [16] J. Rao and K. A. Ross. Making B+-Trees Cache Conscious in Main Memory. In Proc. SIGMOD, Madison, USA, 2000.
- [17] K. A. Ross. Conjunctive selection conditions in main memory. In Proc. PODS, Madison, USA, 2002.
- [18] A. Shatdal, C. Kant, and J. F. Naughton. Cache conscious algorithms for relational query processing. In Proc. VLDB, Santiago, 1994.
- [19] M. Stonebraker, J. Anton, and M. Hirohama. Extendability in POSTGRES. IEEE Data Eng. Bull., 10(2):16-23, 1987.
- [20] A. Wilschut, J. Flokstra, and P. Apers. Parallel Evaluation of Multi-Join Queries. In San Jose, USA, San Jose, CA, USA, May 1995.
- [21] J. Zhou and K. A. Ross. Buffering accesses to memoryresident index structures. In Proc. VLDB, Toronto, Canada, 2003.
- [22] J. Zhou and K. A. Ross. Buffering database operations for enhanced instruction cache performance. In Proc. SIGMOD, Paris, France, 2004.
