---
paper_id: vldb-2009-tutorial-column-stores
title: 'Tutorial: Column oriented Database Systems'
language: zh-CN
source: source.pdf
---

# Tutorial: Column oriented Database Systems（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 摘要

列式数据库系统（column-oriented database systems，column-stores）在过去几年中受到了大量关注。简而言之，列存把数据库表的每一列分开存储，同一列的属性值连续、压缩且紧密排列；这与传统数据库系统把完整记录（行）一条接一条存储的方式相反。读取表中一部分列会更快，但代价可能是对分散读取或更新而言，磁头需要在列与列之间频繁寻道。

在几十篇研究论文以及至少十余家新的列存创业公司出现之后，仍然存在若干问题：这些系统究竟是一类新的系统，还是旧瓶装新酒？主流行存系统能多容易地达到列存性能？列存是否能轻松支撑大规模数据密集型应用？有哪些新的、令人兴奋的系统研究问题值得处理？列存又可能启用哪些新的应用？在本教程中，我们概述列式数据库系统技术，并回答这些及相关问题。

## 1. 引言

本教程面向对数据库系统架构、性能，以及数据库系统对大规模数据密集型应用支持感兴趣的数据库系统研究者、设计者和实践者，尤其关注数据仓库和商业智能场景。

预期的主要学习产出包括：

- 更好地理解基于列的数据管理系统架构，以及它们适合在哪些场景和领域支撑大规模数据分析。
- 深入覆盖高级存储与处理技术，其中若干技术尚未进入商业系统，并讨论学术界和工业界有前景的研究方向。
- 调研当时学术界与商业产品的最新状态，以及这些系统可能启用的新应用。

教程组织为三个部分。

## 2. Part A: 基础、应用领域和性能权衡

列存 DBMS 的根源可以追溯到 1970 年代，当时研究者首先研究了转置文件（transposed files），随后又把垂直分区作为一种表属性聚簇技术进行研究。到 1980 年代中期，完全分解存储模型（Decomposition Storage Model，DSM，列存的前身）相对于 NSM（传统行式存储）的优势已经被记录下来；后续关于连接索引和投影索引的研究进一步强化了 DSM 相对于 NSM 的优势。

尽管 DSM 布局适合分析查询，市场需求以及不利的技术趋势仍然帮助行式数据库系统维持了主导地位。直到 2000 年代，列存研究和商业系统才开始快速发展。教程会追溯列存历史，并详细考察促成列存研究和商业化复兴的技术与应用趋势。

列式数据布局决定了列存的大部分基础架构设计。每一列通常连续存放在磁盘上的独立位置，常使用较大的磁盘页或读取单元，以便在硬盘上扫描多列时摊销磁头寻道成本。为了提升读取效率，列值通常紧密打包，避免显式存储记录 ID，并尽可能使用轻量级压缩方案。列扫描算子不同于行扫描算子：它们负责把值的位置转换为磁盘位置，并在需要时把不同列的部分元组或完整元组合并和重构出来。连接算子既可以依赖列扫描算子接收重构后的元组，也可以先计算连接索引，再直接在列上获取满足条件的值。

教程还概述列存的应用领域。首先覆盖传统领域，例如数据仓库、商业智能和数据挖掘，并讨论个人数据集市（例如 MS Gemini）、在线更新和在线加载等趋势。另一个有前景的方向是科学数据管理，教程以 MonetDB 在 Sloan Digital Sky Survey 上的结果为例。最后，教程描述列存用于替代数据模型的近期工作，包括对象数据模型、数组数据模型、XML 和 RDF。

第一部分以行、列和混合数据表示在磁盘与主存中的性能权衡作为结尾。磁盘列式存储的复兴之前，研究者已经在 1990 年代末开始关注主存数据布局，以应对 CPU 与 RAM 速度差距扩大。MonetDB 和 PAX 项目充分展示了 DSM 在主存中的优势。成熟列存的流行又激发了对读优化数据库性能权衡的兴趣，这类系统使用列式表示和高效压缩方案。

## 3. Part B: 列存内部机制与高级查询处理技术

列存最常被引用的优势之一是数据压缩。直观理由是：压缩算法在信息熵低、数据值局部性高的数据上效果更好。教程讨论特别适合列存数据库的压缩算法，以及如何设计查询执行器，使其直接在压缩数据上操作，从而获得压缩带来的 I/O 性能收益，而不支付解压缩的 CPU 成本。教程也讨论近期工作，这些工作认为列存的许多压缩收益不一定是列存独有的，实际上也可应用于行存。

列存最常被提到的两个劣势是写操作和元组构造。写操作通常被认为有两个问题：

- 插入的元组必须拆成各个属性，每个属性分别写入。
- 紧密打包的数据布局使页内移动元组几乎不可行。

教程讨论列存用于缓解基本写入问题的技术，例如主存缓冲、元组移动和分区合并。元组构造同样被认为有问题，因为一个逻辑实体的信息存放在磁盘的多个位置，而大多数查询会访问该实体的多个属性。此外，ODBC 和 JDBC 等数据库标准通常按实体一次一个的方式访问结果，而不是按列一次一列访问。因此，在查询计划的某个阶段，多列数据必须合并为关于某个实体的“行”。教程讨论降低这类构造成本的技术。

为了更好理解列存内部机制的区别性特征，教程讨论在行存内部模拟列存的近期工作。这类工作分离出列存数据库获得性能收益的关键技术，并推动学术界和工业界构建多种混合系统，使列存与行存技术逐渐收敛。教程还讨论列存系统中的开放研究问题，包括物理数据库设计、索引技术、并行查询执行、复制和负载均衡。

## 4. Part C: 案例研究和列存产品回顾

教程通过深入考察 MonetDB/X100 架构来说明前述技术。MonetDB/X100 实际上是在 CWI 开发的两个不同列存。X100 和 MonetDB 除了从数据访问角度追求列式存储，也把按列处理数据作为提升数据库引擎计算效率的方式，尤其用于更好利用现代处理器特性。

在 MonetDB 中，列式查询处理通过物理列代数（physical column algebra）实现。其思想是：列代数的简单性为更高效的执行原语提供机会，类似 RISC 相对于 CISC 的思想。教程详细解释这些机会，包括提升流水线 CPU 的指令吞吐、CPU 分支预测效率、CPU 缓存效率，以及利用 SIMD 指令和 GPU 硬件。

在 X100 中，列代数的收益被保留下来，并通过向量化查询处理模型扩展为流水线式查询处理。教程阐述向量化查询处理的挑战与机会，也覆盖 X100 新的向量化列式压缩方案及其列存更新创新。最后，教程讨论磁盘能力与数据仓库/列存数据访问需求之间的张力，并概述面向列存的智能 I/O 调度工作，例如数据聚簇和协作扫描。讨论还覆盖 SSD 技术对列式存储可能产生的影响。

教程最后全面回顾当时可用的商业列存，包括 Kdb、MonetDB、VectorWise、Vertica/C-Store、Sybase IQ、Infobright、Exasol、ParAccel、SAP BI accelerator 和 Kickfire。

## 5. 参考文献

1. Abadi, D.J., Madden, S.R., and Ferreira, M.: Integrating compression and execution in column-oriented database systems. In Proc. SIGMOD, 2006.
2. Abadi, D.J., Myers, D.S., DeWitt, D.J., and Madden, S.R.: Materialization strategies in a column-oriented DBMS. In Proc. ICDE, 2007.
3. Abadi, D.J., Madden, S.R., and Hachem, N.: Column-stores vs. row-stores: how different are they really? In Proc. SIGMOD, 2008.
4. Boncz, P.A. Monet: A Next-Generation DBMS Kernel For Query-Intensive Applications. Ph.D. Thesis, Universiteit van Amsterdam, Amsterdam, The Netherlands, May 2002.
5. Copeland, G.P., Khoshafian, S.N.: A Decomposition Storage Model. In Proc. SIGMOD, 1985.
6. Harizopoulos, S., Liang, V., Abadi, D.J., and Madden, S.: Performance tradeoffs in read-optimized databases. In Proc. VLDB, 2006.
7. Stonebraker, M. et al.: C-Store: A Column-oriented DBMS. In Proc. VLDB, 2005.
8. Tsirogiannis, D., Harizopoulos, S., Shah, M.A., Wiener, J.L., and Graefe, G.: Query processing techniques for solid state drives. In Proc. SIGMOD, 2009.
9. Zukowski, M., Heman, S., Nes, N., and Boncz, P.A.: Super-scalar ram-cpu cache compression. In Proc. ICDE, 2006.
10. Zukowski, M., Heman, S., Nes, N., and Boncz, P.A. Cooperative Scans: Dynamic Bandwidth Sharing in a DBMS. In Proc. VLDB, 2007.
