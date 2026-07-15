---
paper_id: milvus-purpose-built-vector-data-management-system
title: 'Milvus: A Purpose-Built Vector Data Management System'
language: zh-CN
source: source.pdf
---

# Milvus: A Purpose-Built Vector Data Management System（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

Jianguo Wang, Xiaomeng Yi, Rentong Guo, Hai Jin, Peng Xu, Shengjun Li, Xiangyu Wang, Xiangzhou Guo, Chengming Li, Xiaohai Xu, Kun Yu, Yuxing Yuan, Yinghao Zou, Jiquan Long, Yudong Cai, Zhenxiang Li, Zhifeng Zhang, Yihua Mo, Jun Gu, Ruiyi Jiang, Yi Wei, Charles Xie

Jianguo Wang：Zilliz、普渡大学，`csjgwang@{zilliz.com; purdue.edu}`；其余本文作者：Zilliz，`{firstname.lastname}@zilliz.com`

## 摘要

近来，数据科学和 AI 应用迫切需要管理高维向量数据。这一趋势由非结构化数据的激增和机器学习（ML）的发展共同推动；机器学习模型通常会把非结构化数据转换为供数据分析使用的特征向量，例如用于商品推荐。现有向量数据管理系统和算法有两个局限：（1）处理大规模动态向量数据时存在严重性能问题；（2）功能有限，无法满足多样化应用的需求。

本文提出 Milvus，一个面向大规模向量数据高效管理的专用数据管理系统。Milvus 提供易用的应用接口（包括 SDK 和 RESTful API），针对现代 CPU 与 GPU 组成的异构计算平台进行优化，支持超越简单向量相似性搜索的高级查询处理，在保证高效查询的同时处理动态数据以实现快速更新，并把数据分布到多个节点以获得可扩展性和可用性。我们首先介绍 Milvus 的设计与实现，随后展示 Milvus 支撑的真实应用。具体而言，我们在 Milvus 上构建了图像/视频搜索、化学结构分析、COVID-19 数据集搜索、个性化推荐、生物多因子认证和智能问答等十个应用。最后，我们以两个开源系统 Vearch、Microsoft SPTAG 和三个商业系统为对手，系统评估 Milvus。实验表明，在提供更多功能的同时，Milvus 最多比对手快两个数量级。Milvus 已部署于全球数百家组织，并成为 LF AI & Data Foundation 的孵化阶段项目。项目开源地址为 <https://github.com/milvus-io/milvus>。

**关键词：** 向量数据库；高维相似性搜索；异构计算；数据科学；机器学习。

## 1. 引言

近几年，数据科学和 AI 应用取得了显著成功。这个趋势的关键推动力之一，是机器学习能够把非结构化数据转换成高维特征向量。例如，机器学习模型（如 VGG [58]）可把图片变成向量。这些向量携带原始对象的深层语义，可服务于推荐、问答和图像检索等数据科学任务 [10, 69]。从系统角度看，为数据科学和 AI 应用提供高效向量数据管理能力的重要性不断上升。

尽管向量数据极其重要，现有系统通常不能很好地管理它。为了执行向量相似性搜索，传统方案通常把向量视为不透明二进制对象存进关系数据库，然后在应用层处理。这样会产生昂贵的数据传输和序列化开销。近期工业界也出现了支持向量的系统 [39, 65, 68]，但它们主要从关系系统扩展而来，向量并不是一等数据类型，查询处理也没有针对现代异构硬件充分优化。表 1 总结了相关系统和库的差异。

**表 1：系统比较。**

| 系统/库 | 十亿规模 | 动态数据 | GPU | 属性过滤 | 多向量查询 | 分布式 |
| --- | --- | --- | --- | --- | --- | --- |
| Facebook Faiss [3, 35] | 是 | 否 | 是 | 否 | 否 | 否 |
| Microsoft SPTAG [14] | 是 | 否 | 否 | 否 | 否 | 否 |
| ElasticSearch [2] | 否 | 是 | 否 | 是 | 否 | 是 |
| Jingdong Vearch [4, 39] | 否 | 是 | 是 | 是 | 否 | 是 |
| Alibaba AnalyticDB-V [65] | 是 | 是 | 否 | 是 | 否 | 是 |
| Alibaba PASE（PostgreSQL）[68] | 否 | 是 | 否 | 是 | 否 | 否 |
| Milvus | 是 | 是 | 是 | 是 | 是 | 是 |

我们从头设计并实现了面向向量数据的通用数据管理系统 Milvus。Milvus 是 LF AI & Data Foundation 的孵化项目[^1]，采用 Apache 2.0 许可证。系统始终把性能、功能和易用性放在首位；既提供 SDK 与 RESTful API，也兼容 Faiss [3, 35]、HNSW [49] 等索引。Milvus 也是完整的数据管理系统：它支持向量与非向量数据、动态插入删除、快照隔离、持久存储和分布式部署。

Zilliz 客户管理的高维向量通常有数十到数千维。需求增长来自两个趋势：一是智能手机、IoT 与社交应用使图像、视频、文本、医疗和住房等非结构化数据爆炸增长，IDC 预测到 2025 年其占比将达 80% [36]；二是机器学习能把这些数据转换成特征向量。典型 embedding 包括 item2vec [11]、word2vec [52]、doc2vec [37] 和 graph2vec [26]。YouTube 用向量表示视频 [15]，Airbnb 用向量表示房屋 [25]，生物科学家用向量描述药物分子结构 [13, 51]，图像和文本也可自然向量化 [8, 53]。

这类应用一面要求大规模查询，一面要求高效处理插入和删除。例如 YouTube 每分钟上传 500 小时用户视频，同时还要实时推荐 [67]。它们也需要超越普通相似性搜索的高级查询：属性过滤只搜索满足给定条件的向量，如寻找外观相似且价格低于 100 美元的 T 恤；多向量查询则处理由多个向量共同描述的对象，如用面部和姿态向量刻画人物 [10, 56]。

现有算法和开源库主要有四个不足：它们不是管理数据的完整系统，通常假定数据和索引全部在单机内存；数据摄取后趋于静态，难以在动态更新下保持快速实时搜索；缺少高级查询；也没有面向 CPU/GPU 异构体系整体优化。扩展关系数据库的系统又受遗留优化器和存储引擎限制，难以把向量当作一等公民，也错失 CPU/GPU 协同机会。Vearch 虽为向量搜索而设计，但在大规模数据上效率不足且不支持多向量查询。

Milvus 针对 CPU 与 GPU 组成的异构平台进行优化。CPU 侧提出 cache-aware 和 SIMD-aware（SSE、AVX、AVX2、AVX512）优化；GPU 侧支持更大的 top-k 与运行时选择多 GPU；还提出 SQ8H，在数据无法完全放入 GPU 时协同 CPU/GPU。高级查询方面，Milvus 支持属性过滤，并提出比此前代价模型最多快 13.7 倍的分区策略；同时支持一个实体包含多个向量，并提出向量融合与迭代合并两种算法。

我们的贡献如下：

1. 提出并实现开源通用向量数据管理系统 Milvus，提供查询引擎、GPU 引擎和存储引擎，并支持动态数据、快照隔离和分布式部署。
2. 系统研究异构计算上的向量查询，提出 cache-aware、SIMD-aware、GPU 与 CPU 协同优化。
3. 支持属性过滤与多向量查询，提出新的分区、向量融合与迭代合并算法。
4. 通过系统实验表明 Milvus 比现有系统快最高两个数量级，并可近线性扩展到十亿规模。
5. Milvus 已被数百家公司使用，并支撑图像/视频搜索、化学结构分析、COVID-19 数据检索、个性化推荐、多因子生物认证、智能问答、图文检索、跨模态行人检索和菜谱检索等十个应用[^2]。

[^1]: <https://lfaidata.foundation/projects/milvus>
[^2]: <https://github.com/milvus-io/bootcamp/tree/master/EN_solutions>

## 2. 系统设计

本节概述 Milvus。图 1 展示三个主要组件：查询引擎、GPU 引擎与存储引擎。查询引擎执行向量相似性搜索、属性过滤和多向量查询，并通过减少 cache miss 和利用 SIMD 针对现代 CPU 优化；GPU 引擎利用大规模并行性加速并支持多 GPU；存储引擎以 LSM 结构支持动态数据和持久性，可运行在本地文件系统、Amazon S3 与 HDFS 上，并以内存 buffer pool 缓存。

![图 1：Milvus 系统架构](assets/milvus-fig01-system-architecture.png)

*图 1：Milvus 系统架构。*

### 2.1 查询处理

**实体。** 为覆盖多样的数据科学与 AI 应用，Milvus 同时处理向量和非向量数据。一个实体由一个或多个向量以及可选的数值属性描述。例如图像搜索中，除表示正脸、侧脸或姿态的多个学习特征向量外，属性还可表示人物年龄和身高 [10]。当前版本只支持在实际应用中常见的数值属性；未来计划使用倒排表或位图等索引支持类别属性 [64]。

**查询类型。** Milvus 支持三类原语查询：

- **向量查询：** 传统向量相似性搜索 [33, 41, 48, 49]。每个实体由一个向量描述，系统返回用户参数 `k` 指定的最相似 `k` 个向量。
- **属性过滤：** 每个实体包含一个向量和若干属性 [65]，系统返回满足属性约束的 `k` 个最相似向量。例如推荐系统中查找与查询图片相似且价格低于 100 美元的衣服。
- **多向量查询：** 每个实体存储多个向量 [10]，查询按多个向量之间的聚合函数（如加权和）返回 top-k 相似实体。

**相似性函数。** Milvus 提供欧氏距离、内积、余弦相似度、汉明距离和 Jaccard 距离等常用度量。

**应用接口。** Milvus 为 Python、Java、Go、C++ 等语言提供 SDK，也为 Web 应用提供 RESTful API。

### 2.2 索引

索引对 Milvus 的查询处理至关重要。困难在于向量相似性索引非常多，而最新基准 [41] 表明不存在适合所有场景的赢家；每种索引都在性能、准确率和空间开销之间取舍。

Milvus 主要支持两类索引[^3]：量化索引，包括 IVF_FLAT [3, 33, 35]、IVF_SQ8 [3, 35] 和 IVF_PQ [3, 22, 33, 35]；图索引，包括 HNSW [49] 与 RNSG [20]。选择依据包括最新综述 [41]、工业系统（Alibaba PASE [68]、AnalyticDB-V [65]、Vearch [39]）、开源库 Faiss [3, 35] 和客户反馈。系统没有采用 LSH，因为其在十亿规模上的准确率低于量化方法 [65, 68]。

考虑到新索引不断出现，Milvus 提供高层抽象，开发者只需实现少数预定义接口即可添加新索引，目标是成为容纳多种索引的标准向量数据管理平台。

[^3]: Milvus 也支持树索引，例如 ANNOY [1]。

### 2.3 动态数据管理

Milvus 借鉴 LSM-tree [47] 高效支持插入和删除。新实体先进入内存 MemTable；累计大小达到阈值或每隔一秒，MemTable 变为不可变并刷盘成新 segment。较小 segment 按 Apache Lucene 也采用的 tiered merge policy 合并：大小近似的 segment 逐级合并，直到可配置上限（如 1 GB）。删除采用同样的 out-of-place 方法，过期向量在 segment merge 时移除；更新由删除加插入实现。

默认只为大 segment（如大于 1 GB）构建索引，用户也可手动为任意大小 segment 建索引。索引与数据存放在同一 segment，因此 segment 是搜索、调度和缓冲的基本单位。Milvus 提供快照隔离，确保读写看到一致视图且互不干扰，详见 5.2 节。

### 2.4 存储管理

每个实体可视作 entity table 的一行。Milvus 物理上按列存储该表。

**向量存储。** 对单向量实体，系统连续存储所有向量而不显式存 row ID；向量天然按 row ID 排序，因为长度相同，可由 row ID 直接定位。对多向量实体，不同实体的同一向量列放在一起。若实体 A、B、C 各有 `v1`、`v2`，物理布局为 `{A.v1, B.v1, C.v1, A.v2, B.v2, C.v2}`。

**属性存储。** 每个属性列存为按 key 排序的 `<key,value>` 数组，key 是属性值，value 是 row ID。磁盘数据页还按 Snowflake [16] 构建 min/max skip pointer，可高效执行点查和范围查询。

**Buffer pool。** 为高性能，Milvus 假定大部分数据和索引常驻内存；否则使用 LRU buffer manager，缓存单位是 segment。

**多种存储。** 底层支持本地文件系统、Amazon S3 和 HDFS，便于可靠、灵活地部署到云上。

### 2.5 异构计算

Milvus 针对 CPU 与 GPU 的异构平台高度优化，细节见第 3 节。

### 2.6 分布式系统

Milvus 可跨多个节点部署，并采用存算分离、共享存储、读写分离和 single-writer/multi-reader 等现代分布式与云系统实践，细节见 5.3 节。

## 3. 异构计算

本节说明 Milvus 如何充分利用 CPU 与 GPU。Milvus 主要支持量化索引与图索引；以下以量化索引说明，因为它们比图索引内存占用更小、建索引更快，同时保持良好查询性能 [65, 68]。SIMD 和 GPU 等许多优化同样适用于图索引。

### 3.1 背景

向量量化使用量化器 `z` 把向量 `v` 映射到码本 `C` 中的码字 `z(v)` [33]。通常用 K-means 构造码本：码字是质心，`z(v)` 是离 `v` 最近的质心。图 2 中，10 个向量分属三个簇，质心为 c0、c1、c2；v0 至 v3 都映射到 c0。

![图 2：量化示例](assets/milvus-fig02-quantization.png)

*图 2：量化示例。*

IVF_FLAT、IVF_SQ8 和 IVF_PQ 使用粗、细两个量化器。粗量化器用 K-means 把向量分成 K 个桶（Milvus 和 Faiss 中 K 可为 16384）；细量化器编码桶内向量。IVF_FLAT 保留原始向量；IVF_SQ8 用一维标量量化器把 4-byte float 压成 1-byte integer；IVF_PQ 用乘积量化，把向量切成多个子向量并分别 K-means。

处理查询 q 分两步：（1）按 q 与各桶质心的距离找最近的 `nprobe` 个桶；`nprobe` 越大，准确率越高而性能越差。（2）按细量化器搜索这些桶。例如图 2 中 `nprobe=2`，最近的是 c0、c1；若为 IVF_FLAT，则扫描 v0 至 v6。

### 3.2 面向 CPU 的优化

#### 3.2.1 Milvus 中的 cache-aware 优化

给定 m 个查询 `{q1,...,qm}` 和 n 个数据向量 `{v1,...,vn}`，任务是快速为每个查询找 top-k。Faiss 的 OpenMP 实现让每个线程一次处理一个查询：将该查询与全部 n 个向量比较，并维护大小为 k 的堆。这有两个问题：（1）每个查询都要让全部数据流过 CPU cache，下一查询无法复用，每线程访问整个数据 `m/t` 次；（2）batch 较小时不能充分利用多核并行。

Milvus 一方面让多个查询复用已经装入的数据，重点减少代价高昂且容量相对更大的 L3 cache miss；另一方面按数据向量而非查询向量分配线程，获得细粒度并行，因为实际中 `n` 通常远大于 `m`。

![图 3：Milvus 的 cache-aware 设计](assets/milvus-fig03-cache-aware.png)

*图 3：Milvus 的 cache-aware 设计。*

如图 3，t 个线程中，每个线程 Ti 分到 `b=n/t` 个数据向量[^4]。m 个查询分成大小为 s 的块，使查询块连同对应堆始终能放入 L3 cache。一个查询块由多线程共同计算；线程把自身数据装入 L3 后，与缓存中的全部 s 个查询比较。为减少同步，每个线程为每个查询维护独立堆；最终合并 t 个堆得到 top-k。

若维度为 d，每个查询占 `d × sizeof(float)`；每个堆项包含向量 ID 与相似度，每个查询的堆总大小为 `t × k × (sizeof(int64) + sizeof(float))`。因此：

$$
s=\frac{\text{L3 cache size}}{d\times\mathrm{sizeof}(float)+t\times k\times(\mathrm{sizeof}(int64)+\mathrm{sizeof}(float))}. \tag{1}
$$

这样每线程只需访问全部数据 `m/(s×t)` 次，比 Faiss 少 s 倍。7.4 节实验显示性能提高 1.5×–2.7×。

[^4]: 假设 n 可被 t 整除。

#### 3.2.2 Milvus 中的 SIMD-aware 优化

Faiss 已用 SIMD 加速向量相似性计算，Milvus 又做两项工程优化。

**支持 AVX512。** 原 Faiss 不支持主流 CPU 已提供的 AVX512。Milvus 用 `_mm512_add_ps`、`_mm512_mul_ps`、`_mm512_extractf32x8_ps` 等指令扩展相似性函数，支持 SSE、AVX、AVX2 和 AVX512。

**自动选择 SIMD 指令。** 单一 Milvus 二进制需要在不同 CPU 上自动选择合适指令，而 Faiss 要求编译时手动指定如 `-msse4` 的标志。Milvus 重构公共 SIMD 相关函数，为每个函数实现 SSE、AVX、AVX2、AVX512 四个版本，放入不同源文件并分别用对应标志编译；运行时检查 CPU flags，通过 hooking 链接正确函数指针。

### 3.3 面向 GPU 的优化

Milvus 在 Faiss GPU 支持上增强两点。

**GPU kernel 支持更大的 k。** Faiss 因 shared memory 限制只支持 `k≤1024`，而视频监控和推荐系统常需更大 k 做验证或重排 [69, 71]。Milvus 支持到 16384[^5]。当 k 大于 1024 时分多轮执行：首轮取前 1024；后续记录上一轮最后结果的距离 `dl`，并记录距离等于 `dl` 的 ID，过滤距离小于 `dl` 或 ID 已出现的向量，再取接下来的 1024，合并结果，直到足量。

**支持多 GPU。** Faiss 要在编译时声明所有 GPU，导致二进制只能运行在 GPU 数不少于编译机的服务器。Milvus 允许运行时选择任意数量 GPU，并用 segment-based scheduling 把搜索任务分给可用 GPU；一个 segment 仅由一个 GPU 服务。新 GPU 加入后可立即发现并接受下一任务，适合云上弹性资源管理。

[^5]: 技术上可支持任意 k；Milvus 特意限制为 16384，以免网络传输过大，而且已足以覆盖现有应用。

### 3.4 GPU 与 CPU 协同设计

当数据无法完全放入 GPU 时，Faiss 使用低占用的 IVF_SQ8[^6]，并按需经 PCIe 从 CPU 内存搬到 GPU。但有两个局限：（1）实测 I/O 仅 1–2 GB/s，而 PCIe 3.0 ×16 可达 15.75 GB/s；（2）考虑传输成本，GPU 并非始终优于 CPU。Milvus 为此提出 SQ8H（H 表示 hybrid）。

**算法 1：SQ8H。**

```text
1  令 nq 为 batch size；
2  if nq >= threshold then
3      全部查询完全在 GPU 上运行（按需把多个桶装入 GPU memory）；
4  else
5      在 GPU 执行 SQ8 第一步：寻找 nprobe 个桶；
6      在 CPU 执行 SQ8 第二步：扫描每个相关桶；
```

Faiss 逐桶从 CPU 向 GPU 复制，桶小时不能充分利用 PCIe。Milvus 一次尽可能复制多个桶。Faiss 的原地删除方式不利于多桶复制，而 Milvus 的 LSM out-of-place 删除自然解决该问题。

GPU 只有在 batch 足够大时才能抵消数据移动成本，因为更多查询复用同一数据、计算更密集。因此 batch 大于阈值（如 1000）时，全部在 GPU 执行，并在 GPU 内存不足时装入必要桶；否则采用混合执行：在 GPU 上找 `nprobe` 个最近桶，在 CPU 上扫描桶。第一步所有查询共享 K 个质心，计算/I/O 比高且质心可常驻 GPU；第二步访问更分散，不同查询未必访问同一桶。

[^6]: IVF_SQ8 仅占 IVF_FLAT 的 1/4 空间，而召回率只损失约 1%。本节原则也适用于 IVF_FLAT、IVF_PQ 等其他量化索引。

## 4. 高级查询处理

### 4.1 属性过滤

属性过滤同时涉及向量与非向量数据 [65]，只搜索满足属性约束的向量。例如查找尺寸在给定范围内的相似房屋。为简化叙述，假设实体只有一个向量和一个属性，多属性可直接扩展。查询含属性条件 `CA` 和返回 top-k 的向量条件 `CV`；不失一般性，`CA` 写成 `a >= p1 && a <= p2`。

![图 4：属性过滤的不同策略](assets/milvus-fig04-attribute-strategies.png)

*图 4：属性过滤的不同策略。*

Milvus 实现了 AnalyticDB-V [65] 研究的 A–D 策略，并提出实验中比最新策略 D 最多快 13.7× 的策略 E。

**策略 A：attribute-first-vector-full-scan。** 先按 CA 用二分查找（落盘时用 skip pointer；也可用 B-tree）得到实体，再全扫描这些候选并与查询向量比较。CA 高选择性时适用，且产生精确结果。

**策略 B：attribute-first-vector-search。** 先按 CA 得到实体 ID bitmap，再正常执行 CV 的向量查询；遇到向量时检查 bitmap，只有通过者进入 top-k。CA 或 CV 中等选择性时适用。

**策略 C：vector-first-attribute-full-scan。** 先按 CV 用 IVF_FLAT 等取实体，再全扫描验证 CA。为保证最终有 k 个结果，向量阶段取 `θ·k (θ>1)` 个；CV 高选择性时适用。

**策略 D：cost-based。** 估计 A、B、C 成本并选择最低者，即 AnalyticDB-V [65] 的方案。已有工作和我们的实验表明它几乎适合所有情况。

**策略 E：partition-based。** Milvus 按频繁检索的属性把数据分区，每个分区内部使用策略 D。系统用 hash table 统计查询引用属性的频率。给定查询，只搜属性范围与查询范围重叠的分区；若某分区范围完全被查询范围覆盖，则无需再检查 CA，只做 CV。

例如按 price 分为 P0 `[1,100]`、P1 `[101,200]`、P2 `[201,300]`、P3 `[301,400]`、P4 `[401,500]`，查询范围 `[50,250]` 只需搜 P0、P1、P2；搜 P1 时无需检查属性。当前 Milvus 根据历史数据离线分区，在线服务查询。分区数 ρ 由用户配置：太少则难剪枝，太多则每区向量太少、索引退化为线性搜索。经验上每区约一百万向量；十亿数据约 1000 区。用机器学习和统计动态分区并选择 ρ 是未来工作。

### 4.2 多向量查询

许多应用用多个向量描述实体以提高准确率：视频监控以正脸、侧脸和姿态描述人 [10]；菜谱搜索以文本和图片描述菜谱 [56]；同一对象还可能使用多个模型 [30, 69]。

形式化地，每个实体含 μ 个向量 `v0,...,vμ-1`。多向量查询按聚合函数 g 组合各向量的相似度函数 f，寻找 top-k：实体 X 与 Y 的相似度是 `g(f(X.v0,Y.v0),...,f(X.vμ-1,Y.vμ-1))`。假设 g 对每个 f 单调不减 [19]；加权和、均值/中位数、min/max 都满足。

**朴素方案。** 令数据集为 D，`Di={e.vi | e∈D}`。对查询 q 的每个 `q.vi` 在 Di 上分别做 top-k，再聚合候选。该方案曾广泛用于 AI/ML 推荐 [29, 70]，但会漏掉许多真实结果，召回率可低至 0.1。

Milvus 提出面向不同场景的向量融合和迭代合并。

**向量融合。** 以相似度为内积为例，把实体 e 的 μ 个向量连接为 `v=[e.v0,e.v1,...,e.vμ-1]`。查询时把聚合函数应用于 q 的向量；若 g 是权重 wi 的加权和，则查询向量为 `[w0×q.v0,w1×q.v1,...,wμ-1×q.vμ-1]`，再在连接向量上搜索。内积可分解，故正确性直接成立。该方法只调用一次向量查询，简单高效，但要求可分解相似度。数据归一化后，余弦相似度和欧氏距离等也可等价转换为内积。

**迭代合并。** 若数据未归一化且相似度不可分解（如欧氏距离），则使用建立在 Fagin NRA [19] 上的迭代合并[^7]。直接 NRA 把每个 `q.vi` 在 Di 上的结果当流并频繁调用 `getNext()`；但量化和图索引不能高效支持 `getNext()`，每取下一项都要完整搜索，且 NRA 每次访问都更新 heap 中对象分数，维护开销高。

迭代合并做两项优化：（1）不依赖 `getNext()`，而以自适应 k' 调用 `VectorQuery(q.vi,Di,k')`，避免每次访问都重做查询，也消除昂贵 heap 维护；（2）由于 Milvus 返回近似结果，引入最大访问步数上界。

**算法 2：迭代合并。**

```text
1  k' <- k
2  while k' < threshold do
       // 对每个 q.vi 在 Di 上执行 top-k' 处理
3      foreach i do
4          Ri <- VectorQuery(q.vi, Di, k')
5      if 对所有 Ri 运行 NRA [19] 后可完全确定 k 个结果 then
6          return top-k 结果
7      else
8          k' <- k' * 2
9  return union_i Ri 中的 top-k 结果
```

算法反复为每个 q.vi 取 top-k' 并放入 Ri，再对所有 Ri 运行 NRA。若至少 k 个结果已可安全确定就终止，否则 k' 加倍，直到阈值。它不假设数据和相似度函数，适用面更广；但相似度可分解时，性能不如向量融合。数据库领域还有其他 top-k 算法 [5, 12, 31, 42, 62]，但同样受底层索引不能高效 `getNext()` 的限制。算法 2 是通用框架，可替换第 5 行的 top-k 算法；其最优性和进一步优化仍是开放问题。

[^7]: TA 算法 [19] 需要此处不可用的随机访问，因此不能应用。

## 5. 系统实现

本节介绍异步处理、快照隔离和分布式计算的实现。

### 5.1 异步处理

Milvus 通过异步处理尽量减少前台工作、提高吞吐。收到大量写请求时，先把操作像数据库日志一样物化到磁盘，然后向用户确认；后台线程再消费这些操作。因此用户可能不能立即看到插入数据，Milvus 提供 `flush()` API：阻塞新请求，直到所有待处理操作完成。索引也异步构建。

### 5.2 快照隔离

为让动态数据上的读写看到一致视图，Milvus 提供快照隔离。查询只在其开始时的快照上运行，后续更新创建新快照，不干扰进行中的查询。

动态数据按 LSM 风格管理：新数据先插入内存，再刷成不可变 segment。每个 segment 有多个版本，数据或索引发生 flush、merge、build index 等变化就生成新版本。任一时刻的最新 segments 组成快照，一个 segment 可被多个快照引用。假设系统启动时无 segment；t1 时插入刷盘形成 segment 1；t2 时生成 segment 2。此时 snapshot 1 指向 segment 1，snapshot 2 指向 segment 1 与 2。t2 前的查询使用 snapshot 1，之后的使用 snapshot 2。后台线程回收不再被任何快照引用的过期 segment。

快照隔离作用于 LSM 内部数据重组，因此所有内部读都不会被写阻塞。

### 5.3 分布式系统

为获得可扩展性和可用性，Milvus 使用存算分离的 shared-storage 架构。类似 Snowflake [16] 和 Aurora [63]，存储层使用高可用 Amazon S3；计算层处理插入与查询，并用本地内存和 SSD 缓存，减少 S3 访问；协调层维护分片、负载均衡等元数据，由 Zookeeper 管理三个实例以实现高可用。

![图 5：Milvus 分布式系统](assets/milvus-fig05-distributed-system.png)

*图 5：Milvus 分布式系统。*

无状态计算层包含一个 writer 和多个 reader，因为 Milvus 读多写少，单 writer 已满足当时客户需求。Writer 处理插入、删除、更新；reader 处理查询。数据用 consistent hashing 分到 reader，分片信息在协调层中。一次请求内没有混合读写，因此不存在跨分片事务。图 10 的实验显示该设计近线性扩展。

所有计算实例由 Kubernetes（K8s）管理。实例崩溃时 K8s 自动重启替代者；writer 崩溃时依赖 WAL 保证原子性。实例无状态，崩溃不影响一致性；过载时 K8s 还能弹性增加 reader。

为降低计算与存储间网络开销，Milvus 做两项优化：（1）计算层像 Aurora [63] 一样只把日志而非实际数据发送到存储层，再由后台线程异步处理。当前后台线程运行在负载不高的 writer 上，必要时可使用专用实例。（2）每个计算实例配备大量 buffer memory 与 SSD，减少 shared storage 访问。

## 6. 应用

Milvus 支撑十个应用：图像搜索、视频搜索、化学结构分析、COVID-19 数据集搜索、个性化推荐、生物多因子认证、智能问答、图文检索、跨模态行人搜索和菜谱—食物搜索。受篇幅限制，本节介绍两个，更多见项目 bootcamp[^2]。

### 6.1 图像搜索

图像搜索是典型向量搜索：VGG [58]、ResNet [28] 等深度模型自然地把图片转换成向量。

企查查[^8]和贝壳找房[^9]使用 Milvus 做大规模图像搜索。企查查存储并检索超过一亿家公司的工商信息；Milvus 帮助客户检索相似商标，判断商标是否已注册。贝壳找房是中国最大的在线房地产交易平台之一；Milvus 用于查找相似房屋和户型。图 6 展示商标与房屋搜索示例。

![图 6：Milvus 图像搜索](assets/milvus-fig06-image-search.png)

*图 6：Milvus 图像搜索。*

[^8]: <https://www.qcc.com/>
[^9]: <https://www.ke.com/>

### 6.2 化学结构分析

化学结构分析是依赖向量搜索的新兴应用。研究表明，可把化学物质结构编码成高维向量，再以向量相似性搜索（如 Tanimoto 距离 [9]）查找相似结构 [9, 66]。

大型制药企业药明康德[^10]已采用 Milvus 开发新药和医疗器械，把化学结构分析从数小时缩短到一分钟以内。图 7 给出相似结构搜索示例。

![图 7：Milvus 化学结构分析](assets/milvus-fig07-chemical-analysis.png)

*图 7：Milvus 化学结构分析。*

[^10]: <https://www.wuxiapptec.com/>

## 7. 实验

### 7.1 实验设置

**平台。** 实验在阿里云上进行，为节省成本按实验使用不同实例，最多 12 节点。默认 CPU 实例为 `ecs.g6e.4xlarge`：Xeon Platinum 8269 Cascade 2.5 GHz、16 vCPU、35.75 MB L3 cache、AVX512、64 GB 内存和 NAS 弹性存储。GPU 实例为 `ecs.gn6i-c16g1.4xlarge`：NVIDIA Tesla T4、64 KB private memory、512 KB local memory、16 GB global memory、PCIe 3.0 ×16。

**数据集。** 使用公开 SIFT1B [34] 和 Deep1B [8]。SIFT1B 包含十亿个 128 维 SIFT 向量（512 GB）；Deep1B 包含深度神经网络抽取的十亿个 96 维图像向量（384 GB）。两者都是向量相似性和近似最近邻研究的标准数据集 [35, 41, 65, 68]。

**对手。** 比较开源 Vearch v3.2.0 [4, 39]、Microsoft SPTAG [14]，以及截至 2020 年 7 月最新版本、因商业原因匿名为 A、B、C 的三个工业商业系统。Milvus 基于 Faiss [3, 35] 实现，7.4 节也直接评估其算法优化。

**指标。** 默认 `k=50`。若 ground truth top-k 为 S，系统结果为 S'，召回率定义为 `|S∩S'|/|S|`。吞吐通过对数据集发出 10,000 个随机查询测量。

### 7.2 与已有系统比较

取两个数据集前一千万向量（SIFT10M、Deep10M），因为已有系统构建索引和查询十亿数据过慢；7.3 节另在完整十亿向量上验证 Milvus。商业系统最低配置要求多节点：A、C 各用两节点（每节点 64 GB），B 用四节点（每节点 128 GB）；其他系统含 Milvus 均为单节点。尽可能统一使用多数系统都支持的 IVF_FLAT 与 HNSW。

![图 8：IVF 索引上的系统评估](assets/milvus-fig08-ivf-evaluation.png)

*图 8：IVF 索引上的系统评估。*

图 8 的量化索引结果表明，在召回率相近时，即便 CPU 版本 Milvus 也最多领先两个数量级：比 Vearch 快 6.4×–27.0×；比四节点 B 快 153.7×[^11]；比两节点 C 快 4.7×–11.5×；比树索引 SPTAG 快 1.3×–2.1×。SPTAG 不能达到 Milvus 的 0.99 高召回率，而且内存多 14 倍（17.88 GB 对 1.27 GB）[^12]。本设置中数据可放入 GPU，GPU 版更快。B 只支持欧氏距离，故省略其 Deep10M；Vearch GPU 建索引存在尚未修复的 bug，亦省略[^13]。A 只支持 HNSW，结果移至图 9。

优势除工程实现外还来自：（1）同时支持 inter-query 与 intra-query 的细粒度并行；（2）cache-aware 和 SIMD-aware 优化；（3）CPU/GPU 混合执行。

![图 9：HNSW 索引上的系统评估](assets/milvus-fig09-hnsw-evaluation.png)

*图 9：HNSW 索引上的系统评估。*

图 9 中 Milvus 仍显著领先：比 Vearch 快 15.1×–60.4×，比 A 快 8.0×–17.1×，比 C 快 7.3×–73.9×。A 不支持内积，故省略 Deep10M；C 构建 Deep10M 索引超过 100 小时仍未完成，也被省略。

[^11]: 2020 年 8 月测试时，系统 B 禁用了 `nprobe`、`nlist` 等参数调优，使用 brute-force，故图 8 只有一个点且性能较低。若未来开放参数以使用索引，预计性能会改善。
[^12]: SPTAG 也不支持表 1 所列的动态数据管理、GPU、属性过滤、多向量查询和分布式系统。
[^13]: 我们于 2020 年 9 月提交 bug：<https://github.com/vearch/vearch/issues/252>。

### 7.3 可扩展性

在含十亿向量的 SIFT1B 上使用 IVF_FLAT，分别考察数据规模和服务器数量。

![图 10：可扩展性](assets/milvus-fig10-scalability.png)

*图 10：可扩展性。*

图 10(a) 在单台 `ecs.re6.26xlarge`（104 vCPU、1.5 TB 内存，可容纳全部数据）上显示，随着数据增加，吞吐按比例平滑下降。图 10(b) 中，数据分到若干 `ecs.g6e.13xlarge` 节点（每节点 52 vCPU、192 GB）；节点增加时吞吐线性上升。后者吞吐反而高于 `ecs.re6.26xlarge`，原因是更多核心对共享 CPU cache 和内存带宽的争用更严重。

### 7.4 优化评估

![图 11：cache-aware 设计评估](assets/milvus-fig11-cache-aware-evaluation.png)

*图 11：cache-aware 设计评估。*

图 11 比较 12 MB L3（Intel Core i7-8700 3.2 GHz）和 35.75 MB L3（Xeon Platinum 8269 Cascade 2.5 GHz）CPU。Batch size 为 1000，数据从 1000 到一千万向量。Cache-aware 设计分别最多提升 2.7× 和 1.5×。

![图 12：SIMD 优化](assets/milvus-fig12-simd.png)

*图 12：SIMD 优化。*

图 12 沿用图 11 设置，在 Xeon 上比较 AVX2 与 AVX512；AVX512 约快 1.5×。

![图 13：GPU 索引](assets/milvus-fig13-gpu-indexing.png)

*图 13：GPU 索引。*

图 13 在数据放不进 GPU memory 的 SIFT1B 上比较 SQ8H、纯 CPU SQ8 与纯 GPU SQ8。因数据传输，GPU SQ8 比 CPU SQ8 慢；batch 增大时更多计算推到 GPU，差距缩小。所有情况下 SQ8H 都更快：它只把质心存入 GPU 完成第一步，由 CPU 完成第二步，不必运行时把 data segment 传到 GPU。

### 7.5 属性过滤评估

沿用 [65]，把查询选择率定义为不满足 CA 的实体比例，因此值越高，通过 CA 的实体越少。取 SIFT1B 前一亿向量，为每个向量添加 `[0,10000]` 随机属性；设置两种场景：`k=50, recall=0.95` 与 `k=500, recall=0.85`。

![图 14：Milvus 中的属性过滤](assets/milvus-fig14-attribute-filtering.png)

*图 14：Milvus 中的属性过滤。*

图 14 中，A 随选择率提高而更快，因为检查向量更少；B 对选择率不敏感，瓶颈是向量相似性搜索；C 比 B 慢，因为要检查 `θ=1.1` 倍向量；代价策略 D 在 A/B/C 中择优，因而更快；分区策略 E 又比 D 最多快 13.7×。

![图 15：属性过滤比较](assets/milvus-fig15-attribute-comparison.png)

*图 15：属性过滤比较。*

图 15 比较 A、B、C、Vearch 和 Milvus，Milvus 快 48.5×–41299.5×。图 15(b) 省略 B，因为其参数由系统固定、用户不能修改。

### 7.6 多向量查询处理评估

SIFT1B 与 Deep1B 每实体只有一个向量，因此使用 Recipe1M [50, 56]：一百多万份菜谱和食物图片，每个实体有文本向量（菜谱描述）和图像向量（食物图片）。随机选 10,000 个查询，`k=50`，使用 IVF_FLAT 和加权和聚合。

![图 16：Milvus 多向量处理](assets/milvus-fig16-multivector.png)

*图 16：Milvus 多向量处理。*

图 16(a) 使用欧氏距离，比较 k 为 50、2048 的标准 NRA 与 k' 为 4096、8192、16384 的迭代合并（IMG）。NRA 要么慢，要么召回低：NRA-50 快但召回仅 0.1；NRA-2048 召回提高到最高 0.5，但性能低。IMG-4096 在相似召回下快 15×，因为不必每次都调用向量查询，heap 维护也更低。

图 16(b) 使用内积，比较 IMG-4096、IMG-8192 与向量融合。向量融合只需一次 top-k 搜索，因而快 3.4×–5.8×。

## 8. 相关工作

向量相似性搜索（高维最近邻）在近似搜索 [7, 41] 和精确搜索 [38, 42] 中都被广泛研究。本文关注高性能近似搜索。已有近似方法大致分四类：LSH [23, 24, 32, 40, 44, 45, 48, 73]、树 [17, 46, 54, 57]、图 [20, 43, 49, 61, 72] 和量化 [3, 6, 22, 27, 33, 35]。这些工作都聚焦索引，而 Milvus 是包括索引、查询引擎、GPU 引擎、存储引擎和分布式系统的完整向量数据管理系统；其可扩展索引框架也能纳入这些及未来新索引。Faiss [35]、SPTAG [14] 等只是库，不是系统，表 1 已总结差异。

Alibaba PASE [68] 和 AnalyticDB-V [65] 等工业系统并非专为向量优化，而是扩展关系数据库支持向量，实验显示性能严重受损。Vearch [39] 等专用向量系统又不适合十亿规模，且显著慢于 Milvus。

也有 GPU 向量搜索引擎 [35, 72]。[72] 为 GPU 优化 HNSW，却假设数据全部装入 GPU。Faiss [35] 在数据装不下时按需加载完整 data segment，性能较低；Milvus 的 SQ8H 在无需动态装载数据的情况下结合 CPU 与 GPU。

本工作也属于构建专用数据引擎的趋势，因为 one size does not fit all [60]；例子包括图引擎 [18]、IoT 引擎 [21]、时序数据库 [55] 和科学数据库 [59]。Milvus 是其中面向向量数据的专用引擎。

## 9. 结论

在本工作中，我们分享过去几年在 Zilliz 构建 Milvus 的经验。Milvus 已被数百家公司采用，并成为 LF AI & Data Foundation 的孵化项目。未来计划用 FPGA 加速：我们已在 FPGA 上实现 IVF_PQ，初步结果令人鼓舞。另一个有趣而困难的方向，是把 Milvus 构造成 cloud-native 数据管理系统，我们正在开展相关工作。

## 致谢

Milvus 是 Zilliz 众多工程师参与的多年项目。特别感谢 Shiyu Chen、Qing Li、Yunmei Li、Chenglong Li、Zizhao Chen、Yan Wang 和 Yunying Zhang 的贡献；感谢 Haimeng Cai 与 Chris Warnock 校对论文；感谢 Walid G. Aref 和匿名审稿人的宝贵反馈。

## 参考文献

[1] 2020. Annoy: Approximate Nearest Neighbors Oh Yeah. <https://github.com/spotify/annoy>

[2] 2020. ElasticSearch: Open Source, Distributed, RESTful Search Engine. <https://github.com/elastic/elasticsearch>

[3] 2020. Facebook Faiss. https://github.com/facebookresearch/faiss

[4] 2020. Vearch: A Distributed System for Embedding-based Retrieval. <https://github.com/vearch/vearch>

[5] Reza Akbarinia, Esther Pacitti, and Patrick Valduriez. 2007. Best Position Algorithms for Top-k Queries. In International Conference on Very Large Data Bases (VLDB). 495–506.

[6] Fabien André, Anne-Marie Kermarrec, and Nicolas Le Scouarnec. 2015. Cache locality is not enough: High-Performance Nearest Neighbor Search with Product Quantization Fast Scan. Proceedings of the VLDB Endowment (PVLDB) 9, 4 (2015), 288–299.

[7] Martin Aumüller, Erik Bernhardsson, and Alexander John Faithfull. 2018. ANN-Benchmarks: A Benchmarking Tool for Approximate Nearest Neighbor Algorithms. Computing Research Repository (CoRR) abs/1807.05614 (2018).

[8] Artem Babenko and Victor S. Lempitsky. 2016. Efficient Indexing of Billion-Scale Datasets of Deep Descriptors. In IEEE Conference on Computer Vision and Pattern Recognition (CVPR). 2055–2063.

[9] Dávid Bajusz, Anita Rácz, and Károly Héberger. 2015. Why Is Tanimoto Index An Appropriate Choice For Fingerprint-Based Similarity Calculations? Journal of Cheminformatics 7 (2015).

[10] Tadas Baltrusaitis, Chaitanya Ahuja, and Louis-Philippe Morency. 2019. Multimodal Machine Learning: A Survey and Taxonomy. IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI) 41, 2 (2019), 423–443.

[11] Oren Barkan and Noam Koenigstein. 2016. ITEM2VEC: Neural Item Embedding for Collaborative Filtering. In IEEE International Workshop on Machine Learning for Signal Processing (MLSP). 1–6.

[12] Kaushik Chakrabarti, Surajit Chaudhuri, and Venkatesh Ganti. 2011. Interval-based Pruning for Top-k Processing over Compressed Lists. In International Conference on Data Engineering (ICDE). 709–720.

[13] Hongming Chen, Ola Engkvist, Yinhai Wang, Marcus Olivecrona, and Thomas Blaschke. 2018. The Rise of Deep Learning in Drug Discovery. Drug Discovery Today 23, 6 (2018), 1241–1250.

[14] Qi Chen, Haidong Wang, Mingqin Li, Gang Ren, Scarlett Li, Jeffery Zhu, Jason Li, Chuanjie Liu, Lintao Zhang, and Jingdong Wang. 2018. SPTAG: A Library for Fast Approximate Nearest Neighbor Search. https://github.com/Microsoft/SPTAG

[15] Paul Covington, Jay Adams, and Emre Sargin. 2016. Deep Neural Networks for YouTube Recommendations. In ACM Conference on Recommender Systems (RecSys). 191–198.

[16] Benoit Dageville, Thierry Cruanes, Marcin Zukowski, Vadim Antonov, Artin Avanes, Jon Bock, Jonathan Claybaugh, Daniel Engovatov, Martin Hentschel, Jiansheng Huang, Allison W. Lee, Ashish Motivala, Abdul Q. Munir, Steven Pelley, Peter Povinec, Greg Rahn, Spyridon Triantafyllis, and Philipp Unterbrunner. 2016. The Snowflake Elastic Data Warehouse. In ACM Conference on Management of Data (SIGMOD). 215–226.

[17] Sanjoy Dasgupta and Yoav Freund. 2008. Random Projection Trees and Low Dimensional Manifolds. In ACM Symposium on Theory of Computing (STOC). 537–546.

[18] Alin Deutsch, Yu Xu, Mingxi Wu, and Victor E. Lee. 2020. Aggregation Support for Modern Graph Analytics in TigerGraph. In ACM Conference on Management of Data (SIGMOD). 377–392.

[19] Ronald Fagin, Amnon Lotem, and Moni Naor. 2001. Optimal Aggregation Algorithms for Middleware. In ACM Symposium on Principles of Database Systems (PODS). 102–113.

[20] Cong Fu, Chao Xiang, Changxu Wang, and Deng Cai. 2019. Fast Approximate Nearest Neighbor Search With The Navigating Spreading-out Graph. Proceedings of the VLDB Endowment (PVLDB) 12, 5 (2019), 461–474.

[21] Christian Garcia-Arellano, Adam J. Storm, David Kalmuk, Hamdi Roumani, Ronald Barber, Yuanyuan Tian, Richard Sidle, Fatma Özcan, Matt Spilchen, Josh Tiefenbach, Daniel C. Zilio, Lan Pham, Kostas Rakopoulos, Alexander Cheung, Darren Pepper, Imran Sayyid, Gidon Gershinsky, Gal Lushi, and Hamid Pirahesh. 2020. Db2 Event Store: A Purpose-Built IoT Database Engine. Proceedings of the VLDB Endowment (PVLDB) 13, 12 (2020), 3299–3312.

[22] Tiezheng Ge, Kaiming He, Qifa Ke, and Jian Sun. 2014. Optimized Product Quantization. IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI) 36, 4 (2014), 744–755.

[23] Aristides Gionis, Piotr Indyk, and Rajeev Motwani. 1999. Similarity Search in High Dimensions via Hashing. In International Conference on Very Large Data Bases (VLDB). 518–529.

[24] Long Gong, Huayi Wang, Mitsunori Ogihara, and Jun Xu. 2020. iDEC: Indexable Distance Estimating Codes for Approximate Nearest Neighbor Search. Proceedings of the VLDB Endowment (PVLDB) 13, 9 (2020), 1483–1497.

[25] Mihajlo Grbovic and Haibin Cheng. 2018. Real-time Personalization using Embeddings for Search Ranking at Airbnb. In ACM Conference on Knowledge Discovery & Data Mining (KDD). 311–320.

[26] Martin Grohe. 2020. Word2vec, Node2vec, Graph2vec, X2vec: Towards a Theory of Vector Embeddings of Structured Data. In ACM Symposium on Principles of Database Systems (PODS). 1–16.

[27] Ruiqi Guo, Philip Sun, Erik Lindgren, Quan Geng, David Simcha, Felix Chern, and Sanjiv Kumar. 2020. Accelerating Large-Scale Inference with Anisotropic Vector Quantization. In International Conference on Machine Learning (ICML).

[28] Kaiming He, Xiangyu Zhang, Shaoqing Ren, and Jian Sun. 2016. Deep Residual Learning for Image Recognition. In IEEE Conference on Computer Vision and Pattern Recognition (CVPR). 770–778.

[29] D. Frank Hsu and Isak Taksa. 2005. Comparing Rank and Score Combination Methods for Data Fusion in Information Retrieval. Information Retrieval (IR) 8, 3 (2005), 449–480.

[30] Tongwen Huang, Zhiqi Zhang, and Junlin Zhang. 2019. FiBiNET: Combining Feature Importance and Bilinear Feature Interaction for Click-through Rate Prediction. In ACM Conference on Recommender Systems (RecSys). 169–177.

[31] Ihab F. Ilyas, George Beskales, and Mohamed A. Soliman. 2008. A Survey of Top-k Query Processing Techniques in Relational Database Systems. ACM Computing Surveys (CSUR) 40, 4 (2008), 11:1–11:58.

[32] Omid Jafari, Parth Nagarkar, and Jonathan Montaño. 2020. mmLSH: A Practical and Efficient Technique for Processing Approximate Nearest Neighbor Queries on Multimedia Data. Computing Research Repository (CoRR) abs/2003.06415 (2020).

[33] Hervé Jégou, Matthijs Douze, and Cordelia Schmid. 2011. Product Quantization for Nearest Neighbor Search. IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI) 33, 1 (2011), 117–128.

[34] Hervé Jégou, Romain Tavenard, Matthijs Douze, and Laurent Amsaleg. 2011. Searching in One Billion Vectors: Re-rank with Source Coding. In IEEE International Conference on Acoustics, Speech, and Signal Processing (ICASSP). 861–864.

[35] Jeff Johnson, Matthijs Douze, and Hervé Jégou. 2019. Billion-scale similarity search with GPUs. IEEE Transactions on Big Data (2019).

[36] Timothy King. 2019. 80 Percent of Your Data Will Be Unstructured in Five Years. <https://solutionsreview.com/data-management/80-percent-of-your-data-will-be-unstructured-in-five-years/>

[37] Quoc V. Le and Tomas Mikolov. 2014. Distributed Representations of Sentences and Documents. In International Conference on Machine Learning (ICML). 1188–1196.

[38] Hui Li, Tsz Nam Chan, Man Lung Yiu, and Nikos Mamoulis. 2017. FEXIPRO: Fast and Exact Inner Product Retrieval in Recommender Systems. In ACM Conference on Management of Data (SIGMOD). 835–850.

[39] Jie Li, Haifeng Liu, Chuanghua Gui, Jianyu Chen, Zhenyuan Ni, Ning Wang, and Yuan Chen. 2018. The Design and Implementation of a Real Time Visual Search System on JD E-Commerce Platform. In Middleware. 9–16.

[40] Mingjie Li, Ying Zhang, Yifang Sun, Wei Wang, Ivor W. Tsang, and Xuemin Lin. 2020. I/O Efficient Approximate Nearest Neighbour Search based on Learned Functions. In International Conference on Data Engineering (ICDE). 289–300.

[41] Wen Li, Ying Zhang, Yifang Sun, Wei Wang, Mingjie Li, Wenjie Zhang, and Xuemin Lin. 2020. Approximate Nearest Neighbor Search on High Dimensional Data - Experiments, Analyses, and Improvement. IEEE Transactions on Knowledge and Data Engineering (TKDE) 32, 8 (2020), 1475–1488.

[42] Yuliang Li, Jianguo Wang, Benjamin Pullman, Nuno Bandeira, and Yannis Papakonstantinou. 2019. Index-Based, High-Dimensional, Cosine Threshold Querying with Optimality Guarantees. In International Conference on Database Theory (ICDT). 11:1–11:20.

[43] Peng-Cheng Lin and Wan-Lei Zhao. 2019. A Comparative Study on Hierarchical Navigable Small World Graphs. Computing Research Repository (CoRR) abs/1904.02077 (2019).

[44] Wanqi Liu, Hanchen Wang, Ying Zhang, Wei Wang, and Lu Qin. 2019. I-LSH: I/O Efficient c-Approximate Nearest Neighbor Search in High-Dimensional Space. In International Conference on Data Engineering (ICDE). 1670–1673.

[45] Kejing Lu and Mineichi Kudo. 2020. R2LSH: A Nearest Neighbor Search Scheme Based on Two-dimensional Projected Spaces. In International Conference on Data Engineering (ICDE). 1045–1056.

[46] Kejing Lu, Hongya Wang, Wei Wang, and Mineichi Kudo. 2020. VHP: Approximate Nearest Neighbor Search via Virtual Hypersphere Partitioning. Proceedings of the VLDB Endowment (PVLDB) 13, 9 (2020), 1443–1455.

[47] Chen Luo and Michael J. Carey. 2020. LSM-based Storage Techniques: A Survey. VLDB Journal 29, 1 (2020), 393–418.

[48] Qin Lv, William Josephson, Zhe Wang, Moses Charikar, and Kai Li. 2017. Intelligent Probing for Locality Sensitive Hashing: Multi-Probe LSH and Beyond. Proceedings of the VLDB Endowment (PVLDB) 10, 12 (2017), 2021–2024.

[49] Yu A. Malkov and D. A. Yashunin. 2020. Efficient and Robust Approximate Nearest Neighbor Search Using Hierarchical Navigable Small World Graphs. IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI) 42, 4 (2020), 824–836.

[50] Javier Marín, Aritro Biswas, Ferda Ofli, Nicholas Hynes, Amaia Salvador, Yusuf Aytar, Ingmar Weber, and Antonio Torralba. 2018. Recipe1M: A Dataset for Learning Cross-Modal Embeddings for Cooking Recipes and Food Images. Computing Research Repository (CoRR) abs/1810.06553 (2018).

[51] Adam C. Mater and Michelle L. Coote. 2019. Deep Learning in Chemistry. Journal of Chemical Information and Modeling 59, 6 (2019), 2545–2559.

[52] Tomas Mikolov, Kai Chen, Greg Corrado, and Jeffrey Dean. 2013. Efficient Estimation of Word Representations in Vector Space. In International Conference on Learning Representations (ICLR).

[53] Tomas Mikolov, Ilya Sutskever, Kai Chen, Gregory S. Corrado, and Jeffrey Dean. 2013. Distributed Representations of Words and Phrases and their Compositionality. In Annual Conference on Neural Information Processing Systems (NeurIPS). 3111–3119.

[54] Marius Muja and David G. Lowe. 2014. Scalable Nearest Neighbor Algorithms for High Dimensional Data. IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI) 36, 11 (2014), 2227–2240.

[55] Tuomas Pelkonen, Scott Franklin, Justin Teller, Paul Cavallaro, Qi Huang, Justin Meza, and Kaushik Veeraraghavan. 2015. Gorilla: A Fast, Scalable, in-Memory Time Series Database. Proceedings of the VLDB Endowment (PVLDB) 8, 12 (2015), 1816–1827.

[56] Amaia Salvador, Nicholas Hynes, Yusuf Aytar, Javier Marin, Ferda Ofli, Ingmar Weber, and Antonio Torralba. 2017. Learning Cross-modal Embeddings for Cooking Recipes and Food Images. In IEEE Conference on Computer Vision and Pattern Recognition (CVPR). 3068–3076.

[57] Chanop Silpa-Anan and Richard I. Hartley. 2008. Optimised KD-trees for Fast Image Descriptor Matching. In IEEE Conference on Computer Vision and Pattern Recognition (CVPR). 1–8.

[58] Karen Simonyan and Andrew Zisserman. 2015. Very Deep Convolutional Networks for Large-Scale Image Recognition. In International Conference on Learning Representations (ICLR).

[59] Michael Stonebraker, Anastasia Ailamaki, Jeremy Kepner, and Alexander S. Szalay. 2012. The Future of Scientific Data Bases. In International Conference on Data Engineering (ICDE). 7–8.

[60] Michael Stonebraker and Ugur Çetintemel. 2005. "One Size Fits All": An Idea Whose Time Has Come and Gone (Abstract). In International Conference on Data Engineering (ICDE). 2–11.

[61] Suhas Jayaram Subramanya, Fnu Devvrit, Harsha Vardhan Simhadri, Ravishankar Krishnawamy, and Rohan Kadekodi. 2019. Rand-NSG: Fast Accurate Billion-point Nearest Neighbor Search on a Single Node. In Annual Conference on Neural Information Processing Systems (NeurIPS). 13748–13758.

[62] Nikolaos Tziavelis, Wolfgang Gatterbauer, and Mirek Riedewald. 2020. Optimal Join Algorithms Meet Top-k. In ACM Conference on Management of Data (SIGMOD). 2659–2665.

[63] Alexandre Verbitski, Anurag Gupta, Debanjan Saha, Murali Brahmadesam, Kamal Gupta, Raman Mittal, Sailesh Krishnamurthy, Sandor Maurice, Tengiz Kharatishvili, and Xiaofeng Bao. 2017. Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases. In ACM Conference on Management of Data (SIGMOD). 1041–1052.

[64] Jianguo Wang, Chunbin Lin, Yannis Papakonstantinou, and Steven Swanson. 2017. An Experimental Study of Bitmap Compression vs. Inverted List Compression. In ACM Conference on Management of Data (SIGMOD). 1041–1052.

[65] Chuangxian Wei, Bin Wu, Sheng Wang, Renjie Lou, Chaoqun Zhan, Feifei Li, and Yuanzhe Cai. 2020. AnalyticDB-V: A Hybrid Analytical Engine Towards Query Fusion for Structured and Unstructured Data. Proceedings of the VLDB Endowment (PVLDB) 13, 12 (2020), 3152–3165.

[66] Peter Willett. 2014. The Calculation of Molecular Structural Similarity: Principles and Practice. Molecular Informatics 33, 6–7 (2014), 403–413.

[67] Susan Wojcicki. 2020. YouTube at 15: My Personal Journey and the Road Ahead. https://blog.youtube/news-and-events/youtube-at-15-my-personal-journey

[68] Wen Yang, Tao Li, Gai Fang, and Hong Wei. 2020. PASE: PostgreSQL Ultra-High-Dimensional Approximate Nearest Neighbor Search Extension. In ACM Conference on Management of Data (SIGMOD). 2241–2253.

[69] Rex Ying, Ruining He, Kaifeng Chen, Pong Eksombatchai, William L. Hamilton, and Jure Leskovec. 2018. Graph Convolutional Neural Networks for Web-Scale Recommender Systems. In ACM Conference on Knowledge Discovery & Data Mining (KDD). 974–983.

[70] Shaoting Zhang, Ming Yang, Timothée Cour, Kai Yu, and Dimitris N. Metaxas. 2015. Query Specific Rank Fusion for Image Retrieval. IEEE Transactions on Pattern Analysis and Machine Intelligence (TPAMI) 37, 4 (2015), 803–815.

[71] Shilin Zhang and Hangbin Yu. 2018. Person Re-Identification by Multi-Camera Networks for Internet of Things in Smart Cities. IEEE Access 6 (2018), 76111–76117.

[72] Weijie Zhao, Shulong Tan, and Ping Li. 2020. SONG: Approximate Nearest Neighbor Search on GPU. In International Conference on Data Engineering (ICDE). 1033–1044.

[73] Bolong Zheng, Xi Zhao, Lianggui Weng, Nguyen Quoc Viet Hung, Hang Liu, and Christian S. Jensen. 2020. PM-LSH: A Fast and Accurate LSH Framework for High-Dimensional Approximate NN Search. Proceedings of the VLDB Endowment (PVLDB) 13, 5 (2020), 643–655.
