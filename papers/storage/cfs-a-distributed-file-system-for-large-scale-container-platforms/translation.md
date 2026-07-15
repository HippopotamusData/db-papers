---
paper_id: cfs-a-distributed-file-system-for-large-scale-container-platforms
title: 'CFS: A Distributed File System for Large Scale Container Platforms'
language: zh-CN
source: source.pdf
---

# CFS: A Distributed File System for Large Scale Container Platforms（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 摘要

论文提出 CFS，一个面向大规模容器平台的分布式文件系统。CFS 同时支持顺序与随机文件访问，并为大文件和小文件优化存储。它根据不同写入场景采用不同复制协议来提升复制性能。CFS 使用元数据子系统保存文件元数据，并基于内存使用把元数据分布到不同存储节点上，从而避免扩容时的数据重平衡。CFS 还提供 POSIX 兼容 API，但放松部分语义和元数据原子性以提升性能。与容器平台常用的 Ceph 相比，CFS 在 7 类常见元数据操作中平均约有 3 倍性能提升，并在高并发多客户端/多进程场景下表现出更好的随机读写性能。

## 1. 引言

容器化和微服务改变了云环境中的应用构建、部署和管理方式。容器通常不依赖本地磁盘，因此计算与存储解耦虽然提升了资源扩展效率，也带来了独立持久化存储的需求：容器关闭后数据仍需保留；多个容器可能同时访问同一文件；存储资源可能被不同服务共享。

一种方案是通过 Container Storage Interface (CSI)、Rook 等组件接入现有分布式文件系统。但在京东容器平台的大规模生产场景中，工程团队遇到性能、可扩展性和成本问题：数据需要加载到多个系统，内部系统使用不同语言和 API，迁移与互操作成本高；底层组件处理 YouTube 级别或京东级别规模的数据时也存在效率瓶颈。

CFS 的设计目标是：支持丰富 API、高可扩展性、高性能、数据新鲜度，并适配大规模容器平台上的混合文件访问模式。与传统分布式文件系统不同，CFS 明确区分 metadata subsystem、data subsystem 和 resource manager，并针对 append 与 overwrite 采用不同复制策略。

## 2. 设计与实现

CFS 由元数据子系统、数据子系统和资源管理器组成；客户端可以通过容器平台把它作为应用可访问的分布式文件系统。

![图 1：CFS 架构。Metadata subsystem 由 meta node/meta partition 组成，data subsystem 由 data node/data partition 组成，resource manager 负责分配与管理。](assets/cfs-fig01-architecture.png)

### 2.1 元数据存储

#### 2.1.1 内部结构

Metadata subsystem 可以看作一个分布式内存元数据存储。它包含多个 meta node，每个 meta node 可以有数百个 meta partition。每个 meta partition 在内存中保存同一 volume 中文件的 inode 和 dentry，并使用两个 B-tree 加速查找：`inodeTree` 按 inode id 索引，`dentryTree` 按 parent inode id 与 dentry name 索引。

```go
type metaPartition struct {
    config        *MetaPartitionConfig
    size          uint64
    dentryTree    *BTree // btree for dentries
    inodeTree     *BTree // btree for inodes
    raftPartition raftstore.Partition
    freeList      *freeList // free inode list
    vol           *Vol
    ... // other fields
}

type inode struct {
    inode      uint64 // inode id
    type       uint32 // inode type
    linkTarget []byte // symLink target name
    nLink      uint32 // number of links
    flag       uint32
    ... // other fields
}

type dentry struct {
    parentId uint64 // parent inode id
    name     string // name of the dentry
    inode    uint64 // current inode id
    type     uint32 // dentry type
}
```

#### 2.1.2 基于 Raft 的复制

元数据写入按 meta partition 复制。CFS 使用 MultiRaft 保证副本强一致性；与为每个复制组独立运行 Raft 相比，MultiRaft 将多个 Raft 组复用在同一组节点上，可显著减少网络中的心跳流量。每个 meta partition 的 inode 与 dentry 更新都先通过所属 Raft 组排序，再在各副本上以相同顺序应用。

#### 2.1.3 故障恢复

Meta partition 的内存状态通过快照和日志持久化到本地磁盘。恢复时先装载最近快照，再重放其后的日志；定期快照与日志压缩限制了重放量，从而缩短恢复时间。元数据操作跨 inode 与 dentry 两种结构，失败可能产生没有 dentry 关联的 orphan inode。CFS 不为这类跨结构操作提供完整事务，而由客户端在失败后重试，直到操作成功或达到最大重试次数，并由后台流程回收孤儿 inode。

### 2.2 数据存储

#### 2.2.1 内部结构

Data subsystem 同时优化大文件和小文件，并支持顺序和随机访问。它包含多个 data node，每个 data node 有多个 data partition。每个 data partition 维护 partition id、replica 地址等元数据，并包含一个 extent store。

Data partition 是数据放置、复制和恢复的基本单位。Resource manager 记录其成员与状态，客户端缓存可写 partition 列表。Extent store 在 partition 内统一管理物理 extent，但大文件和小文件采用不同分配策略：大文件可以独占 extent，小文件则共享 extent，以避免大量小对象造成空间浪费和元数据膨胀。

![图 2：Data partition 内部结构。大文件可独占 extent，小文件可聚合进同一 extent；partition metadata 与 extent metadata 分别记录分区和 extent 状态。](assets/cfs-fig02-data-partition.png)

```go
type dataPartition struct {
    clusterID       string
    volumeID        string
    partitionID     uint64
    partitionStatus int
    partitionSize   int
    replicas        []string // replica addresses
    disk            *Disk
    isLeader        bool
    isRaftLeader    bool
    path            string
    extentStore     *storage.ExtentStore
    raftPartition   raftstore.Partition
    ... // other fields
}
```

#### 2.2.2 大文件存储

CFS 用阈值 `t` 区分大文件和小文件，默认 `t = 128KB`。大文件内容作为一个或多个 extent 序列存储，可分布在不同 data partition 和 data node 上。写新文件总是写到新 extent 的零偏移处，避免记录 extent 内偏移；最后一个 extent 不需要填满，也不会混入其它文件数据。文件增长超过单个 extent 容量后，客户端再选择新的 data partition 和 extent，因此一个大文件可以自然横跨多个分区和节点。

#### 2.2.3 小文件存储与打孔

多个小文件内容会聚合存储在同一个 extent 中，每个小文件在 extent 中的物理偏移记录在对应 meta node 中。CFS 使用 `fallocate()` 的 punch hole 接口异步释放待删除小文件占用的磁盘空间，从而避免实现垃圾回收和逻辑偏移到物理偏移映射。

#### 2.2.4 场景感知复制

Data subsystem 使用两种强一致复制协议。顺序写（append）采用 primary-backup replication；覆盖写（overwrite）采用类似 metadata subsystem 的 MultiRaft 协议。这样做是因为 primary-backup 不适合 overwrite：覆盖写会产生新 extent，并把原 extent 逻辑拆成多个 fragment；随着覆盖增多，需要 defragmentation，复制性能会受影响。另一方面，MultiRaft 会引入写日志带来的写放大，影响 read-after-write 性能；但覆盖写在目标场景中远少于顺序写，因此可接受。

Primary-backup 路径把 leader 收到的追加数据复制给 follower，所有副本确认后才向客户端提交最大可见 offset，因而不需要为每个数据包额外写 Raft 日志。Overwrite 不能只依赖 offset 单调增长：同一逻辑范围可能被多次修改，副本必须对写入顺序达成一致，所以 CFS 把它交给 Raft 日志排序。论文把这种选择称为 scenario-aware replication，即根据 I/O 语义选择协议，而不是让所有写入承担同一种一致性开销。

#### 2.2.5 故障恢复

失败恢复也分阶段进行：发现副本故障时，先恢复 primary-backup 复制并对齐所有 extent，再恢复 MultiRaft 复制。顺序写期间，未提交的 stale data 可以暂留在分区上，只要不会返回给客户端即可。客户端只记录所有副本都提交过的最大 offset；读请求只会访问已提交 offset 范围内的数据。这个顺序使恢复中的分区先恢复最常见的追加路径，再恢复覆盖写路径，避免两种复制协议的状态交叉干扰。

### 2.3 Resource Manager

Resource manager 负责处理不同类型的文件系统任务，包括放置、分区扩容和 meta partition 拆分。

#### 2.3.1 基于利用率的放置

CFS 按内存/磁盘使用率把文件元数据和内容分布到存储节点上。这种 utilization-based placement 简化了分布式文件系统中的资源分配问题。与 hashing、subtree partition、lazy hybrid、dynamic subtree partition 等元数据放置策略相比，CFS 扩容时不需要主动重平衡已有数据，也降低多个客户端同时访问同一存储节点的概率。

创建 volume 后，客户端向 resource manager 请求若干可用 meta/data partition；这些 partition 通常位于内存或磁盘使用率最低的节点。写文件时，客户端从已分配 partition 中随机选择，避免每次写入都与 resource manager 通信来获取实时利用率。

当 resource manager 发现某个 volume 的所有 partition 即将写满时，会自动为该 volume 增加一批新 partition，同样优先选择内存或磁盘利用率最低的节点。一个 partition 达到容量上限或阈值后不再接收新文件或 extent，但其中已有对象仍可修改和删除。扩容因此只影响后续写入，无须迁移旧数据。

#### 2.3.2 Meta partition 拆分

当某个 meta partition 即将达到 inode/dentry 数量上限时，resource manager 会触发拆分。核心要求是新旧 meta partition 的 inode id 范围不重叠。

算法 1：拆分元数据分区。

```text
procedure PARTITIONING
  mp <- current meta partition
  c <- current cluster
  v <- cluster.getVolume(mp.volName)
  maxPartitionID <- v.getMaxPartitionID()
  if metaPartition.ID < maxPartitionID then return
  if mp.end == math.MaxUint64 then
      end <- maxInodeID + Delta
      mp.end <- end
      task <- newSplitTask(c.Name, mp.partitionID, end)
      c.addTask(task)                  // sync with the meta node
      c.updateMetaPartition(mp.volName, mp)
      c.createMetaPartition(mp.volName, mp.end + 1)
```

拆分时，resource manager 先把当前 meta partition 的 inode 范围截断到上界 `end`，其中 `end` 大于当前已使用最大 inode id `maxInodeID`；然后通知 meta node 更新原分区范围 `[1, end]`，并创建新分区 `[end + 1, infinity)`。这样后续 inode 可唯一分配到旧分区或新分区。

每个 meta partition 的 `maxInodeID` 由 resource manager 与 meta node 的周期通信获得。只有当前分区是该 volume 中编号最大的分区且其范围上界仍为 `math.MaxUint64` 时才执行拆分，避免对旧分区重复切割。

#### 2.3.3 异常处理

当发往 meta/data partition 的请求超时（例如网络中断）时，其余副本会先被标记为只读，防止在状态不明时继续接收修改。当某个 partition 因硬件故障等原因长期不可用，节点连续上报多次失败后，系统才判定其不可用；该 partition 上的数据随后由运维流程迁移到新 partition。论文所述版本的这一步仍需人工触发。

### 2.4 客户端

CFS 客户端集成 FUSE，在用户态提供文件系统接口，客户端进程和缓存都完全运行在用户态。为减少与 resource manager 的通信，客户端启动时取得挂载 volume 可用的 meta/data partition 地址并缓存在本地，之后只做周期同步。

为减少与 meta node 的通信，客户端缓存创建文件时返回的 inode 和 dentry；文件成功写入 data node 后，还缓存 data partition id、extent id 与 offset。打开文件进行读写时，客户端会强制把这些缓存元数据与 meta node 同步，避免使用过期映射。

客户端还缓存最近识别出的 data partition leader。故障恢复可能改变 leader；如果没有缓存，读请求就要逐个尝试每个副本。由于 leader 变更并不频繁，缓存上次的 leader 能在绝大多数情况下把重试次数降到最低。

### 2.5 优化

#### 2.5.1 减少心跳

生产 CFS 集群可能有大量 partition 分布在许多 meta/data node 上。即使采用 MultiRaft，同一 Raft 组各节点之间的心跳仍可能形成很高的通信开销。CFS 在节点之上增加 Raft set 抽象：把节点划分为若干 Raft set，每个集合维护自己的 Raft 组；创建 partition 时优先从同一 Raft set 选择副本。这样一个节点只需与同一集合中的节点交换心跳。

#### 2.5.2 非持久连接

同一 CFS 集群可能同时服务数万客户端。如果所有客户端都与 resource manager 保持长连接，resource manager 会承受不必要的连接压力。因此客户端与 resource manager 之间使用非持久连接，只在请求分配或同步信息时建立通信。

### 2.6 元数据操作

CFS 讨论了 create、link、unlink 三种常见元数据操作。文件创建时，客户端先在 meta partition 中寻找可用 inode，创建 inode，再创建 dentry。Link 会增加 inode 的 `nlink` 并创建新 dentry；如果创建 dentry 失败，`nlink` 会回退。Unlink 先删除 dentry；成功后再减少 inode 的 `nlink`，当 `nlink` 到阈值时 inode 被加入 orphan inode list 并等待清理。

传统 POSIX 文件系统通常让 inode 与 dentry 位于同一存储节点，以保留目录局部性。CFS 的利用率放置不保证这一点，因此一次元数据操作可能访问不同 meta partition。Create 先创建 inode，再创建指向它的 dentry；若 dentry 创建失败，客户端重试。Link 先增加 `nlink`，再创建新 dentry，失败时回滚计数。Unlink 则先删除 dentry，再减少 `nlink`，使可见目录项不会指向已提前删除的 inode。

![图 3：三种常见元数据操作的工作流：create、link 和 unlink。](assets/cfs-fig03-metadata-operations.png)

### 2.7 文件操作

CFS 放松 POSIX 一致性语义：它只保证同一文件/目录上的顺序一致性，不保证多个客户端并发写同一文件/目录时的强一致性。这一取舍减少同步成本，提升容器环境中的常见工作负载性能。

#### 2.7.1 顺序写

顺序写中，客户端从缓存中随机选择可用 data partition，把固定大小的数据包持续发送给 leader；leader 与 follower 复制后，客户端再更新 meta node 中的 offset。写入链路先提交数据，再提交元数据映射；这样即使第二步失败，也只会留下不可见数据，不会让元数据指向尚未复制完成的内容。

![图 4：顺序写工作流。客户端缓存 partition，向 data node 写入数据，并在提交后更新元数据。](assets/cfs-fig04-sequential-write.png)

#### 2.7.2 随机写

覆盖写中，客户端根据原始数据 offset 和新数据 offset 确定覆盖部分，然后分别处理。前一种场景下，客户端顺序写新内容，并在 metadata 中更新 fragment 链；后一种场景中，覆盖写作为 in-place 写进入 Raft group。

![图 5：覆盖已有文件的工作流（不追加）。覆盖写使用 Raft 路径保持相关副本一致。](assets/cfs-fig05-overwrite-existing-file.png)

#### 2.7.3 删除

Delete 是异步操作：客户端发送删除请求后，meta node 删除 dentry；当 inode `nlink` 达到阈值时，inode 加入 orphan inode list，之后再由单独流程删除数据内容。因此删除从命名空间立即生效，磁盘空间回收则可延后执行。

#### 2.7.4 读取

读操作只能发生在 Raft leader 上；primary-backup 组的 leader 与 Raft 组 leader 可能不同。客户端根据缓存中的 data partition id、extent id 和 extent offset 构造请求；若发给的不是当前 Raft leader，则重新定位或转发到 leader 后读取。

## 3. 设计选择讨论

### 3.1 中心化与去中心化

CFS 选择中心化 resource manager，主要是出于简单性。Resource manager 保存所有文件元数据的限制会约束元数据操作规模，但 CFS 通过单独集群保存元数据，降低文件系统整体状态参与程度。实践中，resource manager 的规模受内存和磁盘空间约束，但根据经验不会成为问题。

这里的“中心化”只涉及集群资源与 partition 元信息，并不表示所有文件操作都经过 resource manager。客户端在挂载时取得 partition 列表，之后直接访问 meta/data node；resource manager 主要参与创建 volume、选择低利用率节点、扩容和故障迁移，因此不在普通读写的数据路径上。代价是管理状态集中，需要通过副本与持久化保证可用性；我们接受这一取舍，以换取比完全去中心化放置更简单、可控的实现。

### 3.2 独立 meta node 与数据节点上的元数据

有些分布式文件系统把文件元数据和内容放在同一机器上。CFS 选择独立 meta node 并把所有文件元数据保存在 meta node 内存中。这样可以为 meta node 使用内存更大的机器，为 data node 使用磁盘更大的机器，从而控制成本并提升灵活性。

### 3.3 一致性模型和保证

CFS 的存储层和文件系统层有不同一致性模型。存储层通过 primary-backup 或 Raft 复制保证强一致；文件系统层则选择性放松 POSIX 一致性语义。不同客户端修改同一文件互不重叠的区域时，CFS 保证一致；如果两个客户端并发修改同一部分，则不提供一致性保证。标准 POSIX 要求写操作阻塞到后续读必然能看到新数据，在分布式文件系统上需要锁竞争与同步，代价很高。我们认为容器化、多租户环境中独立作业很少共同写同一共享文件，因此这一取舍能以可接受的语义限制换取性能。

## 4. 评估

### 4.1 实验设置

表 1：系统配置。

| 项目 | 配置 |
| --- | --- |
| Processor Number | Xeon E5-2683V4 |
| Number of Cores | 16 |
| Max Turbo Frequency | 3.00 GHz |
| Processor Base Frequency | 2.10 GHz |
| Network Bandwidth | 1000 Mbps |
| Memory | DDR4 2400MHz, 8 x 32 GB |
| Disk | 16 x 960 GB SSD |
| Operating System | Linux 4.17.12 |

CFS 在 10 台机器上同时部署 meta node 和 data node，另有 1 台 resource manager、3 个 replica。每台机器有 10 个 meta partition 和 1500 个 data partition。Ceph 使用相同 10 台机器部署 16 个 OSD 进程和 1 个 MDS 进程，Ceph 版本为 12.2.11，存储后端为 bluestore over TCP/IP。

### 4.2 元数据操作

表 2：`mdtest` 中测试项说明。

| 测试 | 描述 |
| --- | --- |
| DirCreation | Create a directory |
| DirStat | List all the files in the current directory |
| DirRemoval | Remove a directory |
| FileCreation | Create a file |
| FileRemoval | Remove the file attributes |
| TreeCreation | Create a directory with multiple files as a tree structure |
| TreeRemoval | Remove a directory with multiple files as a tree structure |

表 3：8 个客户端、每客户端 64 个进程时的元数据操作 IOPS。

| Test Name | CFS (multi) | Ceph (multi) | % of Improv. |
| --- | ---: | ---: | ---: |
| DirCreation | 83,729 | 16,627 | 404 |
| DirStat | 875,867 | 91,050 | 862 |
| DirRemoval | 94,235 | 23,807 | 296 |
| FileCreation | 85,556 | 21,919 | 290 |
| FileRemoval | 50,119 | 22,573 | 122 |
| TreeCreation | 10 | 11 | -9 |
| TreeRemoval | 12 | 3 | 300 |

![图 6：单客户端操作文件元数据时的 IOPS。CFS 在 5 个测试中优于 Ceph。](assets/cfs-fig06-single-client-metadata-iops.png)

![图 7：多客户端操作文件元数据时的 IOPS。随着客户端和进程数增加，CFS 的基于利用率元数据放置优势更明显。](assets/cfs-fig07-multiple-client-metadata-iops.png)

CFS 在 `DirStat`、`FileCreation`、`FileRemoval` 等测试中表现较好。`TreeCreation` 中 Ceph 单客户端更优，但多客户端时差距缩小；这与 Ceph 在目录局部性方面的优势以及 CFS 跨 MDS 分布目录项有关。

更具体地说，单客户端、单进程时，Ceph 在 7 项测试中的 5 项领先；并发增加后 CFS 逐步追上，在 8 客户端、每客户端 64 进程时除 `TreeCreation` 外全部领先，平均提升约 3 倍。`DirStat` 中，Ceph 的一次 `readdir` 后接多次 `inodeGet`，而 CFS 用一次批量 `batchInodeGet` 并把结果缓存在客户端；图 7 中偶发的吞吐骤降与客户端缓存未命中有关。

`TreeCreation` 的单客户端结果体现 Ceph 的目录局部性优势：同目录 inode/dentry 可复用同一 MDS 缓存。客户端增多后，热点 MDS 会触发动态放置并经代理 MDS 重定向，额外开销缩小了优势。`TreeRemoval` 中 CFS 的批量目录读取同样有效；少量客户端时 Ceph 的删除请求还可能因同目录元数据集中在单个 MDS 而排队。

### 4.3 大文件

大文件实验使用 `fio` 的 direct I/O 模式，每个进程操作一个 40GB 文件，客户端与服务器部署在不同机器。测试包括顺序写、顺序读、随机写和随机读。为使 Ceph 达到最佳性能，我们把 `osd_op_num_shards` 和 `osd_op_num_threads_per_shard` 分别设为 6 和 4；继续增大会因 CPU 压力而降低写性能。

![图 8：单客户端中不同进程数、不同访问模式下操作文件的 IOPS。每个进程操作独立 40GB 文件。](assets/cfs-fig08-processes-file-access-iops.png)

![图 9：不同客户端数下的 IOPS。随机读/写测试中每个客户端有 64 个进程，顺序读/写测试中每个客户端有 16 个进程；每个进程操作独立 40GB 文件。](assets/cfs-fig09-clients-file-access-iops.png)

结果显示，顺序读写中 CFS 与 Ceph 相近；随机读写中 CFS 明显优于 Ceph。原因包括：CFS 只在内存中缓存文件元数据；随机读中客户端 cache miss 随并发上升而增加，CFS 可一次性缓存文件元数据，避免昂贵磁盘 IO；覆盖写是 in-place，不需要更新文件元数据。

### 4.4 小文件

小文件实验使用 `mdtest` 生成 1KB 到 128KB 文件，模拟创建后通常不再修改的产品图片。CFS 的 128KB 阈值恰好决定文件是否聚合进共享 extent。Ceph 中每个客户端使用不同目录，并把目录绑定到指定 MDS，以最大化并发并稳定性能。

![图 10：8 个客户端、每个 64 进程操作不同大小小文件时的 IOPS。](assets/cfs-fig10-small-files-iops.png)

CFS 在小文件读写中优于 Ceph。读场景中，CFS 将所有文件元数据保存在内存中，避免昂贵磁盘 I/O；写场景中，小文件继续使用已分配 extent，客户端不必向 resource manager 请求新 extent，而可直接把写请求发给 data node，从而进一步减少网络开销。

## 5. 相关工作

CFS 与 Kubernetes、Docker、Mesos 等容器平台相关。Kubernetes 通过 CSI 等接口把外部存储接入容器，解决的是编排与生命周期管理；CFS 解决的是接口背后的文件系统数据路径、元数据扩展和混合 I/O 性能，两者处于不同层次。

传统分布式文件系统中，GFS 和 HDFS 面向大文件顺序访问，采用中心化命名空间和 chunk/block 存储；GlusterFS、MooseFS 和 Amazon EFS 提供更通用的文件接口。PolarFS 面向共享存储云数据库，强调超低延迟和故障恢复；Windows Azure Storage、Dynamo 等则展示了大规模云存储中的分区与复制设计。CFS 同样借鉴日志、复制和分区技术，但需要同时服务容器中的大文件、小文件、顺序访问和随机访问。

Ceph 是论文最直接的比较对象。它使用 CRUSH 做数据放置，并通过动态元数据子树迁移扩展 MDS；目录局部性可提高单客户端树操作性能，但热点目录可能集中到少数 MDS。CFS 不保持严格的目录局部性，而按节点利用率放置 inode、dentry 和数据，使扩容只影响新写入，无需搬迁旧对象。其优势更偏向高并发和均衡，代价是一次元数据操作可能跨多个 partition。

元数据扩展方面，既有工作包括静态哈希、子树分区、动态子树迁移，以及把元数据存入可扩展 key-value store。Haystack 和 hFS 等工作还专门优化大量小文件。CFS 的区别是把元数据常驻内存、以 meta partition 为复制和扩容单位，并让 resource manager 根据实际内存占用分配新 partition；这减少主动重平衡，但也要求客户端重试来处理跨 inode/dentry 操作的非原子性。

## 6. 结论与未来工作

CFS 是面向大规模容器平台的分布式文件系统。它优化大/小文件存储，按顺序写和覆盖写采用不同复制协议，使用基于内存/磁盘利用率的元数据与数据放置，避免扩容重平衡，并以放松的一致性语义换取更高性能。实验表明，与 Ceph 相比，CFS 在常见元数据操作和高并发随机读写中具有优势。

论文所述实现已完成大多数 POSIX 操作，团队仍在补充 `xattr`、`fcntl`、`ioctl`、`mknod` 和 `readdirplus`。后续计划包括利用 Linux page cache 加速文件操作、改进文件锁与缓存一致性、支持 RDMA 等新硬件标准，并开发内核态 POSIX 文件系统接口，以完全消除 FUSE 开销。

## 致谢

我们感谢匿名评审提出的建议和意见，并感谢中国科学技术大学陈恩红教授对本工作的帮助。

## 参考文献

- [1] Balalaie, A., Heydarnoori, A., and Jamshidi, P. Microservices architecture enables devops: Migration to a cloud-native architecture. IEEE Software 33, 3 (May 2016), 42–52.
- [2] Beaver, D., Kumar, S., Li, H. C., Sobel, J., and Vajgel, P. Finding a needle in haystack: Facebook’s photo storage. In Proceedings of the 9th USENIX Conference on Operating Systems Design and Implementation (Berkeley, CA, USA, 2010), OSDI’10, USENIX Association, pp. 47–60.
- [3] Bernstein, D. Containers and cloud: From lxc to docker to kubernetes. IEEE Cloud Computing 1, 3 (Sept. 2014), 81–84.
- [4] Brandt, S. A., Miller, E. L., Long, D. D. E., and Xue, L. Efficient metadata management in large distributed storage systems. In Proceedings of the 20 th IEEE/11 th NASA Goddard Conference on Mass Storage Systems and Technologies (MSS’03) (Washington, DC, USA, 2003), MSS ’03, IEEE Computer Society, pp. 290–.
- [5] Brewer, E. A. Kubernetes and the path to cloud native. In Proceedings of the Sixth ACM Symposium on Cloud Computing (New York, NY, USA, 2015), SoCC ’15, ACM, pp. 167–167.
- [6] Calder, B., Wang, J., Ogus, A., Nilakantan, N., Skjolsvold, A., McKelvie, S., Xu, Y., Srivastav, S., Wu, J., Simitci, H., Haridas, J., Uddaraju, C., Khatri, H., Edwards, A., Bedekar, V., Mainali, S., Abbasi, R., Agarwal, A., Haq, M. F. u., Haq, M. I. u., Bhardwaj, D., Dayanand, S., Adusumilli, A., McNett, M., Sankaran, S., Manivannan, K., and Rigas, L. Windows azure storage: A highly available cloud storage service with strong consistency. In Proceedings of the Twenty-Third ACM Symposium on Operating Systems Principles (New York, NY, USA, 2011), SOSP ’11, ACM, pp. 143–157.
- [7] Cao, W., Liu, Z., Wang, P., Chen, S., Zhu, C., Zheng, S., Wang, Y., and Ma, G. Polarfs: An ultra-low latency and failure resilient distributed file system for shared storage cloud database. Proc. VLDB Endow. 11, 12 (Aug. 2018), 1849–1862.
- [8] DeCandia, G., Hastorun, D., Jampani, M., Kakulapati, G., Lakshman, A., Pilchin, A., Sivasubramanian, S., Vosshall, P., and Vogels, W. Dynamo: Amazon’s highly available key-value store. In Proceedings of Twenty-first ACM SIGOPS Symposium on Operating Systems Principles (New York, NY, USA, 2007), SOSP ’07, ACM, pp. 205–220.
- [9] Ganger, G. R., and Kaashoek, M. F. Embedded inodes and explicit grouping: Exploiting disk bandwidth for small files. In Proceedings of the Annual Conference on USENIX Annual Technical Conference (Berkeley, CA, USA, 1997), ATEC ’97, USENIX Association, pp. 1–1.
- [10] Ghemawat, S., Gobioff, H., and Leung, S.-T. The google file system. In Proceedings of the Nineteenth ACM Symposium on Operating Systems Principles (New York, NY, USA, 2003), SOSP ’03, ACM, pp. 29–43.
- [11] Gibson, G. A., and Van Meter, R. Network attached storage architecture. Commun. ACM 43, 11 (Nov. 2000), 37–45.
- [12] Hat, R. Gluster file system. "https://github.com/gluster/glusterfs", 2005.
- [13] Hindman, B., Konwinski, A., Zaharia, M., Ghodsi, A., Joseph, A. D., Katz, R., Shenker, S., and Stoica, I. Mesos: A platform for finegrained resource sharing in the data center. In Proceedings of the 8th USENIX Conference on Networked Systems Design and Implementation (Berkeley, CA, USA, 2011), NSDI’11, USENIX Association, pp. 295–308.
- [14] Kakoulli,E.,andHerodotou,H. Octopusfs:Adistributedfilesystem with tiered storage management. In Proceedings of the 2017 ACM International Conference on Management of Data (New York, NY, USA, 2017), SIGMOD ’17, ACM, pp. 65–78.
- [15] Morris, J. H., Satyanarayanan, M., Conner, M. H., Howard, J. H., Rosenthal, D. S., and Smith, F. D. Andrew: A distributed personal computing environment. Commun. ACM 29, 3 (Mar. 1986), 184–201.
- [16] Ongaro, D., and Ousterhout, J. In search of an understandable consensus algorithm. In Proceedings of the 2014 USENIX Conference on USENIX Annual Technical Conference (Berkeley, CA, USA, 2014), USENIX ATC’14, USENIX Association, pp. 305–320.
- [17] Pahl, C. Containerization and the paas cloud. IEEE Cloud Computing 2, 3 (May-June 2015), 24–31.
- [18] Roselli, D., Lorch, J. R., and Anderson, T. E. A comparison of file system workloads. In Proceedings of the Annual Conference on USENIX Annual Technical Conference (Berkeley, CA, USA, 2000), ATEC ’00, USENIX Association, pp. 4–4.
- [19] Rosenblum, M., and Ousterhout, J. K. The design and implementation of a log-structured file system. ACM Trans. Comput. Syst. 10, 1 (Feb. 1992), 26–52.
- [20] Service, A. W. Amazon elastic file system. "https://docs.aws.amazon. com/efs/latest/ug/efs-ug.pdf", 2016.
- [21] Shen, K., Park, S., and Zhu, M. Journaling of journal is (almost) free. In Proceedings of the 12th USENIX Conference on File and Storage Technologies (FAST 14) (Santa Clara, CA, 2014), USENIX, pp. 287–293.
- [22] Shvachko, K., Kuang, H., Radia, S., and Chansler, R. The hadoop distributed file system. In Proceedings of the 2010 IEEE 26th Symposium on Mass Storage Systems and Technologies (MSST) (Washington, DC, USA, 2010), MSST ’10, IEEE Computer Society, pp. 1–10.
- [23] Technology, C. Moosefs 3.0 storage classes manual. "https://moosefs. com/Content/Downloads/moosefs-storage-classes-manual.pdf", 2016.
- [24] Thekkath, C. A., Mann, T., and Lee, E. K. Frangipani: A scalable distributed file system. In Proceedings of the Sixteenth ACM Symposium on Operating Systems Principles (New York, NY, USA, 1997), SOSP ’97, ACM, pp. 224–237.
- [25] vanRenesse,R.,andSchneider,F.B. Chainreplicationforsupporting high throughput and availability. In Proceedings of the 6th Conference on Symposium on Opearting Systems Design & Implementation - Volume 6 (Berkeley, CA, USA, 2004), OSDI’04, USENIX Association, pp. 7–7.
- [26] Weil, S. A., Brandt, S. A., Miller, E. L., Long, D. D. E., and Maltzahn, C. Ceph: A scalable, high-performance distributed file system. In Proceedings of the 7th Symposium on Operating Systems Design and Implementation (Berkeley, CA, USA, 2006), OSDI ’06, USENIX Association, pp. 307–320.
- [27] Weil, S. A., Leung, A. W., Brandt, S. A., and Maltzahn, C. Rados: A scalable, reliable storage service for petabyte-scale storage clusters. In Proceedings of the 2Nd International Workshop on Petascale Data Storage: Held in Conjunction with Supercomputing ’07 (New York, NY, USA, 2007), PDSW ’07, ACM, pp. 35–44.
- [28] Weil, S. A., Pollack, K. T., Brandt, S. A., and Miller, E. L. Dynamic metadata management for petabyte-scale file systems. In Proceedings of the 2004 ACM/IEEE Conference on Supercomputing (Washington, DC, USA, 2004), SC ’04, IEEE Computer Society, pp. 4–.
- [29] Zhang, Z., and Ghose, K. hfs: A hybrid file system prototype for improving small file and metadata performance. In Proceedings of the 2Nd ACM SIGOPS/EuroSys European Conference on Computer Systems 2007 (New York, NY, USA, 2007), EuroSys ’07, ACM, pp. 175–187.
