---
paper_id: llvm-compilation-framework-lifelong-program-analysis-transformation
title: 'LLVM: A Compilation Framework for Lifelong Program Analysis & Transformation'
language: zh-CN
source: source.pdf
---

# LLVM: A Compilation Framework for Lifelong Program Analysis & Transformation（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者

Chris Lattner、Vikram Adve

University of Illinois at Urbana-Champaign

## 摘要

本文描述 LLVM（Low Level Virtual Machine），一个编译器框架，旨在通过在编译期、链接期、运行期和离线阶段向编译转换提供高级信息，支持任意程序的透明、贯穿生命周期的程序分析与转换。LLVM 定义了一种通用的低层代码表示，采用静态单赋值（SSA）形式，并包含若干新特性：简单且语言无关的类型系统，用于暴露实现高级语言特性常用的基本原语；用于类型化地址算术的指令；以及一种简单机制，可统一高效地实现高级语言异常处理和 C 中的 `setjmp/longjmp`。LLVM 编译器框架和代码表示共同提供了实践中进行长期程序分析和转换所需的一组关键能力。我们认为，当时没有其他编译方法同时提供这些能力。论文描述 LLVM 表示和编译框架的设计，并从三个方面评估：表示的大小和有效性，包括其类型信息；若干过程间问题上的编译器性能；以及 LLVM 对多个困难编译问题的帮助示例。

## 1. 引言

现代应用规模更大、动态性更强，程序行为会在执行期间变化，并且越来越多依赖库、插件、动态加载和跨语言组件。传统编译器通常只在编译期或链接期优化，错过了运行期和部署后可获得的信息。另一方面，动态优化系统虽然能利用运行期信息，却常缺乏高级类型和程序结构信息。

不同程序的性能分布也不同：有些程序的时间集中在少数热点，另一些则均匀分散在整个应用中。要同时高效处理这两类程序，分析与变换就不能只发生在某个固定阶段，而应贯穿程序生命周期。论文所说的 lifelong optimization 包括链接期的过程间优化、安装时的软件变换、运行期优化，以及利用最终用户行为在两次运行之间进行的离线重优化。

程序优化之外，static debugging、leak detection、memory management transformation 等也需要全程序过程间分析，最适合 link time；安全强制可能要在安装或加载时完成；保留可重优化表示还能让旧程序适应新处理器接口。LLVM 的目标是提供统一表示和工具链，使程序整个生命周期都能被分析和转换：

- 编译期由语言前端生成 LLVM 表示。
- 链接期进行跨模块和过程间优化。
- 运行期可进行动态优化和代码生成。
- 离线阶段可利用 profile 或部署信息继续优化。

LLVM 使用抽象 RISC-like 指令集，同时保留类型、显式 CFG 和无限 typed register 的 SSA dataflow。四项新设计是：语言无关低层类型系统；在保留类型的同时做转换和地址算术；`invoke/unwind` 暴露异常边；区分 heap、stack、global、code 且以 typed pointer 访问的内存模型。

它不表达 class/inheritance 等高级语义，也不规定 runtime/object model，不承诺 type/memory safety 或语言互操作；因此是高层 VM（JVM/CLI）的互补基础，而不是替代。高级 VM 甚至可实现在 LLVM 之上。

框架同时提供五项能力：生命周期编译；可用昂贵后端离线生成高质量机器码；采集最终用户 profile 并在 runtime/idle-time 优化；透明、不绑定 object model 的 runtime；把多语言代码、runtime library、system library 统一做全程序编译。论文认为当时没有其他系统同时满足。

这五项能力之间存在天然张力。离线生成高质量本机代码，通常意味着之后只能面对已经丢失高级信息的机器码，难以继续做运行期或用户侧优化；而传统的生命周期编译往往依赖 bytecode VM，又会把程序绑定到特定语言、对象模型和运行时。LLVM 的关键做法是同时保存可分析的 IR 和高质量本机代码，让两条路径并存。

我们逐类比较了已有方法：传统源码编译器具备离线代码生成和透明运行时，却通常没有生命周期优化、最终用户 profile 和统一全程序能力；商业链接期优化器能跨模块工作，但不会把表示继续保留到运行期和部署后；JVM/CLI 可利用用户运行信息并支持多语言，却依赖特定运行时且通常需要 JIT；Dynamo、Transmeta 等本机二进制优化器透明且覆盖整个程序，但必须从机器码恢复结构，能做的高级分析有限；传统 PGO 需要多阶段训练流程，开发者很少在真实软件中使用，训练输入还可能与最终用户行为不符，并且静态 profile 无法适应阶段变化。

贡献与结果包括：定义兼有低层操作和丰富 type/CFG/SSA 信息的 IR；建立透明生命周期框架；在 SPECINT 2000 C 上平均证明约 74.3%（摘要口径 74.6%）memory access 类型安全；文件大小接近 SPARC、平均仅比 x86 大约 25%；过程间优化相对完整 GCC 编译非常快。

## 2. LLVM 代码表示

LLVM IR 区别于其他表示的三点是：type system 与类型安全的 `getelementptr`、显式 memory model、以及实现源语言异常的 `invoke/unwind`。文本、语义与详细语法由 LLVM reference manual 定义。

### 2.1 指令集概览

指令集捕获普通处理器操作，但移除物理寄存器、pipeline 和 calling convention 等机器约束。它是 load/store 架构，只有 typed pointer 的 `load/store` 在 register 与 memory 间传值。全套仅 31 个 opcode：不为相同运算复制 opcode（`not/neg` 可由 `xor/sub` 表达），大部分 opcode 按类型重载；算术/逻辑采用三地址形式。

每个 SSA register 只定义一次，定义支配使用；显式 `phi` 对应标准 SSA φ。SSA 让许多 dataflow 优化更简单，使 flow-insensitive 算法以较低成本获得 flow-sensitive 的许多收益，也因 register 无 alias 简化转换。每函数是 basic block 集合，block 以 `branch/return/unwind/invoke` 之一结束并显式列出 successor，因此 CFG 完整可见。

### 2.2 语言无关类型信息

每个 SSA register 和显式 memory object 都有类型，opcode 与类型共同决定精确语义。Primitive 包括 `void/bool`、8-64 位有/无符号整数、单/双精度浮点；derived type 只有 pointer、array、structure、function，足以表达大多数高级类型的运行行为。

`cast` 是唯一任意类型转换途径；没有 cast 的程序在排除越界等内存错误时必然 type-safe。弱类型语言可使用 cast，但优化器仍可结合 pointer analysis 保守验证声明类型。

对于查询编译，类型化 IR 使数据库列类型、表达式结果类型和函数接口可以明确表达，减少后端猜测。

#### Cast 与 getelementptr

`getelementptr` 是 LLVM 保存低层地址算术类型信息的关键：输入 aggregate typed pointer 与索引，输出字段或数组元素的 typed pointer，相当于组合的 `.`/`[]`；`load/store` 本身不做 indexing，使 memory access 统一。

### 2.3 显式内存分配与统一内存模型

`malloc` 在 heap 分配一个或多个 typed element，`free` 释放；`alloca` 在当前 frame 的 stack 分配并随函数返回自动释放，所有 automatic variable 也显式使用它。Global/function definition 给出对象地址而非隐式值；包括 `call` 在内的所有操作都通过 typed pointer，不存在隐式 memory access，也无需 address-of operator。

### 2.4 函数调用与异常处理

普通 `call` 接收 typed function pointer 与 typed actual argument，隐藏机器 calling convention。异常和 C 的 `setjmp/longjmp` 统一降为 `invoke/unwind`。`invoke` 类似 `call`，但额外指定 exception handler block；`unwind` 逻辑上弹栈直到移除由 `invoke` 建立的 activation record，再转到该 handler。后端可用 zero-cost table 或 `setjmp/longjmp` 实现，IR 则始终显式暴露异常 CFG。

原文用 C++ 析构函数和可能抛出异常的调用说明这个需求：如果 `func()` 抛出异常，控制流必须先执行 `Object` 的析构逻辑，再继续异常传播。

**图 1：C++ 异常处理示例。**

```cpp
{
  Class Object; // Has a destructor
  func();       // Might throw
  ...
}
```

对应的 LLVM 表示显式区分普通返回目标和异常目标。`invoke` 在正常路径跳到 `OkLabel`，在异常路径跳到 `ExceptionLabel`；异常路径先调用析构函数，再用 `unwind` 继续传播。

**图 2：该示例对应的 LLVM 代码。**

```llvm
...
; Allocate stack space for object:
%Object = alloca %Class, uint 1

; Construct object:
call void %Class::Class(%Class* %Object)

; Call "func()":
invoke void %func() to label %OkLabel
        except label %ExceptionLabel

OkLabel:
  ; ... execution continues...

ExceptionLabel:
  ; If unwind occurs, execution continues here.
  ; First, destroy the object:
  call void %Class::~Class(%Class* %Object)
  ; Next, continue unwinding:
  unwind
```

### 2.5 文本、二进制与内存表示

LLVM 是 first-class language，文本、二进制和编译器内存对象三种表示语义等价，可无损往返，不需要典型 JVM 从离线 stack bytecode 转内部/SSA 的语义转换。这让 transformation debugging、测试用例和理解内存对象更简单，同时同一表示既可持久分发又可直接供 compiler pass 使用。

## 3. LLVM 编译器框架

### 3.1 高层设计

LLVM 框架由语言前端、静态优化器、链接期优化器、运行时优化器和后端组成。前端把源程序转为 LLVM IR；优化 pass 在 IR 上运行；后端把 IR 变成目标机器码。

静态前端输出 LLVM `.o`，linker 合并并做 IPO/IPA；native code 可在链接或安装时生成，同时把 LLVM code 保存进 executable。运行时轻量 instrumentation 检测 hotspot 并做简单优化；最终用户的 profile/trace 可附回程序，在空闲期运行激进的 profile-driven IPO。

这种设计带来五个具体收益：同一表示可用于生命周期各阶段；耗时的寄存器分配和指令调度仍可离线完成；profile 来自最终用户而非开发者构造的训练集；程序不必采用某个规定的对象模型或异常语义；链接后，应用代码、语言运行库和系统库可一起接受过程间分析。

LLVM 策略也有边界。语言专用优化必须在前端生成 LLVM 之前完成，因为 LLVM 并不试图成为能表达所有源语言语义的通用 IR。对于 Java 这类依赖复杂运行时的语言，直接从 LLVM 获益到什么程度在当时仍是开放问题；我们正在探索把 JVM 或 CLI 这类高层 VM 构建在 LLVM 之上。

![LLVM 系统架构图](assets/precise-manual-figure-03-llvm-architecture.png)

**图 3：LLVM 系统架构。**

图 3 展示了 LLVM 的端到端架构：多个编译器前端生成 LLVM `.o` 文件，链接器和 IPO/IPA 阶段合并程序与库并继续保留 LLVM 表示；之后既可以生成本机代码，也可以把 LLVM/executable 交给运行时优化器、JIT 和离线重优化器，结合 profile 与 trace 信息反复优化。

### 3.2 编译期

外部前端执行三类任务：可选的语言专用优化（如 closure）、把源程序翻译为 LLVM 并尽量保留类型、可选调用 LLVM module/global pass。Pass 以 library 提供。前端不必自己构建 SSA：可先用 `alloca` 表示变量，再由 stack promotion pass 建 SSA。许多所谓高级优化实际是语言无关的一般问题，例如全程序 C++ virtual call resolution，更适合加入 LLVM，让其在生命周期各阶段复用。

### 3.3 链接期

链接期是大部分程序首次同时可见的阶段，适合 aggressive interprocedural optimization。Compile time 可为每函数计算 summary 并附到 bytecode；link optimizer 直接消费 summary 而非重算，使修改少数 translation unit 的增量编译大幅加速，无需 program database，也无需把源编译推迟到 link time。

链接器首先读取各个 `.o` 中的 LLVM 表示和 summary，把它们与库合并，再进行函数内联、全局变量优化、无用参数消除和其它 IPO/IPA。因为表示与分析结果一起保留，链接器不必重新解析源语言，也不要求所有源文件由同一种前端生成。这个阶段还是处理语言运行库和系统库的第一个统一机会。

### 3.4 离线或 JIT 本机代码生成

Link optimization 后可选择 SPARC V9/x86 backend。静态模式在 link time 用昂贵技术生成高质量 machine code；若启用后续 optimizer，就把完整 LLVM bytecode 嵌入 executable，并插入轻量 loop-region instrumentation。另一模式是 JIT execution engine 在运行时逐函数生成，若无本机 backend 则用可移植 LLVM interpreter。

静态与 JIT 并不是互斥的语言模式，而是同一 IR 的不同部署选择。性能关键的传统 C/C++ 程序可以预先获得高质量本机代码，同时仍携带 LLVM 供后续优化；需要动态加载或快速启动新代码的环境则可按函数 JIT。后端因此可以独立于源语言前端演进。

### 3.5 运行时路径剖析与重优化

程序运行时先以离线 instrumentation 找频繁 loop region，再由在线库细化该 region 内的高频 path。找到 hot path 后，系统复制相应 LLVM code 成 trace、运行 LLVM optimization、生成 native code 放入 software trace cache，并把新路径拼接进现有程序。

分两级收集 profile 是为了控制运行时成本：离线阶段根据 CFG 预先选择候选循环区域，只插入低开销计数；某个区域真正变热后，运行时才启用更细的路径检测。这样不必像纯二进制动态优化器那样持续解码和分析整个程序，也不必在冷代码上支付昂贵优化成本。

这一设计同时保留三项优势：初始代码由 AOT 昂贵算法生成；code generator 与 runtime optimizer 协作提供 instrumentation/support；runtime 在 LLVM 而非 native binary 上拥有 type/CFG/SSA，可做更强优化。我们把它视作 runtime optimizer 的一个优良设计点。

### 3.6 使用最终用户 profile 的离线重优化

有些大程序没有特别热的小区域，runtime 无法为任何一段投入昂贵优化，但仍能记录路径和布局信息。Offline reoptimizer 可在用户机器空闲时合并 runtime profile 与 LLVM，执行不与应用争抢 CPU 的激进 profile-driven IPO；使用模式变化时，runtime 与 offline optimizer 可继续协同更新。

这解决了传统 PGO 的三个缺点：用户无需手工执行“插桩、训练、重编译”的多阶段流程；优化依据是真实用户负载，不会因训练集失真而反向劣化；profile 可以持续更新，能够响应程序阶段行为和长期使用模式的变化。论文同时注明，idle-time optimizer 在当时仍属计划功能，尚未完成实现。

## 4. 应用与经验

### 4.1 表示问题

评估分三类：表示是否有效、全程序分析/转换是否够快、LLVM 的新能力能否解决困难编译问题。

#### 4.1.1 类型信息有何价值

LLVM 是 weakly typed，cast 可破坏声明类型，因此优化前仍需 pointer analysis 验证。LLVM 的 Data Structure Analysis（DSA）是 flow-insensitive、field-sensitive、context-sensitive points-to analysis；它不推断新类型，只把 IR 中声明类型当作候选，保守验证 memory object 的所有访问是否一致。Automatic Pool Allocation 等变换以此为基础。

这里的“可证明为 typed”并不等同于源语言声明了安全类型。DSA 会沿着对象的所有访问检查声明类型是否一致；只要发现可能不一致的访问，就必须保守地视为 untyped。即便对象经过 `void*` 容器保存和取回，分析有时仍能证明其访问安全。这个结果说明低层 IR 中保留的有限类型信息，经过全程序指针分析后仍有实际价值。

表 1 统计 SPEC CPU2000 C benchmark 中，LLVM 能证明类型的 load/store 比例。除少数大量使用无类型内存访问或保守指针模式的程序外，多数程序的内存访问仍保留了可用类型信息。

| Benchmark | Typed accesses | Untyped accesses | Typed percent |
| --- | ---: | ---: | ---: |
| 164.gzip | 1674 | 15 | 99.1% |
| 175.vpr | 3986 | 400 | 90.9% |
| 179.art | 585 | 0 | 100.0% |
| 181.mcf | 581 | 0 | 100.0% |
| 183.equake | 881 | 48 | 94.8% |
| 186.crafty | 9849 | 603 | 94.2% |
| 188.ammp | 1570 | 3279 | 32.4% |
| 197.parser | 1532 | 2207 | 41.0% |
| 254.gap | 6578 | 15508 | 29.8% |
| 255.vortex | 15845 | 8725 | 64.5% |
| 256.bzip2 | 1020 | 52 | 95.1% |
| 300.twolf | 7279 | 7249 | 50.1% |
| average | | | 74.3% |

许多 C benchmark 实际高度 type-safe；剩余丢失主要来自 custom allocator，以及 `188.ammp` 上 DSA 不够激进。即使通过 `void*` 容器存取，DSA 也常能证明安全。旧 C frontend 基于 GCC RTL，类型信息贫乏，DSA 与 pool allocation 明显更弱；改为 GCC AST frontend 后效果显著提高。

表中没有 `176.gcc`、`177.mesa` 和 `253.perlbmk`，原因是提交论文时 LLVM 的缺陷阻止了我们及时取得数据，而不是这些程序被有意排除。摘要给出的平均值为 74.6%，表中可见项目按展示值计算为约 74.3%，译文保留两种口径并明确来源。

#### 4.1.2 高级特性如何映射到 LLVM

C 的 complex、structure copy、union、bit-field、variable-length array、`setjmp/longjmp` 都需 lowering。以 C++ 为例，implicit copy constructor 和 `this` 显式化；template 在 frontend 完全实例化；base class 嵌为 nested structure。例如：

```cpp
class base1 { int Y; };
class base2 { float X; };
class derived : base1, base2 { short Z; };
```

`derived` 降为 `{{int}, {float}, short}`；若有 virtual method，再含初始化为 vtable 的 pointer。Vtable 是 global constant typed function pointer table 加 class type-id，全程序 pointer analysis 可解析 virtual call。C++ exception 降为 `invoke/unwind`，link-time IPO 还能删除全程序未使用的 handler。我们预计 Scheme/SmallTalk/ML/Java/CLI 的 closure、continuation 等也可类似清晰表达。

#### 4.1.3 LLVM 表示有多紧凑

论文还比较了 LLVM 文件与 GCC 3.3 生成的 x86/SPARC 可执行文件大小。LLVM 采用三地址、类型化、SSA 表示，文件体积通常接近 SPARC 本机代码，平均约比 x86 本机代码大 25%；我们认为这在保留类型、控制流和数据流信息的前提下是可接受的。

![LLVM、x86 与 SPARC 可执行文件大小对比](assets/precise-manual-figure-04-executable-sizes.png)

**图 4：LLVM、x86 与 SPARC 可执行文件大小。**

三地址平坦表示适合线性编码，多数指令在文件中只占一个 32-bit word。Figure 4 比较 link 后 SPEC CPU2000 LLVM 与 GCC 3.3 `-O3` 的 x86/SPARC executable。LLVM 接近 SPARC，平均比指令更密的变长 x86 大 25%；考虑它额外保存 type、CFG、SSA dataflow，结果已很紧凑，且当时尚未针对 bytecode size 优化。

#### 4.1.4 LLVM 有多快

所有时间在 3.06 GHz Intel Xeon 上采集。DGE 是 aggressive dead global/function elimination，DAE 是 dead argument elimination，inline 是函数集成，DSA 是上述指针分析，GCC 是 3.3 `-O3` 完整编译参考；各 LLVM pass 均在 link time 处理 whole program。

**图 5：过程间优化耗时（秒）。**

图 5 报告了若干过程间优化的耗时，单位为秒。DGE 表示 aggressive Dead Global Elimination，DAE 表示 aggressive Dead Argument Elimination，inline 是函数内联 pass，DSA 是 Data Structure Analysis；GCC 列作为完整编译时间参考点。

| Benchmark | DGE | DAE | inline | DSA | GCC |
| --- | ---: | ---: | ---: | ---: | ---: |
| 164.gzip | 0.0052 | 0.0001 | 0.0241 | 0.0299 | 3.10 |
| 175.vpr | 0.0001 | 0.0000 | 0.0045 | 0.0081 | 7.11 |
| 179.art | 0.0005 | 0.0000 | 0.0096 | 0.0047 | 0.69 |
| 181.mcf | 0.0005 | 0.0000 | 0.0202 | 0.0040 | 2.00 |
| 183.equake | 0.0006 | 0.0000 | 0.0119 | 0.0054 | 0.91 |
| 186.crafty | 0.0178 | 0.0005 | 0.0917 | 0.2709 | 10.98 |
| 188.ammp | 0.0066 | 0.0003 | 0.1693 | 0.1115 | 6.81 |
| 197.parser | 0.0088 | 0.0006 | 0.1888 | 0.2880 | 6.17 |
| 254.gap | 0.0345 | 0.0034 | 0.3856 | 7.8341 | 20.08 |
| 255.vortex | 0.0287 | 0.0073 | 1.2419 | 3.0451 | 24.15 |
| 256.bzip2 | 0.0022 | 0.0000 | 0.0322 | 0.0154 | 1.86 |
| 300.twolf | 0.0128 | 0.0003 | 0.2580 | 0.1381 | 17.34 |

DGE/DAE 只触及小部分程序，极快；inline 成本近似与实际 inline 数线性，例如 `255.vortex` inline 792 个函数并随后删除 292 个 dead body。DSA 因 context/field sensitive 最昂贵，但除最大程序外仍远低于 GCC 完整编译；GCC 还没有 cross-module optimization。

这些数据衡量的是编译器分析与变换速度，而不是生成代码的运行速度。我们把 GCC 3.3 `-O3` 的完整编译时间作为参照，是为了说明 LLVM 即使在链接期处理整个程序，多个过程间 pass 仍足够快，可用于链接期甚至更晚阶段。所谓 aggressive dead elimination 会先假设对象无用，只有被证明存活时才保留，因此能够删除形成引用环的无用对象。

### 4.2 使用生命周期分析与优化能力的应用

#### 4.2.1 通用编译基础设施

DSA 与 Automatic Pool Allocation 需要 link-time 的全程序可见性、可靠 type、语言独立性，并受益于 SSA 提高 flow-insensitive DSA 精度。外部研究者也已探索 LLVM 用于 binary-to-binary transformation、硬件 trace cache backend、Grid 程序 runtime adaptation、embedded memory partitioning。

这些案例说明 LLVM 的价值不局限于传统“源代码到本机代码”编译器。二进制到二进制变换可把 LLVM 当作中间层；硬件 trace cache 项目可复用后端；Grid 程序可在运行时适应资源变化；嵌入式系统则可用它分析并重新划分内存。它们依赖的是同一组底层能力，而不是某种特定源语言语义。

#### 4.2.2 SAFECode：安全低层表示与执行环境

SAFECode 以 LLVM type-safe subset 为基础，目标是通过 static analysis、pool allocation 而非 GC 实现 memory safety，并以 interprocedural analysis 最小化 runtime check。它直接分析 C/C++ 与 system library；使用 LLVM type 检查 type safety、array type 实施 bounds safety，再跨过程消除许多 bounds check。Link framework 让它在保留 separate compilation 的同时使用全程序 safety checking。

SAFECode 几乎使用了 LLVM 除运行时优化以外的全部能力。它不要求把 C/C++ 改写成安全语言，也不依赖垃圾收集器，而是在链接期利用类型、数组边界和 points-to 信息建立安全保证。这对嵌入式软件、中间件和系统库尤其重要，因为这些领域通常必须继续支持低层 C/C++ 代码。

#### 4.2.3 Virtual Instruction Set Computer 的外部 ISA

VISC 把分发用 virtual ISA（V-ISA）与实际 hardware ISA（I-ISA）分开，由软硬件协同 translator 唯一了解 I-ISA。我们提出扩展 LLVM 作为 V-ISA，并以 OS-independent 方式离线翻译、缓存 native code。LLVM 足够低层，可表示包括 OS 在内的任意软件，又有足够 rich information 支撑 translator 的高级优化；同时支持 offline/online translation。

在这种处理器设计中，应用和操作系统面向稳定的 V-ISA 分发，只有实现相关 translator 需要了解真实硬件。LLVM 的优势一方面是足够接近机器，能覆盖操作系统代码；另一方面又保留类型、CFG 和 SSA，使 translator 能采用比普通机器码翻译更强的优化。离线翻译结果还可以缓存，避免每次启动都重复付费。

## 5. 相关工作

LLVM 与 JVM/CLI 等高层 VM 的目标不同：后者直接表示 class、object model 和特定 runtime，且 offline stack bytecode 常需转换为 compiler IR/SSA；LLVM 不规定这些语义，可用来实现它们。Omniware 等低层 mobile code 更接近机器，却不保留同等高级分析信息。

早期 UNCOL 和后来的 ANDF 试图定义统一的高层、语言中立表示，必须在 AST 层容纳各种源语言特性：前者停留在讨论阶段，后者虽实现但应用有限。LLVM 的目标更克制，它更像严格的 RISC 汇编，只提供少量低层类型和操作，让高级语言特性由这些原语的组合来表达。

Typed Assembly Language、SafeTSA 等以安全移动代码为重点，通常在类型系统中编码更强证明。LLVM 不强制 safety，而让 SAFECode 等在相同 IR 上借助 static analysis 选择性建立安全保证，因而仍能表示非安全 C/C++ 和 system code。

Kistler/Franz 的生命周期优化体系使用紧凑 tree-based Slim Binary，并在 runtime/offline 重建 SSA；LLVM 可直接替代其表示，省去每次重编译重建 SSA。商业 link-time optimizer 有的处理特定机器 assembly，有的从 compiler 导出 IR/annotation，但都未延伸到部署后的 runtime/offline profile optimization。

Dynamo、Transmeta 等 transparent binary runtime optimizer 还要从 native code 恢复结构，并受 runtime 严格时间限制；LLVM runtime 直接拥有 type、SSA、CFG，在线 tracing 可只 instrument hot loop。既有 binary system 也没有同时覆盖 link/install/offline 多阶段。

这些本机优化系统还继承了机器级代码分析本身的困难。相比之下，LLVM 在运行时已经拥有显式 CFG，可把插桩限制到热点循环区域，并直接在 SSA 数据流上变换。论文认为这不仅提高优化能力，也让同一基础设施可以自然延伸到安装期和离线阶段。

## 6. 结论

LLVM 以低层但完整类型化的语言贯穿程序生命周期；语言独立性让多语言代码、runtime 和 system library 可统一 link/optimize。框架包含 link-time IPO、低开销 runtime trace optimization，以及 JIT 与 static backend。

实验表明，即使 C 程序也保留大量可验证类型，足以安全执行过去只在 type-safe source language 上采用的激进变换；LLVM 表示大小接近 SPARC、平均仅比 x86 大 25%，而 whole-program pass 可很快完成。我们下一步要回答的是，高层 VM 能否有效构建在 LLVM runtime optimization/code generation 之上。

因此，论文的核心并不是单独提出一种新 IR 或某个优化 pass，而是把可持久保存的低层表示与链接期、运行期和用户侧重优化组织成一个连续体系。它试图让静态编译程序既保留离线生成高质量机器码的优势，又获得过去主要属于动态 VM 的持续优化能力。

## 参考文献

- [1] A.-R. Adl-Tabatabai, G. Langdale, S. Lucco, and R. Wahbe. Efficient and language-independent mobile programs. In Proceedings of the ACM SIGPLAN 1996 conference on Programming language design and implementation, pages 127–136. ACM Press, 1996.
- [2] V. Adve, C. Lattner, M. Brukman, A. Shukla, and B. Gaeke. A Low-level Virtual Instruction Set Architecture. page (to appear), San Diego, CA, Dec 2003.
- [3] W. Amme, N. Dalton, M. Franz, and J. ery. SafeTSA: A type safe and referentially secure mobile-code representation based on static single assignment form. In PLDI, June 2001.
- [4] A. Ayers, S. de Jong, J. Peyton, and R. Schooler. Scalable cross-module optimization. ACM SIGPLAN Notices, 33(5):301–312, 1998.
- [5] V. Bala, E. Duesterwald, and S. Banerjia. Dynamo: A transparent dynamic optimization system. In PLDI, pages 1–12, June 2000.
- [6] M. Burke and L. Torczon. Interprocedural optimization: eliminating unnecessary recompilation. TOPLAS, 15(3):367–399, 1993.
- [7] M. G. Burke, J.-D. Choi, S. Fink, D. Grove, M. Hind, V. Sarkar, M. J. Serrano, V. C. Sreedhar, H. Srinivasan, and J. Whaley. The Jalapeño Dynamic Optimizing Compiler for Java. In Java Grande, pages 129–141, 1999.
- [8] D. Chase. Implementation of exception handling. The Journal of C Language Translation, 5(4):229–240, June 1994.
- [9] J. Chen, D. Wu, A. W. Appel, and H. Fang. A provably sound TAL for back-end optimization. In PLDI, San Diego, CA, Jun 2003.
- [10] A. Chernoff, et al. FX!32: A profile-directed binary translator. IEEE Micro, 18(2):56–64, 1998.
- [11] R. Cohn, D. Goodwin, and P. Lowney. Optimizing Alpha executables on Windows NT with Spike. Digital Technical Journal, 9(4), 1997.
- [12] R. Cohn, D. Goodwin, P. Lowney, and N. Rubin. Spike: An optimizer for Alpha/NT executables, 1997.
- [13] A. Consortium. The Architectural Neutral Distribution Format, http://www.andf.org/.
- [14] R. Cytron, J. Ferrante, B. K. Rosen, M. N. Wegman, and F. K. Zadeck. Efficiently computing static single assignment form and the control dependence graph. TOPLAS, pages 13(4):451–490, October 1991.
- [15] J. C. Dehnert, et al. The Transmeta Code Morphing Software: Using speculation, recovery and adaptive retranslation to address real-life challenges. In Proc. 1st IEEE/ACM Symp. Code Generation and Optimization, San Francisco, CA, Mar 2003.
- [16] R. DeLine and M. Fahndrich. Enforcing high-level protocols in low-level software. In PLDI, Snowbird, UT, June 2001.
- [17] D. Dhurjati, S. Kowshik, V. Adve, and C. Lattner. Memory safety without runtime checks or garbage collection. In LCTES, San Diego, CA, Jun 2003.
- [18] K. Ebcioglu and E. R. Altman. DAISY: Dynamic compilation for 100% architectural compatibility. In ISCA, pages 26–37, 1997.
- [19] M. F. Fernández. Simple and effective link-time optimization of Modula-3 programs. ACM SIGPLAN Notices, 30(6):103–115, 1995.
- [20] M. Franz and T. Kistler. Slim binaries. Communications of the ACM, 40(12), 1997.
- [21] D. Grossman, G. Morrisett, T. Jim, M. Hicks, Y. Wang, and J. Cheney. Region-based memory management in cyclone. In PLDI, Berlin, Germany, June 2002.
- [22] D. L. Heine and M. S. Lam. A practical flow-sensitive and context-sensitive c and c++ memory leak detector. In Proceedings of the ACM SIGPLAN 2003 conference on Programming language design and implementation, pages 168–181. ACM Press, 2003.
- [23] IBM Corp. XL FORTRAN: Eight Ways to Boost Performance. White Paper, 2000.
- [24] S. Kowshik, D. Dhurjati, and V. Adve. Ensuring code safety without runtime checks for real-time control systems. In CASES, Grenoble, France, Oct 2002.
- [25] C. Lattner and V. Adve. LLVM Language Reference Manual. http://llvm.cs.uiuc.edu/docs/LangRef.html.
- [26] C. Lattner and V. Adve. Automatic Pool Allocation for Disjoint Data Structures. In Proc. ACM SIGPLAN Workshop on Memory System Performance, Berlin, Germany, Jun 2002.
- [27] C. Lattner and V. Adve. Data Structure Analysis: A Fast and Scalable Context-Sensitive Heap Analysis. Tech. Report UIUCDCS-R-2003-2340, Computer Science Dept., Univ. of Illinois at Urbana-Champaign, Apr 2003.
- [28] G. Morrisett, D. Walker, K. Crary, and N. Glew. From System F to typed assembly language. TOPLAS, 21(3):528–569, May 1999.
- [29] R. Muth. Alto: A Platform for Object Code Modification. Ph.d. Thesis, Department of Computer Science, University of Arizona, 1999.
- [30] T. Romer, G. Voelker, D. Lee, A. Wolman, W. Wong, H. Levy, B. Bershad, and B. Chen. Instrumentation and optimization of Win32/Intel executables using Etch. In Proc. USENIX Windows NT Workshop, August 1997.
- [31] Z. Shao, C. League, and S. Monnier. Implementing Typed Intermediate Languages. In International Conference on Functional Programming, pages 313–323, 1998.
- [32] A. Srivastava and D. W. Wall. A practical system for intermodule code optimization at link-time. Journal of Programming Languages, 1(1):1–18, Dec. 1992.
- [33] T. Steel. Uncol: The myth and the fact. Annual Review in Automated Programming 2, 1961.
- [34] D. Wall. Global register allocation at link-time. In Proc. SIGPLAN ’86 Symposium on Compiler Construction, Palo Alto, CA, 1986.
