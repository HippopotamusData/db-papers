---
paper_id: low-latency-compilation-sql-queries-machine-code
title: Low-Latency Compilation of SQL Queries to Machine Code
language: zh-CN
source: source.pdf
---

# Low-Latency Compilation of SQL Queries to Machine Code（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者与机构

- Henning Funke（`henning.funke@cs.tu-dortmund.de`），TU Dortmund University
- Jens Teubner（`jens.teubner@cs.tu-dortmund.de`），TU Dortmund University

## 出版信息

Henning Funke and Jens Teubner. “Low-Latency Compilation of SQL Queries to Machine Code.” PVLDB 14(12):2691–2694，2021。doi:[10.14778/3476311.3476321](https://doi.org/10.14778/3476311.3476321)。

Proceedings of the VLDB Endowment，Vol. 14，No. 12，ISSN 2150-8097。

许可声明：该作品采用 [Creative Commons BY-NC-ND 4.0 International License](https://creativecommons.org/licenses/by-nc-nd/4.0/) 许可。超出该许可范围的使用须通过 `info@vldb.org` 取得授权。版权由原权利人持有，出版权许可给 VLDB Endowment。

## 摘要

查询编译已被证明是最高效的查询处理技术之一。尽管它处理速度快，但额外编译时间限制了适用范围，因为只有当处理时间的改进明显超过编译时间时，这种方法才最有利。最近的研究展示了极低编译时间查询编译器的可行性，可能使查询编译成为更通用的方法。本文及对应现场演示展示 ReSQL 数据库系统的能力。ReSQL 使用中间表示 Flounder IR 实现极低编译时间。与现有基于 LLVM 的技术相比，ReSQL 在真实分析查询中把从 SQL 到机器码的编译时间最多降低 101.1 倍。

## 1. 引言

查询编译通过 JIT 为每个查询生成定制机器码，消除在处理期间解释查询计划和 schema 的开销，从而获得很高的资源效率和吞吐。当查询到达时，查询计划和 schema 已是常量，可以在处理开始前求值。

问题是编译会引入额外时间，直接增加响应时间；因此，查询编译主要用于执行时间的减少明显超过额外编译时间的应用。大数据集很容易摊销这项成本，甚至编译时间长达数秒的 GPU 技术也能如此 [2]。较短的编译时间不仅能直接降低查询响应时间，还会使查询编译更实用：当编译时间足够短时，系统无需为不同类型的工作负载维护不同 backend。已有工作建议在解释执行与编译执行之间无缝切换，以隐藏编译成本 [3]；编译本身足够快时，便无需承担冗余 backend 的额外实现成本。

### 1.1 低延迟查询编译

查询编译通常分两步：先把查询翻译成中间表示（IR），再把 IR 翻译成机器码。尤其是在第二步中，IR 的选择会显著影响编译时间。LLVM 等低层 IR 已被用于实现较短的编译时间 [4, 5]，但用 LLVM 生成机器码仍需数十毫秒；传统非 JIT 技术在这段时间内足以处理数百万 tuple，因而基于 LLVM 的查询编译对较小数据量的收益有限。此前关于 Flounder IR 的工作 [1] 已证明，编译时间远低于 LLVM 的查询编译器是可行的：Flounder IR 采用针对关系工作负载裁剪的特性集，并且在翻译成机器码时只运行很轻量的算法。

![图 1：Flounder IR 的低延迟编译流程](assets/precise-manual-figure-01-flounder-flow.png)

图 1：Flounder IR 能在极短时间内把 SQL 查询编译成机器码。

### 1.2 贡献

本文演示 Flounder IR 如何用于从 SQL 到机器码的完整翻译栈，从而实现查询的低延迟 JIT 编译。该演示允许检查翻译过程中的不同层次，并展示采用 Flounder IR 进行查询编译的实用性。下文先介绍用于低延迟查询编译的 IR（第 2 节），再说明如何使用 ReSQL 数据库系统进行演示（第 3 节），随后评估翻译性能（第 4 节），最后给出总结（第 5 节）。

## 2. 面向快速翻译的低层 IR

Flounder 和 LLVM 之类的低层 IR 用于在查询编译期间实现较短的编译时间。查询编译分为两步：先把查询翻译成 IR，再把 IR 翻译成机器码。相对于查询处理速度，LLVM 的第二步仍然相当耗时；Flounder 则能在短得多的时间内完成机器码翻译，方法是简化 IR，并针对关系工作负载裁剪 IR 及其翻译过程。

下面用一个例子说明两种 IR 的异同。原文页边的查询计划展示一个 hash join probe 算子；假定 hash join build 的代码已经生成，接下来为使用 S 中 tuple 探测哈希表生成代码。下文先给出 probe 功能的高层描述，再比较支持快速编译的两种低层 IR；关于使用 Flounder IR 进行查询编译的更多细节见文献 [1]。

### 2.1 Join Probe 示例

先用 C 代码描述为 hash join probe 生成的功能。这里并不把 C 用作 IR，但用 C 描述该功能最为直接。对于 $R \bowtie S$，其 probe 语义为：

```c
[...] /* child code */
int64_t* entry = null;
while (true) {
  entry = ht_get(ht, s_a, entry);
  if (entry == null) break;
  int64_t r_a = entry[0];
  int64_t r_b = entry[1];
  [...] /* parent code */
}
[...] /* child code */
```

probe entry 初始化为 null，随后在循环中调用 `ht_get(..)` 执行 hash probe。调用返回 null 时，表示没有更多匹配项，循环结束；循环体从哈希表位置 `entry` 读取属性值 `r_a` 和 `r_b`，随后执行后继的父算子。

### 2.2 低层表示

下面给出上述 C 代码所描述的 hash join probe 功能的低层表示。这些 IR 指令的粒度与处理器执行的指令相近，但仍包含若干便于翻译的抽象。原文 Figure 2(a) 给出 LLVM IR，Figure 2(b) 给出对应的 Flounder IR；该图主要是代码/IR，因此这里转写为代码块，并在后文比较两者的异同。

**图 2：hash join probe 算子的中间表示：(a) LLVM IR；(b) Flounder IR。**

LLVM IR 片段：

```llvm
joinProbe:
  ; get previous probe value
  %prev = phi i64* [ null, %scan ], [ %ht_get, %match ]
  ; ht_get(..) call
  %ht_get = call i64* %htGetPtr(%ht, %s_a, %prev)
  ; break when entry = NULL
  %1 = icmp ne i64* %ht_get, null
  br i1 %1, label %match, label %miss

match:
  ; read ht entry
  %addr0 = getelementptr i64, i64* %ht_get, i64 0
  %r_a = load i64, i64* %addr0
  %addr1 = getelementptr i64, i64* %ht_get, i64 1
  %r_b = load i64, i64* %addr1
  [...] ; parent code
  br label %joinProbe

miss:
  [...]
  ; child code
```

Flounder IR 片段：

```asm
[...] ; child code
vreg {entry}
mov {entry}, 0
loop_headN: ; while(..)
  ; ht_get(..) call
  mcall {entry}, {ht_get}, {ht}, {s_a}, {entry}
  ; break when entry = NULL
  cmp {entry}, 0
  je loop_footN
  ; read ht entry
  vreg {r_a}
  vreg {r_b}
  mov {r_a}, [{entry}]
  mov {r_b}, [{entry}+8]
  [...] ; parent code
  clear {r_a}
  clear {r_b}
  jmp loop_headN
loop_footN:
  clear {entry}
[...] ; child code
```

#### 结构

LLVM IR 是 basic block 图：每个块以 label 开始、以 `br` 结束，jump 构成边；编译器可据此重新选择 fall-through。Flounder 只有一条线性指令序列，查询编译器已经确定常见路径，因此不需要通用编译器再做图级布局。较简单的表示直接提高翻译速度。

#### 虚拟寄存器

两者都提供逻辑上无限的虚拟寄存器。LLVM 的名称以 `%` 开头，例如 `%prev`；Flounder 的虚拟寄存器名放在花括号中，例如 `{entry}`。为降低翻译成本，Flounder 用 marker instruction 标明虚拟寄存器的使用范围：`vreg {entry}` 表示开始，`clear {entry}` 表示结束。

#### 寄存器分配

LLVM 会使用 live-range splitting 等算法寻找能高效使用机器寄存器的分配。Flounder 则把机器寄存器分为 attribute register 和少量 temporary register，以简化这一过程；属性值的寄存器分配只需线性扫描 IR，temporary register 用于访问栈上的 spill 值以及其他用途。

## 3. 演示：ReSQL DBMS

该演示基于构建在 Flounder IR 之上的 ReSQL 数据库系统。ReSQL 能以极短的编译时间对数据库工作负载进行 JIT 处理；演示时，用户可以使用一个 ReSQL 实例的命令行界面。

![图 3：ReSQL 命令行界面](assets/embedded-p03-xref120.png)

图 3：ReSQL 的命令行界面。

### 3.1 即时编译

演示系统允许用户在样例数据库上现场输入并执行 SQL 语句。许多 SQL 查询都能在极短时间内完成 JIT 编译。ReSQL 使用以下翻译栈：

```text
SQL --Grammar (lemon)--> Expression Tree
    --Query Planner----> Query Plan
    --Query Compiler---> Flounder IR
    --Flounder Library-> Machine Code
```

解析从把 SQL 语句转换为 expression tree 开始。query planner 把 expression tree 转换成 query plan，后者是 query compiler 的输入；query compiler 再按第 2 节所示，把每个关系算子翻译成 Flounder IR。最后，Flounder library 把 IR 翻译成可直接执行的二进制机器码。演示系统对所有查询执行这些步骤，并报告编译时间和执行时间。

### 3.2 IR 检查

用户可以同时检查生成的 IR 和最终 machine assembly，并按算子观察 register allocation、post-projection optimization、关系算子实现、hash aggregation 和 hash join。Figure 2(b) 就是 hash join probe 的可检查输出。

### 3.3 示例：寄存器分配

论文回到 Figure 2 的解物化片段。假定 4 个 attribute register 中 3 个已占用，仅 `r8` 空闲，且栈上还没有 spill：

```asm
vreg {r_a}
vreg {r_b}
; read r_a
mov {r_a}, [{entry}]
; read r_b
mov {r_b}, [{entry}+8]
[...] ; parent code
clear {r_a}
clear {r_b}
```

遇到 `vreg {r_a}` 时，分配器必须提供新位置；由于 attribute register `r8` 空闲，它被分配给 `{r_a}`。此时寄存器状态为：

| attribute register | `r8` | `rdi` | `rsi` | `rdx` |
| --- | --- | --- | --- | --- |
| 保存的值 | `r_a`（新分配） | `entry` | `s_a` | `...` |

遇到 `vreg {r_b}` 时已无空闲 attribute register，故为 `{r_b}` 分配栈槽。后续指令使用 `{r_a}` 时直接替换为 `r8`；使用 `{r_b}` 时，register allocator 会生成 spill code，在栈与 temporary register 之间交换其值，再由指令操作该临时寄存器。末尾两个 `clear` 分别释放 `r8` 和 `{r_b}` 的栈槽；原文图中的 × 符号表示这两个释放动作。

```asm
mov r8,  [rdi]     ; read r_a
mov rax, [rdi+8]   ; read r_b through temporary
mov [rsp-8], rax   ; spill store
[...] ; parent code
```

`vreg/clear` 只驱动分配，最终机器码中被删除。第一条 move 把 `r_a` 载入 `r8`；第二、三条经 `rax` 把 `r_b` 写入 `[rsp-8]`。

## 4. 评估

论文以编译时间为演示的首要指标；执行时间结果见相关工作 [1]。测试机为 Intel Xeon E5-1607 v2 3.00 GHz、32 GB RAM、Ubuntu 18.04.4、LLVM 6.0.0，并使用同样基于 LLVM JIT 的 HyPer `v0.5-222-g04766a1` 对照。

复杂度模板 $Q _ {\pi}$ 改变投影属性数量， $Q _ {\bowtie}$ 改变 join 关系数；改变复杂度参数可以测量不同 JIT 技术的渐近编译时间。TPC-H 则用于刻画真实分析查询的编译速度；由于 ReSQL 当时的 planner 尚不支持 subquery，只选择无子查询的 Q1、Q3、Q5、Q6、Q10、Q12、Q14、Q19。

### 4.1 渐近编译时间

$Q _ {\pi}$ 从投影 50 个属性增加到极端的 500 个，过滤选择率为 1%； $Q _ {\bowtie}$ 从连接 2 张表增加到 100 张。比较 Flounder、LLVM O0 和 LLVM O3。

原文 Figure 4 给出两个复杂度查询模板，分别控制投影属性数量和连接关系数量：

**图 4：复杂度查询模板。**

```sql
-- Q_pi: vary projection complexity p
select r.a₁, r.a₂, ..., r.aₚ
from r
where r.a₁ < c;
```

```sql
-- Q_bowtie: vary join complexity j
select r₁.a, r₂.a, ..., rⱼ.a
from r₁, r₂, ..., rⱼ
where r₁.a = r₂.a
  ...
  and rⱼ₋₁.a = rⱼ.a;
```

![图 5：查询复杂度对不同 IR 编译时间的影响](assets/precise-manual-figure-05-complexity-compile-time.png)

图 5：查询复杂度对不同中间表示编译时间的影响。

所有方法都随复杂度增长。 $Q _ {\bowtie}$ 最高 657 ms， $Q _ {\pi}$ 最高 560 ms。LLVM O0 在 10-265 ms 间，O3 在 28-657 ms 间，两者均呈超线性；Flounder 近似线性，只从 0.3 ms 增至 10.8 ms。100 表 join 上，它分别比 O0/O3 快 24.6/60.9 倍；投影模板相对 O0 的最大提升达 283 倍。

### 4.2 真实查询编译时间

为评估真实工作负载的编译时间，论文用 HyPer 和 ReSQL 执行 TPC-H 查询，结果见 Figure 6。HyPer 的编译时间从 Q6 的 15 ms 到 Q5 的 90 ms；ReSQL 的编译时间从 Q6 的 0.21 ms 到 Q19 的 1.71 ms。ReSQL 的平均编译时间比 HyPer 短 70.1 倍，Q5 的最大提升为 101.1 倍。ReSQL 使用 Flounder IR 而不是 LLVM；Flounder IR 更简单，并针对关系工作负载裁剪，因此显著加快了编译过程。Figure 6 还标出了各查询生成的 166–1,134 条机器指令。

![图 6：TPC-H 查询在 HyPer 和 ReSQL 中的编译时间](assets/precise-manual-figure-06-tpch-compile-time.png)

图 6：采用不同查询编译器的 TPC-H 查询的编译时间与机器指令数。

## 5. 总结

本文展示 Flounder IR 作为中间表示的能力，并从概念层面和编译性能视角对比 Flounder IR 与 LLVM IR。本文还说明了现场演示中可以观察到的编译与查询处理环节。

## 致谢

本文工作获得 DFG Collaborative Research Center SFB 876 Project A2 支持。

## 参考文献

- [1] Henning Funke, Jan Mühlig, and Jens Teubner. 2020. Efficient generation of machine code for query compilers. In Proceedings of the 16th International Workshop on Data Management on New Hardware. 1–7.
- [2] Henning Funke and Jens Teubner. 2020. Data-Parallel Query Processing on Non-Uniform Data. PVLDB 13, 6 (2020).
- [3] André Kohn, Viktor Leis, and Thomas Neumann. 2018. Adaptive execution of compiled queries. In 2018 IEEE 34th International Conference on Data Engineering (ICDE). IEEE, 197–208.
- [4] Thomas Neumann. 2011. Efficiently compiling efficient query plans for modern hardware. PVLDB 4, 9 (2011), 539–550.
- [5] OmniSci Incorporated. 2021. OmniSciDB. https://www.omnisci.com/, last accessed on 07/25/2021.
