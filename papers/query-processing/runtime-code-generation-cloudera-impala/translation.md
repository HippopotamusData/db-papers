---
paper_id: runtime-code-generation-cloudera-impala
title: Runtime Code Generation in Cloudera Impala
language: zh-CN
source: source.pdf
---

# Runtime Code Generation in Cloudera Impala（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 摘要

本文讨论如何在 SQL 引擎中使用运行时代码生成来改善查询执行时间。代码生成允许只在运行时才知道的查询特定信息，例如列类型和表达式操作符，在性能关键函数中像编译期已知一样使用，从而得到更高效实现。论文介绍 Cloudera Impala，一个面向 Hadoop 的开源 MPP 数据库。Impala 使用代码生成，查询时间最高可加速 5 倍。

## 1. 引言

Cloudera Impala 是构建在 Hadoop 生态上的开源 MPP 数据库。Hadoop 使用 HDFS 和 HBase 存储大量数据，并以 MapReduce 作为处理框架。Impala 的目标是结合 Hadoop 的灵活性和可扩展性，以及商业 MPP 数据库的性能和 SQL 支持。Impala 执行查询比已有 Hadoop 方案快 10 到 100 倍，并接近商业 MPP 数据库，使用户能对大数据执行交互式探索分析。

Impala 从底层设计上尽量利用现代硬件和高效查询执行技术。它面向分析负载而不是 OLTP，因此复杂、长时间、CPU-bound 查询很常见。运行时代码生成是 Impala 广泛使用的优化技术之一。Impala 使用 LLVM 在运行进程中生成、优化和执行查询特定函数。

LLVM 是编译器库和工具集合。与传统独立编译器不同，LLVM 模块化且可复用，应用程序可以在运行中调用 JIT 编译，同时获得现代优化器和多架构机器码生成能力。

## 2. 运行时代码生成的优势

Impala 使用运行时代码生成，为性能关键函数生成查询专用版本，尤其针对会在一次查询中执行许多次、因而占据大部分总耗时的“内层循环”函数。例如，把数据文件中的一条记录解析为 Impala 内存 tuple 的函数，需要对扫描到的每一条记录调用一次；扫描大表时，调用次数可能达到数万亿。因此，即使每次调用只减少几条指令，也可能显著缩短查询时间。

如果没有代码生成，为了处理编译期未知的运行时信息，函数通常不得不保留额外开销。例如，只处理整数的记录解析函数会比同时支持字符串、浮点数等类型的通用函数更快，但待扫描文件的 schema 在编译期并不知道，所以预编译系统只能选择最通用的实现，即使运行时已经知道实际只需其中很小一部分功能。

代码生成允许系统把运行时变量当作编译期常量嵌入性能关键函数，从生成结果中删除解释这些查询常量所需的开销。查询不同，生成的专用函数也可能不同。

原文 Figure 1 用 `MaterializeTuple()` 展示了解释版本与 codegen 版本的差异。该图本质是代码对比，因此这里转写为代码块而不是嵌入截图。

**图 1：展示运行时代码生成可实现优化的示例函数。**

解释版本需要循环 slot、读取 `offsets_` 和 `types_`，再按类型分派：

```cpp
void MaterializeTuple(char* tuple) {
  for (int i = 0; i < num_slots_; ++i) {
    char* slot = tuple + offsets_[i];
    switch(types_[i]) {
      case BOOLEAN:
        *slot = ParseBoolean();
        break;
      case INT:
        *slot = ParseInt();
        break;
      case FLOAT: ...
      case STRING: ...
      // etc.
    }
  }
}
```

codegen 版本把运行时常量内联到专用函数中，去掉循环和类型分派：

```cpp
void MaterializeTuple(char* tuple) {
  *(tuple + 0) = ParseInt();      // i = 0
  *(tuple + 4) = ParseBoolean();  // i = 1
  *(tuple + 5) = ParseInt();      // i = 2
}
```

代码生成把这些运行时常量固化到专用函数中，主要带来三类优化：

- **消除条件分支。** 解释函数必须用 `if` 或 `switch` 处理的运行时信息，在生成函数中已经解析为唯一分支。以 Figure 1 为例，循环次数和每个 slot 的类型都已知，因此可以展开循环并消除类型分支。分支指令会妨碍指令流水线和指令级并行，这通常是收益最大的优化之一。
- **消除内存加载。** 如果一次加载在函数每次调用时都会得到不同结果，例如加载 tuple 中的实际值，就无法消除；但若每次调用都会得到相同结果，就可以直接用常量替换。Figure 1 中的 `offsets_` 和 `types_` 在查询开始时生成、整个查询期间不变，因此展开循环后可把数组内容直接内联。
- **内联虚函数调用。** 虚调用本身代价较高，而且阻止编译器内联被调函数。若运行时知道对象的具体类型，代码生成可以把虚调用替换成对具体函数的直接调用，再将其内联。表达式树尤其受益：Impala 中每种表达式通过覆写基类虚函数实现，并递归调用子表达式；对于加法等很简单的操作，调用成本甚至高于计算本身。解析并内联这些调用后，表达式树可直接求值，不再产生逐节点调用开销。

Impala 的经验是，某些表达式求值、hash、比较和聚合逻辑经代码生成后可获得显著加速。

![图 2：表达式树优化示意图](assets/precise-manual-figure-02-expression-tree.png)

图 2：表达式树优化示意图。左侧解释执行通过表达式树和函数指针逐层求值；右侧 codegen 后直接得到 `(col1 + 10) * 7 / col2` 形式的表达式，避免虚函数调用和树遍历。函数内联还提高了指令级并行度，并让编译器能够跨表达式执行公共子表达式消除等进一步优化。

## 3. 使用 LLVM 生成代码

### 3.1 LLVM IR

Impala 不直接生成机器码，而是生成 LLVM IR。IR 是低层、类型化的中间表示，可以被 LLVM 优化并编译为目标机器码。Impala 将运行时已有的通用函数编译为 LLVM bitcode，并在查询到达时把这些函数与查询特定 IR 组合。

### 3.2 IRBuilder

LLVM 的 C++ API 提供 `IRBuilder` 类，可以用程序逐条构造 IR 指令。这类似直接用汇编语言编写函数：表达能力完整，却相当繁琐。在 Impala 中，用 IRBuilder 生成一个 IR 函数的 C++ 代码，通常比同一函数的解释版本长许多倍。它适合必须从头构造的查询专用逻辑，但并不是我们的首选工程路径。

### 3.3 编译为 IR

相比用 IRBuilder 从零构造函数，Impala 通常更愿意先用 C++ 编写函数，再通过 Clang 编译成 IR，并在运行时注入查询专用信息。系统还会把同一函数同时交叉编译为 IR 和本机代码，从而能够方便地选择解释版本或代码生成版本。这对调试很重要：开发者可以判断错误来自函数本身还是代码生成过程，也可以用 `gdb` 调试本机函数。

论文发表时，Impala 修改已编译 IR 的机制还比较有限：它只能把对解释函数的调用替换为等价的查询专用生成函数。表达式节点的虚函数会同时编译为 IR 和本机代码；禁用代码生成时直接运行通用本机实现，启用时则递归查找对子表达式的调用，并替换为生成函数调用。

这种机制足以消除虚调用，却还不能完整实现第 2 节所述的条件分支和内存加载消除。此类函数当时仍需用 IRBuilder 生成。我们正在开发新的预编译 IR 变换框架：对 Figure 1 的 `MaterializeTuple()`，计划先利用已知的 `num_slots_` 展开循环，再把对 `offsets_` 和 `types_` 的访问替换为实际值。完成这套变换后，开发者便能继续用 C++ 编写通用函数，同时比手写 IRBuilder 更容易、更快速地生成专用实现。

这种方式兼顾工程可维护性和性能：开发者仍用 C++ 写通用逻辑，运行时再通过 LLVM 把它专门化。

## 4. 用户自定义函数

Impala 提供 C++ 用户自定义函数（UDF）API。最传统的写法是用 C++ 实现 UDF，编译为共享对象，再在运行时动态链接。不过，既然 Impala 已经能够编译和执行 Clang 生成的 IR，用户也可以把 UDF 编译为 IR，而不是共享对象。这样 LLVM 就能跨用户函数边界进行内联，使 UDF 获得与 Impala 内建函数相同的性能。

这套架构还让其它语言更容易接入。任何拥有 LLVM 前端的语言都可以生成 UDF，而无需修改查询引擎。例如 Numba 可以把 Python 编译成 IR；按论文提出的方式，开发者编写的 Python UDF 甚至可能比静态编译到共享对象的 C++ UDF 更快，因为前者能够参与跨函数内联。

## 5. 实验结果

Table 3 的实验运行在 10 节点集群上，数据集是 6 亿行 Avro 数据。第一个查询只统计总行数，不需要真正解析 Avro 记录，代码生成只能优化已经很简单的计数聚合，因此收益较小。第二个查询统计单列，需要解析 Avro 数据以识别 NULL，代码生成相对第一个查询多带来约 60% 的收益。最后的 TPC-H Q1 包含多个聚合、表达式和 `GROUP BY`，因此加速显著增大。

表 3 展示随着查询复杂度增加，code generation 带来的端到端收益也增加：

| Query | Code generation disabled | Code generation enabled | Speedup |
| --- | ---: | ---: | ---: |
| `select count(*) from lineitem` | 3.554 sec | 2.976 sec | 1.19x |
| `select count(l_orderkey) from lineitem` | 6.582 sec | 3.522 sec | 1.87x |
| `TPCH-Q1` | 37.852 sec | 6.644 sec | 5.70x |

原文 Figure 3 给出用于实验的 TPCH-Q1 查询，这里转写为 SQL：

**图 3：TPC-H Q1 查询。**

```sql
select
  l_returnflag,
  l_linestatus,
  sum(l_quantity),
  sum(l_extendedprice),
  sum(l_extendedprice * (1 - l_discount)),
  sum(l_extendedprice * (1 - l_discount) * (1 + l_tax)),
  avg(l_quantity),
  avg(l_extendedprice),
  avg(l_discount),
  count(1)
from lineitem
where l_shipdate <= '1998-09-02'
group by l_returnflag, l_linestatus
```

实验说明代码生成不是单独决定查询性能的全部因素，但它能显著降低 CPU-bound 查询中的解释和分派开销。对 MPP 系统而言，每个节点上的 CPU 节省会累积为整体查询延迟下降。

表 4 使用硬件计数器展示 TPCH-Q1 的指令数和分支数下降：

| 配置 | # Instructions | # Branches |
| --- | ---: | ---: |
| Code generation disabled | 72,898,837,871 | 14,452,783,201 |
| Code generation enabled | 19,372,467,372 | 3,318,983,319 |
| Speedup | 4.29x | 3.76x |

这些计数由 Linux `perf` 的硬件计数器采集，覆盖整个查询执行过程，因此也包含尚未受益于代码生成的路径。

![图 4：TPC-DS 查询在启用/禁用 code generation 下的执行时间](assets/precise-manual-figure-04-tpcds-codegen.png)

图 4：TPC-DS 查询在启用和禁用 code generation 下的执行时间。浅色柱为启用 codegen，深色柱为禁用 codegen。

Figure 4 使用 10 节点集群和 scale factor 1 TB 的 Parquet 数据集，运行若干略作修改的 TPC-DS 查询。它们没有达到 TPC-H Q1 的约 5 倍加速，因为部分执行路径尚未实现代码生成：几乎所有这些查询都包含 `ORDER BY`，当时排序不受益于代码生成；Parquet 解析器也尚未使用代码生成。实验选择 Parquet 而非已经支持代码生成的 Avro，是因为若使用 Avro，这些查询会转为 I/O-bound，难以观察 CPU 优化效果。即便如此，每个查询仍获得明显加速，我们预计扩大代码生成覆盖后收益还会提高。

## 6. 结论与未来工作

LLVM 让 Impala 能够实现一个通用 SQL 引擎，同时让每个查询的运行效果接近为该查询专门编写的应用。代码生成从 Impala 最初发布时就已提供，但论文发表时只覆盖部分算子和函数。我们计划继续扩大覆盖范围，以利用更多函数内联和跨函数优化；长期目标是把整棵查询执行树折叠成单个函数，尽量消除内存访问并把状态保留在寄存器中。

另一个进行中的项目是把 Python 开发环境与 Impala 集成，利用 IR UDF 能力，让用户完全在 Python shell 或脚本中编写 UDF，并在 Hadoop 集群上运行，由系统自动封送参数和结果。

## 参考文献

- [1] Erickson, Justin, Greg Rahn, Marcel Kornacker, and Yanpei Chen. "Impala Performance Update: Now Reaching DBMS-Class Speed." Cloudera Developer Blog. Cloudera, 13 Jan. 2014. http://blog.cloudera.com/blog/2014/01/impala-performance-dbms-class-speed/
- [2] "Introducing Parquet: Efficient Columnar Storage for Apache Hadoop." Cloudera Developer Blog. Cloudera, 13 March 2013. http://blog.cloudera.com/blog/2013/03/introducing-parquet-columnar-storage-for-apache-hadoop/
- [3] "LLVM: An Infrastructure for Multi-Stage Optimization", Chris Lattner. Masters Thesis, Computer Science Dept., University of Illinois at Urbana-Champaign, Dec. 2002.
- [4] http://avro.apache.org/
- [5] http://clang.llvm.org/
- [6] http://parquet.io/
- [7] http://llvm.org/docs/doxygen/html/classllvm_1_1IRBuilder.html
- [8] http://llvm.org/docs/LangRef.html
- [9] http://numba.pydata.org
