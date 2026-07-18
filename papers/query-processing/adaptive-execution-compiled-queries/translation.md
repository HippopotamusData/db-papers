---
paper_id: adaptive-execution-compiled-queries
title: Adaptive Execution of Compiled Queries
language: zh-CN
source: source.pdf
---

# Adaptive Execution of Compiled Queries（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

André Kohn，Viktor Leis，Thomas Neumann

慕尼黑工业大学（Technische Universität München），`{kohna,leis,neumann}@in.tum.de`

## 摘要

把查询编译成机器码是一种非常高效的查询执行方式。编译中一个经常被忽视的问题，是生成机器码本身所需的时间。即使采用 LLVM 这样的快速编译框架，为复杂查询生成机器码也往往需要数百毫秒。对于需要执行许多复杂但很快就能完成的查询的工作负载，这样的时延会成为严重劣势。为解决这一问题，我们提出一种自适应执行框架（adaptive execution framework），它能从解释执行动态切换到编译执行。我们还提出一个面向 LLVM 的快速字节码解释器；它无需把查询昂贵地翻译成机器码即可执行查询，从而显著降低查询时延。自适应执行具有细粒度，可以让同一查询的不同代码路径采用不同执行模式。实验表明，该方法在多种设置中都能达到最优性能：对小数据集提供低时延，对大数据规模提供最大吞吐量。

## I. 引言

将查询编译为机器码，已经成为一种非常流行的查询执行方法。越来越多的商业系统采用编译，包括 Hekaton [1]、[2]、MemSQL [3]、Spark [4] 和 Impala [5]；研究项目中也有 HIQUE [6]、HyPer [7]、DBToaster [8]、Tupleware [9]、[10]、LegoBase [11]、ViDa [12]、Vodoo [13]、Weld [14] 以及 Peloton [15]、[16]。编译的主要优势当然是效率。通过为给定查询生成代码，编译避开了传统执行引擎的解释开销，从而取得高得多的性能。

生成机器码有一个显而易见的缺点：编译需要时间。以下面的元数据查询为例：

```sql
SELECT c.oid, c.relname, n.nspname
FROM pg_inherits i
JOIN pg_class c ON c.oid = i.inhparent
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE i.inhrelid = 16490
ORDER BY inhseqno;
```

这个查询只接触很少量的元组，因此执行时间可以忽略不计，在 HyPer 中不足 1 毫秒。然而，HyPer 在执行它之前必须先把它编译成机器码。启用优化时，LLVM 编译该查询需要 54 毫秒。换言之，编译所花时间是执行时间的 50 倍。假设某个工作负载频繁执行类似查询，那么 98% 的时间都会浪费在编译上。而且这个查询还算相当小；更大查询的编译时间会高得多。例如，最大的 TPC-DS 查询编译时间接近 1 秒。当然，数据规模很大时编译确实值得，因为生成的代码比解释执行高效得多。

本文关注把查询编译为 LLVM IR（Intermediate Representation，中间表示）的数据库系统；随后，LLVM 编译器后端再把 LLVM IR 编译为机器码。与编译到 C/C++ 相比，这种方法产生的机器码质量相同，却能把编译时间降低一个数量级 [7]。对某些工作负载而言，LLVM 编译器的编译时间可能足够低，例如由长时间运行的即席查询或预编译存储过程组成的负载。但对其他应用而言，漫长的编译时间仍是严重问题。

上面的示例查询是 PostgreSQL 管理工具 pgAdmin 发出的查询之一。启动时，pgAdmin 会发送数十条复杂查询，其中最多包含 22 个连接；所有这些查询都只访问很小的元数据表。编译这些查询会造成可感知且没有必要的延迟。缓存机器码（例如去掉常量之后再缓存）或许能改善后续执行，却不能改善用户的首次体验。更一般地说，人类的感知阈值低于 1 秒，因此编译附加的时延会使交互式应用的用户体验变差。最后，商业智能工具偶尔会生成极大的查询，例如 1 MB 的 SQL 文本；标准编译器事实上无法编译这种查询。

对上述工作负载而言，基于编译的引擎所提供的用户体验，可能比传统的解释式引擎（例如 Volcano 风格执行）还差。因此，根据查询不同，有时我们会偏好编译式引擎，有时又会偏好解释式引擎。然而，在同一系统中实现两个查询引擎不仅工作量不成比例，还可能因为细小的语义差异引入隐蔽 bug。本文改为提出一种自适应执行框架：它原则上建立在单一的编译式查询引擎之上，同时集成解释技术来降低查询时延。设计的关键组件是：（i）针对数据库查询特化的快速字节码解释器；（ii）精确跟踪查询进度的方法；（iii）在解释与编译之间动态切换的机制。这种动态方法不依赖查询优化器出了名地不准确的代价估计，却能兼得两者之长：短查询获得低时延，长时间运行的查询获得高吞吐。

我们的自适应执行框架可以直接应用于许多基于编译的系统。此外，该方法不具侵入性，也就是说，无需重写查询引擎本身。系统仍会为到来的查询生成 LLVM IR，但不会立刻把它编译成机器码；它改用运行时反馈，自适应地保证查询尽可能快地执行，并且不依赖查询优化器的代价估计。

![基于编译的查询引擎架构](assets/precise-manual-figure-01-architecture.png)

**图 1：基于编译的查询引擎架构。**

图 1 展示了基于编译的查询引擎架构以及各阶段在示例中的耗时。

## II. 通过编译执行查询

关系数据库系统执行一条 SQL 查询，需要经历图 1 所示的复杂多阶段过程。SQL 文本首先由“解析器”（Parser）解析为抽象语法树（AST）。随后，“语义分析”（Semantic Analysis）把 AST 转换成未经优化的查询计划，再由“优化器”（Optimizer）对它进行优化。传统引擎直接执行这个查询计划，例如采用 Volcano 风格的迭代。与之不同，基于编译的引擎会把优化后的查询计划转换为某种命令式、低层、机器无关的语言（“代码生成”，Code Generation），再次进行优化（“LLVM 优化 Pass”，LLVM Opt. Passes），最后编译成机器码（“LLVM 优化编译”，LLVM Comp. Optimized）。有些基于编译的系统在关系代数和低层命令式表示（本文中是 LLVM IR）之间设有多个中间语言。这并不真正影响本文的讨论，因为机器码生成通常比这些附加阶段耗时更长。下面我们将说明把查询编译为机器码的编译式查询引擎所面临的主要挑战。

### A. 延迟与吞吐的权衡

本文以 HyPer 为基础；HyPer 通过把查询编译为 LLVM IR 来执行查询。LLVM 是一种广泛使用的开源编译框架，支持提前编译和即时编译。图 1 给出了系统使用 LLVM 执行 TPC-H 查询 1 时各阶段的耗时。数字表明，大多数时间花在最后两个 LLVM 编译阶段，即“LLVM 优化 Pass”和“LLVM 优化编译”；此前的代码生成、查询优化和分析阶段可以忽略。因此，要优化整体时延，我们必须把重点放在降低机器码生成的成本，或者彻底避开机器码生成。

编译时间和执行时间会随编译器及优化设置而变化。图 2 给出了不同设置下，TPC-H 查询 1 在 scale factor 1 上的编译时间和执行时间。[^1] 如图所示，LLVM 生成的查询吞吐与手写 C++ 查询相近，而所需的编译时间低得多。[^2] 禁用全部 LLVM 优化会显著缩短编译时间，代价是执行时间略有增加。图中还包括直接解释 LLVM IR 模块的 LLVM 内置解释器（“LLVM IR”），以及本文将在第 IV 节介绍的字节码解释器（“LLVM bytecode”）。这些数字表明，只有解释器能够实现极低的时延；当然，这要以牺牲吞吐为代价。

![不同执行模式的编译时间与执行时间权衡](assets/precise-manual-figure-02-latency-throughput.png)

**图 2：TPC-H 查询 1 在 scale factor 1 上，不同执行模式的单线程查询编译时间与执行时间。**

图 2 清楚显示了时延和吞吐之间的权衡。对长时间运行的查询，通常最好以最高优化等级编译成机器码；对很快的查询，解释器更合适。未优化机器码介于两种极端之间，提供了良好的折中。SQL 查询的复杂度和所访问的数据量不同，最优执行方案也不同。因此，本文提出在 LLVM 字节码解释器和带可选优化 Pass 的 LLVM 编译器之间切换，从而动态调整查询执行。

另一个相关方面是，一条查询的所有代码路径并非同等重要。例如，对于一个由很小的 build 关系和很大的 probe 关系构成的内存哈希连接，最好解释执行哈希表构建代码，却编译哈希 probe 代码。因此，查询的不同部分可能分别适合不同执行模式。还应注意，编译器是单线程的，而现代查询引擎通常是多线程的。也就是说，编译进行时，除一个 CPU 核之外的所有核都处于空闲；解释器却可以更早利用全部可用核心。

### B. 编译大型查询

TPC-H 查询 1 的 59 毫秒编译时间，对某些应用来说可能还算足够低。然而，从生成代码的规模来看，查询 1 仍然相当小；更大查询需要长得多的编译时间。最大的 TPC-H 查询和最大的 TPC-DS 查询，编译时间分别为 146 毫秒和 911 毫秒。

此外，我们还观察到，对特别大的机器生成查询，例如商业智能工具产生的查询，编译时间会随着查询规模超线性增长。因此，编译时间可能变得长得多，查询甚至可能根本无法完成，参见第 V-E 节。尽管这类查询并不常见，任何工业级系统都必须能够执行它们，尤其是因为传统数据库系统没有这个问题。

[^1]: 实验设置见第 V 节。
[^2]: 手写版本没有实现溢出检查，这解释了它的运行时间为何略快。

## III. 自适应执行框架

我们认为，基于编译的引擎应当支持图 3 所示的三种执行模式。字节码解释能让快速查询获得极低时延，未优化机器码为中等规模查询提供良好折中，优化机器码则为长时间运行的查询提供峰值吞吐。一个支持这些模式的系统，只要为给定查询选中正确模式，就能提供最优的用户体验。

决定采用哪种执行模式的一种可能办法，是依赖查询优化器给出的代价估计。然而，基数估计和代价模型往往都不准确 [17]、[18]，可能导致系统进行不必要的编译，或让长时间运行的查询一直由解释器执行。错误决策的后果可能非常严重：字节码解释器可能慢一个数量级，而编译很容易耗费数百毫秒。此外，编译本身是单线程的，因此预先编译会让其他所有线程空闲到编译结束。

我们的自适应执行方法是动态的，因为它不在执行前决定执行模式。相反，我们总是让每条查询先使用字节码解释器和全部可用线程开始执行。然后，系统监控执行进度，判断进行未优化编译或优化编译是否有利。若有利，后台线程开始编译，其他线程继续解释执行。编译完成后，所有线程迅速切换到已编译机器码。由于所有执行模式都在相同数据结构上执行语义相同的指令，切换执行模式时不会丢失工作；机器码可以从解释器停止之处继续。

我们的方法是细粒度的。进度跟踪和是否编译的决策不针对整条查询，而针对具体的查询 pipeline，例如代价高昂的哈希表 probe。因此，不同 pipeline 可以采用不同执行模式。这样做可能优于任何静态的预先决策，因为只有查询中代价很高的部分才会进行优化编译。正如后文所示，在多线程设置中，让同一 pipeline 先后运行全部三种模式也往往有利。

实现这种动态方法需要若干机制，下面三个小节将分别介绍。第一，必须能够跟踪 pipeline 的进度。第二，必须能在不丢失任何工作的前提下，从字节码执行切换到编译执行。最后，还需要一个模型来判断切换到编译是否有利。

![三种执行模式及其编译时间](assets/precise-manual-figure-03-execution-modes.png)

**图 3：三种执行模式及其编译时间。**

图 3 把自适应执行放入编译流程：规划和代码生成之后，同一份 LLVM IR 可以转换为字节码、未优化 x86 机器码，或者经过 LLVM Pass 后转换为优化的 x86 机器码。

### A. 跟踪查询进度

图 4 展示了一个示例查询计划的基本代码结构，以及编译器为它生成的代码结构。入口点是 `queryStart` 函数；调用该函数就会执行查询。`queryStart` 主要负责调用 C++ 初始化代码并启动查询中的各条 pipeline。它的体积可能相当大，但因为这些代码只执行一次，编译它永远得不偿失。查询中真正依赖数据的部分总是在 worker 函数中执行；每个 worker 函数计算一条 pipeline 的结果。图 4 的查询计划包含三条 pipeline，分别由 `workerA`、`workerB` 和 `workerC` 三个 worker 函数处理。

![查询计划翻译为伪代码的结构](assets/precise-manual-figure-04-query-plan-translation.png)

**图 4：查询计划向伪代码的翻译。`queryStart` 是主函数，三个查询 pipeline 分别转换为 worker 函数；左下角显示每个 pipeline 的工作被分成小 morsel 并动态调度到线程。**

选择这种代码结构时，考虑了多核并行。每个 worker 函数需要两个参数：状态，例如查询处理中间哈希表；以及一个 morsel，用来确定要处理的值域。每次调用一个 worker 函数时，该调用只接收并处理一个 morsel。查询内并行通过多个 worker 线程运行同一个 worker 函数来实现，但每个线程拿到不同且不重叠的 morsel，例如某个关系的不同区间。在我们的并行框架中，线程使用工作窃取；每次调用处理的范围相当小，例如 10,000 个元组，从而避免线程负载不均。Morsel-wise（或 block-wise）执行已被认定为内存数据库中一种快速的算子内并行模型 [19]、[20]，而且它恰好也是监控查询进度的合适粒度。

每处理完一个 morsel，worker 线程本来就要查询一次工作窃取数据结构。我们在这一位置加入少量监控代码和计时信息，记录每条 pipeline 已处理多少 morsel。此外，每当 pipeline 开始时，我们还记录总工作量，例如待扫描关系或哈希表的大小。这些信息使我们能够监控查询进度。

![解释执行到编译执行的在线切换](assets/precise-manual-figure-05-switching-execution.png)

**图 5：从解释执行在线切换到编译执行；每个 morsel 都会运行 dispatch 代码。**

### B. 在执行模式间切换

在自适应执行中，一个 morsel 表示查询引擎能够处理的最小工作单元。除了用于跟踪查询进度，morsel 也是在不同执行模式间动态切换的关键机制。处理一个 morsel，就是读取指定范围的值，并操作哈希表之类的共享状态。把范围和共享状态同时作为 worker 函数的输入参数，可以简化生成的代码，并使不同 morsel 的处理彼此独立。

这种独立性允许系统为一个 worker 函数选择执行模式。让字节码解释器处理所有 morsel、每隔一个 morsel、或者一个 morsel 都不处理，再让已编译 worker 函数处理其余 morsel，在语义上彼此等价。我们还可以用不同优化等级反复编译同一个 worker 函数，逐步提高该函数的吞吐。这里切换和编译决策的对象始终是 pipeline 对应的 worker 函数；基本块并不是可以独立选择执行模式的单位。

图 5 展示了如何把这一概念集成到 morsel 驱动的并行框架中。系统不再用内存地址标识 worker 函数，而是引入额外的 handle 间接层。handle 对象存放同一函数的多种变体。对每一个 morsel，系统选择当时最快的可用表示：它可能是字节码，也可能是已编译机器码的地址。因此，改变执行模式只需设置 handle 对象中的函数指针。设置之后，所有剩余 morsel 都会用新变体处理，从而实现执行模式之间的无缝切换。

### C. 选择执行模式

前面已经表明，更高的查询吞吐要以更高的查询时延为代价。因此，我们总是让每个 worker 函数先用低时延字节码解释器开始执行，只有在确有必要时才编译。但这引出一个问题：怎样判断编译有利？为此，我们针对每条 pipeline 持续评估三个选项：

1. 沿用当前执行模式；
2. 不使用编译器优化，把 worker 函数编译为机器码，即未优化模式；
3. 使用编译器优化，把 worker 函数编译为机器码，即优化模式。

若不编译，剩余时间完全由当前处理速度，也就是字节码解释器的速度决定。每个 worker 线程完成一个 morsel 时，系统计算其局部元组处理速率，从而分别跟踪各线程的速度。根据当时始终已知的 pipeline 剩余元组数和活跃 worker 线程数，很容易外推 pipeline 的总持续时间。动态增大 morsel 大小还能得到更多早期采样点，使外推更加精细。

若选择编译，pipeline 的剩余时间还取决于预期编译时间，以及已编译代码预计能快多少。此外还必须考虑：编译进行时，pipeline 可以在多线程环境中继续执行，使用字节码或已经存在的优化代码。因此，我们必须计算在编译期间其余线程能够处理多少元组，再外推编译完成后处理剩余元组所需的时间。

![LLVM 指令数与编译时间的关系](assets/precise-manual-figure-06-llvm-compilation-time.png)

**图 6：TPC-H 与 TPC-DS 查询的 LLVM 优化/未优化机器码编译时间。**

worker 函数的编译时间和加速比取决于生成的查询计划，在系统中根据经验数据确定。图 6 表明，对全部 TPC-H 和 TPC-DS 查询，查询的 LLVM 指令数与编译时间高度相关。生成的计划包含 300 到 19,000 条指令；在这个范围内，我们观察到近似线性的编译时间。不同执行模式之间的加速比也使用经验数据，参见第 V-D 节。虽然准确预测查询加速比和编译时间一般很困难，自适应执行只需要粗略外推。

图 7 给出了比较不同执行模式的伪代码。令 $r_0$ 为各线程当前速率的平均值， $r_1$ 和 $r_2$ 为两种编译模式的估计速率， $c_1$ 和 $c_2$ 为其编译时间。剩余元组数为 $n$，活跃 worker 线程数为 $w$。三种选择的估计持续时间为：

$$
t_0 = \frac{n}{r_0 w}
$$

$$
t_1 = c_1 + \frac{\max(n - (w - 1) r_0 c_1, 0)}{r_1 w}
$$

$$
t_2 = c_2 + \frac{\max(n - (w - 1) r_0 c_2, 0)}{r_2 w}
$$

其中， $w-1$ 个未承担编译的线程在编译期间仍能处理数据。

```text
// f: worker function
// n: remaining tuples
// w: active worker threads
extrapolatePipelineDurations(f, n, w):
  r0 = avg(rate in threadRates)
  r1 = r0 * speedup1(f); c1 = ctime1(f)
  r2 = r0 * speedup2(f); c2 = ctime2(f)
  t0 = n / r0 / w
  t1 = c1 + max(n - (w - 1) * r0 * c1, 0) / r1 / w
  t2 = c2 + max(n - (w - 1) * r0 * c2, 0) / r2 / w
  switch min(t0, t1, t2):
    case t0: return DoNothing
    case t1: return Unoptimized
    case t2: return Optimized
```

**图 7：pipeline 持续时间的外推。**

为降低同步开销，只有一个 worker 线程执行外推。我们把第一次评估推迟 1 毫秒，以提高估计精度；之后每处理完一个 morsel 就重新评估。每次完成 morsel 后，该线程计算所有线程的平均处理速度，并比较不同执行模式的剩余处理时间。若切换到新执行模式看来有利，该线程就编译 worker 函数，并重置全部处理速率。这样，每条 pipeline 最终都可以切换到最快的执行模式。

## IV. LLVM 字节码解释器

如图 2 所示，即使不使用编译器优化，生成机器码也要花费不可忽略的时间。因此，解释器是本文设计中的关键组成部分。

LLVM 是为生成机器码而设计的编译框架，但它也包含一个解释器。这个解释器无需任何额外编译步骤，直接执行 LLVM IR。因此，把查询编译成 LLVM IR 的系统本可以使用这个解释器执行查询。然而，图 2 表明，LLVM 内置解释器极其缓慢，比对应机器码慢 800 倍以上。原因在于，LLVM IR 是为实现优化 Pass 而设计的通用格式。它在内存中采用基于指针的表示，便于代码变换，却对 cache 极不友好。此外，一条指令在执行时需要昂贵的运行时分派，因为不同操作数宽度，例如 8、16、32 和 64 位，共用一条指令，例如整数加法。

为使解释成为可行策略，我们把原生 LLVM IR 转换为一种优化的虚拟机（VM）字节码格式，以便高效得多地解释。这里必须解决两个关键挑战。第一，处理字节码的成本应当尽可能低，以减小解释开销。第二，必须能够高效地翻译为这种字节码。第二点尤其困难，因为活性分析之类的许多标准编译技术在最坏情况下具有超线性行为，会给极大查询带来不可接受的翻译时间。最后，VM 的行为必须与原生机器码 100% 一致，因为我们希望在解释执行的 VM 代码与原生机器码之间无缝切换。因此，我们开发了一种虚拟机：它大体遵循 LLVM 指令集，但以低成本解释为目标，并为常见结构提供额外功能。

### A. 虚拟机

我们的虚拟机是一台寄存器机。调用一个解释执行的函数时，系统分配一个寄存器文件，保存函数执行期间计算出的全部值。若可能，这一分配在栈上完成；寄存器文件太大时才回退到堆分配。暂时可以假设，LLVM IR 中计算出的每个值，在寄存器文件中都有一个固定位置。第 IV-C 节将说明，把值这样映射到寄存器其实并不可取；这里暂时只假设所有值都存在于寄存器文件的某处。寄存器文件的前两个条目分别初始化为 0 和 1，使这两个常量始终可以直接从寄存器取得。

VM 指令集采用定长编码和静态类型，大部分指令都模仿 LLVM IR 指令集。例如，下面这个很小的 LLVM 函数：

```llvm
define i32 @add(i32, i32) {
  %3 = add i32 %1, %0
  ret i32 %3
}
```

```text
add_i32     24 16 20
return_i32 24
```

其中，`add_i32` 指令从寄存器 16 和 20 加载两个函数参数；这些数字是寄存器文件中的字节偏移，并把结果写回寄存器 24。`return_i32` 指令把这个值返回给调用者。应注意，LLVM 指令和 VM 指令并不总像该示例一样一一对应。第一，LLVM 指令带有类型标注，而 VM 指令把类型直接编码在操作码中；例如，LLVM 的 `add` 在翻译时会按照参数类型展开成多种 `add` 指令。第二，为处理频繁出现的指令序列，我们有时会把多条 LLVM 指令合并成一条 VM 指令，参见第 IV-F 节。

我们对操作码采用定长编码，以提高解码速度。相较原生机器码，这会增大翻译后函数的内存占用，但它仍比基于大量指针的原始 LLVM IR 紧凑得多。如图 8 所示，VM 代码本身由一个很大的 `switch` 语句组成，用来执行所有支持的指令。

```cpp
while (true) {
  switch ((++ip)->op) {
    case Op::add_i32:
      *((int32_t*)(regs + ip->a1)) =
          *((int32_t*)(regs + ip->a2)) + *((int32_t*)(regs + ip->a3));
      break;
    case Op::add_i64:
      *((int64_t*)(regs + ip->a1)) =
          *((int64_t*)(regs + ip->a2)) + *((int64_t*)(regs + ip->a3));
      break;
    case Op::call_void_i32:
      (void(*)(int32_t))(ip->lit)(*((int32_t*)(regs + ip->a1)));
      break;
    ... // around 500 more instructions
  }
}
```

**图 8：实现解释器循环的 VM 代码片段；`ip` 指向当前指令，`regs` 指向存放寄存器的内存。**

VM 总计处理大约 500 种“指令/类型”组合；每一种组合在 VM 代码中通常只有一行相当简单的 C++。字节码解释器约有 800 行代码。对于一个无需修改查询代码生成就能解释任意查询计划的组件而言，这个规模小得惊人。它对系统的可维护性很重要，因为分别为原生代码和解释执行维护完全独立的代码路径会很没有吸引力。

### B. 翻译为 VM 代码

图 9 展示了从 LLVM IR 代码到 VM 代码的翻译。第一步是计算寄存器分配所需的活性信息；这是翻译过程中最有挑战性的步骤，因此下文会详细讨论。完成后，系统便知道一个值在控制流中的何处开始存活、何处死亡。

```text
compute liveness and order blocks
for each block b:
  allocate registers for values that become live in b
  for each instruction i in b:
    if i is not subsumed:
      translate i into VM opcodes
  propagate values in phi nodes
  release register for values that ended in b
```

**图 9：将 LLVM IR 翻译为 VM 代码。**

有了这些信息，变换本身很简单。变换利用了 LLVM 程序采用静态单赋值（SSA）形式这一事实：每个值只产生一次，并且在程序的整个生命周期中从不改变。

我们按照活性计算确定的顺序，遍历程序的所有基本块。对每个块，系统首先检查某些值是否在产生它们的指令不属于该块时就开始存活；这种情况很少见，但复杂控制流中可能发生。若是如此，就立即为这些值分配寄存器。随后，块内指令逐条翻译为 VM 操作码；如果后续指令已被之前的指令吸收，则不再单独翻译，例如把一串指令折叠为一条 VM 操作码，参见第 IV-F 节。块结束时，若后继块使用 $\phi$ 节点在 SSA 表示中合并不同值，系统就把值复制到后继块的 $\phi$ 节点；同时，释放所有生命周期已经结束的值所占用的寄存器。与块开始时的分配一样，这也是控制流带来的例外，下文还会讨论。

绝大多数情况下，寄存器都是按需分配的，并在相应值的最后一个用户消失时释放。也就是说，只有控制流迫使系统延长某个值的生命周期时，才需要在基本块边界上专门处理。

完成这一步翻译后，VM 程序就可以执行。它完成与原生代码完全相同的工作，包括全部函数调用和内存写入；这一点对在解释与编译之间切换至关重要。要实现这种替换，还需处理一些工程细节。例如，在翻译期间必须修补对解释代码的调用，使其多接收一个参数，即 VM 程序。不过，这与编译器处理嵌套函数的标准技术相似，不会引入太多复杂性。我们的翻译器约有 2,400 行代码，其中大部分用于寄存器分配。因为翻译几乎完全作用于定义良好的 LLVM IR 语言，额外工程工作并不算多。

### C. 寄存器分配

如前所述，把 LLVM 值映射到寄存器槽位，也就是寄存器分配，是 LLVM IR 到 VM 代码翻译中唯一在算法上具有挑战性的步骤。本文的问题与传统寄存器分配略有不同：我们只使用虚拟寄存器，因而理论上可以分配几乎任意多的寄存器。然而我们显然不能这样做。解释执行期间会极其频繁地访问寄存器文件，因此它应始终驻留在 L1 cache 中；过大的寄存器文件会浪费宝贵的 L1 cache 条目。

因此，我们的寄存器分配问题包含四项目标：

1. 为程序中的每一个 LLVM 值分配一个寄存器槽位；
2. 只有两个值的生命周期不重叠时，才允许它们共享一个寄存器；
3. 尽量减少寄存器总数；
4. 高效翻译极大的程序。

原则上，寄存器分配是编译器构造中一个已得到充分研究的问题 [21]。寄存器分配需要活性信息，也就是必须知道每个基本块中哪些值存活、哪些值死亡。然而，计算这类活性信息的运行时间会随基本块数量超线性增长，使这些算法对大函数昂贵到无法使用。不幸的是，我们的一些查询确实会编译成极大的函数，其中包含数千个基本块和数万个值。这与通常由小函数组成的手写程序截然不同。

寄存器分配器会尝试通过溢出到内存来切分生命区间，以避开昂贵的活性计算 [22]。但这对我们并不真正可行，这一点与常规机器码不同：我们仍然必须设法最小化溢出区域，因为它也必须驻留 cache。某些 JIT 系统因而把寄存器分配限制在单个基本块内，这很容易实现；另一些系统只考察固定数量的相邻基本块。这些方法计算简单，却可能产生很差的寄存器分配。

我们开发了一种新的线性时间寄存器算法。它识别并利用循环结构，从而快速近似最优寄存器分配。在寄存器数量不受限制的情况下，为 SSA 程序寻找最优寄存器分配本身是超线性的。本文的分配器改为允许在必要时，把一个变量的生命周期保守地延长到“包含该值所有使用点的最内层循环”边界以内。实践中，这只会在复杂控制流下发生，影响无法察觉，却为线性最坏情况行为提供了合理折中。

线性时间算法对自适应执行框架非常重要。第 V-E 节将表明，由于所用算法是超线性的，常规 LLVM 编译器事实上无法编译某些极其复杂的查询。我们确实遇到过机器生成查询：其中最大的函数包含 300,000 个值和数千个基本块。对这种函数使用超线性算法，会造成不可接受的编译时间，可能长达数小时甚至数天。

为直观比较不同寄存器分配策略，我们给出相当大的 TPC-DS 查询 55 在不同策略下的寄存器文件大小。若直接为每个值分配寄存器而不复用，需要 36 KB，已经大于我们的 L1 cache。若改用贪心策略，并在一个固定基本块窗口内估计生命周期，需要 21 KB；这对某些 JIT 编译器已经够用，但仍然相当大。下文算法把这一数字降到 6 KB，合理得多。

### D. 线性时间活性分析

算法基于两个关键概念。第一，我们把一个值的活性表示为带起始块和结束块的生命区间。逐块计算活性的传统方法在本质上需要 $O(n^2)$ 时间。第二，我们按控制流给块编号，并显式处理循环，从而让每个值的生命区间尽可能紧凑。

![变量活性范围的控制流示例](assets/precise-manual-figure-10-liveness-cfg.png)

**图 10：计算变量 $v$ 的活性；顶点是由控制流边（即分支指令）连接的基本块。**

图 10 说明了第二个概念。基本块按逆后序编号，这与控制流顺序一致。值 $v$ 在块 2 中创建，在块 5 中使用。直观但错误的做法，是把 $v$ 的生命周期视为区间 $[2,5]$。块 5 属于一个从块 3 开始、涉及块 $[3,6]$ 的循环；其中任意块都能到达块 5。因此，我们把生命周期扩展到包含读取者所在的整个循环，得到生命区间 $[2,6]$。

完整算法见图 11。算法分两阶段运行。第一阶段识别函数中的全部循环，并把每个基本块关联到包含它的最内层循环。有了这些信息，系统就能找出包含某个值之定义或使用的全部基本块，再把这些块提升到包含全部块的最内层循环层次，从而计算该值的生命周期。从概念上说，一个值从定义处一直存活到最后一个用户；由于循环结构，途中所有可能被经过的基本块也包括在内。

```text
// compute the liveness of values in function F
ComputeLiveness(F):
  // find loop structures in F
  label all basic blocks in F in reverse postorder
  compute the dominator tree D for each basic block
  label all nodes in D with pre-/postorder numbers
  mark the first basic block in F as loop head
  for each jump edge j: B -> B':
    if B' is ancestor of B in D:
      mark B' as loop head
  for each basic block B:
    associate B with the next dominating loop head
  for each loop:
    compute the first and last block of the loop
    compute the next dominating loop head
    label loop with nesting depth

  // use the loop information to compute lifetimes
  for each value v in F:
    B_v = set of basic blocks containing definition and users of v
    C_v = innermost loop containing all blocks in B_v
    L_v = empty lifetime interval
    for each B in B_v:
      if C_v is innermost loop for B:
        extend L_v with B
      else:
        extend L_v with outermost loop below C_v that contains B
```

**图 11：活性计算的线性时间算法。**

![带 pre-/post-order 标注的 dominator tree](assets/precise-manual-figure-12-dominator-tree.png)

**图 12：以前序/后序编号标注的支配树。**

下面更详细地考察算法。首先按逆后序标注并排序全部基本块，也就是说，一个块排在它的所有入边块之后。忽略循环时，这恰好对应控制流顺序，也是人类在编程语言中对块进行排序的“自然”方式。后续算法步骤需要这个顺序；它还有一个额外好处，就是块编号对控制流具有明确意义。

有了这种编号，就能高效计算支配树 $D$ [23]、[24]；对每个基本块，支配树指出在它之前必然已经执行的最近基本块。为便于查询，我们给 $D$ 中的全部节点标上前序和后序编号 [25]。这种编号允许在 $O(1)$ 时间内判断祖先/后代关系。示例的支配树见图 12。借助前序/后序编号可以立刻看出，例如块 2 传递地支配块 6，因为块 6 的区间 $[8,11]$ 包含在块 2 的区间 $[2,13]$ 中，即 $[8,11] \subset [2,13]$。

这些基础结构用于识别循环。为避免对循环外基本块进行特殊处理，我们假装整个函数体都属于一个大循环，并把函数的第一个基本块标为循环头，也就是该顶层伪循环的入口点。随后考察基本块对 $B$ 和 $B'$ 之间的全部跳转。若 $B'$ 在支配树 $D$ 中是 $B$ 的祖先，就找到了一个循环，并把 $B'$ 标为循环头。在示例中，块 6 跳转到块 3，而块 3 支配块 6，因此块 3 是循环头，也就是循环入口。

找出全部循环后，系统把每个块关联到包含它的最内层循环；该循环由最近的、支配它的循环头表示。这里使用带路径压缩的并查集，使计算保持快速。我们记录每个循环的第一个和最后一个块，编号依据仍是块标签；还记录该循环嵌套在哪个循环内。在示例中，从块 3 开始的循环包含块 3、4、5、6，并被从块 1 开始的顶层伪循环包含。最后，算法计算每个循环的嵌套深度。

尽管这段计算牵涉多个并不平凡的算法，每一步的总体复杂度都是线性的。事实上，大部分复杂性都来自我们对线性运行时间的保证。例如，可以省去前序/后序编号或路径压缩，但那会使后续步骤的运行时间变成超线性；支配树算法的选择也是如此。

有了循环信息，单个值 $v$ 的活性计算就很简单。定义：

$$
U_v = \text{包含 } v \text{ 的定义或某个使用者的全部基本块}
$$

并令 $C_v$ 为包含 $U_v$ 中全部基本块的最小公共循环。若 $U_v$ 中所有块所属的循环相同，那么按逆后序编号，生命周期只是从第一个块到最后一个块的跨度。一般情况下，系统先找出包含 $U_v$ 全部块的最小公共循环 $C_v$。对 $U_v$ 中直接位于 $C_v$ 而不处于更深嵌套循环的块，直接把它们纳入 $v$ 的生命区间。对其余每个块 $b \in U_v$，把 $v$ 的生命区间扩展为包含 $C_v$ 之内、且包含 $b$ 的最外层循环的全部块。

在示例中，值 $v$ 的包含循环 $C_v$ 是整个函数。 $v$ 在块 2 中的定义直接位于这个循环中，而块 5 中对 $v$ 的使用深一层。因此， $U_v$ 只包含块 2 和块 5，经上述规则推导为生命区间 $[2,6]$。由于第一阶段分析循环时已经准备好查询结构，整个计算成本很低。

LLVM 的 $\phi$ 节点需要谨慎处理。 $\phi$ 节点用于 SSA 形式，它根据进入含有该 $\phi$ 节点之基本块的入边来选择一个值。计算生命周期时， $\phi$ 的参数在相应入边块的末尾被“读取”；紧接着， $\phi$ 节点在同一个块中被“写入”，然后又在包含该 $\phi$ 节点的块中被“读取”。这不难实现，但计算 $\phi$ 节点的活性时必须记住这项规则。

### E. 互操作性

我们用虚拟机解释原始 LLVM IR。因此，除速度差异外，字节码解释器的行为与生成的机器码等价。这一点很重要，因为它使系统无需修改其他部分，就能在解释执行与机器码之间无缝切换。

然而，字节码与机器码之间的互操作带来了一个问题。运行机器码时，一个函数指针就够了；解释字节码却需要调用虚拟机。因此，系统不能直接调用函数，而要调用额外的分派代码，参见图 5，并把函数的字节码作为附加参数传入。可以给指针加标签，动态区分两种签名，再调用相应函数；但这样侵入性很强，还会引入不必要的分支。本文的做法是始终给函数多传一个指针参数，即使在机器码情况下该参数是多余的。这样，只需替换函数指针并注入附加参数，就能透明地从解释代码切换到编译代码。

反方向更简单：生成的机器码和 VM 都可以调用已有 C++ 代码。系统只需确保 VM 对每一种现有函数签名都提供适当的调用指令。以图 8 为例，调用具有一个 32 位整数参数且没有返回值的 C++ 函数，需要操作码 `Op::call_void_i32`。因为所有导出的 C++ 函数都已知，缺少的操作码可以在编译期识别。

### F. 优化

虽然可以把 LLVM 指令彼此独立地翻译，但这样做有时并不明智。溢出检查就是一例。查询中的所有算术都要检查溢出，以便向用户报告溢出错误。在 LLVM 中，这项检查归结为总是顺序执行的 4 条指令。字节码翻译器会识别这个序列，把它替换为一条 VM 字节码，一次完成全部四步。对某些查询，这能大幅减少指令数并缩短执行时间。

另一个频繁出现的模式，是 `GetElementPtr` 指令，也就是指针算术，后面紧跟一次 load 或 store。翻译时同样会识别这种序列，把它合并为一个 VM 操作码以减少指令数。

一般而言，可以翻译一个大型查询语料库，寻找频繁出现的指令序列，再用宏指令替换它们。例如，NULL 处理就是一个候选，因为它也倾向于产生相似的指令序列。未来工作将扩展这项机制，以识别更多此类结构。

## V. 实验评估

本节通过实验，把第 III 节提出的自适应查询执行框架与多种静态选择的执行模式进行比较。我们还特别考察第 IV 节介绍的字节码解释器，以回答查询解释是否能给基于编译的数据库带来额外价值。

实验在 HyPer 中进行。HyPer 直接生成 LLVM IR，在本文工作之前总是把它编译成机器码。默认模式是优化编译：先执行一组手工选择的 LLVM IR 优化 Pass，再启用全部机器相关的后端优化。这里的五类 LLVM IR Pass 是：窥孔优化、表达式重结合、公共子表达式消除、控制流图简化和激进死代码消除。

我们还实现了未优化编译模式。它同样生成机器码，但禁用大部分编译器优化来缩短编译时间。具体来说，该模式启用快速指令选择，不执行任何 LLVM IR 优化 Pass，并使用较低的后端优化等级。解释器把 LLVM IR 直接翻译为第 IV 节所述的字节码。最后，自适应执行模式按照第 III 节所述方式，交错进行机器码生成和执行。

实验运行在一台桌面系统上，配备 8 核 AMD Ryzen 7 1700X CPU、32 GB 内存，软件为 LLVM 3.8 和 Linux 4.11。我们在 Intel CPU 上重复了全部实验，观察到相似结果。

### A. 静态与自适应模式选择

首先考察执行模式的自适应切换能否与静态的预先决策竞争。在这个实验中，我们运行全部 22 条 TPC-H 查询，scale factor 从 0.01（约 10 MB）到 30（约 30 GB）。

![TPC-H 不同 scale factor 上的几何平均端到端时间](assets/precise-manual-figure-13-tpch-geomean.png)

**图 13：使用 8 个线程时，不同 scale factor 和执行模式下全部 TPC-H 查询的几何平均时间，包括规划、编译与执行。**

图 13 给出了全部查询在所有执行模式下的几何平均。即使事先不知道确切数据规模，自适应执行也始终能与最佳的静态执行模式竞争。在 scale factor 0.01 和 0.1 上，优劣完全由查询时延决定，解释执行明显优于编译。在这些数据规模上，自适应执行从不选择编译，表现与纯字节码解释相同。

从 scale factor 1 开始，许多 pipeline 已经值得编译，因此未优化编译开始具有竞争力。不过，自适应执行仍能胜过未优化编译，因为快速 pipeline 仍可直接由字节码处理。最后，在 scale factor 30 上，查询运行时间已经足以证明优化编译值得。此时，自适应执行会针对每条 pipeline，从三种执行模式中选择最佳者，并明显胜过两种编译模式。

我们预计，在更大的 scale factor 上，这个趋势仍会延续，优化编译将成为自适应执行的主要竞争者。不过，自适应执行应当仍有最低的总体处理时间，因为查询计划中依旧会存在便宜的 pipeline，可以立即解释执行。

### B. 自适应执行过程

下一步，我们以 scale factor 1、使用 4 个线程的 TPC-H 查询 11 为例，考察框架的自适应行为。[^3] 图 14 给出了动态执行轨迹，它包含被处理 morsel 的精确计时信息，用于比较自适应执行及其竞争者。

![TPC-H Q11 的自适应执行轨迹](assets/precise-manual-figure-14-execution-trace.png)

**图 14：TPC-H 查询 11 在 scale factor 1、4 线程下的执行轨迹。优化模式的编译需 103 ms，因而未绘出。**

从字节码解释器开始，图中表明数据库迅速使用全部 4 个 worker 线程，并行处理 pipeline morsel。它还显示，工作量在 7 条 pipeline 之间分布得极不均匀；大部分时间花在 `scan partsupp 1` 和 `scan partsupp 2` 两条 pipeline 上。

相较之下，未优化编译会把相当大一部分时间用于对查询计划进行最初的单线程编译。编译完成后，已编译 pipeline 处理得快得多，以至于轨迹中几乎无法区分各个 morsel。优化编译的执行轨迹与未优化编译很相似，但为了让图形可读，图中没有画出它；额外的编译器优化把编译时间延长到 103 毫秒。总的来说，对这个 scale factor 1 的查询，未优化编译支配了其他静态执行模式，因为它在提高效率和快速准备查询之间取得了良好折中。这些观察已经表明，静态预先决策的质量高度依赖各条 pipeline 的复杂度以及正在处理的数据。

图 14 还展示了自适应执行模式的轨迹；它能胜过全部竞争者。与纯字节码解释器非常相似，自适应执行可以立即在全部 4 个 worker 线程上开始处理 pipeline morsel。1 毫秒后，它判断切换两条最大 pipeline 的执行模式值得，因而让一个 worker 线程编译它们。因为编译范围限于单个函数，耗时仅为先前编译整个查询计划时的一小部分。

编译完成后，所有 worker 线程自动换挡到新生成的机器码，高效处理剩余 morsel。不过，复杂度分布不均意味着只有 7 条 pipeline 中的 2 条值得编译。框架因而让其余 pipeline 继续使用字节码解释器，最终分别比三个竞争者快 10%、40% 和 80%；这三个竞争者依次是未优化编译、字节码解释器和优化编译。

[^3]: 选择查询 11，是因为它在图中可以清楚分辨出各个 morsel。

### C. 编译时间

字节码解释是在基于编译的数据库中提供低时延执行模式的一种可行方法。为给出支持这一论断的证据，我们评估 HyPer 的规划和编译时间，并与 PostgreSQL 9.6 和 MonetDB 1.7 比较；前者采用 Volcano 风格解释执行，后者采用 column-at-a-time 处理。表 I 给出 TPC-H 查询 1 到 5 的规划时间，以及全部 22 条查询中的最大值。

**表 I：PostgreSQL（PG）、MonetDB（Monet）和 HyPer 上 TPC-H 查询的规划与编译时间，单位为毫秒。**

| TPC-H | PG plan | Monet plan | HyPer plan | HyPer cdg. | HyPer bc. | HyPer unopt. | HyPer opt. |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.1 | 0.8 | 0.2 | 0.7 | 0.4 | 6 | 42 |
| 2 | 1.0 | 0.7 | 0.7 | 1.5 | 1.2 | 23 | 149 |
| 3 | 0.3 | 0.5 | 0.4 | 0.9 | 0.7 | 10 | 69 |
| 4 | 0.2 | 0.4 | 0.2 | 0.7 | 0.4 | 7 | 47 |
| 5 | 1.2 | 0.8 | 0.7 | 1.2 | 0.9 | 15 | 104 |
| max | 1.9 | 1.0 | 0.8 | 1.5 | 1.2 | 23 | 149 |

对 TPC-H 而言，表中的“plan”表示计划生成，其中包括解析、语义分析和查询优化；所有系统完成这部分都很快。MonetDB 和 PostgreSQL 可以直接执行该计划，而 HyPer 还要在代码生成阶段生成 LLVM IR，这一列缩写为“cdg.”。LLVM IR 生成通常比规划稍慢，但对全部 22 条 TPC-H 查询仍然很快，均不足 2 毫秒。

HyPer 的下一阶段可以是生成字节码（“bc.”）、未优化机器码（“unopt.”）或优化机器码（“opt.”）。表中表明，即使是未优化机器码编译，通常也比规划和代码生成慢约 10 倍。优化编译更慢，对 TPC-H 最高接近 150 毫秒。相反，字节码生成非常快，始终在 2 毫秒内完成。

### D. 解释代码与编译代码的性能

接下来比较字节码解释器与编译机器码的执行时间。表 II 给出 scale factor 1 上不同执行模式的 TPC-H 性能，并与 MonetDB 和 PostgreSQL 比较。`geo.m.` 是全部 22 条查询的几何平均。

**表 II：scale factor 1 上 PostgreSQL（PG）、MonetDB（Monet）和 HyPer 执行 TPC-H 查询的时间；几何平均覆盖全部 22 条查询，单位为毫秒。**

| TPC-H | PG 1 thread | Monet 1 thread | bc. 1 thread | unopt. 1 thread | opt. 1 thread | bc. 8 threads | unopt. 8 threads | opt. 8 threads |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 4908 | 484 | 858 | 161 | 77 | 170 | 34 | 16 |
| 2 | 254 | 5 | 94 | 13 | 8 | 25 | 5 | 3 |
| 3 | 1258 | 64 | 323 | 104 | 80 | 54 | 21 | 17 |
| 4 | 193 | 56 | 352 | 67 | 45 | 57 | 16 | 12 |
| 5 | 516 | 51 | 362 | 60 | 37 | 67 | 14 | 10 |
| geo.m. | 497 | 57 | 232 | 60 | 46 | 45 | 15 | 12 |

考虑全部 22 条查询的几何平均，字节码解释器比未优化机器码慢 3.6 倍，比优化机器码慢 5.0 倍。虽然解释代码慢于编译代码，它仍比 PostgreSQL 快 2.1 倍；使用多个核心时，其扩展性与编译代码同样好。

### E. 编译超大查询

第 III 节引入了一个线性代价函数，根据 pipeline 中的指令数估计编译时间。然而，该函数是从 TPC-H 和 TPC-DS 基准中推导出来的，而这两个基准不包含特别复杂的查询。另一方面，机器生成的查询很容易包含数 MB 的 SQL 文本，其特征会让查询编译器非常难以处理。因此，在最后一个实验中，我们考察极大查询对三种执行模式的影响，并表明快速翻译为字节码对这类工作负载不可或缺。

样本查询由一次单表扫描和数量不断增加的聚合表达式组成。把聚合表达式数量从 10 增加到 1,900 后，得到的查询计划包含 1,000 到 160,000 条 LLVM 指令，其中大多数集中在一个大函数中。

![大量 LLVM instruction 查询的编译时间](assets/precise-manual-figure-15-large-query-compile-time.png)

**图 15：对指令数量很大的查询，使用优化编译、未优化编译和解释执行时的编译时间。**

图 15 给出了不同执行模式对这些查询的编译时间。最重要的观察是，对较大的查询规模，LLVM 优化编译已不再可行。其编译时间呈爆炸式增长，在仅有 10,000 条 LLVM 指令时就超过 4 秒。不执行优化 Pass 时，查询编译的扩展性更好，但最大的查询仍需 4.4 秒。相比之下，字节码解释器的翻译时间呈完美线性扩展，只用 0.9 秒就能处理这个极大的查询。

这一工作负载凸显了第 IV 节所述快速字节码翻译的重要性。借助该翻译，系统可以用解释器执行规模几乎任意大的查询，并且只在需要效率时，才自适应地编译查询中的一部分。

## VI. 相关工作

许多基于编译的查询处理论文只报告执行时间，却不说明生成机器码本身花了多久。少数报告这一数字的论文表明，以 LLVM IR 为目标语言时，编译时间为 5 到 37 毫秒 [26]；编译到 C 时则接近 1 秒 [11]、[27]。随着编译日益普及，我们预计编译时间会得到更多关注，因为任何工业级系统都必须处理极大的查询。

事实上，我们的亲身经验是：一旦从通常经过良好设计而且“正常”的标准基准查询，转向有时非常“有趣”的真实客户查询，查询编译时延就会成为严重问题。因此，我们认为自适应执行是让查询编译在实践中真正可用的关键组件；尤其是因为传统引擎和现代列存系统 [28]、[29]、[30]、[31] 并没有很长的编译时间。下面说明如何把自适应编译集成到其他系统，并讨论其他降低编译时间的方法。

自适应执行是为直接把查询编译到 LLVM IR 的系统设计的，包括 HyPer [7] 和 Peloton [15]。MemSQL 是另一个能从自适应执行获益的编译式系统。它最初把查询编译为大量使用模板的 C++，导致很高的编译时间。可能正因如此，较新的版本先编译到称为 MemSQL Plan Language 的高层命令式语言，再经过名为 MemSQL Bit Code 的中层中间语言，逐步降低到 LLVM IR [3]。由于 MemSQL Bit Code 可以解释执行，因此可以很容易地在这一层实现解释与编译执行之间的切换。

与自适应执行相似的方法也可用于 LegoBase [11] 及其后继系统 [27]；两者既能通过 Java VM 执行查询，也能编译到 C 之类的低层语言。自适应执行还可能对传统系统有用，例如 Volcano 风格系统；这些系统会用编译为特定查询专门化查询引擎代码 [32]、[33]、[5]。SQL Server 的 Microsoft Hekaton 会把存储过程编译到 C [2]。对这种用例，编译时间或许不如即席查询重要，因为存储过程通常很少定义，却经常执行。

自动计划缓存，即在同一条或相似查询的后续执行间复用查询计划，是另一种与本文正交的编译时间优化方法。然而，和显式预备语句一样，计划缓存无法隐藏第一条到达查询的编译时间。对交互式应用而言，这意味着编译式系统的首次用户体验远非理想。

计划缓存还有另一个缺点：重复查询往往并不完全相同，例如选择常量有所不同。本文的自适应方法可以在每次执行时重新优化查询，优点是查询优化器能够看到具体查询常量，从而可能得到更好的查询计划。尽管如此，本文方法也可以与计划缓存结合。可以扩展自适应执行以纳入同一查询的多次执行，记录每条 pipeline 被执行的频率。在这种设计下，频繁执行之查询的所有 pipeline 最终都会以优化模式编译。

自适应执行与 Java（HotSpot）、C#（CLR）和 JavaScript（V8、JägerMonkey）等现代托管语言的执行引擎相似。这些系统先在解释器中执行代码，再对热点代码动态切换到编译执行。本文的自适应执行框架可以看作类似思想的一种数据库专用实现。

不过，为取得最大性能，数据库系统需要精确控制内存管理，因此通常以低层语言编写，或生成低层语言。这意味着数据库不能直接使用语言层面的自动方案；据我们所知，这类自动方案只存在于托管语言中。另一方面，与通用编程语言不同，数据库系统对代码结构和生成的指令了解得更多。这既简化了自适应执行的设计与实现，例如无需实现系统从不生成的 LLVM IR 指令，也允许进行数据库专用优化，例如为溢出检查等常见操作提供宏操作。

## VII. 总结

我们证明，解释和编译都是实现低查询时延与高吞吐的重要构件。我们还提出一种自适应执行框架，它动态、自动地调整查询的执行模式，从而最小化总体执行时间。在这种方法中，所有决策都在 pipeline 粒度上进行，并以运行时反馈为依据，而不是预先决定。我们进一步提出一种字节码解释器，它能在线性时间内把 LLVM IR 翻译为高效字节码。通过把该解释器与可选优化 Pass 的现有 LLVM 编译器结合起来，系统能够动态适应从 10 MB 到 30 GB 的数据规模，并在 TPC-H 查询上胜过所有静态选择的执行模式。

## 致谢

本项目获得欧洲研究委员会（European Research Council，ERC）在欧盟 Horizon 2020 研究与创新计划下的资助，资助协议编号 725286。

## 参考文献

- [1] C. Diaconu, C. Freedman, E. Ismert, P. Larson, P. Mittal, R. Stonecipher, N. Verma, and M. Zwilling, "Hekaton: SQL server’s memory-optimized OLTP engine," in SIGMOD, 2013, pp. 1243–1254.
- [2] C. Freedman, E. Ismert, and P. Larson, "Compilation in the Microsoft SQL Server Hekaton engine," IEEE Data Eng. Bull., vol. 37, no. 1, pp. 22–30, 2014.
- [3] D. Paroski, "Code generation: The inner sanctum of database performance," http://highscalability.com/blog/2016/9/7/code-generation-the-inner-sanctum-of-database-performance.html, 2016.
- [4] S. Agarwal, D. Liu, and R. Xin, "Apache Spark as a compiler: Joining a billion rows per second on a laptop," https://databricks.com/blog/2016/05/23/apache-spark-as-a-compiler-joining-a-billion-rows-per-second-on-a-laptop.html, 2016.
- [5] S. Wanderman-Milne and N. Li, "Runtime code generation in Cloudera Impala," IEEE Data Eng. Bull., vol. 37, no. 1, pp. 31–37, 2014.
- [6] K. Krikellas, S. Viglas, and M. Cintra, "Generating code for holistic query evaluation," in ICDE, 2010, pp. 613–624.
- [7] T. Neumann, "Efficiently compiling efficient query plans for modern hardware," PVLDB, vol. 4, no. 9, 2011.
- [8] C. Koch, Y. Ahmad, O. Kennedy, M. Nikolic, A. Nötzli, D. Lupei, and A. Shaikhha, "DBToaster: higher-order delta processing for dynamic, frequently fresh views," VLDB J., vol. 23, no. 2, pp. 253–278, 2014.
- [9] A. Crotty, A. Galakatos, K. Dursun, T. Kraska, U. Çetintemel, and S. B. Zdonik, "Tupleware: "big" data, big analytics, small clusters," in CIDR, 2015.
- [10] A. Crotty, A. Galakatos, K. Dursun, T. Kraska, C. Binnig, U. Çetintemel, and S. Zdonik, "An architecture for compiling UDF-centric workflows," PVLDB, vol. 8, no. 12, pp. 1466–1477, 2015.
- [11] Y. Klonatos, C. Koch, T. Rompf, and H. Chafi, "Building efficient query engines in a high-level language," PVLDB, vol. 7, no. 10, pp. 853–864, 2014.
- [12] M. Karpathiotakis, I. Alagiannis, T. Heinis, M. Branco, and A. Ailamaki, "Just-in-time data virtualization: Lightweight data management with ViDa," in CIDR, 2015.
- [13] H. Pirk, O. Moll, M. Zaharia, and S. Madden, "Voodoo - a vector algebra for portable database performance on modern hardware," PVLDB, vol. 9, no. 14, pp. 1707–1718, 2016.
- [14] S. Palkar, J. J. Thomas, A. Shanbhag, M. Schwarzkopt, S. P. Amarasinghe, and M. Zaharia, "A common runtime for high performance data analysis," in CIDR, 2017.
- [15] P. Menon, T. C. Mowry, and A. Pavlo, "Relaxed operator fusion for in-memory databases: Making compilation, vectorization, and prefetching work together at last," PVLDB, vol. 11, no. 1, 2017.
- [16] A. Pavlo, G. Angulo, J. Arulraj, H. Lin, J. Lin, L. Ma, P. Menon, T. C. Mowry, M. Perron, I. Quah, S. Santurkar, A. Tomasic, S. Toor, D. V. Aken, Z. Wang, Y. Wu, R. Xian, and T. Zhang, "Self-driving database management systems," in CIDR, 2017.
- [17] V. Leis, A. Gubichev, A. Mirchev, P. Boncz, A. Kemper, and T. Neumann, "How good are query optimizers, really?" PVLDB, vol. 9, no. 3, 2015.
- [18] V. Leis, B. Radke, A. Gubichev, A. Mirchev, P. Boncz, A. Kemper, and T. Neumann, "Query optimization through the looking glass, and what we found running the join order benchmark," VLDB J., 2018.
- [19] C. Chasseur and J. M. Patel, "Design and evaluation of storage organizations for read-optimized main memory databases," PVLDB, vol. 6, no. 13, pp. 1474–1485, 2013.
- [20] V. Leis, P. Boncz, A. Kemper, and T. Neumann, "Morsel-driven parallelism: A NUMA-aware query evaluation framework for the many-core age," in SIGMOD, 2014, pp. 743–754.
- [21] F. M. Q. Pereira, "The design and implementation of a SSA-based register allocator," 2007.
- [22] M. Poletto and V. Sarkar, "Linear scan register allocation," ACM Trans. Program. Lang. Syst., vol. 21, no. 5, pp. 895–913, Sep. 1999.
- [23] L. Georgiadis, R. E. Tarjan, and R. F. F. Werneck, "Finding dominators in practice," J. Graph Algorithms Appl., vol. 10, no. 1, pp. 69–94, 2006.
- [24] W. Fraczak, L. Georgiadis, A. Miller, and R. E. Tarjan, "Finding dominators via disjoint set union," J. Discrete Algorithms, vol. 23, pp. 2–20, 2013.
- [25] T. Grust, "Accelerating XPath location steps," in SIGMOD, 2002, pp. 109–120.
- [26] T. Neumann and V. Leis, "Compiling database queries into machine code," IEEE Data Eng. Bull., vol. 37, no. 1, pp. 3–11, 2014.
- [27] A. Shaikhha, Y. Klonatos, L. Parreaux, L. Brown, M. Dashti, and C. Koch, "How to architect a query compiler," in SIGMOD, 2016, pp. 1907–1922.
- [28] P. Larson, C. Clinciu, E. N. Hanson, A. Oks, S. L. Price, S. Rangarajan, A. Surna, and Q. Zhou, "SQL server column store indexes," in SIGMOD, 2011, pp. 1177–1184.
- [29] D. Abadi, P. A. Boncz, S. Harizopoulos, S. Idreos, and S. Madden, "The design and implementation of modern column-oriented database systems," Foundations and Trends in Databases, vol. 5, no. 3, pp. 197–280, 2013.
- [30] V. Raman, G. K. Attaluri, R. Barber, N. Chainani, D. Kalmuk, V. KulandaiSamy, J. Leenstra, S. Lightstone, S. Liu, G. M. Lohman, T. Malkemus, R. Müller, I. Pandis, B. Schiefer, D. Sharpe, R. Sidle, A. J. Storm, and L. Zhang, "DB2 with BLU acceleration: So much more than just a column store," PVLDB, vol. 6, no. 11, pp. 1080–1091, 2013.
- [31] J. Patel, H. Deshmukh, J. Zhu, H. Memisoglu, N. Potti, S. Saurabh, M. Spehlmann, and Z. Zhang, "Quickstep: A data platform based on the scaling-in approach," University of Wisconsin - Madison, Tech. Rep., 2017.
- [32] R. Zhang, R. T. Snodgrass, and S. Debray, "Micro-specialization in DBMSes," in ICDE, 2012, pp. 690–701.
- [33] R. Zhang, S. Debray, and R. T. Snodgrass, "Micro-specialization: dynamic code specialization of database management systems," in International Symposium on Code Generation and Optimization, 2012, pp. 63–73.
