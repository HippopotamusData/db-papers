---
paper_id: generating-code-holistic-query-evaluation
title: Generating code for holistic query evaluation
language: zh-CN
source: source.pdf
---

# Generating code for holistic query evaluation（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者与机构

- Konstantinos Krikellas（`k.krikellas@sms.ed.ac.uk`），英国爱丁堡大学信息学院
- Stratis D. Viglas（`sviglas@inf.ed.ac.uk`），英国爱丁堡大学信息学院
- Marcelo Cintra（`mc@inf.ed.ac.uk`），英国爱丁堡大学信息学院

## 出版信息

ICDE Conference 2010；IEEE，2010；页 613–624。

## 摘要

本文介绍定制化代码生成在数据库查询求值中的应用。核心思想是使用一组高效代码模板，并在运行时实例化这些模板，生成面向查询和硬件的源代码。生成的源代码经过编译，再动态链接到数据库服务器中用于处理查询。代码生成减少了实现通用解释式 SQL 查询引擎所必需的高层编程抽象造成的代码膨胀；与此同时，生成的代码还能针对实际运行它的硬件定制。我们把这种方法称为整体查询求值（holistic query evaluation）。本文介绍融入上述方案的原型系统 HIQUE，即 Holistic Integrated Query Engine 的设计与开发，并对系统性能展开详细实验研究。结果表明，HIQUE 达到了设计目标，其效率超过成熟的查询处理技术和当时正在兴起的查询处理技术。

## I. 引言

本文把定制化代码生成用于高效数据库查询处理。方法源自基于模板的编程：为各种查询处理算法准备代码模板，在运行时动态实例化这些模板，并把它们组合成一段能够求值完整查询的源代码。动态模板实例化消除了当前查询引擎为实现通用查询求值器而不得不引入的各种高层抽象所带来的缺陷。由于代码是动态生成的，它还能针对实际运行它的硬件架构特征定制。我们称之为整体查询求值，因为核心前提是同时从整体上看待待求值的查询与宿主硬件。由此带来的主存执行性能优势十分可观：例如在 TPC-H 查询 1 上，相对成熟数据库技术可达到 167 倍。我们所主张的创新在于，基于模板的代码生成可以推广到任意类型查询的高效处理，同时不影响数据库系统的其他正交部分。

**动机。**传统查询处理算法一直优先减少磁盘 I/O，把内存内执行效率放在次要位置。现代服务器具有大量内存，大部分乃至整个磁盘数据库都可能装入主存；此时，processor register 与 main memory 的访问延迟差成为性能瓶颈 [1]。要优化这种负载，就必须精心构造执行代码，尽量减少 query execution 中的 processor stall time。

已有工作把 data layout 识别为主要瓶颈，认为它妨碍具有多级 cache 的现代处理器在数据库负载中发挥全部潜力。我们认为改变 storage layer 会彻底偏离既有设计；query engine 更大的问题，是把 SQL query 编译成 operator plan，以及公共 operator interface——iterator model——过于通用。后者使 CPU resource 利用率不佳：抽象实现和频繁 function call 增加查询求值所需的 instruction 与 memory access；generic code 又不能根据具体查询与硬件平台的特征定制。不过，主存中的 SQL 和 query processing 很适合 just-in-time compilation，因此我们把这个思路推到极致。

**用于查询求值的代码生成。**理想的查询处理代码既应最优利用 cache hierarchy，又应减少求值所需的 instruction，同时还要保留 iterator model 的可组合性，并且不影响独立系统模块。为此，我们提出 holistic query evaluation：在传统查询求值流程中插入 source-code generation。系统从完整查询出发整体优化，生成 query-specific、hardware-specific source code，再编译并执行。

该方法有多项收益：（a）最小化查询求值期间的 function call；（b）generated code 具有更好的 data locality，能最优利用 cache-resident data；（c）代码生成和编译允许对每个查询应用 compiler optimization，在传统 query optimization 之上增加一层优化；（d）generated code 的性能接近 hard-coded evaluation plan。同时，该模型保持灵活，不影响 storage management、concurrency control 等正交系统部分。

在此框架下，我们实现了 holistic query engine 原型，并把它与 iterator-based solution 和既有数据库系统比较。实验结果一方面量化 per-query code generation 相对 generic query operator implementation 的优势，另一方面表明整体方法在一部分 TPC-H 查询上优于 iterator-based 和 hardware-conscious 系统，证明它可作为另一种 query engine 设计。

本文其余部分安排如下：第 II 节介绍当前 processor/compiler 技术和传统 query engine 设计；第 III 节回顾相关工作；第 IV 节介绍采用整体求值的系统设计；第 V 节给出 code generation 方法和 query evaluation algorithm；第 VI 节实验评估该模型；第 VII 节总结并指出未来研究方向。

## II. 背景

### A. 硬件概览

现代 CPU 通过流水线与超标量执行同时处理多条指令 [14]。如果 CPU 支持乱序执行，那么在流水线中，等待数据传输或等待其他指令先执行的指令，会把执行机会让给排在其后的、已经可以执行的指令。乱序执行能够掩盖停顿，但当执行代码包含连续的内存请求以及很长的数据依赖链和控制依赖链时，收益就很有限；而这些情况在数据库负载中十分常见。

从主存把数据传送到处理器寄存器的延迟很高，多级高速缓存用来抵消这一延迟。一个层级越靠近处理器，容量就越小，访问速度也越快。缓存数据按固定长度的数据块组织，每个数据块称为一条缓存行（cache line），它也是与主存交换数据的单位。现代处理器包含访问速度很快的一级缓存（L1），并把它分为指令缓存 I1 与数据缓存 D1；还包含容量更大、访问速度适中的二级缓存 L2；部分型号另有容量更大、速度却慢得多的三级缓存 L3。缓存同时利用时间局部性——数据往往会在短时间内反复访问——和空间局部性——连续分配的数据往往会一起访问。非阻塞操作与超标量执行允许同时存在多个尚未完成的内存操作，从而重叠数据获取延迟。数据密集型负载会限制这种能力：缓存控制器只能并发服务有限数量的请求，随后便会饱和。缓存虽然能满足处理器的大部分指令与数据请求，但其余请求，即缓存未命中，代价昂贵，可能成为性能瓶颈。

为了辅助缓存，较新的处理器带有硬件预取器，它们识别近期可能访问的指令和数据，并预先将其取入适当的缓存层级 [10]。如图 1 所示，当时的 CPU 使用多个与缓存层次紧密耦合的预取单元。最简单的预取器能够发现顺序模式；更高级的预取器则密切监控处理器访问过的地址，通过两种方法识别更复杂的访问模式：（a）保存少量最常访问地址的访问历史；（b）跟踪相邻两次取数之间的距离，即步长（stride）。

为了量化硬件预取的影响，我们在一台使用 1.86 GHz Intel Core 2 Duo 6300 处理器的系统上，测量了内存层次中顺序访问和随机访问的数据访问延迟。[^1] 结果表明，访问 D1 缓存的代价都相同，均为 3 个 CPU 周期；但切换到 L2 缓存后，顺序访问与随机访问之间出现明显差异，前者需要 9 个周期，后者需要 14 个周期。如果缓存无法满足数据访问，差距会进一步扩大：主存顺序访问需要 28 个周期，而随机访问需要 77 个周期或更多。

[^1]: 这些结果使用 RightMark Memory Analyzer [22] 得出。

![图 1：现代 CPU 架构示意图](assets/embedded-p02-xref63.jpeg)

图 1：现代 CPU 的取指、调度、执行单元、cache 层次与多个硬件预取器。

### B. Iterator 的缺点

大多数查询引擎都建立在迭代器模型之上 [11]。该模型提供一个抽象接口，用于在查询算子之间以流式方式传递元组，接口由三个函数构成：（a）`open()`，表示开始交换信息并初始化算子内部状态；（b）`get_next()`，在算子之间传递元组；（c）`close()`，表示处理结束，并允许算子释放资源。查询计划由此组织为流水化的二叉算子树，算子之间通过迭代器调用通信。

迭代器模型虽然通用，却会产生大量函数调用。对于流中的每条元组，系统至少进行两次调用：调用方请求元组一次，被调用方传回元组一次。迭代器必须保持通用，因而调用数量还会继续增加；其函数可能是虚函数，以便根据所处理的数据类型动态绑定，这意味着每次字段访问与比较都可能需要一次函数调用。每次调用都会更新栈寄存器，并把 CPU 寄存器的内容保存到栈中、再从栈中恢复。现代 CPU 有数十个寄存器，频繁调用可能造成显著开销，使相当比例的 CPU 时间没有为结果计算作出实际贡献。此外，函数调用是执行代码中的一次跳转，会迫使流水线装入新的指令流，从而限制超标量执行。

除了与栈交互之外，数据层面也存在开销。每个迭代器都维护内部状态；一次迭代器调用需要执行多次内存操作来访问和更新这些状态，并且每次操作都可能触发缓存未命中。迭代器状态的处理还会干扰数据流访问：即使数据访问模式本来是顺序的，也会被频繁打断，从而降低硬件预取效率。还要注意，迭代器接口无法控制流水化算子的数据流，因为每个算子的实现彼此独立。因此，流水化的迭代器调用可能引起缓存竞争，让不同算子数据集的缓存行相互驱逐，最终造成缓存颠簸（cache thrashing）。

### C. 编译器优化

开发者依靠编译器转换代码，以减少执行期间的处理器停顿。由于可执行代码由编译器生成，编译器可以针对目标架构与硬件平台进行优化。它会从几个方面转换代码：（a）让执行流水线中始终充满彼此独立的指令；（b）把变量分配到寄存器，并鼓励复用寄存器中的值；（c）把对同一数据的访问组织到一起 [16]。这些优化提高并行度、减少内存访问并最大化缓存局部性，从而限制处理器停顿。

然而，迭代器模型会阻碍编译器应用这类优化。每次迭代器调用都会触发一串函数调用，最终只产生一条元组。编译器无法把这串调用提取出来并识别输入上的访问模式——该模式本身还可能是迭代式的——因为过程间分析和优化远比过程内分析和优化受限。函数调用带来的条件与跳转还会打断指令序列，缩小编译器能够作为整体检查并寻找优化机会的代码范围。迭代器实例化所需的一些参数，例如谓词值的类型和字段在元组中的偏移量，直到运行时才会确定，这会进一步加重问题。由于这些不确定性，编译器无法把很大一部分代码优化技术应用到迭代器实现上。

## III. 相关工作

人们早已知道，处理器面向在基本数据类型上执行复杂数值运算而设计，并不特别适合数据库负载。[23] 的作者不仅用响应时间衡量性能，也使用硬件性能指标，并提出多项修改来改善连接算法在现代处理器上的行为。在存储层方面，人们很快意识到，成熟的 N 元存储模型（N-ary Storage Model，NSM）会惩罚一种常见情形：查询求值只需要每条元组中的少数字段。由此出现了垂直分区和分解存储模型（Decomposed Storage Model，DSM）[9]，其中每个元组字段分别存储。这种布局减少查询求值需要接触的数据量，并允许算子使用数组计算。然而，改变存储布局意味着必须重新审视全部查询求值算法；它不仅影响查询引擎设计，也影响并发控制等其他 DBMS 正交部分。文献 [2] 提出了跨属性分区（Partition Attributes Across，PAX）存储模型：页仍提供元组级接口，但页内元组采用垂直分区，从而大幅改善缓存局部性。这种混合方案兼具 NSM 与 DSM 的优点，而数据库系统只需作适度修改。

在迭代器模型下，文献 [25] 提出缓冲算子，以提高算子间通信时的元组粒度。这样可以明显减少算子流水线上跨算子的迭代器调用，但不会减少算子主体中的求值函数调用。文献 [20] 则提出把多个聚合操作合并进一个阻塞算子，通过数组计算在一系列元组上执行这些操作。各聚合函数共有的计算只执行一次，并保存为中间结果；聚合值用数组计算求得，这种技术更符合现代处理器的超标量设计。

当时主存查询执行的先进代表是 MonetDB [3], [18]。除垂直分解外，它的整个查询引擎都建立在数组操作这一概念之上，并在该框架中发展了基数聚簇哈希连接（radix-cluster hash join）等复杂查询处理技术。MonetDB 引擎的数据流不同于传统 DBMS，但它仍是一种与 DSM 紧密绑定的基于算子的方法；同时，它要求物化所有中间结果，因而减少了跨不同查询算子利用缓存局部性的机会。这些限制促成了 MonetDB/X100 [4], [26]：它把文献 [20] 的阻塞算子思想与按列存储布局结合起来，使用复合的向量化原语执行全部计算，从而取得可与手写实现相比的性能。

预取也是受到关注的方向，文献 [7], [8] 给出了在哈希连接求值中使用软件预取的方法。软件预取虽然可能缩短响应时间，却需要根据 CPU 频率、缓存延迟和运行时负载动态计算预取距离。计算不准确时，要么无法及时预取所需数据，要么把近期并不需要的数据带入缓存，造成缓存污染。此外，缓存控制器只把软件预取指令视为提示；如果已有尚未完成的取数请求，它可以忽略这些指令。因此，本文实现没有采用软件预取。

System R [5] 已经使用过一种原始形式的代码生成，但迭代器模型 [11] 的采用此后主导了查询引擎设计。Daytona 数据管理系统 [13] 重新采用代码生成，可以即时生成面向具体查询的代码；然而，它依赖操作系统提供传统 DBMS 的大部分功能，例如缓冲和并发控制。文献 [21] 的作者也给出了一个使用动态查询编译的 Java 原型系统。这个系统仍用迭代器进行算子通信与执行，代码生成器只用于移除迭代器主体中的虚函数；它也没有提出新的查询处理选择，例如连接完全通过预先构建的连接索引来求值。

## IV. 系统概览

本节介绍以代码生成为高效查询求值基本原则的查询引擎。系统名为 HIQUE（Holistic Integrated Query Engine），用 C/C++ 实现，在 GNU/Linux 上由 GNU GCC 编译，采用多个客户端与查询引擎通信的传统 client-server 模型。

### 存储层

原型使用 NSM，tuple 连续存入 4096-byte page；但系统并不绑定 NSM，换用 DSM 或 PAX 时本文方案仍然适用。每张表各存于一个磁盘文件；storage manager 维护 table/file 对应关系和 schema。采用 LRU replacement policy 的 buffer manager 负责缓冲磁盘页并提供 concurrency control。除普通文件外，系统还使用节省内存的 fractal B+-tree 索引 [6]，每个物理页切成四个 1024-byte tree node。

### 查询处理

图 2 展示查询经过系统的路径。第一个模块是 SQL parser。SQL grammar 支持带 equi-join 的合取查询，以及任意 grouping 和 sort order；它不支持聚合值中的统计函数和 nested query，但我们认为这两项都是直接扩展，不限制整体求值模型的一般性。

![图 2：HIQUE 整体查询引擎概览](assets/precise-manual-figure-02-engine-overview.png)

图 2 展示 HIQUE 的端到端路径：Parser 结合 DB catalog 产生内部查询表示，Optimizer 结合 DB statistics 输出 scheduled plan，Generator 根据 templates、data staging 和 holistic algorithms 生成 source code，再由 compiler 生成 shared-library file，Executor 动态加载并在 DB tables 上执行。

SQL parser 根据 system catalogue 检查查询是否合法，并向 optimizer 输出内部查询表示。Optimizer 采用以最小化中间结果规模为目标的 greedy approach 选择最优求值计划；它还为每个算子选择最优求值算法，并设置实例化 code generator 模板所需的参数，详见第 V 节。

Optimizer 输出按拓扑排序的 operator descriptor 列表 $O$。每个 $o _ i$ 的输入是 base table，或者 $o _ j$（ $j \lt i$）的输出；descriptor 包含实现该算子所用的算法，以及初始化该算法代码模板所需的附加信息。由于只有一个 root operator，这个列表实际上描述了一棵已经调度的物理算子树。列表开头依次是查询中的 join，后面是 aggregation 和 sorting；后两者是一元算子，各至多有一个 descriptor。Optimizer 跟踪 interesting order [5] 和 join team [12]，把 join 操作组合在一起，并尽量避免重复排序。

Code generator 遍历拓扑有序列表，为每个算子分两步生成代码：

1. **Data staging：**扫描全部输入表，应用全部 selection predicate，并丢弃输入中不再需要的字段，以缩小 tuple、提高后续处理的 cache locality。后继算子所需的 sorting、partitioning 等预处理与 scan code 交织执行。输出随后被物化；若 staging 后的输入足以放入主存，则不写入磁盘。
2. **Holistic algorithm instantiation：**生成实现该算子的 source code；该代码是第 V-B 节所述相应整体算法模板的一次实例化。

Code generator 根据各算子的输入关系组合其实现，产生一个供 query engine 调用、求值完整查询的最终函数；随后把所有生成函数写入新的 C source file。Source code 生成后，系统调用 compiler，把文件编译成面向该具体查询、可应用激进 compiler optimization 的 shared library。Query executor 动态链接并加载这个文件，调用其中的函数求值查询，再把输出发送给客户端。

## V. 代码生成

本节介绍代码生成器的实现。代码生成器采用基于模板的方法：每种算法都表示为一个抽象模板，再依据执行计划实例化。

### A. 实现

代码生成器接收优化器的输出，即按拓扑排序的算子描述符列表 $O$，并生成一个包含查询专用代码的 C 源文件。生成算法见图 3。前文已经提到，每个描述符都包含要实现的算法，以及实例化代码模板所必需的参数。这些参数包括谓词的数据类型、算子输入是基表还是中间结果等输入信息，以及输出模式。

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
5.      generate C function cs_mn for staging i_n
6.    retrieve code template tj_m in TJ for j_m's algorithm
7.    instantiate tj_m for j_m
8.    generate C function cj_m to evaluate join
9.  if there exists aggregate operator a in O
10.   retrieve code template ts_a in TS to stage a's input
11.   instantiate ts_a for a
12.   generate C function cs_a for staging a
13.   retrieve code template t_a in TA for a's algorithm
14.   instantiate t_a for a
15.   generate C function c_a to compute aggregate values
16. if there exists ordering operator s in O
17.   retrieve code template t_s in TS for sorting
18.   instantiate t_s and generate sorting C function c_s
19. traverse O to compose the function c_m calling all functions
20. write all generated functions to a new source file F
21. return F
```

代码生成按如下过程进行：生成器遍历算子描述符列表，先处理连接算子（图 3 第 1–8 行），再处理可能存在的聚合算子（第 9–15 行）和排序算子（第 16–18 行）。对每个算子，生成器产生两类函数：（a）准备输入，每张输入表各有一个函数；（b）执行该算子的算法。这些函数通过取出适当的代码模板——例如连接的第 2、6 行——并按照算子描述符中的参数实例化模板——例如第 4、7 行——来构造。

列表 $O$ 中的算子描述符包含算子之间如何连接的信息，因此代码生成的最后一步是再次遍历 $O$，产生一个主组合函数。该函数按正确顺序调用所有求值函数，确保正确分配和释放资源，并把输出发送给客户端（第 19 行）。最后，全部生成函数都按照生成时的顺序写入一个新的 C 源文件。

### B. 算法与代码模板

整体算法的目标，是利用代码生成把众所周知的数据处理算法定制成硬件效率更高的实现。面向每个查询生成代码，可以执行以下查询级优化：（a）属性类型预先已知，因此数据访问和谓词求值原本各自需要的函数调用，可以分别退化为指针类型转换和基本数据比较；（b）每一页中的定长元组可以通过指针运算和直接引用作为数组访问。系统了解访问内存层次各级时的延迟差异。第 II 节已经说明，在 D1 缓存之外，从顺序访问切换为随机访问甚至可能让延迟翻倍；在内存层次中向下移动一级，延迟会增加一个数量级。因此，生成代码会：（a）按能够装入 D1 或 L2 缓存的数据块检查输入；（b）在缓存驻留数据上执行多项操作，以最大化复用；（c）尽量只让随机访问模式出现在 D1 缓存内，因为只有在这一层，顺序取数与随机取数的代价相同。

代码清单 1 给出优化后的 scan-select 模板：

**代码清单 1：优化后的 table scan-select。**

```c
1  // loop over pages
2  for (int p = start_page; p <= end_page; p++) {
3    page_str *page = read_page(p, table);
4    // loop over tuples
5    for (int t = 0; t < page->num_tuples; t++) {
6      void *tuple = page->data + t * tuple_size;
7      int *value = tuple + predicate_offset;
8      if (*value != predicate_value) continue;
9      add_to_result(tuple); // inlined
10 }}
```

作为生成代码的示例，代码清单 1 给出了过滤一张表中元组的 C 代码。利用类型信息——此例中为 `int`——并采用数组访问，可以消除除装入页面和生成输出之外的所有函数调用，节省大量 CPU 周期。由于谓词直接在基本数据类型上求值，执行的指令数量也会减少。数组计算还使代码能够利用处理器的超标量设计。内层循环没有函数调用，同时通过引用直接访问元组及其字段，这进一步帮助编译器优化生成代码，把数据高效分配到寄存器并促进缓存复用。

代码清单 2 给出 join evaluation 的 nested-loops 模板：

**代码清单 2：用于 join evaluation 的 nested-loops 模板。**

```c
1  /* Inlined code to hash-partition or sort inputs */
2
3  hash join: // examine corresponding partitions together
4  for (k = 0; k < M; k++) {
5    // update page bounds for both k-th partitions
6    hybrid hash-sort-merge join: // sort partitions
7
8    for (p_1 = start_page_1; p_1 <= end_page_1; p_1++) {
9      page_str *page_1 = read_page(p_1, partition_1[k]);
10     for (p_2 = start_page_2; p_2 <= end_page_2; p_2++) {
11       page_str *page_2 = read_page(p_2, partition_2[k]);
12
13       for (t_1 = 0; t_1 < page_1->num_tuples; t_1++) {
14         void *tuple_1 = page_1->data + t_1 * tuple_size_1;
15         for (t_2 = 0; t_2 < page_2->num_tuples; t_2++) {
16           void *tuple_2 = page_2->data + t_2 * tuple_size_2;
17
18           int *value_1 = tuple_1 + offset_1;
19           int *value_2 = tuple_2 + offset_2;
20           if (*value_1 != *value_2) {
21             merge join: // update bounds for all loops
22             continue;
23           }
24           add_to_result(tuple_1, tuple_2); // inlined
25 }}}}}
```

#### 输入准备

输入准备算法包括排序、分区和一种混合方法。排序先在能够装入 L2 缓存的输入分区上使用优化版快速排序，再把这些分区合并。分区可以是细粒度的，即把属性值映射到分区；也可以是粗粒度的，即用哈希与取模运算把元组导向分区。当分区属性的不同取值足够少，使“值到分区”的映射能够轻松装入缓存层次时，系统使用细粒度分区。对于每条输入元组，系统查询映射以找到对应分区；具体做法是维护一个排好序的属性值数组，并用二分查找完成查询。如果目录延伸到较低的缓存层级，搜索目录可能触发代价高昂的缓存未命中，此时粗粒度分区更高效。

不过，粗粒度分区生成的每个分区包含多个属性值，因此对分区排序可以提高后续处理中的复用。这形成了本文所称的一类混合哈希排序算法，可用于某些连接求值和聚合场景。如果分区数量足够多，使最大分区可以装入 L2 缓存，这类算法就会表现良好。

#### 连接求值

所有连接求值算法都使用代码清单 2 所示的公共嵌套循环模板；各算法之间的区别在于其输入如何准备。该模板采用类似数组的顺序访问模式，有利于在第一次遍历每个页面中的元组时使用硬件预取器。后续元组迭代会在缓存驻留的页面上进行，不会发生缓存未命中。

归并连接假定输入已经预先排序（第 1 行）。连接求值随后线性检查输入表；第 4 行的 $M$ 被设为 1。随着归并过程推进，系统不断更新循环边界（第 21 行），既包括每张表的起始页和结束页，也包括每页的起始元组和结束元组。一个条件变量控制这一过程，它可以取三个值：第一个值表示当前元组之间不匹配；第二个值表示已经找到至少一个匹配，应继续扫描内层元组以寻找更多匹配；最后一个值表示内层匹配元组组已经耗尽，因此需要推进外层元组，并回溯到这组内层匹配元组的开头。如果外层循环的每条元组与内层循环中的元组至多匹配一次，那么两个输入的访问模式都是线性的；回溯到一小组内层匹配元组的开头时，也很可能命中缓存，因为小组通常会驻留在 L2 甚至 D1 缓存中。

分区连接建立在 Grace 哈希连接 [17] 之上。两张输入表首先分别被细粒度或粗粒度地划分为 $M$ 个分区（第 1 行），然后用嵌套循环连接对应分区（第 3–5 行）。在细粒度分区中，对应分区内的所有元组都会匹配；在粗粒度分区中，每条元组可能与对应分区内零条、部分或全部元组匹配。为此，系统不使用哈希表，因为哈希表会导致不可控制的随机访问模式；系统选择先对分区排序（第 6 行），再对每对对应分区执行归并连接。本文把这一算法称为混合哈希排序归并连接。还要注意，如果每个分区的大小小于 L2 缓存的一半，那么在连接之前才对一对对应分区排序——而不是在数据准备期间排序——可以确保它们在连接求值时都驻留在 L2 缓存中。

嵌套循环模板还能以流水方式求值多个连接，而不物化中间结果，从而大幅减少内存操作和处理器停顿。这适用于带有连接组（join team）的多路连接查询，也就是多张表按同一个键连接的查询。这类查询很常见，例如星型模式查询或主键—外键连接。本文模型通过增加循环嵌套来处理哈希组和有趣顺序等概念。为了支持连接组，需要对代码清单 2 的模板略作修改：首先正确准备所有输入表，即排序或分区；然后对每张输入表，代码生成器产生一个页面循环和一个元组循环。所有页面循环排在元组循环之前，并且两组循环采用相同的表顺序。代码布局类似循环分块优化技术 [16] 建议的布局，能够增强缓存局部性。

#### 聚合

聚合算法取决于输入准备。排序聚合假定输入已经按分组属性排序，随后线性扫描输入，识别不同分组并即时求出每个分组的聚合结果。对于混合哈希排序聚合，输入先按第一个分组属性进行哈希分区，再按全部分组属性对每个分区排序；之后，只需分别单趟扫描每个有序分区即可完成聚合。

另一种选择是为每个分组属性使用值目录。如果全部分组属性的目录总大小足够小，可以装入缓存层次并避免目录查询触发缓存未命中，就适合使用这种方法。此时，映射聚合无需任何预先准备，只需对输入作一次线性扫描。系统为每个分组属性维护一个值目录——图 4(a) 给出了三个属性的情形——并为每个聚合函数维护一个存放聚合值的数组。

图 4 的例子中， $R.a = 200$、 $R.b = C$、 $R.c = \mathrm{Asia}$ 对应的聚合数组偏移量为 $1 \cdot 3 \cdot 4 + 2 \cdot 4 + 1 = 21$。

![图 4：聚合的 group directory 与 offset 计算](assets/precise-manual-figure-04-group-directories.png)

一般地，假设 $M _ i$ 是属性 $i$ 的映射， $M _ i[v]$ 给出属性 $i$ 的取值 $v$ 的标识符，那么跨 $n$ 个属性分组时，可以把元组 $(v _ 1,\ldots,v _ n)$ 的多维映射化为下面的标量：

$$
\mathrm{Offset}(v_1,\ldots,v_n)=\sum _ {i=1}^{n}\left(M_i[v_i]\prod _ {j=i+1}^{n}|M_j|\right).
$$

其中， $|M _ i|$ 是属性 $i$ 的映射表大小。该公式把每种取值组合映射到聚合数组中的唯一偏移量，每个聚合数组都包含 $\prod _ {i=1}^{n}|M _ i|$ 个值。图 4(b) 展示了公式的一个应用示例。聚合求值按如下方式推进：对每条输入元组，使用分组属性映射找出该元组所属分组的偏移量；然后，用各聚合函数的当前值更新每个聚合数组中该分组对应的变量。

在所有情形下，代码生成器都会内联识别分组与应用聚合函数的代码。没有函数调用对聚合尤其重要：它让编译器可以为这种计算密集型操作生成广泛复用寄存器的可执行代码。优化后的代码减少由栈交互打断执行序列的频率，避免重复求值公共算术表达式，并减少处理每条元组所需的数据访问次数。

### C. 开发经验

为查询求值设计代码生成器时，工程上的主要难题有三项：（a）在不同算法之间识别公共代码模板；（b）不同算子之间不再有公共接口，因而需要重新解决算子的互连；（c）验证全部受支持操作的生成代码都正确。

整体求值模型缓解了这些问题。它的主要优势是，各类操作的算法都利用通用代码模板。数据准备使用代码清单 1 的模板，排序和分区操作可以交织进这段代码。连接求值始终使用代码清单 2 的嵌套循环模板；不同算法之间的差异，要么由输入准备处理，要么由循环内部的额外步骤处理。例如，哈希连接包含代码清单 2 第 3–5 行对应的代码段，排除第 6、21 行；把后两个代码段也包括进来，就会把算法变为混合哈希排序归并连接。聚合则扩展代码清单 1 的模板，注入跟踪不同分组和计算聚合函数的代码。此外，算子之间通过以下方式连接：在缓冲池中把中间结果物化为临时表，再将它们以流式方式传给后继算子。

开发 HIQUE 的经验验证了上述主张。引入新算法乃至新算子时，扩展解析器和优化器所需的工作，比扩展代码生成器更多。作为引入算法的一般方法，我们会先为新算法建立一个模型实现，并把它与现有模板比较。多数情况下，新算法相对现有求值算法只差几行代码；接下来再扩展模板与代码生成器以支持新算法。代码生成器输出的是 C 源文件，这一点也有助于上述过程：编译器帮助开发者轻松识别生成代码中的错误，从而减少完整支持新算法所需的迭代次数。

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

我们还把硬件性能事件用作指标，并用 OProfile [19] 从 CPU 的性能事件计数器收集采样数据。执行时间被分解为指令执行、D1 缓存未命中停顿、L2 缓存未命中停顿和其他流水线资源停顿。[^2] 为计入硬件预取，对已经预取的缓存行使用顺序访问延迟，对所有其他缓存未命中使用随机访问延迟。这样可以近似计算缓存未命中的代价；由于缓存的非阻塞设计允许 CPU 在取数期间继续执行指令，该计算不是精确值，但仍能很好地近似实际缓存未命中停顿时间。

[^2]: “其他流水线资源停顿”是指并非由 D1 或 L2 缓存未命中引起的资源停顿，另见文献 [15]。

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

Aggregation Q1 使用 hybrid hash-sort：staging 主导 execution time，后续只需单趟扫描已排序 partition。由于各版本采用相同 partitioning 和 sorting 实现，memory stall cost 相近；HIQUE 仍比 iterator 快 1.61 倍，差异来自 instruction、data access 和 function call 减少。D1 prefetch efficiency 升至约原来的 3 倍，所有实现的 L2 prefetch efficiency 接近 90%。

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

Multi-way 实验把一张含 1,000,000 条 tuple 的表与数量可变、各含 100,000 条 tuple 的表按单一 join attribute 连接；连接表的总数从 2 增至 8。所有 tuple 都是 72 bytes，输出 cardinality 恒为 1,000,000。比较对象包括 binary iterator merge join、HIQUE 生成的对应 binary 版本，以及启用 join team 后的 HIQUE merge/hybrid join。即使 binary HIQUE 也大幅优于 iterator；join team 又通过避免 intermediate result materialization 显著缩短时间，连接 8 张表时差距达到 3.32 倍。

Join selectivity 实验连接两张各有 1,000,000 条 72-byte tuple 的表，每个 outer tuple 的 inner match 数量从 1 增至 1,000。随着 iterator call 增多、join evaluation cost 超过所有实现共同承担的 input staging，差距迅速扩大，在每个 outer tuple 匹配 1,000 条时达到 5 倍。

Aggregation 实验采用 1,000,000 条 72-byte tuple、两个 sum function 和一个 grouping attribute，把 distinct value 数量从 10 调到 100,000。Group 很少时，map aggregation 的 iterator 与 holistic 版本都很高效；sort 和 hybrid aggregation 对 group 数量只受中等程度影响。当 map 的 value directory 和 aggregate array 跨出 L2 后，sort/hybrid 反而更快，100,000 个 group 时差距接近 2 倍。

### C. TPC-H benchmark

最后一组实验采用标准且更真实的 TPC-H benchmark [24]。我们把 HIQUE 与三个数据库系统比较：（a）PostgreSQL 8.2.7，广泛使用的高性能开源 DBMS，采用 NSM 和 iterator model；（b）匿名商业系统 System X，同样采用 NSM 和 iterator，但用 software prefetch instruction 减少 cache-miss stall；（c）MonetDB 5.8.2，采用 DSM storage layer 和 column-wise evaluation algorithm 的 architecture-conscious DBMS。这个组合分别代表传统 I/O-optimized 设计、用 software prefetch 衔接 I/O-bound 与 CPU-bound execution 的设计，以及面向 main-memory execution 优化的设计。

我们用 benchmark generator 生成 scaling factor 1 的数据集。导入各系统前未对表作排序等任何修改；不含索引的 raw data 约 1.3 GB，能放入实验机器主存。所有系统都建立索引、以最高详细级别收集统计信息，并把内存参数设置为允许 in-memory execution。实验使用 TPC-H Q1、Q3 和 Q10。后两者含有不能作为 join team 求值的高选择性 join predicate，并包含 grouping attribute 和 aggregate function 数量不一的 aggregation。TPC-H tuple 很宽、跨越多个 cache line，而每个查询实际只需要少数字段；因此预期 MonetDB 会从 vertical partitioning 获益，优于 NSM 系统。

![图 8：TPC-H 查询性能对比](assets/precise-manual-figure-08-tpch-queries.png)

图 8 比较 TPC-H Q1、Q3、Q10 上 PostgreSQL、System X、MonetDB 与 HIQUE 的响应时间。

Q1 对几乎整张 `lineitem` 表（约 5,900,000 条 tuple）做 aggregation，输出 4 个 group。两个 grouping attribute 的 distinct value cardinality 乘积仅为 6，因此最合适的整体算法是 map aggregation。HIQUE 把 selection、grouping 和 aggregation 全部内联到一个无 function call、面向高效 register utilization 的紧凑 code block 中。HIQUE 用时 0.356 s，MonetDB 1.376 s、System X 37.185 s、PostgreSQL 59.353 s；即比 MonetDB 快约 4 倍，比另外两个基于 NSM 的系统快约两个数量级，其中相对 PostgreSQL 达到 167 倍。实测 662.16 million CPU cycles，与 MonetDB/X100 的 DSM 方案相当，并比其 NSM 方案快 30% [26]。因此，我们认为 HIQUE 生成的代码等同于 hard-coded implementation，至少在 NSM 系统的 aggregation 上达到最高效率。

Q3/Q10 同时测试 join、aggregation 和 sorting。Holistic optimizer 在进一步处理前先 stage 全部输入；TPC-H tuple 很宽而查询只使用其中一小部分，这一步代价较高，恰好有利于只取所需字段的 DSM 系统。HIQUE 相对 MonetDB 在 Q3 上快 34.5%，在 Q10 上慢 18.1%；但相对两个 NSM 系统仍快 2.2-11.1 倍。

这些结果证明整体求值在真实查询负载中可行：整体模型简化代码并提高执行时的 cache locality，减少求值所需的 instruction 和 data access，因而降低 processor 和 memory subsystem 压力、显著加速查询。这使采用 NSM 的 HIQUE 达到了此前通常只能由 vertical-partitioning 系统实现的性能。

### D. 代码生成成本

面向每个查询生成代码的缺点，是发出并编译查询专用源代码会产生额外开销。为了量化这一开销，表 III 给出 TPC-H 查询的准备成本，分别列出查询解析、优化、代码生成与编译时间，以及生成源文件和共享库文件的大小。

| TPC-H Query | Parse ms | Optimize ms | Generate ms | Compile -O0 ms | Compile -O2 ms | Source bytes | Shared library bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| #1 | 21 | 1 | 1 | 121 | 274 | 17,733 | 16,858 |
| #3 | 11 | 1 | 2 | 160 | 403 | 33,795 | 24,941 |
| #10 | 15 | 1 | 4 | 213 | 619 | 50,718 | 33,510 |

解析、优化和生成代码所需时间很短，合计低于 25 ms。编译生成代码耗时更长，而且取决于优化级别：不作优化、使用 `-O0` 编译器选项时需要 121–213 ms；把优化级别提高到 `-O2` 后需要 274–619 ms。生成的源文件与共享库文件大小都只有约 50 KB。

准备时间并非可以忽略；对于运行时间很短的查询，它可能占执行时间的很大一部分。此时最好不要应用会增加编译时间、而执行收益又不明显的编译器优化。此外，系统通常会保存频繁执行或最近执行过的查询的预编译、预优化版本；HIQUE 同样可以这样做，尤其是考虑到生成的二进制文件很小。在多数情况下，性能收益仍然超过代码生成成本。

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
