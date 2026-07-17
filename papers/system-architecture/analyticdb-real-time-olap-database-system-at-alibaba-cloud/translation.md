---
paper_id: analyticdb-real-time-olap-database-system-at-alibaba-cloud
title: 'AnalyticDB: Real-time OLAP Database System at Alibaba Cloud'
language: zh-CN
source: source.pdf
---

# AnalyticDB: Real-time OLAP Database System at Alibaba Cloud（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 摘要

随着数据在规模和种类上呈爆发式增长，OLAP 数据库在以低延迟（例如数百毫秒）提供实时分析方面发挥着越来越重要的作用，尤其是在输入查询本身复杂且为即席查询时。此外，人们还希望这些系统提供高查询并发和高写入吞吐，并支持对结构化数据以及 JSON、向量和文本等复杂数据类型进行查询。

我们在本文中介绍 AnalyticDB，这是一个由阿里巴巴开发的实时 OLAP 数据库系统。AnalyticDB 以可接受的开销异步维护全列索引，为复杂即席查询提供低延迟。它的存储引擎扩展了混合行列布局（hybrid row-column layout），可以快速检索结构化数据和复杂类型数据。为了以高查询并发和高写入吞吐处理大规模数据，AnalyticDB 解耦了读写访问路径。为进一步降低查询延迟，我们还开发了新的存储感知 SQL 优化器和执行引擎，以充分利用底层存储和索引的优势。AnalyticDB 已经成功部署在阿里云上，服务大量大小客户。它可以容纳 100 万亿行记录，即超过 10PB 的数据；同时每秒可处理超过 1,000 万次写入和 10 万次查询，并在数百毫秒内完成复杂查询。

## 1. 引言

AnalyticDB 是一个用于 PB 级高并发、低延迟和实时分析查询的 OLAP 数据库系统，已经运行在阿里云的 2,000 多台物理机上 [1]。它面向电子商务、金融、物流、公共交通、气象分析和娱乐等广泛行业的外部阿里云客户，也服务阿里巴巴集团内部业务。

近期工作 [35, 28, 29, 36, 25] 将 OLAP 系统设计的主要挑战总结为：低查询延迟、数据新鲜度、灵活性、低成本、高可扩展性和高可用性。与这些工作相比，我们客户的分析负载把 AnalyticDB 推到了更大规模：超过 10PB 的数据、数十万张表和数万亿行，给 AnalyticDB 的设计与实现带来了重大挑战。

第一个挑战是，当今用户面对的分析场景比以往更复杂，却仍然对低查询延迟有很高期待。用户往往不能容忍长时间运行的查询。但 AnalyticDB 的用户来自各种领域，分析需求差异很大且可能频繁变化，所以这些多样、复杂的查询很难优化。查询范围从全表扫描、点查找到多表 join，并涉及任意多列组合上的条件。索引虽是提高查询性能的直接方法，但仅为预先指定的列建立索引已经往往无效。

第二个挑战是，新兴的复杂分析往往同时涉及不同的查询类型和数据类型，因而要求系统在存储层拥有友好且统一的数据布局。传统 OLAP 查询和点查找分别需要列存和行存 [34, 12]。更何况，我们用户超过一半的数据属于复杂数据类型，例如文本、JSON 字符串、向量和其他多媒体资源。实用的存储布局必须能够快速检索多种数据类型，从而高效支持同时涉及结构化数据和复杂类型数据的查询。

第三个挑战是，系统在以低延迟处理实时查询的同时，还必须每秒处理数千万个在线写请求。传统设计 [6, 8, 10, 29, 5] 在同一进程路径中处理读写，从而使读可以在新写入数据提交后立即看到它。然而，这种设计已不适合我们的场景：消耗大量资源保证查询性能会损害写性能，反之亦然。必须仔细设计，在查询延迟、写入吞吐和数据可见性之间取得平衡。

本文贡献包括：

- **高效索引管理。** AnalyticDB 内嵌了高效且有效的索引引擎，通过两个关键方法以可接受的开销实现低延迟。首先，它在每张表的所有列上构建索引，使复杂即席查询的性能得到显著提升；我们还提出了基于运行时过滤比的索引路径选择机制，避免滥用索引导致性能下降。其次，在关键路径中更新大型索引是不可行的，因此索引在非高峰时段异步构建。我们还维护一个轻量级排序索引，以尽量降低异步索引构建对查询增量数据（即索引开始构建后新写入的数据）的影响。
- **面向结构化数据和复杂类型数据的存储布局。** 我们设计底层存储来支持混合行列布局，特别是利用快速顺序磁盘 I/O，使它在 OLAP 风格和点查找负载下都只产生可接受的开销。我们还在存储（包括索引）中纳入复杂数据类型，使系统能够将 JSON、向量和文本等资源的搜索与结构化数据的查询结合起来。
- **读写解耦。** 为了同时支持高吞吐写入和低延迟查询，系统使用读写解耦架构：写入和读取分别由写节点和读节点提供服务。两种节点彼此隔离，因而可以独立扩展。写节点把写请求持久化到可靠的分布式存储盘古 [7]。为了在服务查询时保证数据新鲜度，读节点使用版本验证机制，使先前由写节点处理的写入可见。
- **增强优化器和执行引擎。** 为进一步降低查询延迟并提高并发，我们增强了 AnalyticDB 的优化器和执行引擎，以充分利用存储和索引的优势。具体而言，我们提出了存储感知 SQL 优化机制，根据存储特征生成最优执行计划；还为基于代价的优化器设计了高效实时采样技术，用于基数估计。此外，我们设计了适用于混合存储的高性能向量化执行引擎，提高计算密集型分析查询的效率。

本文其余部分安排如下：第 2 节讨论相关工作；第 3 节介绍读写解耦架构；第 4 节说明面向结构化数据与复杂类型数据的存储结构和索引；第 5 节介绍优化器与执行引擎上的优化；第 6 节评估 AnalyticDB；第 7 节给出结论。

## 2. 相关工作

AnalyticDB 是为云平台上的大规模实时分析从头开始构建的。本节将 AnalyticDB 与其他系统比较。

**OLTP 数据库。** MySQL [6] 和 PostgreSQL [8] 等 OLTP 数据库用于支持事务查询；这些查询可以视为涉及一行或数行的点查找。因此，OLTP 数据库的存储引擎采用行式布局，并构建 B+tree 索引 [16] 来加速查询。但行存不适合只需要子集列的分析查询，因为它会显著放大 I/O。此外，OLTP 数据库通常在写路径中主动更新索引，开销很高，同时影响写入吞吐和查询延迟。

**OLAP 数据库。** 为提高分析查询的效率，人们开发了 Vertica [29]、Teradata DB [10] 和 Greenplum [5] 等诸多 OLAP 数据库。Vertica [29] 使用 projection 提高查询性能；它不在列上构建常规索引，而只保留最小值/最大值信息，因剪枝效果较差而导致高延迟。Teradata DB [10] 和 Greenplum [5] 采用列存，并允许用户指定建立索引的列。但它们有两个主要局限：一是在写路径中修改列索引，所以全列索引不可行；二是列存需要许多随机 I/O 来处理点查找。

**大数据系统。** 随着 MapReduce 模型 [18] 兴起，Hive [35] 和 Spark SQL [37, 13] 等批处理引擎开始广泛用于在多台机器上处理大规模数据。但它们执行的查询被视为“离线”查询，整个执行可能持续数分钟或数小时，因而不适合实时查询。Impala [28] 利用流水线处理模型和列存把“离线”查询转换为交互式查询，将常见查询延迟降到秒级。但 Impala 没有列索引（只有 Min/Max 统计信息），因此无法很好地处理复杂查询。

**实时 OLAP 系统。** 近期的实时 OLAP 系统包括 Druid [36] 和 Pinot [25]，二者都采用列存。它们都构建基于位图的倒排索引：Pinot 在所有列上建索引，Druid 则在 Dimension Column 上建索引。如果 Druid 查询涉及不在 Dimension Column 中的列，就可能遭遇高延迟。它们的所有索引都在写路径中更新，会影响写性能。此外，它们不支持 JOIN、UPDATE 和 DELETE 等重要查询类型，并且因采用列式布局而不善于点查找。

**云分析服务。** 近年出现了 Amazon Redshift [21] 和 Google BigQuery [33] 等多种云分析服务。Amazon Redshift 是完全托管的云数据库服务，利用列式存储和大规模并行处理（MPP）将查询分发到多个节点。典型 Redshift 集群包含两个或更多由 Leader Node 协调的 Compute Node。与它相比，AnalyticDB 引入了由独立读节点、写节点和一组与客户通信的协调器组成的读写解耦架构。Google BigQuery 是 Google 核心技术 Dremel [31] 的对外实现，其中包含用于提高存储效率的列式存储，以及用于在数千台机器上数秒内分发查询和聚合结果的树形拓扑。AnalyticDB 则利用高效索引引擎和 DAG 执行框架，与之不同。

## 3. 系统设计

AnalyticDB 作为云数据库运行在飞天（Apsara）之上。飞天是阿里云自 2009 年起开发的大规模、通用且高可靠的计算基础设施，管理数十万台物理机上的所有资源，并支撑搜索、计算和存储等众多阿里云服务。如图 1 所示，AnalyticDB 使用飞天的两个核心组件：盘古（Pangu）[7]，一个可靠的分布式存储系统；以及伏羲（Fuxi）[38]，一个资源管理和作业调度系统。本节将介绍 AnalyticDB 中的重要设计选择，包括数据模型和系统架构。

图 1 展示了 AnalyticDB 架构。客户端通过 JDBC/ODBC 连接协调器（coordinator）。协调器把写入请求分派给写节点，把查询请求分派给读节点。写节点处理 INSERT、DELETE、UPDATE，并把 SQL/log 持久化到盘古；读节点处理 SELECT，并缓存/加载分区数据；Fuxi 为异步任务提供计算资源。

![图 1：AnalyticDB 架构。](assets/analyticdb-fig01-architecture.png)

### 3.1 数据模型和查询语言

AnalyticDB 遵循标准关系数据模型，即记录存放在具有固定 schema 的表中。此外，它还支持全文、JSON 和向量等许多常见复杂数据类型，以满足真实应用不断增长的分析需求（详见第 4.1.1 节和第 4.2.2 节）。AnalyticDB 支持 ANSI SQL:2003 [19]，并在此基础上增加了分区声明和复杂类型数据操作等功能。

### 3.2 表分区

AnalyticDB 的每张表包含两级分区：主分区（primary partition）和次分区（secondary/sub partition）。图 2 展示了一个建表 DDL：主分区按 `id` 哈希成 50 个分区，次分区按 `dob` 列做列表分区，最多保留 12 个可用分区。

![图 2：创建分区表的 DDL。](assets/analyticdb-fig02-partition-ddl.png)

```sql
CREATE TABLE db_name.table_name (
    id int,
    city varchar,
    dob date,
    primary key (id)
)
PARTITION BY HASH KEY(id)
PARTITION NUM 50
SUBPARTITION BY LIST (dob)
SUBPARTITION OPTIONS (available_partition_num = 12);
```

主分区按用户指定列的哈希分布行，以最大化并发；实践中通常选择高基数列。次分区常用于时间列，如天、周、月。一旦次分区数超过阈值，最旧分区会被自动回收。

### 3.3 架构概览

AnalyticDB 主要包含三类节点：协调器、写节点和读节点。协调器接收客户端请求并解析为读或写；写节点负责接收和持久化写日志；读节点负责查询执行。Fuxi 为计算 worker 分配资源。AnalyticDB 还提供通用执行引擎与流水线执行引擎。

图 3 展示流水线执行引擎。数据以列块（page）为单位从存储流向客户端；所有数据处理都在内存中完成，并跨网络在不同阶段间流水化。这样的流水线工作流使 AnalyticDB 能以高吞吐、低延迟服务用户的复杂查询。

![图 3：流水线模式执行引擎。](assets/analyticdb-fig03-pipeline-engine.png)

### 3.4 读写解耦

传统 OLAP 数据库常把读写请求放在同一执行路径中，共享同一资源池。在查询和写入并发都很高时，这会造成资源争用。AnalyticDB 将读写分离：写节点只服务写请求，读节点只服务查询，两者彼此隔离并可独立扩展。

#### 3.4.1 高吞吐写入

每个写节点集群中有一个 master，其余为 worker。它们通过基于 ZooKeeper [24] 构建的锁服务协调。写节点首次启动后，master 根据表分区配置分配 worker；协调器先解析 SQL 并识别出写请求，再按该配置把它分发给对应写节点。每个写节点将接收的 SQL 语句缓存在内存中，并像传统数据库的日志写线程一样，定期把它们作为日志刷到盘古。缓冲区完全刷盘后，写节点返回版本号（即 log sequence number），协调器再针对每次已提交写入向用户返回成功消息。

当盘古上的日志文件达到一定规模时，AnalyticDB 会在 Fuxi 上启动多个 MapReduce [18] 作业，把日志提交转化为实际数据文件，即基线数据和索引（详见第 4 节）。

#### 3.4.2 实时读取

图 4 展示读节点之间的数据放置。具有相同哈希值的分区被放在同一读节点上。这样的分区放置配合存储感知优化器，可减少数据重分布成本；生产统计表明，数据重分布可减少 80% 以上。读节点默认有副本，以支持并发和可靠性。

![图 4：读节点之间的数据放置。](assets/analyticdb-fig04-data-placement.png)

每个读节点从盘古加载初始分区，再周期性地从对应写节点拉取后续更新，并把更新应用到不会回写盘古的本地数据副本。系统持续从写节点而非盘古拉取数据，以降低同步延迟；因此，写节点也充当缓存，为不同读节点副本的并发拉取提供服务。

由于近期写入需要远程获取，读节点向用户提供两种可见性级别：写入后立即可读的实时读（real-time read），以及在有限延迟内可见的有界陈旧读（bounded-staleness read）。为维持低查询延迟，AnalyticDB 默认使用多数 OLAP 场景可以接受的有界陈旧读；需要更高可见性时可以启用实时读，但这会暴露读写节点之间的数据同步问题。

AnalyticDB 用版本验证机制解决这一问题。图 5 展示了一个先写后读的请求序列：每个主分区在写节点上关联自己的版本。一批分区写入刷盘后，写节点递增该分区版本，并把版本附在响应中。用户写入一条记录（步骤 1、2）后立即发查询；协调器收到查询时，把查询和此前刷盘响应中缓存的版本 $V_1$ 一并发给相应读节点（步骤 4）。对有界陈旧读，协调器使用缓存版本；对实时读，则在步骤 3 从写节点拉取版本。读节点将本地版本 $V_2$ 与 $V_1$ 比较：若 $V_1 \leq V_2$，即可直接执行查询；否则须先从写节点拉取最新数据（步骤 5）并更新本地副本。

![图 5：实时读取工作流。](assets/analyticdb-fig05-realtime-read-workflow.png)

为了避免读节点等待拉取导致高延迟，AnalyticDB 还把读节点拉取优化为写节点推送：写节点观察到新写入时，主动把数据与版本推送给对应读节点。

#### 3.4.3 可靠性和可扩展性

写节点失败时，master 会把受影响分区均匀迁移到其他可用写节点；master 失败时，从活跃 worker 中选举新的 master。用户可以配置读节点副本因子（默认值为 2），同一读节点的不同副本部署在不同物理机上。读节点服务查询时发生故障，协调器会自动把查询重新发送到其他副本，对用户透明。读节点拉取新数据时不会因写节点故障而阻塞；若无法联系写节点，它可以直接从盘古读取数据（图 5 步骤 6），以较高延迟继续执行。

写节点扩容时，master 调整表分区放置并写入 ZooKeeper；协调器随后按新放置分发写请求。读节点扩容类似，由协调器调整表分区位置。

### 3.5 集群管理

AnalyticDB 的集群管理组件 Gallardo 面向多租户。它使用 Control Group 技术隔离不同 AnalyticDB 实例的 CPU、内存和网络带宽，并在创建实例时把 coordinator、write node、read node 及读节点副本放置到不同物理机以满足可靠性需求。Gallardo 负责实例间资源隔离，Fuxi 负责所有实例内部的计算任务调度，两者职责不同。

## 4. 存储

AnalyticDB 的存储模型同时支持结构化数据和 JSON、向量等复杂类型。下面先讨论其混合行列存储布局，再介绍快速且强大的索引引擎。

### 4.1 物理数据布局

本节先介绍 AnalyticDB 的数据布局和元数据，再说明如何操作数据。

#### 4.1.1 混合行列存储

AnalyticDB 的一个设计目标是同时支持 OLAP 风格查询和点查找。OLAP 查询通常只涉及宽表中的少数列；列存 [34] 能有效压缩数据和减少 I/O，适合这类查询，却难以高效处理需要访问一整行或数整行的点查找。行存擅长点查找，但会放大 OLAP 查询的访问成本 [12]。

为解决这一矛盾，我们设计了图 6 所示的混合行列存储布局。每个表分区的数据保存在一个 detail file 中，并划分为多个 row group。每个 row group 包含固定数量的行（该数量可配置；生产实践中的默认值为 30,000）；同一列的所有值连续聚集为一个 data block，各 data block 顺序存储。data block 是 AnalyticDB 中 fetch、cache 等操作的基本单位，也有助于取得较高压缩率并节省存储空间。

![图 6：混合行列存储中的数据格式，包括元数据和索引格式。](assets/analyticdb-fig06-hybrid-row-column-format.png)

这种设计以可接受的开销平衡 OLAP 风格查询和点查找 [12, 20, 34]。与列存类似，混合存储仍按列聚集数据，有利于 OLAP 查询。虽然完整的一列分布在不同 row group 的多个 data block 中，但取出全部数据只需少量顺序 seek；生产中的 AnalyticDB 服务显示，这一开销占总查询延迟不到 5%。点查找也能保持良好性能，因为特定行的所有列都在同一个 row group 中；组装一行只需短距离顺序 seek [23]，而不需要列存中的跨 segment seek。

**复杂类型数据。** 上述混合行列存储适合数值和短字符串等短列，却不适合 JSON、向量等复杂类型，因为这类数据大小可变且通常大得多；把它们按固定行数组织成 row group 可能产生意外巨大的 block。为此，我们为复杂类型设计了固定大小存储模型：如图 7 所示，它再引入一级固定为 32KB 的 FBlock。一个包含 30,000 行的 data block 把行分布到多个 FBlock，只在自身保存指向这些 FBlock 的指针；data block 仍有固定行数，而全部 FBlock 存在单独文件中。

一个 FBlock 所含行数可以从不足一行（即一行的局部）到多行不等。为支持快速查找，data block 为每个 FBlock 维护一条 block entry，记录对应 FBlock 的起始行和结束行。一行可以拆到多个连续 FBlock 中；例如图 7 的 FBlock1 和 FBlock2 分别保存行区间 $[0,99]$ 与 $[99,200]$，说明第 99 行跨越两个 FBlock。访问该行时，系统先扫描 data block 中的 block entry 定位相关 FBlock，再取出并拼接各部分行。

![图 7：复杂类型数据格式。](assets/analyticdb-fig07-complex-type-format.png)

#### 4.1.2 元数据

detail file 中每一列都有单独的元数据，用来加速对该列海量数据的检索。它存放在独立的 detail meta file 中；文件很小（小于 1MB），会缓存在内存中供频繁访问。元数据包含四部分：header，记录版本号和该 detail meta file 的总长度；summary，记录行数、NULL 数、值基数、SUM、MAX/MIN 等优化器所需统计信息；dictionary，对低基数列自动启用以节省空间；block map，为每个 data block 记录其在 detail file 中的 offset/length，以支持快速访问。

#### 4.1.3 数据操作

AnalyticDB 的底层存储采用 Lambda 架构，包含基线数据和增量数据。图 8 展示对存储执行 INSERT/DELETE/UPDATE 与查询时，基线数据、增量数据、删除位图和版本之间的关系。基线数据保存历史数据，包含索引和行列数据；增量数据保存新写入数据，不含完整索引，只维护简单排序索引（详见第 4.2.5 节）。增量数据只出现在读节点从写节点拉取并重放日志时；基线数据与增量数据采用上文相同的数据和元数据格式。

**查询执行。** 为支持 UPDATE，AnalyticDB 使用 bit-set 记录已删除数据的 row id，并用 copy-on-write 技术支持 MVCC（多版本并发控制）[15]。查询给定版本号后，同时访问基线与增量数据：分别从基线数据的完整索引和增量数据的排序索引取得合格 row id，再用对应删除位图过滤被删除的行，得到最终结果。

行被更新或删除时，系统把 bit-set snapshot 连同版本号存入内存映射，供后续查询使用。为节省空间，删除 bit-set 被切分成多个小型压缩 segment，使不同 snapshot 能共享未变化的 segment。创建新版本 snapshot 后，一旦最旧版本上已无查询运行，系统便将其淘汰。目前 UPDATE 只支持按主键更新，以避免一次操作改动过多数据；一次 UPDATE 被视为 DELETE 与 INSERT 的组合。

![图 8：存储上的数据操作与查询执行。](assets/analyticdb-fig08-storage-manipulation-query.png)

算法 1：`INSERT(SQL, version)`。该算法解析 SQL、把值追加到增量数据尾部、为删除位图添加新位、创建位图快照，并把版本与快照写入映射。

```text
Input: SQL statement and version number

/* 从 SQL 中解析多个列值 */
values = parse(SQL);
/* 把值追加到增量数据尾部 */
row_id = incremental_data.append(values);
/* 在删除位图中添加一个新 bit */
delete_bitset[row_id] = 0;
/* 创建删除位图的快照 */
delete_bitset_snap = create_snapshot(delete_bitset);
/* 将版本—快照对放入映射 */
snap_map.put(version, delete_bitset_snap);
```

算法 2：`DELETE(SQL, version)`。该算法先按 WHERE 条件搜索，再把满足条件的 row id 在删除位图中置为 1，最后创建版本快照。

```text
Input: SQL statement and version number

/* 按 WHERE 条件搜索 */
row_ids = search(baseline_data, incremental_data, SQL.where);

/* 删除满足条件的记录 */
for each row_id in row_ids do
    delete_bitset[row_id] = 1;
delete_bitset_snap = create_snapshot(delete_bitset);
snap_map.put(version, delete_bitset_snap);
```

算法 3：`FILTER(conditions, version)`。该算法根据查询版本获取删除位图快照，搜索索引得到候选 row id，再减去已删除 row id。

```text
Input: filter conditions and version number
Output: row ids satisfying conditions

/* 按版本取得删除位图 */
delete_bitset_snap = snap_map.get(version);
/* 使用条件搜索索引以取得 row id */
row_ids = search(baseline_data, incremental_data, conditions);
/* 从结果中移除已删除的 row id */
return minus(row_ids, delete_bitset_snap);
```

随着数据持续写入，在增量数据上搜索会显著变慢，因此系统异步启动构建过程，把增量数据并入基线数据；该过程忽略已删除记录，并相应创建新索引。图 9 展示合并流程。构建开始时，当前增量数据被冻结，并创建新的增量数据继续接收写入。在构建结束前，所有查询都访问旧基线数据、被冻结的旧增量数据和新增量数据。新版本基线数据合并完成后，旧基线数据和旧增量数据可安全删除；此后，由新基线数据与新增量数据共同服务后续查询。

![图 9：合并基线数据和增量数据的过程。](assets/analyticdb-fig09-baseline-incremental-merge.png)

### 4.2 索引管理

索引是几乎所有数据库提升查询性能的关键组件，但现有索引方法无法完全满足 OLAP 应用需求。例如，B+tree 会因节点分裂产生高昂更新成本，因而只能负担得起在审慎选择的列上构建。Druid [36] 等系统选择基于位图的倒排索引，以覆盖更多列，却只适合字符串等特定数据类型。随着查询 JSON、向量和文本等复杂类型的需求增长，系统也必须支持这些类型上的索引。此外，多数系统在写路径中构建索引 [8, 6, 5, 10]，显著限制了写性能。

因此，我们设计并实现了一个不会影响写吞吐的索引引擎，为结构化数据和复杂类型数据构建索引。它在所有列上建索引以全面支持即席查询，并把索引构建彻底移出写路径；系统还采用多项设计来尽量降低存储开销并提高性能。

#### 4.2.1 索引过滤

每个分区的每列都构建倒排索引，每个索引存放在独立文件中；索引键是原列值，索引值是对应 row id（即行号）列表。由于每个 row group 行数固定，系统可以按 row id 轻松定位一行。图 10 给出一个同时包含结构化条件和复杂类型条件的 SQL 过滤示例。索引引擎先在每个条件对应的索引上过滤，得到一组局部 row id；再通过交、并、差等操作把所有局部结果合并为最终结果。多数数据库常用的 2-way merging 会产生巨大内存开销并导致低并发。为减轻这一影响，AnalyticDB 改用 K-way merging [17]，在大数据集上保证亚秒级查询延迟。

![图 10：在所有列索引上执行查询。](assets/analyticdb-fig10-all-column-index-query.png)

**索引路径选择。** 过度使用索引有时会降低性能。例如条件 A 的局部结果远小于条件 B 时，先用 A 取得少量结果再用 B 过滤，比同时取得 A、B 的局部结果并合并更划算。为此，我们提出基于运行时过滤比（filter ratio）的索引路径选择机制，在运行时评估每个条件的过滤比，决定是否使用相应索引。过滤比定义为索引返回的合格行数除以元数据中的总行数。AnalyticDB 按过滤比从小到大使用索引处理条件；每完成一个条件，如果所有已处理条件的联合过滤比（由各过滤比相乘得到）已经足够小，例如低于总行数的 1%，便停止该过程，并以 K-way merging 合并此前取得的局部结果。后续条件直接作用于这些 row id，而不再访问索引。

#### 4.2.2 复杂类型数据索引

**JSON。** 插入 JSON 对象时，AnalyticDB 将层次属性展平成多个列并分别建立倒排索引。例如对象 `{id, product_name, properties {color, size}}` 被展平成 `id`、`product_name`、`product_properties.color` 和 `product_properties.size`。每个索引键下的 row id 使用 PForDelta 算法 [39] 压缩。一个 JSON 对象可能包含数千个属性，也就对应数千个索引；为限制文件数，系统把一个对象的所有索引打包到单个文件中。借助索引，AnalyticDB 可以根据 JSON 格式的谓词直接取得对象，比从磁盘读取并解析 JSON data block 更高效。

**全文。** 对于全文数据，AnalyticDB 扩展倒排索引，额外存储 term frequency 以及 document 到 term 的映射，并使用 TF（Term Frequency）/IDF（Inverse Document Frequency）分数计算查询与数据库文本的相似度，只向用户返回分数超过阈值的对象。

**向量。** 特征向量是对象/场景识别、机器学习等许多计算机视觉任务的常见组成部分；训练后的 AI 模型可以从图像提取高维向量，而两个对象的相似度可以用特征向量之间的距离衡量。用户查询向量数据时通常需要最近邻搜索（nearest neighbour search, NNS），即从数据库中寻找离查询点最近的对象。给定数据库同一列保存的有限向量集合 $Y \subset \mathbb{R}^D$ 和查询向量 $q \in \mathbb{R}^D$，NNS 定义为寻找使距离 $d(q, y)$ 最小的对象：

$$
NN(q) = \arg\min _ {y \in Y} d(q, y)
\tag{1}
$$

AnalyticDB 支持欧氏距离、余弦距离等相似度度量，并可在 SQL 中指定。最直接的 NNS 方法会线性扫描数据库中的所有向量，逐个计算与查询向量的距离，最后返回 top-k 结果。为避免穷举搜索，我们实现并结合了 Product Quantization（PQ）[26] 和 Proximity Graph（k-NNG）[22]。实验已经证明，这两种近似 NNS 方法 [4] 能以高概率取得 NN（或 k-NN）。PQ 通过分解向量空间获得较小索引，k-NNG 则借助高效、连通良好的图索引取得更好的搜索性能和准确度。AnalyticDB 会根据内存资源以及用户对准确度和效率的要求，自适应选择更合适的方法。

#### 4.2.3 索引空间节省

为降低索引空间，AnalyticDB 会根据索引值类型自动选择 bitmap 或整数数组。例如值为 `[1,2,8,12]` 时，bitmap（2 字节）比整数数组（4 字节）更省空间；值为 `[1,12,35,67]` 时，整数数组（4 字节）比 bitmap（9 字节）更合适。该自适应选择能将总索引大小降低约 50%。用户也可以禁用不需要索引的列以进一步节省空间。

#### 4.2.4 异步索引构建

AnalyticDB 每秒服务数千万写请求，无法在写路径同步构建全列索引。因此，写路径在写节点刷新日志到盘古后结束（第 3.4.1 节）；索引引擎随后周期性地在这些新写入（即增量数据）上构建倒排索引，并在后台与已有完整索引合并。这种异步方法向用户完全隐藏索引构建开销，同时维持查询效率和写吞吐。构建和合并索引的过程会转化为大量 MapReduce 任务；借助 Fuxi [38]，这些任务在 AnalyticDB 集群的非高峰时段并发、自动运行，只引入可接受的开销。

表 1 比较了列存 OLAP 数据库 Greenplum [5] 与 AnalyticDB 在 1TB 数据上构建全列索引的开销。AnalyticDB 只为索引额外使用 0.66TB，远小于 Greenplum 的 2.71TB。尽管 AnalyticDB 的索引构建时间约为 Greenplum 的两倍，异步过程并不影响在线读写性能。表中 Greenplum 实时摄取（INSERT）1TB 数据的时间约为 AnalyticDB 的四倍。由此，AnalyticDB 以可接受的开销换取即席查询的显著性能提升，第 6 节将对此进行评估。

表 1：AnalyticDB（ADB）与 Greenplum（GP）在 1TB 数据上构建全列索引的比较。

| 指标 | AnalyticDB (ADB) | Greenplum (GP) |
| --- | ---: | ---: |
| Index Space | 0.66TB | 2.71TB |
| Index Building Time | 1 hour | 0.5 hour |
| Asynchronous? | Yes | No |
| Data Insertion Time | 4,015s | 20,910s |

#### 4.2.5 增量数据索引

异步索引会带来一个性能空窗：新索引上线前，增量数据缺少完整索引，查询增量数据可能变慢。AnalyticDB 在读节点上独立地为增量数据建立 sorted index。图 11 中，升序 sorted index 是 data block 中按值排序的 row id 数组，第 $i$ 个元素 $T_i$ 表示 data block 中第 $i$ 小的值位于第 $T_i$ 行；查询因此从扫描 $O(n)$ 转化为二分搜索 $O(\log n)$。系统在每个 data block 中分配额外 header 保存该索引；一个 block 约含 30K 行，row id 使用 short integer，因此 header（即 sorted index）约 60KB。flush data block 前，索引引擎构建 sorted index 并写入文件头。整个过程在读节点本地执行，开销很小。

![图 11：增量数据的排序索引。](assets/analyticdb-fig11-sorted-index-incremental.png)

#### 4.2.6 条件索引缓存

传统数据库以 index page 为粒度把索引缓存在内存中，以降低昂贵的磁盘 I/O。AnalyticDB 不仅使用 index-page cache，还使用更激进的 query-condition cache：查询条件（例如 `id < 123`）作为 key，结果 row id 作为 value，从而完全避免对 index page 重复过滤；condition cache 未命中时，再访问 index-page cache 中的索引计算结果。

这一两级缓存策略的挑战在于，用户条件持续且剧烈变化，可能频繁淘汰缓存。不过，我们观察到这不会明显损害整体缓存效果：一是结果集很大的条件较少且不经常变化，例如 `WHERE city='Beijing'`，所以缓存可以长时间保留；二是结果集很小的条件数量庞大、变化剧烈，例如 `WHERE user_id=XXX`，但重新计算成本很低。总体而言，高成本计算能被良好缓存以节省资源，轻量查询则重新计算而几乎不增加开销。

## 5. 优化器和执行引擎

本节分别介绍 AnalyticDB 优化器和执行引擎采用的新优化，它们进一步降低查询延迟并提高并发能力。

### 5.1 优化器

AnalyticDB 优化器同时提供 CBO（cost-based optimization）和 RBO（rule-based optimization），目标是服务要求极低响应时间和高并发的实时在线分析。优化器包含丰富的关系代数转换规则，以保证总能选出最优计划。这些规则包括：cropping、pushdown/merge、deduplication、constant folding/predicate derivation 等基本优化规则；面向 BroadcastHashJoin、RedistributedHashJoin、NestLoopIndexJoin 等不同 join，以及 Aggregate、JoinReorder、GroupBy pushdown、Exchange pushdown、Sort pushdown 等操作的 probe 优化规则；以及 Common Table Expression 等高级优化规则。除通用 CBO/RBO 外，AnalyticDB 还开发了两个关键特性：存储感知优化和高效实时采样。

图 12 展示 STARs（Strategy Alternative Rules）框架。优化器内部包含数据源能力、STARs 建模、动态规划、source-specific planner 和 connector manager。不同数据源向框架注册能力，优化器据此生成可执行 API 调用，并选择合适的数据位置和执行路径。

![图 12：AnalyticDB 的 STARs 框架。](assets/analyticdb-fig12-stars-framework.png)

#### 5.1.1 存储感知计划优化

谓词下推。谓词（即条件）下推会从 SQL 中抽取可利用底层存储能力的关系代数计算，并把查询计划转换成计算层和存储层两个等价部分。原始查询计划中没有支持这种拆分的明确边界，因此完全依赖优化器完成。许多分布式数据库已经实现谓词下推，但主要关注单列条件的 AND 运算，不考虑 function、join 等通常在计算层实现的常见算子；原因是很多数据库没有接口让存储层注册高级能力，存储层最多只能执行单列或组合条件过滤。

AnalyticDB 引入 STARs（STrategy Alternative Rules）框架 [30, 14]，使优化器能够扩展谓词下推，如图 12 所示。STARs 以高层、声明式且与实现无关的方式描述合法查询执行策略；每个 STAR 都由底层数据库算子或其他 STAR 构造出一组高层结构。框架按照关系代数维度抽象异构数据源能力，并把存储能力表述成可利用的关系代数。STARs 还提供成本计算：是否下推不仅取决于存储能力，也取决于执行该关系代数能力的成本。动态规划会同时参考成本和执行能力，避免盲目下推造成性能下降，这对低延迟、高并发环境十分重要。优化器完成初始分布式执行计划后，会通过 dynamic programming 封装适用于目标数据源的关系代数算子，并把它们转换成对应的存储 API 调用。

Join 下推。分布式数据库执行计划中的另一个重要问题是数据重分布；物理数据分布特征与关系代数逻辑语义不匹配时，数据重分布会产生序列化、反序列化和网络传输等高昂成本。以 `SELECT T.tid, count(*) FROM T JOIN S ON T.sid = S.sid GROUP BY T.tid` 为例，AnalyticDB 会根据表 T、S 是否在同一字段上哈希，以及其分区是否放在同一读节点（第 3.4.2 节），选择最佳 join pushdown 策略。如果 T、S 没有按同一字段哈希，优化器会从底层存储取得两表大小，明确判断 shuffle 哪张表更高效。优化器会展开并计算所有可能执行计划的成本，从而针对不同数据规模的数据特征得到最优计划。

基于索引的 join 和 aggregation。全列索引允许直接查询现有索引，进一步消除构建 hash index 的开销。调整 join order 时，如果大多数 join column 都是 partition column 且已有索引，优化器会避免生成 BushyTree，优先选择 LeftDeepTree，以便更充分利用现有索引（图 13）。AnalyticDB 还下推 predicate 和 aggregation；例如 `count` 等聚合可直接由索引返回，过滤也可完全在索引上求值。这些优化降低查询延迟并改善集群利用率，使 AnalyticDB 能够支持高并发。

![图 13：存储感知 join 优化。](assets/analyticdb-fig13-storage-aware-join.png)

#### 5.1.2 高效实时采样

成本估计是 CBO 的基础，它取决于高度依赖可用统计信息的基数估计。现代数据库收集和使用统计信息的方式有限，不能很好处理数据倾斜和相关性，因而可能产生次优查询计划。AnalyticDB 的目标之一是让简单与复杂查询都获得很短响应时间；实时统计、谓词选择率 profiling 和执行结果反馈等传统方法因开销和复杂度而不适用。

因此，AnalyticDB 设计并实现了高效的、基于采样的基数估计框架。它利用高性能存储引擎中的丰富索引类型、缓存和优化计算路径，快速访问并求值数据。优化时，优化器通过框架 API 把采样谓词发送给存储引擎；谓词是单个还是复合形式，由优化规则决定。存储引擎通过合适的 index/cache 访问样本数据，以优化计算路径求值谓词，并返回基数结果。优化器据此估计候选计划并选择最优计划。

即使该框架已经能高效估计基数，AnalyticDB 仍进一步降低关键业务场景中亚秒级查询的开销，包括缓存之前的采样结果和基数估计、优化采样算法，以及改进派生基数等。应用这些优化后，基于采样的基数框架可在毫秒级的极低开销下给出高精度估计。

### 5.2 执行引擎

AnalyticDB 提供通用的 pipeline-mode 执行引擎，并在其上提供 DAG [27]（Directed Acyclic Graph）运行框架。该引擎既适合低延迟的小型负载，也适合高吞吐的大规模负载。执行引擎以列为中心，利用底层 hybrid store 按列聚集数据的特性；相对行式执行引擎，这种向量化引擎更 cache-friendly，也避免把不需要的数据加载到内存。

与许多 OLAP 系统一样，AnalyticDB 使用 runtime code generator [32]（CodeGen）提高 CPU-intensive 操作的效率。CodeGen 基于 ANTLR ASM [2]，为 expression tree 动态生成代码，并把运行时因素纳入考虑，从而在 task 粒度上利用异构硬件。例如，向量化引擎中的大多数数据类型（如 `int` 和 `double`）都已经对齐；在 CPU 支持 AVX-512 指令集的异构集群中，AnalyticDB 可生成使用 SIMD 指令的 bytecode 来提升性能。存储层和执行引擎还统一内部数据表示，使执行引擎能直接操作 serialized binary data，而不是 Java object；这消除了序列化和反序列化开销，后者在 shuffle 大量数据时会占用超过 20% 的时间。

## 6. 评估

本节通过真实工作负载和 TPC-H benchmark [11] 评估 AnalyticDB，展示它在不同查询类型下的性能和写入能力。

### 6.1 实验设置

实验运行在 8 台物理机组成的集群上。每台机器包含 Intel Xeon Platinum 8163 CPU（2.50GHz）、300GB 内存和 3TB SSD，并通过 10Gbps Ethernet 连接。实验创建一个 AnalyticDB 实例，包含 4 个 coordinator、4 个 write node 和 32 个 read node。

**真实工作负载。** 实验使用生产中的两张真实表。`Users` 表以 `user_id` 为主键，包含 64 个主分区、无次分区；`Orders` 表以 `order_id` 为主键，包含 64 个主分区和 10 个次分区。两张表通过 `user_id` 关联。表 2 展示从用户请求中生成的三类查询，覆盖全扫描、点查找到多表 join。

表 2：用于评估的三类查询。

| Query type | Query |
| --- | --- |
| Full Scan (Q1) | `SELECT * FROM orders ORDER BY o_trade_time LIMIT 10` |
| Point Lookup (Q2) | `SELECT * FROM orders WHERE o_trade_time BETWEEN '2018-11-13 15:15:21' AND '2018-11-13 16:15:21' AND o_trade_prize BETWEEN 50 AND 60 AND o_seller_id=9999 LIMIT 1000` |
| Multi-table Join (Q3) | `SELECT o_seller_id, SUM(o_trade_prize) AS c FROM orders JOIN user ON orders.o_user_id = user.u_id WHERE u_age=10 AND o_trade_time BETWEEN '2018-11-13 15:15:21' AND '2018-11-13 16:15:21' GROUP BY o_seller_id ORDER BY c DESC LIMIT 10;` |

三条查询都包含时间戳列 `o_trade_time`。这是因为 Druid 必须以时间戳列作为分区键；不指定时间戳列的查询会慢得多 [36]。

**对比系统。** 我们将 AnalyticDB 与四个 OLAP 系统比较：PrestoDB [9]、Spark SQL [13]、Druid [36] 和 Greenplum [5]，均使用默认配置。Greenplum 在所有列上有索引；Druid 不支持数值列索引；PrestoDB 和 Spark SQL 使用 Apache ORC（Optimized Record Columnar）文件 [3]，没有任何列索引。Druid 不支持 JOIN 等复杂查询，因此无法执行表 2 中的 Q3 和多数 TPC-H 查询；我们在相应实验中省略 Druid。下文所有实验中的 concurrency number 均指同时运行的查询数。

### 6.2 真实工作负载

本节先介绍 1TB 和 10TB 数据上的查询性能，再给出写吞吐。

#### 6.2.1 1TB 数据查询

我们生成 1TB 数据集，运行表 2 中的三条查询。图 14 和图 15 分别展示 AnalyticDB、PrestoDB、Druid、Spark SQL 和 Greenplum 的 50 分位与 95 分位查询延迟。三个子图对应 Q1、Q2 和 Q3。AnalyticDB 在三类查询上都至少比其他系统低一个数量级。

![图 14：1TB 数据上的 50 分位延迟，子图 (a) Q1、(b) Q2、(c) Q3；PDB 表示 PrestoDB，ADB 表示 AnalyticDB，GP 表示 Greenplum。](assets/analyticdb-fig14-latency-p50-1tb.png)

![图 15：1TB 数据上的 95 分位延迟，子图 (a) Q1、(b) Q2、(c) Q3；PDB 表示 PrestoDB，ADB 表示 AnalyticDB，GP 表示 Greenplum。](assets/analyticdb-fig15-latency-p95-1tb.png)

**Q1。** 受益于索引引擎，AnalyticDB 避免对全表执行昂贵的扫描和排序，这不同于 PrestoDB 和 Spark SQL。它把 ORDER BY 与 LIMIT 算子分发到每个次分区；次分区保存 `o_trade_time` 列的有序索引，所以各分区只需遍历几十条索引项即可取得合格 row id。Greenplum 虽有全列索引，却不能将其用于 ORDER BY，仍需全扫描；Druid 以 `o_trade_time` 做范围分区 [36]，执行该列上的 ORDER BY 时从最大的范围分区开始过滤，表现好于 Greenplum，但因仍需扫描该分区全部行而慢于 AnalyticDB。

**Q2。** 数据集中满足 `o_trade_time`、`o_trade_prize`、`o_seller_id` 条件的行数分别为 306,340,963、209,994,127 和 210,408。PrestoDB 与 Spark SQL 无索引，需要扫描全部行；Druid 和 Greenplum 可从索引列的快速搜索中获益，但 Druid 只在字符串列上建索引，Greenplum 虽在所有列上建索引，却必须依次过滤多个条件，且不缓存未变化的条件。AnalyticDB 并行扫描三列索引，并分别缓存合格 row id（第 4.2.6 节），所以后续具有相同条件的查询能从索引缓存中获益。

**Q3。** Q3 是多表 join scan 与 GROUP BY、ORDER BY 的组合，比 Q1/Q2 更复杂，因此不同并发下的 50/95 分位延迟都更高。尽管查询复杂度使延迟略高，AnalyticDB 仍能保证最优执行：它把 join 算子转化为等值子查询，并利用索引完成这些子查询；还继续借助索引执行 GROUP BY 和 ORDER BY，避免构建 hash map 的开销。Greenplum 因 hash join 的 hash map 开销而更慢；为公平比较，我们也让 AnalyticDB 使用 hash join，此时其性能可与 Greenplum 相当。

#### 6.2.2 10TB 数据查询

我们进一步生成 10TB 数据集并提高并发。由于对比系统在大数据集和更高并发下远慢于 AnalyticDB，本节省略这些系统。图 16 对比 1TB 与 10TB 数据上三类查询的 50 分位延迟。Q1 和 Q2 在不同并发下仍保持百毫秒级。Q3 在 200 并发下延迟显著高于 40 并发，因为 8 台机器的计算能力已经饱和：64 个主分区、10 个次分区和 200 并发会产生多达 128,000 个实际并发线程，而 8 台机器总共只有 $48 \times 8 = 384$ 个 CPU 核。Q3 是计算密集型查询，频繁上下文切换导致性能下降和高延迟。

![图 16：AnalyticDB 在 1TB 和 10TB 数据上的 50 分位延迟。](assets/analyticdb-fig16-latency-1tb-10tb.png)

10TB 上不同并发的趋势与 1TB 类似。数据量增加后查询延迟仅约翻倍，因为 AnalyticDB 先通过索引查找 row id，再获取合格行；索引缓存降低了 lookup 成本。总体性能更多受索引计算和合格行数影响，而非表总大小。

#### 6.2.3 写吞吐

为评估写性能，实验向 Orders 表插入记录，每条记录 500 bytes。表 3 展示不同写节点数量下的写吞吐。由于读写解耦和异步索引构建，吞吐随写节点数近似线性增长，直到盘古带宽饱和。当写节点数为 10 时，吞吐达到每秒 625,000 次写请求，对应约 300MB/s。索引构建任务分布在整个 AnalyticDB 集群上、占用的带宽开销已在第 4.2.4 节评估，不会影响查询效率或写吞吐。

表 3：不同写节点数量下的写吞吐。

| write node number | 2 | 4 | 6 | 8 | 10 |
| --- | ---: | ---: | ---: | ---: | ---: |
| write throughput | 130k | 250k | 381k | 498k | 625k |

### 6.3 TPC-H Benchmark

我们生成 1TB 数据用于 TPC-H 评估。图 17 比较 AnalyticDB、PrestoDB、Spark SQL 和 Greenplum 的执行时间。若某个查询时间为 1,000 秒，表示系统运行该查询时发生异常且未得到结果，例如 PrestoDB 的 Query No.3 和 Spark SQL 的 Query No.21。AnalyticDB 在 22 个查询中的 20 个上取得最短运行时间，并比第二名 Greenplum 快约 2 倍。

![图 17：TPC-H 性能对比。](assets/analyticdb-fig17-tpch-comparison.png)

相较 Spark SQL，AnalyticDB 采用流水线处理模型和索引，比 stage-based 处理更快；PrestoDB 也采用流水线处理，但列上没有索引。Greenplum 同样兼具流水线处理和全列索引，而 AnalyticDB 还有四项优势：第一，AnalyticDB 使用混合行列存储，Greenplum 使用列存；常见 TPC-H 查询涉及约一半列，所以 AnalyticDB 一次 I/O 即可取得一行的多个列。第二，AnalyticDB 基于运行时代价的索引路径选择使用真实中间结果，比 Greenplum 基于统计信息的规划产生更好的表访问计划。第三，AnalyticDB 把 K-way merging 与复合谓词下推结合。第四，AnalyticDB 使用向量化执行引擎，并把优化后的 CodeGen 应用于所有算子和表达式。Query No.2 上 AnalyticDB 慢于 PrestoDB 与 Greenplum，原因是为多表 join 选择了不同的 join order。

## 7. 结论

本文介绍了 AnalyticDB，这是阿里巴巴面向高并发、低延迟和实时分析的 OLAP 数据库。AnalyticDB 具有高效的索引引擎，可在所有列上异步构建索引，从而提升查询性能并隐藏索引构建开销；经过审慎设计，全列索引只额外消耗 66% 的存储空间。AnalyticDB 扩展混合行列布局，以支持复杂查询可能涉及的结构化数据和其他复杂类型数据。为了同时提供高吞吐写入和高并发查询，AnalyticDB 采用读写解耦架构。此外，我们增强了 AnalyticDB 的优化器和执行引擎，以充分利用存储和索引的优势。我们的实验表明，这些设计使 AnalyticDB 相较先进 OLAP 系统取得更好的性能。

## 致谢

我们感谢匿名审稿人对本文提出的深刻意见。我们也借此机会感谢 Yineng Chen、Xiaolong Xie、Congnan Luo、Jiye Tu、Wenjun Dai、Xiang Zhou、Shaojin Wen、Wenbo Ma、Jiannan Ji、Yu Dong、Jin Hu、Caihua Yin、Yujun Liao、Zhe Li、Ruonan Guo、Shengtao Li、Chisheng Dong、Xiaoying Lan、Lindou Liu、Qian Li、Angkai Yang、Fang Sun、Yongdong Wu、Wei Zhao、Xi Chen、Bowen Zheng、Haoran Zhang、Qiaoyi Ding、Yong Li、Dongcan Cui 和 Yi Yuan 对 AnalyticDB 开发、实现和管理所作的贡献。

## 8. 参考文献

- [1] Alibaba Cloud. https://www.alibabacloud.com.
- [2] ANTLR ASM. https://www.antlr.org.
- [3] Apache ORC File. https://orc.apache.org/.
- [4] Benchmarking Nearest Neighbours. https://github.com/erikbern/ann-benchmarks.
- [5] Greenplum. https://greenplum.org/.
- [6] MySQL. https://www.mysql.com/.
- [7] Pangu. https://www.alibabacloud.com/blog/pangu-the-high-performance-distributed-file-system-by-alibaba-cloud-594059.
- [8] PostgreSQL. https://www.postgresql.org/.
- [9] Presto. https://prestodb.io/.
- [10] Teradata Database. http://www.teradata.com.
- [11] TPC-H Benchmark. http://www.tpc.org/tpch/.
- [12] D. J. Abadi, S. R. Madden, and N. Hachem. Column-stores vs. row-stores: how different are they really? In SIGMOD, pages 967–980. ACM, 2008.
- [13] M. Armbrust, R. S. Xin, C. Lian, Y. Huai, D. Liu, J. K. Bradley, X. Meng, T. Kaftan, M. J. Franklin, A. Ghodsi, et al. Spark SQL: Relational data processing in Spark. In SIGMOD, pages 1383–1394. ACM, 2015.
- [14] J. Backus. Can programming be liberated from the von Neumann style?: a functional style and its algebra of programs. ACM, 2007.
- [15] P. A. Bernstein and N. Goodman. Multiversion concurrency control-theory and algorithms. ACM Transactions on Database Systems (TODS), 8(4):465–483, 1983.
- [16] D. Comer. Ubiquitous B-tree. ACM Computing Surveys (CSUR), 11(2):121–137, 1979.
- [17] T. H. Cormen, C. E. Leiserson, R. L. Rivest, and C. Stein. Introduction to Algorithms. MIT Press, 2009.
- [18] J. Dean and S. Ghemawat. MapReduce: simplified data processing on large clusters. Communications of the ACM, 51(1):107–113, 2008.
- [19] A. Eisenberg, J. Melton, K. Kulkarni, J.-E. Michels, and F. Zemke. SQL: 2003 has been published. ACM SIGMOD Record, 33(1):119–126, 2004.
- [20] M. Grund, J. Krüger, H. Plattner, A. Zeier, P. Cudre-Mauroux, and S. Madden. Hyrise: a main memory hybrid storage engine. PVLDB, 4(2):105–116, 2010.
- [21] A. Gupta, D. Agarwal, D. Tan, J. Kulesza, R. Pathak, S. Stefani, and V. Srinivasan. Amazon Redshift and the case for simpler data warehouses. In SIGMOD, pages 1917–1923. ACM, 2015.
- [22] K. Hajebi, Y. Abbasi-Yadkori, H. Shahbazi, and H. Zhang. Fast approximate nearest-neighbor search with k-nearest neighbor graph. In IJCAI, pages 1312–1317, 2011.
- [23] S. Harizopoulos, V. Liang, D. J. Abadi, and S. Madden. Performance tradeoffs in read-optimized databases. In VLDB, pages 487–498. VLDB Endowment, 2006.
- [24] P. Hunt, M. Konar, F. P. Junqueira, and B. Reed. ZooKeeper: Wait-free coordination for internet-scale systems. In USENIX ATC, volume 8. Boston, MA, USA, 2010.
- [25] J.-F. Im, K. Gopalakrishna, S. Subramaniam, M. Shrivastava, A. Tumbde, X. Jiang, J. Dai, S. Lee, N. Pawar, J. Li, et al. Pinot: Realtime OLAP for 530 million users. In SIGMOD, pages 583–594. ACM, 2018.
- [26] H. Jégou, M. Douze, and C. Schmid. Product quantization for nearest neighbor search. IEEE Transactions on Pattern Analysis and Machine Intelligence, 33(1):117–128, 2011.
- [27] F. V. Jensen. An introduction to Bayesian networks, volume 210. UCL Press London, 1996.
- [28] M. Kornacker, A. Behm, V. Bittorf, T. Bobrovytsky, C. Ching, A. Choi, J. Erickson, M. Grund, D. Hecht, M. Jacobs, et al. Impala: A modern, open-source SQL engine for Hadoop. In CIDR, volume 1, page 9, 2015.
- [29] A. Lamb, M. Fuller, R. Varadarajan, N. Tran, B. Vandiver, L. Doshi, and C. Bear. The Vertica analytic database: C-store 7 years later. PVLDB, 5(12):1790–1801, 2012.
- [30] G. M. Lohman. Grammar-like functional rules for representing query optimization alternatives, volume 17. ACM, 1988.
- [31] S. Melnik, A. Gubarev, J. J. Long, G. Romer, S. Shivakumar, M. Tolton, and T. Vassilakis. Dremel: interactive analysis of web-scale datasets. PVLDB, 3(1-2):330–339, 2010.
- [32] T. Neumann. Efficiently compiling efficient query plans for modern hardware. PVLDB, 4(9):539–550, 2011.
- [33] K. Sato. An inside look at Google BigQuery.(2012). Retrieved Jan, 29:2018, 2012.
- [34] M. Stonebraker, D. J. Abadi, A. Batkin, X. Chen, M. Cherniack, M. Ferreira, E. Lau, A. Lin, S. Madden, E. O'Neil, et al. C-store: a column-oriented DBMS. In VLDB, pages 553–564. VLDB Endowment, 2005.
- [35] A. Thusoo, J. S. Sarma, N. Jain, Z. Shao, P. Chakka, S. Anthony, H. Liu, P. Wyckoff, and R. Murthy. Hive: a warehousing solution over a MapReduce framework. PVLDB, 2(2):1626–1629, 2009.
- [36] F. Yang, E. Tschetter, X. Léauté, N. Ray, G. Merlino, and D. Ganguli. Druid: A real-time analytical data store. In SIGMOD, pages 157–168. ACM, 2014.
- [37] M. Zaharia, M. Chowdhury, T. Das, A. Dave, J. Ma, M. McCauley, M. J. Franklin, S. Shenker, and I. Stoica. Resilient distributed datasets: A fault-tolerant abstraction for in-memory cluster computing. In NSDI, pages 2–2. USENIX Association, 2012.
- [38] Z. Zhang, C. Li, Y. Tao, R. Yang, H. Tang, and J. Xu. Fuxi: a fault-tolerant resource management and job scheduling system at internet scale. PVLDB, 7(13):1393–1404, 2014.
- [39] M. Zukowski, S. Heman, N. Nes, and P. Boncz. Super-scalar RAM-CPU cache compression. IEEE, 2006.
