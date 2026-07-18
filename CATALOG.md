# 论文目录

> 本文件由 `python3 scripts/papers.py catalog` 从各论文的 `paper.yaml` 生成，请勿手工编辑。

## 总览

- 论文记录：134
- 已验收译文：128
- 译文草稿：0
- 仅有原文：0
- 已跳过：6
- 原文不可用：0

## 领域分布

| 一级领域 | 数量 |
| --- | ---: |
| 基础与综述 (`foundations`) | 2 |
| 系统架构 (`system-architecture`) | 23 |
| 查询处理 (`query-processing`) | 52 |
| 存储 (`storage`) | 18 |
| 事务与并发控制 (`transactions`) | 7 |
| 分布式数据库 (`distributed-databases`) | 6 |
| 数据集成 (`data-integration`) | 2 |
| 流处理 (`streaming`) | 6 |
| 可靠性与测试 (`reliability-and-testing`) | 4 |
| 专用数据库 (`specialized-databases`) | 8 |
| AI 与数据系统 (`ai-and-data`) | 6 |

## 按领域浏览

### 基础与综述 (`foundations`，2 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [A Relational Model of Data for Large Shared Data Banks](papers/foundations/a-relational-model-of-data-for-large-shared-data-banks/translation.md) | 数据库总览、关系模型 | 1970 | 5.0 | translated | [原文](https://research.ibm.com/publications/a-relational-model-of-data-for-large-shared-data-banks) |
| [Architecture of a Database System](papers/foundations/architecture-of-a-database-system/source.pdf) | 数据库总览 | 2007 | 4.0 | skipped | [原文](https://dsf.berkeley.edu/papers/fntdb07-architecture.pdf) |

### 系统架构 (`system-architecture`，23 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [Alibaba Hologres: A Cloud-Native Service for Hybrid Serving/Analytical Processing](papers/system-architecture/alibaba-hologres-a-cloud-native-service-for-hybrid-serving-analytical-processing/translation.md) | 数据库系统设计 | 2020 | 3.5 | translated | [原文](https://www.vldb.org/pvldb/vol13/p3272-jiang.pdf) |
| [Amazon Redshift and the Case for Simpler Data Warehouses](papers/system-architecture/amazon-redshift-and-the-case-for-simpler-data-warehouses/translation.md) | 数据库系统设计 | 2015 | 4.0 | translated | [原文](https://www.amazon.science/publications/amazon-redshift-and-the-case-for-simpler-data-warehouses) |
| [AnalyticDB: Real-time OLAP Database System at Alibaba Cloud](papers/system-architecture/analyticdb-real-time-olap-database-system-at-alibaba-cloud/translation.md) | 数据库系统设计 | 2019 | 3.5 | translated | [原文](https://www.vldb.org/pvldb/vol12/p2059-zhan.pdf) |
| [Big Metadata: When Metadata is Big Data](papers/system-architecture/big-metadata-when-metadata-is-big-data/translation.md) | 数据库系统设计 | 2021 | 3.5 | translated | [原文](http://vldb.org/pvldb/vol14/p3083-edara.pdf) |
| [Bringing Cloud-Native Storage to SAP IQ](papers/system-architecture/bringing-cloud-native-storage-to-sap-iq/translation.md) | 云原生 | 2021 | 3.0 | translated | [原文](https://dl.acm.org/doi/abs/10.1145/3448016.3457563) |
| [Building An Elastic Query Engine on Disaggregated Storage](papers/system-architecture/building-an-elastic-query-engine-on-disaggregated-storage/translation.md) | 数据库系统设计 | 2020 | 4.0 | translated | [原文](https://www.usenix.org/system/files/nsdi20-paper-vuppalapati.pdf) |
| [Data Warehousing in the Cloud: Amazon Redshift vs Microsoft Azure SQL](papers/system-architecture/data-warehousing-in-the-cloud-amazon-redshift-vs-microsoft-azure-sql/translation.md) | 数据库系统设计 | 2017 | 1.5 | translated | [原文](https://www.scitepress.org/papers/2017/65871/65871.pdf) |
| [DB2 with BLU Acceleration: So Much More than Just a Column Store](papers/system-architecture/db2-with-blu-acceleration-so-much-more-than-just-a-column-store/translation.md) | 数据库系统设计 | 2013 | 4.0 | translated | [原文](http://www.vldb.org/pvldb/vol6/p1080-barber.pdf) |
| [Dremel: Interactive Analysis of Web-Scale Datasets](papers/system-architecture/dremel-interactive-analysis-of-web-scale-datasets/translation.md) | 数据库系统设计 | 2010 | 5.0 | translated | [原文](https://static.googleusercontent.com/media/research.google.com/zh-CN//pubs/archive/36632.pdf) |
| [DuckDB: an Embeddable Analytical Database](papers/system-architecture/duckdb-embeddable-analytical-database/translation.md) | 数据库系统设计、分析型数据库 | 2019 | 4.5 | translated | [原文](https://duckdb.org/library/duckdb/) |
| [F1 Query: Declarative Querying at Scale](papers/system-architecture/f1-query-declarative-querying-at-scale/translation.md) | 数据库系统设计 | 2018 | 3.5 | translated | [原文](http://www.vldb.org/pvldb/vol11/p1835-samwel.pdf) |
| [HAWQ: A Massively Parallel Processing SQL Engine in Hadoop](papers/system-architecture/hawq-a-massively-parallel-processing-sql-engine-in-hadoop/translation.md) | 数据库系统设计 | 2014 | 3.0 | translated | [原文](https://doi.org/10.1145/2588555.2595636) |
| [Lakehouse: A New Generation of Open Platforms that Unify Data Warehousing and Advanced Analytics](papers/system-architecture/lakehouse-new-generation-open-platforms/translation.md) | 数据库系统设计、云原生、面向 AI 的数据系统、湖仓一体 | 2021 | 4.5 | translated | [原文](https://www.vldb.org/cidrdb/2021/lakehouse-a-new-generation-of-open-platforms-that-unify-data-warehousing-and-advanced-analytics.html) |
| [Napa: Powering Scalable Data Warehousing with Robust Query Performance at Google](papers/system-architecture/napa-powering-scalable-data-warehousing-with-robust-query-performance-at-google/translation.md) | 数据库系统设计 | 2021 | 3.5 | translated | [原文](http://vldb.org/pvldb/vol14/p2986-sankaranarayanan.pdf) |
| [Procella: Unifying serving and analytical data at YouTube](papers/system-architecture/procella-unifying-serving-and-analytical-data-at-youtube/translation.md) | 数据库系统设计 | 2019 | 3.5 | translated | [原文](http://www.vldb.org/pvldb/vol12/p2022-chattopadhyay.pdf) |
| [Resilient Distributed Datasets: A Fault-Tolerant Abstraction for In-Memory Cluster Computing](papers/system-architecture/resilient-distributed-datasets-a-fault-tolerant-abstraction-for-in-memory-cluster-computing/translation.md) | 数据库系统设计 | 2012 | 5.0 | translated | [原文](http://people.csail.mit.edu/matei/papers/2012/nsdi_spark.pdf) |
| [Starling: A Scalable Query Engine on Cloud Function Services](papers/system-architecture/starling-scalable-query-engine-cloud-function-services/translation.md) | 云原生 | 2019 | 2.5 | translated | [原文](https://arxiv.org/pdf/1911.11727.pdf) |
| [System R: Relational Approach to Database Management](papers/system-architecture/system-r-relational-approach-to-database-management/translation.md) | 数据库系统设计、关系模型 | 1976 | 5.0 | translated | [原文](https://research.ibm.com/publications/system-r-relational-approach-to-database-management) |
| [The Design and Implementation of INGRES](papers/system-architecture/design-and-implementation-of-ingres/translation.md) | 数据库系统设计、关系模型 | 1976 | 4.5 | translated | [原文](https://www2.eecs.berkeley.edu/Pubs/TechRpts/1976/29338.html) |
| [The Design of POSTGRES](papers/system-architecture/design-of-postgres/translation.md) | 数据库系统设计 | 1985 | 5.0 | translated | [原文](https://www2.eecs.berkeley.edu/Pubs/TechRpts/1985/602.html) |
| [The Snowflake Elastic Data Warehouse](papers/system-architecture/the-snowflake-elastic-data-warehouse/translation.md) | 数据库系统设计 | 2016 | 5.0 | translated | [原文](https://doi.org/10.1145/2882903.2903741) |
| [The Vertica Analytic Database: C-Store 7 Years Later](papers/system-architecture/the-vertica-analytic-database-c-store-7-years-later/translation.md) | 数据库系统设计 | 2012 | 4.0 | translated | [原文](https://vldb.org/pvldb/vol5/p1790_andrewlamb_vldb2012.pdf) |
| [What Serverless Computing Is and Should Become: The Next Phase of Cloud Computing](papers/system-architecture/what-serverless-computing-is-and-should-become/translation.md) | 云原生 | 2021 | 4.0 | translated | [原文](https://dl.acm.org/doi/pdf/10.1145/3406011) |

### 查询处理 (`query-processing`，52 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [Access Path Selection in a Relational Database Management System](papers/query-processing/access-path-selection-relational-database-management-system/translation.md) | 查询优化 | 1979 | 5.0 | translated | [原文](https://research.ibm.com/publications/access-path-selection-in-a-relational-database-management-system) |
| [Adaptive Execution of Compiled Queries](papers/query-processing/adaptive-execution-compiled-queries/translation.md) | 查询编译 | 2018 | 3.5 | translated | [原文](https://db.in.tum.de/~leis/papers/adaptiveexecution.pdf) |
| [Adaptive Optimization of Very Large Join Queries](papers/query-processing/adaptive-optimization-very-large-join-queries/translation.md) | 查询优化 | 2018 | 3.5 | translated | [原文](https://db.in.tum.de/~radke/papers/hugejoins.pdf) |
| [An Overview of Query Optimization in Relational Systems](papers/query-processing/overview-query-optimization-relational-systems/translation.md) | 查询优化 | 1998 | 4.0 | translated | [原文](https://www.microsoft.com/en-us/research/publication/an-overview-of-query-optimization-in-relational-systems-paper/) |
| [Apache Calcite: A Foundational Framework for Optimized Query Processing Over Heterogeneous Data Sources](papers/query-processing/apache-calcite-a-foundational-framework-for-optimized-query-processing-over-heterogeneous-data-sources/translation.md) | 查询优化、数据联邦 | 2018 | 5.0 | translated | [原文](https://arxiv.org/pdf/1802.10233.pdf) |
| [Are We Ready For Learned Cardinality Estimation?](papers/query-processing/are-we-ready-for-learned-cardinality-estimation/translation.md) | 基数估计、AI 优化数据库 | 2021 | 3.5 | translated | [原文](https://doi.org/10.14778/3461535.3461552) |
| [Balancing vectorized query execution with bandwidth-optimized storage](papers/query-processing/balancing-vectorized-query-execution-bandwidth-optimized-storage/source.pdf) | 向量化执行 | 2009 | 4.0 | skipped | [原文](https://dare.uva.nl/search?identifier=5ccbb60a-38b8-4eeb-858a-e7735dd37487) |
| [Balsa: Learning a Query Optimizer Without Expert Demonstrations](papers/query-processing/balsa-learning-a-query-optimizer-without-expert-demonstrations/translation.md) | 查询优化、AI 优化数据库 | 2022 | 3.5 | translated | [原文](https://doi.org/10.1145/3514221.3517885) |
| [Bao: Making Learned Query Optimization Practical](papers/query-processing/bao-making-learned-query-optimization-practical/translation.md) | 查询优化、AI 优化数据库 | 2021 | 4.0 | translated | [原文](https://doi.org/10.1145/3448016.3452838) |
| [BIPie: Fast Selection and Aggregation on Encoded Data using Operator Specialization](papers/query-processing/bipie-fast-selection-aggregation-encoded-data-operator-specialization/translation.md) | 向量化执行 | 2018 | 2.5 | translated | [原文](https://doi.org/10.1145/3183713.3190658) |
| [DeepDB: Learn from Data, not from Queries!](papers/query-processing/deepdb-learn-from-data-not-from-queries/translation.md) | 基数估计、AI 优化数据库 | 2020 | 3.5 | translated | [原文](https://doi.org/10.14778/3384345.3384349) |
| [Efficiency in the Columbia Database Query Optimizer](papers/query-processing/efficiency-columbia-query-optimizer/source.pdf) | 查询优化 | 1998 | 3.5 | skipped | [原文](https://15721.courses.cs.cmu.edu/spring2018/papers/15-optimizer1/xu-columbia-thesis1998.pdf) |
| [Efficiently Compiling Efficient Query Plans for Modern Hardware](papers/query-processing/efficiently-compiling-efficient-query-plans-modern-hardware/translation.md) | 查询编译 | 2011 | 4.5 | translated | [原文](https://www.vldb.org/pvldb/vol4/p539-neumann.pdf) |
| [Everything You Always Wanted to Know About Compiled and Vectorized Queries But Were Afraid to Ask](papers/query-processing/compiled-and-vectorized-queries-afraid-to-ask/translation.md) | 查询编译 | 2018 | 3.5 | translated | [原文](https://www.vldb.org/pvldb/vol11/p2209-kersten.pdf) |
| [Exploiting Upper and Lower Bounds in Top-Down Query Optimization](papers/query-processing/exploiting-upper-lower-bounds-top-down-query-optimization/translation.md) | 查询优化 | 2001 | 3.0 | translated | [原文](https://doi.org/10.1109/IDEAS.2001.938068) |
| [Expression Templates Revisited: A Performance Analysis of the Current ET Methodology](papers/query-processing/expression-templates-revisited/translation.md) | 查询执行 | 2011 | 3.5 | translated | [原文](https://arxiv.org/pdf/1104.1729.pdf) |
| [Generating code for holistic query evaluation](papers/query-processing/generating-code-holistic-query-evaluation/translation.md) | 查询编译 | 2010 | 3.5 | translated | [原文](https://doi.org/10.1109/ICDE.2010.5447892) |
| [How Good Are Query Optimizers, Really?](papers/query-processing/how-good-are-query-optimizers-really/translation.md) | 查询优化 | 2015 | 4.5 | translated | [原文](http://www.vldb.org/pvldb/vol9/p204-leis.pdf) |
| [Impala: A Modern, Open-Source SQL Engine for Hadoop](papers/query-processing/impala-a-modern-open-source-sql-engine-for-hadoop/translation.md) | 查询执行 | 2015 | 4.0 | translated | [原文](http://cidrdb.org/cidr2015/Papers/CIDR15_Paper28.pdf) |
| [Improving Unnesting of Complex Queries](papers/query-processing/improving-unnesting-of-complex-queries/translation.md) | 查询优化 | 2025 | 3.5 | translated | [原文](https://portal.fis.tum.de/en/publications/improving-unnesting-of-complex-queries/) |
| [Interleaved Multi-Vectorizing](papers/query-processing/interleaved-multi-vectorizing/translation.md) | 向量化执行 | 2019 | 3.0 | translated | [原文](http://www.vldb.org/pvldb/vol13/p226-fang.pdf) |
| [Learned Cardinalities: Estimating Correlated Joins with Deep Learning](papers/query-processing/learned-cardinalities-estimating-correlated-joins-deep-learning/translation.md) | 查询优化、基数估计、AI 优化数据库 | 2019 | 4.0 | translated | [原文](https://vldb.org/cidrdb/2019/learned-cardinalities-estimating-correlated-joins-with-deep-learning.html) |
| [LLVM: A Compilation Framework for Lifelong Program Analysis & Transformation](papers/query-processing/llvm-compilation-framework-lifelong-program-analysis-transformation/translation.md) | 查询编译 | 2003 | 4.5 | translated | [原文](https://llvm.org/pubs/2003-09-30-LifelongOptimizationTR.pdf) |
| [Low-Latency Compilation of SQL Queries to Machine Code](papers/query-processing/low-latency-compilation-sql-queries-machine-code/translation.md) | 查询编译 | 2021 | 2.5 | translated | [原文](https://vldb.org/pvldb/vol14/p2691-funke.pdf) |
| [Merge Path - A Visually Intuitive Approach to Parallel Merging](papers/query-processing/merge-path-visually-intuitive-parallel-merging/translation.md) | 查询执行 | 2014 | 4.0 | translated | [原文](https://arxiv.org/abs/1406.2628) |
| [MonetDB/X100: Hyper-Pipelining Query Execution](papers/query-processing/monetdb-x100-hyper-pipelining-query-execution/translation.md) | 向量化执行 | 2005 | 5.0 | translated | [原文](https://www.cidrdb.org/cidr2005/papers/P19.pdf) |
| [Morsel-Driven Parallelism: A NUMA-Aware Query Evaluation Framework for the Many-Core Age](papers/query-processing/morsel-driven-parallelism/translation.md) | 查询执行 | 2014 | 4.5 | translated | [原文](https://doi.org/10.1145/2588555.2610507) |
| [Neo: A Learned Query Optimizer](papers/query-processing/neo-a-learned-query-optimizer/translation.md) | 查询优化、AI 优化数据库 | 2019 | 4.0 | translated | [原文](https://www.vldb.org/pvldb/vol12/p1705-marcus.pdf) |
| [NeuroCard: One Cardinality Estimator for All Tables](papers/query-processing/neurocard-one-cardinality-estimator-for-all-tables/translation.md) | 基数估计、AI 优化数据库 | 2021 | 3.5 | translated | [原文](https://doi.org/10.14778/3421424.3421432) |
| [Optimization of Common Table Expressions in MPP Database Systems](papers/query-processing/optimization-common-table-expressions-mpp/translation.md) | 查询优化 | 2015 | 3.5 | translated | [原文](http://www.vldb.org/pvldb/vol8/p1704-elhelw.pdf) |
| [Optimizing Queries over Partitioned Tables in MPP Systems](papers/query-processing/optimizing-queries-partitioned-tables-mpp/translation.md) | 查询优化 | 2014 | 3.5 | translated | [原文](https://d1fto35gcfffzn.cloudfront.net/big-data/white-paper/OptimizingQueriesOverPartitionedTablesInMPPSystems.pdf) |
| [Optimizing Queries Using Materialized Views: A Practical, Scalable Solution](papers/query-processing/optimizing-queries-using-materialized-views/translation.md) | 查询优化 | 2001 | 4.0 | translated | [原文](https://doi.org/10.1145/375663.375706) |
| [Orca: A Modular Query Optimizer Architecture for Big Data](papers/query-processing/orca-modular-query-optimizer-architecture-big-data/translation.md) | 查询优化 | 2014 | 4.5 | translated | [原文](https://doi.org/10.1145/2588555.2595637) |
| [Pattern-defeating Quicksort](papers/query-processing/pattern-defeating-quicksort/translation.md) | 查询执行 | 2021 | 4.0 | translated | [原文](https://arxiv.org/abs/2106.05123) |
| [Permutable Compiled Queries: Dynamically Adapting Compiled Queries without Recompiling](papers/query-processing/permutable-compiled-queries-dynamically-adapting-without-recompiling/translation.md) | 查询编译 | 2021 | 3.0 | translated | [原文](https://db.cs.cmu.edu/papers/2020/p101-menon.pdf) |
| [Photon: A Fast Query Engine for Lakehouse Systems](papers/query-processing/photon-fast-query-engine-lakehouse-systems/translation.md) | 云原生、查询执行、向量化执行、湖仓一体 | 2022 | 4.0 | translated | [原文](https://doi.org/10.1145/3514221.3526054) |
| [Presto: SQL on Everything](papers/query-processing/presto-sql-on-everything/translation.md) | 查询执行、数据联邦 | 2019 | 4.5 | translated | [原文](https://trino.io/Presto_SQL_on_Everything.pdf) |
| [Push vs. Pull-Based Loop Fusion in Query Engines](papers/query-processing/push-vs-pull-loop-fusion/translation.md) | 查询执行 | 2016 | 3.5 | translated | [原文](https://arxiv.org/abs/1610.09166) |
| [Relaxed Operator Fusion for In-Memory Databases: Making Compilation, Vectorization, and Prefetching Work Together At Last](papers/query-processing/relaxed-operator-fusion-in-memory-databases/translation.md) | 查询编译 | 2017 | 3.5 | translated | [原文](http://www.vldb.org/pvldb/vol11/p1-menon.pdf) |
| [Rethinking SIMD Vectorization for In-Memory Databases](papers/query-processing/rethinking-simd-vectorization-in-memory-databases/translation.md) | 向量化执行 | 2015 | 4.0 | translated | [原文](http://www.cs.columbia.edu/~orestis/sigmod15.pdf) |
| [Runtime Code Generation in Cloudera Impala](papers/query-processing/runtime-code-generation-cloudera-impala/translation.md) | 查询编译 | 2014 | 3.5 | translated | [原文](http://sites.computer.org/debull/A14mar/p31.pdf) |
| [SAHA: A String Adaptive Hash Table for Analytical Databases](papers/query-processing/saha-string-adaptive-hash-table-analytical-databases/translation.md) | 向量化执行 | 2020 | 3.0 | translated | [原文](https://www.mdpi.com/2076-3417/10/6/1915) |
| [Spark SQL: Relational Data Processing in Spark](papers/query-processing/spark-sql-relational-data-processing-in-spark/translation.md) | 查询执行 | 2015 | 5.0 | translated | [原文](https://cs.stanford.edu/~matei/papers/2015/sigmod_spark_sql.pdf) |
| [The Cascades Framework for Query Optimization](papers/query-processing/cascades-framework-query-optimization/translation.md) | 查询优化 | 1995 | 5.0 | translated | [原文](https://www.sigmod.org/publications/dblp/db/journals/debu/Graefe95a.html) |
| [The Complete Story of Joins (in HyPer)](papers/query-processing/complete-story-of-joins-hyper/translation.md) | 查询优化 | 2017 | 3.5 | translated | [原文](http://btw2017.informatik.uni-stuttgart.de/slidesandpapers/F1-10-37/paper_web.pdf) |
| [The MemSQL Query Optimizer: A modern optimizer for real-time analytics in a distributed database](papers/query-processing/memsql-query-optimizer/translation.md) | 查询优化 | 2016 | 3.5 | translated | [原文](http://www.vldb.org/pvldb/vol9/p1401-chen.pdf) |
| [The Volcano Optimizer Generator: Extensibility and Efficient Search](papers/query-processing/volcano-optimizer-generator/translation.md) | 查询优化 | 1993 | 4.5 | translated | [原文](https://doi.org/10.1109/ICDE.1993.344061) |
| [Towards Practical Vectorized Analytical Query Engines](papers/query-processing/towards-practical-vectorized-analytical-query-engines/translation.md) | 向量化执行 | 2019 | 3.0 | translated | [原文](https://dl.acm.org/doi/pdf/10.1145/3329785.3329928) |
| [Unnesting Arbitrary Queries](papers/query-processing/unnesting-arbitrary-queries/translation.md) | 查询优化 | 2015 | 4.5 | translated | [原文](https://portal.fis.tum.de/en/publications/unnesting-arbitrary-queries/) |
| [Vectorization vs. Compilation in Query Execution](papers/query-processing/vectorization-vs-compilation-query-execution/translation.md) | 向量化执行 | 2011 | 4.0 | translated | [原文](https://ir.cwi.nl/pub/18550) |
| [Velox: Meta’s Unified Execution Engine](papers/query-processing/velox-metas-unified-execution-engine/translation.md) | 查询执行、向量化执行、面向 AI 的数据系统 | 2022 | 4.5 | translated | [原文](https://doi.org/10.14778/3554821.3554829) |
| [WinMagic: Subquery Elimination Using Window Aggregation](papers/query-processing/winmagic-subquery-elimination-window-aggregation/translation.md) | 查询优化 | 2003 | 3.0 | translated | [原文](https://doi.org/10.1145/872757.872840) |

### 存储 (`storage`，18 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [Bridging the Archipelago between Row-Stores and Column-Stores for Hybrid Workloads](papers/storage/tile-row-store/translation.md) | 存储引擎 | 2016 | 3.5 | translated | [原文](https://doi.org/10.1145/2882903.2915231) |
| [C-Store: A Column-oriented DBMS](papers/storage/c-store-column-oriented-dbms/translation.md) | 存储引擎、分析型数据库 | 2005 | 4.5 | translated | [原文](https://www.cs.umd.edu/~abadi/papers/vldb.pdf) |
| [Ceph: A Scalable, High-Performance Distributed File System](papers/storage/ceph-a-scalable-high-performance-distributed-file-system/translation.md) | 分布式存储、文件系统 | 2006 | 5.0 | translated | [原文](https://www.usenix.org/legacy/events/osdi06/tech/full_papers/weil/weil.pdf) |
| [CFS: A Distributed File System for Large Scale Container Platforms](papers/storage/cfs-a-distributed-file-system-for-large-scale-container-platforms/translation.md) | 分布式存储、文件系统 | 2019 | 2.5 | translated | [原文](https://arxiv.org/pdf/1911.03001.pdf) |
| [Data Blocks: Hybrid OLTP and OLAP on Compressed Storage using both Vectorization and Compilation](papers/storage/data-blocks-hybrid-oltp-olap-compressed-storage-vectorization-compilation/translation.md) | 存储引擎 | 2016 | 3.5 | translated | [原文](https://db.in.tum.de/downloads/publications/datablocks.pdf) |
| [Delta Lake: High-Performance ACID Table Storage over Cloud Object Stores](papers/storage/delta-lake-high-performance-acid-table-storage-cloud-object-stores/translation.md) | 云原生、存储引擎、湖仓一体 | 2020 | 4.5 | translated | [原文](https://doi.org/10.14778/3415478.3415560) |
| [Facebook's Tectonic Filesystem: Efficiency from Exascale](papers/storage/facebook-tectonic-filesystem-efficiency-from-exascale/translation.md) | 存储引擎 | 2021 | 3.5 | translated | [原文](https://www.usenix.org/system/files/fast21-pan.pdf) |
| [Kudu: Storage for Fast Analytics on Fast Data](papers/storage/kudu-storage-for-fast-analytics-on-fast-data/translation.md) | 存储引擎、分布式存储 | 2015 | 3.5 | translated | [原文](https://kudu.apache.org/kudu.pdf) |
| [Main Memory Database Systems](papers/storage/main-memory-database-systems/source.pdf) | 存储引擎 | 2016 | 3.5 | skipped | [原文](http://justinlevandoski.org/papers/fnt-mmdb.pdf) |
| [Mainlining Databases: Supporting Fast Transactional Workloads on Universal Columnar Data File Formats](papers/storage/mainlining-databases-fast-transactional-workloads-universal-columnar-data-file-formats/translation.md) | 存储引擎 | 2021 | 2.5 | translated | [原文](https://db.cs.cmu.edu/papers/2020/p534-li.pdf) |
| [The Case for Learned Index Structures](papers/storage/case-for-learned-index-structures/translation.md) | 索引、AI 优化数据库 | 2018 | 4.0 | translated | [原文](https://research.google/pubs/the-case-for-learned-index-structures/) |
| [The Design and Implementation of Modern Column-Oriented Database Systems](papers/storage/design-implementation-modern-column-oriented-database-systems/source.pdf) | 存储引擎 | 2012 | 4.0 | skipped | [原文](https://stratos.seas.harvard.edu/files/stratos/files/columnstoresfntdbs.pdf) |
| [The Log-Structured Merge-Tree (LSM-Tree)](papers/storage/log-structured-merge-tree/translation.md) | 存储引擎、索引 | 1996 | 5.0 | translated | [原文](https://doi.org/10.1007/s002360050048) |
| [The Ubiquitous B-Tree](papers/storage/ubiquitous-b-tree/translation.md) | 存储引擎、索引 | 1979 | 4.5 | translated | [原文](https://doi.org/10.1145/356770.356776) |
| [Tutorial: Column oriented Database Systems](papers/storage/vldb-2009-tutorial-column-stores/translation.md) | 存储引擎 | 2009 | 3.0 | translated | [原文](https://www.vldb.org/pvldb/vol2/vldb09-tutorial6.pdf) |
| [Weaving Relations for Cache Performance](papers/storage/pax-cache-friendly-hybrid-storage/translation.md) | 存储引擎 | 2001 | 4.5 | translated | [原文](https://www.vldb.org/conf/2001/P169.pdf) |
| [WiscKey: Separating Keys from Values in SSD-conscious Storage](papers/storage/wisckey-ssd-conscious-storage/translation.md) | 存储引擎 | 2016 | 4.0 | translated | [原文](https://www.usenix.org/conference/fast16/technical-sessions/presentation/lu) |
| [X-Engine: An Optimized Storage Engine for Large-scale E-commerce Transaction Processing](papers/storage/x-engine-an-optimized-storage-engine-for-large-scale-e-commerce-transaction-processing/translation.md) | 存储引擎、事务处理 | 2019 | 3.5 | translated | [原文](https://www.cs.utah.edu/~lifeifei/papers/sigmod-xengine.pdf) |

### 事务与并发控制 (`transactions`，7 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [A Critique of ANSI SQL Isolation Levels](papers/transactions/critique-ansi-sql-isolation-levels/translation.md) | 事务处理、并发控制 | 1995 | 5.0 | translated | [原文](https://sigmodrecord.org/1995/06/06/a-critique-of-ansi-sql-isolation-levels/) |
| [ARIES: A Transaction Recovery Method Supporting Fine-Granularity Locking and Partial Rollbacks Using Write-Ahead Logging](papers/transactions/aries-transaction-recovery-method/source.pdf) | 事务处理 | 1992 | 5.0 | skipped | [原文](https://research.ibm.com/publications/aries-a-transaction-recovery-method-supporting-fine-granularity-locking-and-partial-rollbacks-using-write-ahead-logging) |
| [Calvin: Fast Distributed Transactions for Partitioned Database Systems](papers/transactions/calvin-fast-distributed-transactions-partitioned-database-systems/translation.md) | 事务处理、并发控制 | 2012 | 4.5 | translated | [原文](https://doi.org/10.1145/2213836.2213838) |
| [Granularity of Locks and Degrees of Consistency in a Shared Data Base](papers/transactions/granularity-locks-degrees-consistency-shared-database/translation.md) | 事务处理、并发控制 | 1976 | 5.0 | translated | [原文](https://www.seas.upenn.edu/~zives/05s/cis650/papers/granularity-locks.pdf) |
| [On Optimistic Methods for Concurrency Control](papers/transactions/optimistic-methods-concurrency-control/translation.md) | 事务处理、并发控制 | 1981 | 5.0 | translated | [原文](https://doi.org/10.1145/319566.319567) |
| [Speedy Transactions in Multicore In-Memory Databases](papers/transactions/speedy-transactions-multicore-in-memory-databases/translation.md) | 事务处理、并发控制 | 2013 | 4.5 | translated | [原文](https://people.csail.mit.edu/stephentu/papers/silo.pdf) |
| [The Notions of Consistency and Predicate Locks in a Database System](papers/transactions/notions-consistency-predicate-locks-database-system/translation.md) | 事务处理、并发控制 | 1976 | 4.5 | translated | [原文](https://research.ibm.com/publications/the-notions-of-consistency-and-predicate-locks-in-a-database-system) |

### 分布式数据库 (`distributed-databases`，6 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [Bigtable: A Distributed Storage System for Structured Data](papers/distributed-databases/bigtable-distributed-storage-system-structured-data/translation.md) | 存储引擎、分布式存储 | 2006 | 5.0 | translated | [原文](https://research.google/pubs/bigtable-a-distributed-storage-system-for-structured-data/) |
| [CockroachDB: The Resilient Geo-Distributed SQL Database](papers/distributed-databases/cockroachdb-the-resilient-geo-distributed-sql-database/translation.md) | 分布式 SQL、事务处理 | 2020 | 3.5 | translated | [原文](https://cdn2.hubspot.net/hubfs/1753393/guides/White%20Paper%20%7C%20CockroachDB%20The%20Resilient%20Geo-Distributed%20SQL%20Database%20%28SIGMOD%202020%29.pdf) |
| [Dynamo: Amazon’s Highly Available Key-value Store](papers/distributed-databases/dynamo-amazon-highly-available-key-value-store/translation.md) | 分布式存储 | 2007 | 5.0 | translated | [原文](https://doi.org/10.1145/1294261.1294281) |
| [FoundationDB: A Distributed Unbundled Transactional Key Value Store](papers/distributed-databases/foundationdb-a-distributed-unbundled-transactional-key-value-store/translation.md) | 分布式存储、事务处理 | 2021 | 4.5 | translated | [原文](https://www.foundationdb.org/files/fdb-paper.pdf) |
| [Mesa: Geo-Replicated, Near Real-Time, Scalable Data Warehousing](papers/distributed-databases/mesa-geo-replicated-near-real-time-scalable-data-warehousing/translation.md) | 分析型数据库、分布式存储 | 2014 | 3.5 | translated | [原文](https://static.googleusercontent.com/media/research.google.com/zh-CN//pubs/archive/42851.pdf) |
| [Spanner: Google’s Globally-Distributed Database](papers/distributed-databases/spanner-googles-globally-distributed-database/translation.md) | 分布式 SQL、事务处理 | 2012 | 5.0 | translated | [原文](https://static.googleusercontent.com/media/research.google.com/zh-CN//archive/spanner-osdi2012.pdf) |

### 数据集成 (`data-integration`，2 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [Instant Loading for Main Memory Databases](papers/data-integration/instant-loading-main-memory-databases/translation.md) | 数据导入 | 2013 | 3.5 | translated | [原文](https://www.vldb.org/pvldb/vol6/p1702-muehlbauer.pdf) |
| [Speculative Distributed CSV Data Parsing for Big Data Analytics](papers/data-integration/speculative-distributed-csv-data-parsing-big-data-analytics/translation.md) | 数据导入 | 2019 | 3.5 | translated | [原文](https://www.microsoft.com/en-us/research/publication/speculative-distributed-csv-data-parsing-for-big-data-analytics/) |

### 流处理 (`streaming`，6 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [Apache Flink™: Stream and Batch Processing in a Single Engine](papers/streaming/apache-flink-stream-and-batch-processing-in-a-single-engine/translation.md) | 流处理 | 2015 | 4.5 | translated | [原文](http://sites.computer.org/debull/A15dec/p28.pdf) |
| [Aurora: A New Model and Architecture for Data Stream Management](papers/streaming/aurora-new-model-architecture-data-stream-management/translation.md) | 流处理 | 2003 | 4.5 | translated | [原文](https://cs.brown.edu/research/aurora/publications.html) |
| [DBToaster: Higher-order Delta Processing for Dynamic, Frequently Fresh Views](papers/streaming/dbtoaster-higher-order-delta-processing/translation.md) | 流处理 | 2012 | 4.0 | translated | [原文](https://doi.org/10.14778/2336664.2336670) |
| [SnappyData: A Unified Cluster for Streaming, Transactions, and Interactive Analytics](papers/streaming/snappydata-unified-cluster-for-streaming-transactions-and-interactive-analytics/translation.md) | 流处理、事务处理 | 2017 | 3.5 | translated | [原文](https://web.eecs.umich.edu/~mozafari/php/data/uploads/cidr_2017.pdf) |
| [The CQL Continuous Query Language: Semantic Foundations and Query Execution](papers/streaming/cql-continuous-query-language/translation.md) | 流处理 | 2006 | 4.5 | translated | [原文](https://cs.stanford.edu/people/widom/pubs.html) |
| [The Dataflow Model: A Practical Approach to Balancing Correctness, Latency, and Cost in Massive-Scale, Unbounded, Out-of-Order Data Processing](papers/streaming/dataflow-model-balancing-correctness-latency-cost/translation.md) | 流处理 | 2015 | 5.0 | translated | [原文](https://www.vldb.org/pvldb/vol8/p1792-Akidau.pdf) |

### 可靠性与测试 (`reliability-and-testing`，4 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [Automated SQL Query Generation for Systematic Testing of Database Engines](papers/reliability-and-testing/automated-sql-query-generation-systematic-testing-database-engines/translation.md) | 数据库测试 | 2010 | 3.0 | translated | [原文](https://doi.org/10.1145/1858996.1859063) |
| [Detecting Optimization Bugs in Database Engines via Non-Optimizing Reference Engine Construction](papers/reliability-and-testing/detecting-optimization-bugs-non-optimizing-reference-engine/translation.md) | 数据库测试 | 2020 | 4.5 | translated | [原文](https://arxiv.org/abs/2007.08292) |
| [QAGen: Generating Query-Aware Test Databases](papers/reliability-and-testing/qagen-generating-query-aware-test-databases/translation.md) | 数据库测试 | 2007 | 3.0 | translated | [原文](https://cs.uwaterloo.ca/~tozsu/publications/other/sigmod07-final.pdf) |
| [Quantifying TPC-H Choke Points and Their Optimizations](papers/reliability-and-testing/quantifying-tpch-choke-points/translation.md) | 数据库测试 | 2020 | 3.5 | translated | [原文](http://www.vldb.org/pvldb/vol13/p1206-dreseler.pdf) |

### 专用数据库 (`specialized-databases`，8 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [AnalyticDB-V: A Hybrid Analytical Engine Towards Query Fusion for Structured and Unstructured Data](papers/specialized-databases/analyticdb-v-hybrid-analytical-engine-query-fusion/translation.md) | 查询优化、分析型数据库、面向 AI 的数据系统、向量检索 | 2020 | 3.5 | translated | [原文](https://doi.org/10.14778/3415478.3415541) |
| [DiskANN: Fast Accurate Billion-point Nearest Neighbor Search on a Single Node](papers/specialized-databases/diskann-fast-accurate-billion-point-nearest-neighbor-search/translation.md) | 索引、面向 AI 的数据系统、向量检索 | 2019 | 4.5 | translated | [原文](https://papers.nips.cc/paper_files/paper/2019/hash/09853c7fb1d3f8ee67a61b6bf4a7f8e6-Abstract.html) |
| [Druid: A Real-time Analytical Data Store](papers/specialized-databases/druid-a-real-time-analytical-data-store/translation.md) | 分析型数据库 | 2014 | 4.5 | translated | [原文](http://static.druid.io/docs/druid.pdf) |
| [Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs](papers/specialized-databases/hnsw-efficient-and-robust-approximate-nearest-neighbor-search/translation.md) | 索引、面向 AI 的数据系统、向量检索 | 2020 | 5.0 | translated | [原文](https://doi.org/10.1109/TPAMI.2018.2889473) |
| [Milvus: A Purpose-Built Vector Data Management System](papers/specialized-databases/milvus-purpose-built-vector-data-management-system/translation.md) | 数据库系统设计、面向 AI 的数据系统、向量检索 | 2021 | 4.0 | translated | [原文](https://doi.org/10.1145/3448016.3457550) |
| [Pinot: Realtime OLAP for 530 Million Users](papers/specialized-databases/pinot-realtime-olap-for-530-million-users/translation.md) | 分析型数据库 | 2018 | 4.5 | translated | [原文](https://cwiki.apache.org/confluence/download/attachments/103092375/Pinot.pdf?version=1&modificationDate=1571428741000&api=v2) |
| [SPANN: Highly-efficient Billion-scale Approximate Nearest Neighbor Search](papers/specialized-databases/spann-highly-efficient-billion-scale-approximate-nearest-neighbor-search/translation.md) | 索引、面向 AI 的数据系统、向量检索 | 2021 | 4.0 | translated | [原文](https://proceedings.neurips.cc/paper/2021/hash/299dc35e747eb77177d9cea10a802da2-Abstract.html) |
| [VBASE: Unifying Online Vector Similarity Search and Relational Queries via Relaxed Monotonicity](papers/specialized-databases/vbase-unifying-vector-search-relational-queries/translation.md) | 查询优化、面向 AI 的数据系统、向量检索 | 2023 | 3.5 | translated | [原文](https://www.usenix.org/conference/osdi23/presentation/zhang-qianxi) |

### AI 与数据系统 (`ai-and-data`，6 篇)

| 论文 | 主题 | 年份 | 评分 | 阅读状态 | 权威原文入口 |
| --- | --- | ---: | ---: | --- | --- |
| [Can Foundation Models Wrangle Your Data?](papers/ai-and-data/can-foundation-models-wrangle-your-data/translation.md) | AI 优化数据库、语言模型与数据 | 2022 | 3.5 | translated | [原文](https://www.vldb.org/pvldb/vol16/p738-narayan.pdf) |
| [Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs](papers/ai-and-data/bird-can-llm-already-serve-as-a-database-interface/translation.md) | 面向 AI 的数据系统、语言模型与数据 | 2023 | 4.0 | translated | [原文](https://proceedings.neurips.cc/paper_files/paper/2023/hash/83fc8fab1710363050bbd1d4b8cc0021-Abstract-Datasets_and_Benchmarks.html) |
| [DBAIOps: A Reasoning LLM-Enhanced Database Operation and Maintenance System using Knowledge Graphs](papers/ai-and-data/dbaiops-reasoning-llm-database-operation-maintenance-knowledge-graphs/translation.md) | AI 优化数据库、语言模型与数据 | 2026 | 3.0 | translated | [原文](https://www.vldb.org/pvldb/vol19/p1319-zhou.pdf) |
| [Language Models Enable Simple Systems for Generating Structured Views of Heterogeneous Data Lakes](papers/ai-and-data/language-models-enable-structured-views-heterogeneous-data-lakes/translation.md) | 面向 AI 的数据系统、语言模型与数据 | 2023 | 3.5 | translated | [原文](https://doi.org/10.14778/3626292.3626294) |
| [Palimpzest: Optimizing AI-Powered Analytics with Declarative Query Processing](papers/ai-and-data/palimpzest-optimizing-ai-powered-analytics-declarative-query-processing/translation.md) | 查询优化、面向 AI 的数据系统、语言模型与数据 | 2025 | 2.5 | translated | [原文](https://www.vldb.org/cidrdb/2025/palimpzest-optimizing-ai-powered-analytics-with-declarative-query-processing.html) |
| [Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation](papers/ai-and-data/text-to-sql-empowered-by-large-language-models-benchmark-evaluation/translation.md) | 面向 AI 的数据系统、语言模型与数据 | 2024 | 4.0 | translated | [原文](https://doi.org/10.14778/3641204.3641221) |

## 元数据完整性

| 字段 | 已确认 | 待补证据 |
| --- | ---: | ---: |
| 作者 | 134 | 0 |
| 发表年份 | 134 | 0 |
