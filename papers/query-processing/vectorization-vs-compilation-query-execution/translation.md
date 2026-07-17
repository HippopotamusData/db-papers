---
paper_id: vectorization-vs-compilation-query-execution
title: Vectorization vs. Compilation in Query Execution
language: zh-CN
source: source.pdf
---

# Vectorization vs. Compilation in Query Execution（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者

Juliusz Sompolski（VectorWise B.V.）、Marcin Żukowski（VectorWise B.V.）、Peter Boncz（Vrije Universiteit Amsterdam）

Juliusz Sompolski 的这项工作是其在 Vrije Universiteit Amsterdam 撰写的硕士论文的一部分。Peter Boncz 同时仍任职于 CWI Amsterdam。

## 摘要

将数据库查询编译成可执行的（子）程序，相比传统解释执行有显著收益。许多此类收益，例如降低解释开销、改善指令代码局部性，以及提供使用 SIMD 指令的机会，此前已经可以通过把查询处理器重新设计为向量化执行模型获得。本文试图阐明：对于现代 CPU 上的分析型数据库工作负载，最先进的编译策略与向量化执行究竟是什么关系。

为此，我们在 Ingres VectorWise 数据库系统内部仔细考察向量化策略和编译策略在三类使用场景中的行为：Project、Select 和 Hash Join。一个发现是，编译应始终与块式查询执行（block-wise query execution）结合。另一项贡献是识别出三种“循环编译（loop-compilation）”不如向量化执行的情形。因此，为获得最优性能，应谨慎融合这两种策略：要么把向量化执行原则纳入编译后的查询计划，要么使用查询编译为向量化处理创建构建块。

## 1. 引言

数据库系统提供许多重要抽象，例如数据独立性、ACID 属性，以及在大量数据上提出声明式、复杂、即席查询的能力。这种灵活性意味着数据库服务器直到运行时才知道具体查询，因此传统系统通常使用解释引擎实现查询求值。解释引擎执行由 Scan、Join、Project、Aggregation 和 Select 等代数算子组成的计划；算子内部还包含表达式，例如 Join 和 Select 中使用的布尔条件、Project 中生成新列的计算，以及 Aggregation 中使用的 MIN、MAX 和 SUM 等函数。

大多数查询解释器遵循 Volcano 所描述的迭代器模型 [5]：每个算子实现由 `open()`、`next()` 和 `close()` 组成的 API；每次 `next()` 调用产生一个新元组；查询求值遵循“拉取”模型，从根算子向下递归调用 `next()` 遍历算子树，再把结果元组向上拉取。

一次一个元组（tuple-at-a-time）的模型会带来解释开销：系统花在求值查询计划上的时间，可能远多于真正计算查询结果的时间。此外，这种解释模型会妨碍现代 CPU 引入的高性能特性 [13]。真正完成工作的指令夹杂在解释代码和函数调用中，编译器和现代 CPU 因而难以利用深流水线与 SIMD 指令；要利用这些特性，工作指令应当在指令流中相邻并且彼此独立。

### 相关工作：向量化执行

MonetDB [2] 使用批量处理降低解释开销：每个算子完整处理其输入，然后才调用下一执行阶段。X100 项目 [1] 进一步改进了这一思想，后来演化为 VectorWise 的向量化执行。它是一种块式查询处理形式 [8]，其中 `next()` 返回的不是单个元组，而是一块元组，典型大小为 100 到 10000。向量化模型把数据表示成 CPU 易于访问的小型一维数组，即向量（vector）。

这种模型有两个效果。第一，花在解释逻辑上的指令比例按向量大小的倍数下降。第二，真正工作的函数通常在紧凑循环中处理一组值。编译器可以很好地优化这类循环，例如在有益时展开循环，并自动生成 SIMD 指令。现代 CPU 也善于执行这类循环：函数调用被消除，分支更容易预测，乱序执行往往会同时推进多个循环迭代，从而利用现代处理器的深流水线资源。已有研究表明，向量化执行可使数据密集型 OLAP 查询加速约 50 倍。

### 相关工作：循环编译

消除解释负面影响的另一种策略是即时查询编译（JIT query compilation）。查询处理器第一次收到查询时，把查询或其一部分编译为例程，随后执行该例程。在 Java 引擎中，可以生成新 Java 类，通过反射加载，再由虚拟机 JIT 编译 [10]。在 C 或 C++ 系统中，则生成源代码文本、编译、动态加载并执行。System R 最初跳过编译器而直接生成汇编，但这种方法不可移植，最终被放弃 [4]。

根据编译策略，生成代码可以求解整个查询，即“整体式（holistic）”编译 [7]，也可以只覆盖某些性能关键片段。已知采用编译的其他系统还有 ParAccel [9] 和当时刚发布的 HyPer [6]。本文把当时的主流做法概括为“循环编译”：它们通常尝试把查询核心编译为一个遍历元组的单一循环。与之相对，向量化执行把算子分解成多个基本步骤，每个基本步骤用独立循环执行，形成“多循环（multi-loop）”结构。

编译可以消除解释开销，并生成精简、对 CPU 友好的代码。本文把编译置于最有利的条件下，假定编译时间可以忽略。这对通常长时间运行的 OLAP 查询往往成立；Java JIT 和用于 C/C++ 的 LLVM 框架 [12] 也已经能以毫秒级延迟完成编译与链接。

### 路线图：向量化与编译

向量化表达式处理一个或多个输入数组，并把结果存入输出数组。即便 VectorWise 尽力保证这些数组驻留在 CPU 缓存中，这种物化仍会增加加载和存储工作。编译可以避免这些工作，让中间结果在表达式之间流动时保留在 CPU 寄存器中。此外，编译作为一种通用技术与具体执行策略正交，原则上可以改善任何执行策略。我们使用 VectorWise DBMS 考察三个能揭示编译与向量化关系的案例。VectorWise 的数据存储和查询求值以 X100 项目 [1] 为基础。

第 2 节讨论 Project 表达式计算。循环编译往往得到最佳结果，但这一结论依赖块式处理。因此，在一次一个元组的引擎中编译表达式虽然可能改善性能，却远达不到可能获得的收益。第 3 节讨论 Select：在求值合取谓词时，分支预测失败会伤害循环编译；向量化方法则可沿用文献 [11] 的思想，把求值布尔表达式时的控制依赖转换为数据依赖。第 4 节讨论大型哈希表探测，以 Hash Join 为例：循环编译在处理链表，也就是哈希桶链时，会被 CPU 缓存未命中阻塞。实验表明，使用向量化跟随桶链的混合方法最快，并且对键查找问题的不同参数更稳健。第 5 节给出结论。

## 2. 案例研究：Project

我们以 TPC-H Q1 中的表达式为灵感，使用以下简单的 Scan-Project 查询作为微基准：

```sql
SELECT l_extprice * (1 - l_discount) * (1 + l_tax)
FROM lineitem;
```

扫描的三个列都是精度为两位的 decimal。VectorWise 在内部把它们表示为整数，在此例中即把值乘以 100。扫描和解压后，系统根据实际值域选择能表示这些值的最小整数类型。计算表达式也采用相同原则：结果类型选择为不会溢出的最小宽度整数。对 TPC-H 而言，`l_extprice` 是 4 字节整数，另两列是一字节整数；加减仍产生一字节结果，二者相乘产生 2 字节整数；最后，4 字节整数与 2 字节整数相乘，产生 4 字节结果。

### 向量化执行

![算法 1：示例查询的向量化和编译实现。静态编译的 map primitive 覆盖操作、类型与输入形式组合；动态编译的 primitive 可承载任意复杂表达式。](assets/algorithm-01-project-vectorized-compiled.png)

VectorWise 在 Project 中把函数作为 map primitive 执行。算法 1 展示二元 primitive 的代码模式。`chr`、`sht`、`int` 和 `lng` 分别表示 1、2、4、8 字节整数；`idx` 是内部类型，用于表示数据列中的大小、索引或偏移，其实现采用所需宽度的整数。primitive 名称中的 `val` 后缀表示该参数是常量，而非列参数。VectorWise 为所需的操作、类型和参数模式组合预生成 primitive。支持 SQL 的全部函数约用 9000 行宏代码表达，展开后得到约 3000 个不同的 primitive 函数、20 万行代码以及一个 5 MB 的二进制文件。

一个声称支持 SIMD 的编译器理应能够向量化 map 函数中的简单循环。在 x86 系统上，gcc 4.5.1 通常可以做到，Intel 编译器 icc 则从不失败。一条 SSE 指令可以对 16 个一字节值做加减、把 8 个一字节整数相乘得到二字节结果，或者相乘 4 个四字节整数。因此，该表达式的 16 个元组可以用 8 条 SIMD 指令处理：一条 8 位加法、一条 8 位减法、两条产生 16 位结果的 8 位乘法，以及四条 32 位乘法。

这些指令都会存储一个结果；前两个操作各加载一个输入，因为另一参数是常量；后两个操作各加载两个输入。由此产生 22 次加载/存储，即 $2 \times 2 + 6 \times 3$。粗略估计需要 30 条指令；实际上还需类型转换、填充和循环指令，所以处理 16 个元组总计约 60 条指令。相比之下，不使用 SIMD 时，每次计算需要 4 条指令，即两次加载、一次计算和一次存储；单个元组共需 16 条指令，比 SIMD 多 4 倍以上。

图 1 的向量化 “SIMD” 和 “no-SIMD” 曲线改变向量大小来计算表达式结果。实验使用 2.67 GHz Nehalem 单核、64 位 Linux 和 12 GB RAM；编译器为 icc 11.0，显式关闭 SIMD 后得到 no-SIMD 代码。gcc 使用 `-O3`，icc 还使用 `-xSSE4.2 -mp1 -unroll`。no-SIMD 向量化代码确实约比 SIMD 慢 4 倍。随着向量增大，解释开销持续下降，直到向量大小约为一千；向量超过 L1 和 L2 缓存后，缓存未命中又使性能下降，这一趋势已在文献 [13, 1] 中详细说明。

### 编译执行

算法 1 下半部分展示了 VectorWise 修改版可以即时生成的编译代码：它把向量化与编译结合起来。这种组合本身并不新鲜，即文献 [1] 的 compound primitive。结果类似 HIQUE [7] 这类整体查询编译器为 Scan-Project 计划生成的代码，只是整体编译器还会加入 Scan 代码。如果假定 HIQUE 使用简单的内存存储系统，并把 `l_tax` 等列视为列式表中的指针，那么算法中的 `c000()` 正是循环编译策略的产物。

编译方式的主要收益是消除中间加载和存储。向量化方式每个元组需要 22 次加载/存储，而编译方式只保留最底层的三次加载和最顶层的一次存储。比较两者时，结果却令人意外：向量化版本显著更快，约为 2 cycles/tuple，而普通编译版本约为 4 cycles/tuple。检查生成代码后发现，icc 在生成 SIMD 时把所有计算都对齐到最宽单位，即 4 字节整数，因而丧失了一字节和二字节 SIMD 操作的机会。这可以视为编译器缺陷或次优选择。

为展示编译本来可以达到的性能，我们重新实验，并假定 `l_extprice` 能装入 2 字节整数，对应图 1 中的 “SIMD-sht” 曲线。此时编译版本超过向量化执行，符合 Project 任务的一般预期。另一个观察是，编译后的 map primitive 对缓存大小较不敏感，只对 L2 而非 L1 敏感，因此混合的向量化/编译引擎可以使用更大的向量。

### 一次一个元组的编译

图 1 中的黑色星形和菱形表示 primitive 一次只处理一个元组。这里把未编译策略称为 interpreted。像 MySQL 这样整个迭代器接口都是 tuple-at-a-time 的引擎，每个时刻只有一个元组可操作，因此只能使用这类函数。概念上，这些 primitive 很接近算法 1 中向量大小 `n=1` 的函数，但不含 `for` 循环；为了公平，实验单独实现它们，避免循环本身的开销。

实验表明，如果在不打破 tuple-at-a-time 算子 API 的情况下给 MySQL 一类引擎加入编译，表达式计算可加速约 3 倍，从 23 cycles/tuple 降至 7 cycles/tuple。但绝对性能仍明显低于块式处理的 1.2 cycles/tuple，原因主要是无法利用 SIMD，同时每个元组一次的虚方法调用会阻碍 CPU 跨元组推测执行。更糟的是，在 tuple-at-a-time 的 OLAP 查询求值中，表达式 primitive 只占总时间很小一部分，不足 5% [1]，大部分工作耗在 tuple-at-a-time 算子 API 上。因此，如果不改变引擎一次一个元组的本质，仅使用编译带来的总体收益最多只有几个百分点，价值值得怀疑。

![图 1：Project 微基准中编译、向量化和 SIMD 的不同组合；SIMD-sht 曲线规避了 icc SIMD 代码生成中的对齐次优问题。](assets/figure-01-project-microbenchmark.png)

## 3. 案例研究：Select

第二个微基准考察以下合取选择：

```sql
WHERE col1 < v1 AND col2 < v2 AND col3 < v3
```

![算法 2：小于号选择 primitive 的两种实现。算法返回所选元素数量；VectorWise 根据观察到的选择率动态选择有分支或无分支版本。](assets/algorithm-02-select-primitives.png)

算法 2 的选择 primitive 生成条件为真的位置索引向量，即 selection vector。选择 primitive 也可接收 selection vector 参数，只求值该向量所指位置上的元素；事实上，其他 primitive 同样能处理 selection vector，只是与实验无关的代码片段省略了这一参数。向量化合取把多个选择 primitive 串联：前一个 primitive 的输出 selection vector 成为下一个的输入，后续条件只在原始向量逐渐缩小的子集上求值。因此，合取仍是惰性求值，只处理通过先前条件的元素。

每个条件都可用两种选择 primitive 实现。朴素的有分支实现惰性求值条件，任一谓词失败时立即跳出。若条件选择率既不很低也不很高，CPU 分支预测器便难以正确猜测分支结果，无法用有用的后续代码填满流水线，性能因而受损。文献 [11] 表明，选择代码中的分支，即控制依赖，可以转换为数据依赖以获得更好性能。

算法 2 的 `sel_lt` 函数包含这两种方法。无分支 primitive 对每个输入位置先执行 `res[j] = i`，再只用谓词真假增加 `j`；若存在输入 selection vector，则读取并写回其中的原始位置。有分支版本只在谓词为真时写入并递增 `j`。VectorWise 根据观察到的选择率选择有分支或无分支策略，性能因而达到图 2 两条向量化曲线中的较小值。系统甚至会动态重排合取谓词，让选择性最强的谓词最先求值。

![算法 3：合取选择的四种编译实现。单循环无法在不急切执行其余操作的同时完全消除分支，四种实现分别权衡分支与急切计算。](assets/algorithm-03-compiled-select.png)

循环编译的自然写法是在一个循环中使用 `if (p1 && p2 && p3)`。这可以短路求值，避免不必要的工作，但在中等选择率下会产生难预测分支。算法 3 比较四种生成方式：三个条件都使用短路分支；前两个使用分支而第三个转为无分支计数；只对第一个使用分支而后两个用布尔与；以及三个条件全部计算后用布尔与合并。最后一种近似为：

```c
for (idx i = 0, j = 0; i < n; ++i) {
    result[j] = i;
    j += (col1[i] < v1) & (col2[i] < v2) & (col3[i] < v3);
}
```

实验中，`col1`、`col2` 和 `col3` 都是整数列，`v1`、`v2` 和 `v3` 是用于控制各条件选择率的常量。三个分支的选择率保持相同，因此每个条件的选择率等于总体选择率的立方根；总体选择率从 0 变化到 1。实验处理 1K 个输入元组。

![图 2：合取选择条件的总 cycles、分支预测失败次数与选择率的关系。](assets/figure-02-select-case.png)

图 2 表明，编译后的合取 Select 不如纯向量化方法。惰性编译程序略优于有分支的向量化版本，但在中等选择率下，有分支版本远非最佳。问题的实质在于，单一循环不能同时做到两点：把所有控制依赖转换为数据依赖，又避免不必要的条件求值。若像算法 3 的 compute-all 方法那样消除所有分支，就必须始终求值全部条件，即便前一条件已经失败，仍会浪费资源。

可以尝试混合方法：前几个谓词使用分支，剩余谓词使用数据依赖。这些方法在某些选择率区间更好，但仍保留基本问题；当分支谓词之后的选择率约为 50% 时，其表现最差。多循环 selection vector 则能同时获得无分支求值与逐步缩小候选集合的收益。

## 4. 案例研究：Hash Join

最后一个微基准考察 Hash Join：

```sql
SELECT build.col1, build.col2, build.col3
FROM probe, build
WHERE probe.key1 = build.key1
  AND probe.key2 = build.key2;
```

我们关注键由两个整数列构成的等值连接，因为复合键对向量化执行器更具挑战。讨论假设使用 VectorWise 所采用的简单 bucket chaining，如图 3 所示。键被哈希到数组 `B` 的桶上；`B` 的大小 `N` 是 2 的幂。每个桶保存 value space `V` 中某个元组的 offset。`V` 可按 DSM 或 NSM 组织，VectorWise 两者都支持 [14]；其中保存 build 关系的值，以及实现桶链的 `next` offset。链长大于 1 可能来自哈希碰撞，也可能来自 build 关系中存在多个相同键的元组。

![图 3：VectorWise 使用的 bucket-chain hash table。图中 value space V 为 DSM，每个属性单独成列；也可改用按元组存储的 NSM。](assets/figure-03-bucket-chain-hash-table.png)

### 向量化哈希探测

由于篇幅限制，算法 4 只讨论 probe 阶段，代码采用 DSM 数据表示，并聚焦每个 probe 元组至多命中一次的场景，这在通过外键参照约束连接的关系中很常见。

![算法 4：向量化 hash probing 实现，包括哈希、候选位置查找、键复核、桶链推进以及非键属性获取。](assets/algorithm-04-vectorized-hash-probe.png)

探测首先按列使用 map primitive 计算键的哈希值。`map_hash_T_col` 把类型为 `T` 的每个键哈希为 `lng` 长整数。若为复合键，则使用 `map_rehash_lng_col_T_col` 逐列细化哈希值，每次传入已有哈希值和下一键列。随后用按位与 map primitive 计算桶号：`H & (N - 1)`。

读取已算出桶的链头位置时，系统使用专用 primitive `ht_lookup_initial`。它类似选择 primitive：创建 selection vector `Match`，保存桶号向量 `H` 中找到候选的位置；同时用哈希表中候选元组的位置填充 `Pos`。若桶中的 offset 为 0，说明哈希表没有该键；对应元组在 `Pos` 中存 0，也不会进入 `Match`。

得到可能匹配的元组索引后，下一步是检查键值是否真正相等。专用 map primitive `map_check` 把按 offset 取值与不等测试合并。与哈希过程类似，复合键由 `map_recheck` 支持；它把前一次检查的布尔输出作为额外的第一个参数。得到的布尔值标记检查失败的位置。随后用 `sel_nonzero` 选择这些位置，覆盖 `Match`，使其仅保留需要推进到桶链下一位置的 probe。

`ht_lookup_next` 对 `Match` 中每个 probe 元组，把 `Pos` 推进到 `V` 的桶链下一位置；它还删除推进后 `Pos` 为 0 的位置，从而处理链尾。循环在 `Match` 为空时结束：一种原因是到达链尾，`Pos` 元素为 0，表示未命中；另一种原因是检查成功，`Pos` 指向 `V` 中的命中位置。最终用 `sel_nonzero` 选择 `Pos` 中确实命中的元素，得到 `Hits`。`Pos` 与 `Hits` 构成用于 fetch 的 pivot vector；系统随后对每个结果列使用一个 fetch primitive，从 build value area 取出非键属性。

这种向量化探测同时维护多个待探测键，并把不同键的链式访问交织在一起。当一个键等待内存时，其他键仍可推进，从而提供更多内存级并行性。

### 部分编译

向量化哈希有三处可应用编译。第一，把 hash、rehash、bitwise-and 和 bucket fetch 的整个序列编译为一个 primitive。第二，把检查、复合键的逐列 re-check，以及 `select > 0` 合并为一个选择 primitive。调优良好的哈希表中，键检查的选择率约为 75%，因此这里只需无分支实现。这两项重复了前面 Project 和 Select primitive 的编译收益，原文没有再给出代码。

第三处机会是 fetch 代码：可以生成 compound fetch primitive，根据位置向量一次获取多个列。这一收益尤其出现在 NSM 组织的 `V` 上。向量化方式一次处理一列，因此结果有几列，就会对 NSM value space 做几轮随机访问；此处为三轮。在有效向量大小下，随机访问数量肯定超过 TLB 容量，甚至可能超过缓存行数量。前一轮访问的页和缓存行会在下一轮到来前被逐出，造成 TLB 和缓存抖动。编译后的 fetch 在同一位置一次取出全部列，因而有更好的数据局部性。

![图 4：从哈希表获取不同数量的列时，每元组 cycles 与 TLB miss 总数。](assets/figure-04-hash-table-fetching.png)

图 4 表明，普通向量化哈希下 NSM 与 DSM 性能相近，但编译使 NSM 明显优于 DSM。输出列越多，一次从同一 NSM 元组取全多列的收益越明显，TLB miss 也显著更少。

### 完整循环编译与并行内存访问

也可以像 HIQUE [7] 那样创建整个 Join 的循环编译版本。算法 5 展示并测试了它的 hash probe 部分：遍历 probe key；对每个键读取相应桶；沿桶链逐项检查键是否相等；若相等，则取出所需结果列。

![算法 5：完整循环编译的 hash probing。对每个 NSM 元组读取 B 中的桶，沿 V 中的链检查，并在匹配时获取结果。](assets/algorithm-05-compiled-hash-probe.png)

主存延迟长期停留在约 100 ns，而 cache line 粒度必须维持在 64 字节，因此现代硬件的内存带宽不能再简单用二者相除得到。单个 Nehalem 核凭借顺序访问时的 CPU 自动预取，可获得约为 $0.64\ \mathrm{GB/s}$ 十倍的带宽。性能关键在于始终保持多个未完成的内存请求。

随机访问很难做到这一点，但深流水线、乱序执行的 CPU 可以提供帮助：若某次 load 停顿，CPU 可能向上游指令推测执行并遇到更多 load。Intel Nehalem 最多能维持四个 outstanding load，因而理论上把带宽提高四倍。不过成功与否没有保证，因为 CPU 的指令推测窗口有限，效果取决于分支预测，而且只有相互独立的上游指令才能执行。对这种情形，便于推测的代码比手工 prefetch 更有效；手工预取通常只带来较小改善，并且难以针对多个平台调优和维护。

问题的关键在于，向量化 fetch primitive 是由彼此独立的 load 组成的紧凑循环，天然能填满 CPU 支持的 outstanding load；部分编译版本也一样。完整编译的 hash probe 在跟随桶链时却可能停滞。只有当 CPU 能跨多个 probe 元组推测执行，即并发执行外层 `for` 循环的多个迭代时，它才表现良好。这又取决于分支预测器把 `while(pos...)` 预测为 false；当连接键分布没有碰撞时通常如此。

如果存在碰撞，或 build 关系含多个相同键，分支预测器会让执行停留在 `while` 循环中。下一位置 `pos = V.next[pos]` 依赖当前 cache/TLB miss 的返回值，CPU 因而只能等待一个 outstanding memory request `V[pos]`，无法推进到下一个 probe 元组。文献 [3] 在 Hash Join 显式预取的语境下描述了类似现象。最坏情况下，这一效应会使完整编译哈希比向量化哈希慢 4 倍。

### 实验

图 5 比较向量化、完整编译和部分编译方法，并分别采用 DSM 和 NSM 表示哈希表 value space `V`。实验改变哈希表大小、选择率（probe key 命中的比例）和桶链长度；默认值分别为 16M、1.0 和 1。

![图 5：哈希表探测。左：value space V 大小变化；中：probe 命中率变化；右：桶数组 B 相对 V 的大小变化，即链长变化。](assets/figure-05-hash-probing.png)

左图显示，哈希表增大时，每元组性能下降；原因是 cache 和 TLB miss，且 DSM 局部性弱于 NSM。中图显示，命中率提高时成本上升，主要因为生成元组所需的 fetch 工作增加；编译后的 NSM fetch 表现最佳。右图显示，随着链长增加，完整编译的 NSM 版本受损最重，因为它无法获得并行内存访问；在 bucket 数从表大小的 2 倍缩小到 $1/32$ 时，图中完整编译曲线达到 4419 和 5293 cycles/tuple 的极端值。

总体最佳方案是部分编译 NSM：它通过编译后的多列 fetch 获得高效率；在复合键情况下，高效的键检查和哈希也有较小贡献；同时在 lookup、fetch 和 chain-following 中保留向量化带来的并行内存访问。

## 5. 结论

对于希望提高数据库引擎计算性能的架构师，表面上似乎需要在“向量化表达式引擎”和“引入表达式编译”之间选择。向量化是一种块式处理；如果系统现有的算子 API 一次处理一个元组，那么需要修改的远不止表达式计算，还包括全部查询算子和存储层。若目标是高计算性能，这种深层改造无法避免，因为实验已经表明：继续遵守 tuple-at-a-time 算子 API 时，仅加入表达式编译只能带来边际改善。

我们的核心结论是，不必在编译和向量化之间二选一；两者结合才能得到最佳结果。本文展示了近来提出的循环编译技术可能不如纯向量化，原因包括向量化具有更好的 SIMD 对齐、避免分支预测失败的能力，以及并行内存访问。因此，在这些情况下，编译应拆成多个循环，并物化中间向量结果。本文也指出了解释式但向量化的执行策略所具有、而编译很难实现的优化机会，例如动态选择谓词求值方法和动态调整谓词求值顺序。

三个案例分别体现这一点。Project 中，编译通常能减少中间物化并保留寄存器值，但必须采用块式处理并生成正确的 SIMD。Select 中，向量化 selection vector 能避免中等选择率下的分支预测失败。Hash Join 中，向量化的多路桶链跟随能够缓解随机内存访问延迟。可以把向量化原则纳入编译后的查询计划，也可以用查询编译生成向量化处理的构建块。

简单编译策略并不足够。最先进的算法可能对问题进行复杂变换，有时需要运行时自适应，并且始终依赖细致调优。为达到同等成熟度，基于编译的查询引擎需要增加大量复杂性，甚至可能比解释式引擎更复杂。

向量化执行本身是迭代器模型的演进；在此基础上加入编译，可以进一步演进为更高效、更灵活的方案，而无需彻底改变 DBMS 架构。它既能获得很好的性能，又能维持清晰的模块化、简化测试，以及便于跟踪性能和质量；这些都是软件产品的关键属性。

## 参考文献

- [1] P. Boncz, M. Zukowski, and N. Nes. MonetDB/X100: Hyper-Pipelining Query Execution. In Proc. CIDR, Asilomar, CA, USA, 2005.
- [2] P. A. Boncz. Monet: A Next-Generation DBMS Kernel For Query-Intensive Applications. Ph.d. thesis, Universiteit van Amsterdam, Amsterdam, The Netherlands, May 2002.
- [3] S. Chen, A. Ailamaki, P. B. Gibbons, and T. C. Mowry. Improving hash join performance through prefetching. In Proc. ICDE, Boston, MA, USA, 2004.
- [4] D. Chamberlin et al. A history and evaluation of System R. Commun. ACM, 24(10):632-646, 1981.
- [5] G. Graefe. Volcano - an extensible and parallel query evaluation system. IEEE TKDE, 6(1):120-135, 1994.
- [6] A. Kemper and T. Neumann. HyPer: Hybrid OLTP and OLAP High Performance Database System. Technical report, Technical Univ. Munich, TUM-I1010, May 2010.
- [7] K. Krikellas, S. Viglas, and M. Cintra. Generating code for holistic query evaluation. In ICDE, pages 613-624, 2010.
- [8] S. Padmanabhan, T. Malkemus, R. Agarwal, and A. Jhingran. Block Oriented Processing of Relational Database Operations in Modern Computer Architectures. In Proc. ICDE, Heidelberg, Germany, 2001.
- [9] ParAccel Inc. Whitepaper. The ParAcel Analytical Database: A Technical Overview, Feb 2010. http://www.paraccel.com.
- [10] J. Rao, H. Pirahesh, C. Mohan, and G. M. Lohman. Compiled Query Execution Engine using JVM. In Proc. ICDE, Atlanta, GA, USA, 2006.
- [11] K. A. Ross. Conjunctive selection conditions in main memory. In Proc. PODS, Washington, DC, USA, 2002.
- [12] The LLVM Compiler Infrastructure. http://llvm.org.
- [13] M. Zukowski. Balancing Vectorized Query Execution with Bandwidth-Optimized Storage. Ph.D. Thesis, Universiteit van Amsterdam, Sep 2009.
- [14] M. Zukowski, N. Nes, and P. Boncz. DSM vs. NSM: CPU Performance Tradeoffs in Block-Oriented Query Processing. 2008.
