---
paper_id: towards-practical-vectorized-analytical-query-engines
title: Towards Practical Vectorized Analytical Query Engines
language: zh-CN
source: source.pdf
---

# Towards Practical Vectorized Analytical Query Engines（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者与单位

- Orestis Polychroniou<sup>∗</sup>（Amazon Web Services，`orestis@amazon.com`）
- Kenneth A. Ross<sup>†</sup>（Columbia University，`kar@cs.columbia.edu`）

<sup>∗</sup> 本工作完成时，第一作者仅隶属于 Columbia University。

<sup>†</sup> 本工作得到美国国家科学基金会（NSF）IIS-1422488 资助以及 Oracle 赠款支持。

会议：DaMoN ’19，2019 年 7 月 1 日，荷兰阿姆斯特丹

DOI：<https://doi.org/10.1145/3329785.3329928>

ACM ISBN 978-1-4503-6801-8/19/07；© 2019 Association for Computing Machinery；定价 15.00 美元。

> 许可说明：允许为个人或课堂用途免费制作本文全部或部分内容的数字或纸质副本，但副本不得用于营利或商业利益，并须在首页载明本声明及完整引文。ACM 以外主体拥有的组成部分之版权必须得到尊重；注明出处的摘要引用不受限制。其他复制、再版、发布到服务器或向列表分发的行为，须事先取得明确许可并且/或者付费。许可申请请联系 `permissions@acm.org`。

## 摘要

查询执行引擎正在适应底层硬件以最大化性能。主流 CPU 正在出现更宽的 SIMD 寄存器和更复杂的 SIMD 指令集；新的处理器设计，例如依赖 SIMD 数据并行性的众核平台，也通过在单芯片上放入更多小核心来提升吞吐。在数据库文献中，用 SIMD 优化带有 key-rid 对的独立算子很常见；然而，最先进的查询引擎依赖紧密耦合算子的编译，在这种设计下，手工优化的独立算子不再实际。

本文提出 VIP，一个从预编译、列式、数据并行子算子自底向上构建的分析型查询引擎，并且完全用 SIMD 实现。在基于 TPC-H 的评测中，VIP 超过了针对查询手工优化的标量代码。

## 1. 引言

硬件感知的数据库设计与实现一直是研究热点，因为现代硬件演进对查询执行有深刻影响。数据库系统已经分化出面向事务、分析、科学计算等不同负载的设计。随着存储和执行目标变窄，系统也围绕新的硬件动态重新设计。

在分析型数据库中，列式存储已经成为标准选择，因为查询通常访问大量元组中的少数列，而事务负载更常更新少量元组。分析型查询引擎本身则仍存在多种设计取舍：列式执行还是行式执行，解释还是按查询编译，缓存感知执行还是算子流水线。

高效的内存内执行需要低解释成本、优化的内存访问和高 CPU 效率。低解释成本通常与高指令级并行相关，可以通过一次处理整列 [27]、每次迭代器调用处理一批元组 [5, 8, 9]，或者在运行时编译查询专用代码 [13, 20, 31] 实现。内存访问可通过算子流水线减少物化 [12]，或通过分区减少缓存和 TLB 未命中 [28]。数据并行则通过 SIMD 向量化实现。线性访问算子，如扫描和压缩 [22, 38, 49, 50]，天然适合数据并行且容易向量化；针对单个数据库算子的临时 SIMD 优化也已有大量研究 [7, 14–16, 23, 35, 36, 41, 42, 44, 46]。

本文作者近期提出了面向非线性访问算子（包括分区、哈希表构建与探测以及 Bloom filter 探测）的通用 SIMD 向量化技术 [34, 37]。本文介绍 VIP[^1]：一个从预编译数据并行子算子自底向上构建的分析型查询执行引擎。VIP 完全用 SIMD 实现，是第一个把高级 SIMD 向量化技术 [34] 用于现实查询的查询引擎设计。它支持每个算子中的多列和多数据类型、扫描和连接中的复杂谓词组合，以及带表达式的多个聚合。

VIP 的算子调用预编译子算子。每个子算子一次处理一个列 [27]、一个元组块 [5]，数据几乎一直停留在 SIMD 寄存器中。查询代码生成和编译是当前查询引擎的主流设计 [20, 31]，也被现代商业分析型数据库采用 [9, 13]。我们的评测使用源自 TPC-H 的查询，显示 VIP 超过了模仿最新代码生成引擎的查询专用手工标量代码，并且 VIP 没有运行时按查询编译开销。

第 2 节介绍相关工作，第 3 节说明 VIP 引擎设计，第 4 节给出实验评测，第 5 节讨论未来工作，第 6 节总结全文。

## 2. 相关工作

块式执行（block-at-a-time）[^2] [5] 和查询专用代码生成/编译 [13, 20, 31] 是分析型查询引擎的主流设计。二者都能消除解释开销；后者还通过融合流水线算子减少中间结果物化，但需要承担运行时编译成本。块式执行可以用预取缓解缓存未命中 [30]。若执行已经受内存带宽限制，基础 SIMD 向量化收益也会下降 [18]。

SIMD 向量化通常用于孤立数据库算子，输入形式多为 key-rid 对。已有大量连接实现 [2–4, 19, 45]，其中包括面向众核平台的实现 [6, 17]；排序等独立算子的 SIMD 实现也很常见 [7, 14, 36, 43]。扫描 [21, 50] 和压缩 [22, 25, 26, 38, 49] 等线性访问算子具有数据并行性，更容易向量化；哈希表和分区等非线性访问算子则需要更高级的 SIMD 技术 [34, 37]。商业系统没有采用完全向量化实现，主要困难在于同时有效支持多列、多数据类型和复杂谓词。

最近提出的向量代数 Voodoo [33] 是同时面向 SIMD CPU 和 SIMT GPU、最具原则性的方案；但其中的非线性访问算子仍是围绕 SIMD primitive 的基础循环，例如连接使用 SIMD gather 从缓存外解引用 rid。简单地使用 SIMD load/gather 或依赖编译器自动向量化，只能得到有限收益 [18]，无法与 VIP 的复杂实现相比。

[^1]: VIP 之名取自 Vectorization、Interpretation 和 Partitioning，并且主要以这三者为基础。
[^2]: 相关工作曾把 block-at-a-time 称为 vectorized；本文所说的“向量化”专指 SIMD 向量化的设计与实现。

## 3. 设计与实现

VIP 使用列式执行 [27, 47]，但不会一次处理整列。相反，它一次处理下一个元组块中的一个列，让中间结果留在缓存中，从而摊销解释成本 [5]。它不是在元组块上使用 Volcano 模型，而是扩展 column-at-a-time 模型 [27]。实验中，由于平台的 NUMA 影响，本文在线程之间静态分配工作单元；VIP 也可扩展为动态分配 [24]。

VIP 的算子由列式、数据并行子算子自底向上构成，并完全用 SIMD 实现。执行查询时，每个算子调用预编译子算子；每个子算子在一个元组块上一次处理一个列。块大小被选择为既能摊销解释成本，又让工作集留在 CPU 私有高速缓存中。子算子在一个特定数据类型的列上执行基本操作，因此可以做极端手工优化。

一个复合键哈希连接可以说明子算子如何跨列工作。为了计算复合键哈希，VIP 先根据第一列的数据类型调用哈希子算子，并把哈希值留在缓存中；然后对第二列调用哈希子算子并更新哈希值。如果块足够小，哈希数组会保持在缓存里。原文给出了对 32 位整数列执行 FNV 哈希 [11] 的 AVX-512 子算子。每个数据类型都需要对应实现，例如 `hash_T(T* data, uint32_t* hash, size_t tuples)`。

**代码清单：32 位整数列的 FNV 哈希子算子 `hash_int32`。**

```cpp
void hash_int32(int32_t* data, uint32_t* hash, size_t tuples) {
  const __m512i m_255 = _mm512_set1_epi32(255);  // mask to isolate lower byte
  const __m512i m_fnv = _mm512_set1_epi32(16777619);  // FNV prime constant
  for (size_t i = 0; i != tuples; i += 16) {  // 16 SIMD lanes
    __m512i h = _mm512_load_epi32(&hash[i]);  // load hash values from cache
    __m512i d = _mm512_load_epi32(&data[i]);  // load data values from column
    for (size_t j = 0; j != 4; ++j) {  // FNV hash processes 1 byte at a time
      h = _mm512_ternarylogic_epi32(h, d, m_255, 120);  // xor byte with hash
      h = _mm512_mullo_epi32(h, m_fnv);  // multiply hash with the FNV prime
      d = _mm512_srli_epi32(d, 8); }  // shift right to process the next byte
    _mm512_store_epi32(&hash[i], h); }  // store back the updated hash values
  [...] }  // process the last (up to 15) values using scalar code
```

### 3.1 选择扫描

![图 1：selection scan 示例（未使用短路求值）。](assets/figure-01-selection-scan-example.png)

现代分析型数据库在选择上更偏向线性扫描而非索引 [39, 40]。代码生成引擎也倾向于对扫描和解压使用预编译 SIMD 代码 [22]。在原始 column-at-a-time 模型 [27] 中，每个谓词产生一个表示合格元组的 rid 列表（数组），合取和析取通过 rid 列表的交或并计算。VIP 使用 bitmap 保存谓词之间的中间结果，类似商业系统的做法 [39]。

在线性扫描中，性能由访问的缓存行数量决定。SIMD 可以非常高效地在 W 个连续值上处理谓词，因此 VIP 以 W 个元组为单位求值或跳过。原文给出 32 位整数比较谓词的子算子：输入 bitmap 表示哪些元组可以跳过、哪些仍需判断，输出 bitmap 表示求值结果；输出 bitmap 不必严格是输入 bitmap 的子集。复杂谓词表达式表示为树，VIP 在同一个元组块上遍历该树，一次处理一个谓词。

**代码清单：32 位整数列比较谓词子算子 `select_int32`。**

```cpp
void select_int32(const int32_t* data, size_t tuples,  // the input column
    const uint16_t* bitmap_in,  // bitmap denoting the yet undetermined tuples
    uint16_t* bitmap_out,  // bitmap denoting a superset of qualifying tuples
    int32_t constant, int op) {  // the comparison constant and the operator
  const __m512i m_con = _mm512_set1_epi32(constant);  // mask
  switch (op) {  // separate code per comparison operator
  case '>':  // code for the ">" operator (can be split as separate function)
    for (i = 0; i != tuples; i += 256) {  // scan over data column and bitmap
      __m256i bit = _mm256_load_si256(bitmap_in);  // load 256 bitmap bits
      if (!_mm256_testz_si256(b, b)) {  // skip 256 tuples if all bits are 0
        __m512i bit_E = _mm512_cvtepu16_epi32(bit);
        // find groups of 16 tuples (out of 256 tuples) that are not all 0
        uint64_t m = _mm512_test_epi32_mask(bit_E, bit_E);
        do {  // evaluate groups of 16 tuples at a time that are not all 0
          size_t j = _tzcnt_u64(m);  // load 16 values from the 32-bit column
          __m512i key = _mm512_load_epi32(&data[j << 4]));
          // evaluate the selective predicate (in this example greater than)
          bitmap_out[j] = _mm512_cmpgt_epi32_mask(key, m_con);
        } while (m = _blsr_u64(m)); }  // process the next 16 tuples
      bitmap_in += 16, bitmap_out += 16, data += 256; }
    break; [...] }}  // other comparison operators, e.g., "=", "<", etc.
```

原文可见片段没有声明 `i`，并写成 `_mm256_testz_si256(b, b)`，而前一行变量名是 `bit`；`_mm512_load_epi32(&data[j << 4]))` 还多出一个右括号。以上均按原文保留。

对复杂谓词而言，最简单做法是对所有列、所有谓词全部求值，再合并 bitmap。但在某些情况下，短路谓词可以快几个数量级。因此 VIP 用前面谓词的输出跳过后续谓词的求值，同时也跳过列加载。在合取节点中，输入 bitmap 表示已经满足所有前序兄弟谓词的元组；其他元组可以跳过。在析取节点中，输入 bitmap 表示此前所有谓词都失败的元组。图 1 的示例给出了不跳过任何元组时，每个谓词对应的输入 bitmap。对于空值，系统可以使用单独的 null bitmap 并将其与其他谓词合并，也可以为每种类型保留一个特殊值，并把空值判断作为附加谓词求值。

扫描输出是排序的 rid 列表（数组），用于访问列值。若采用 late materialization，系统只追加 rid。物化策略属于查询优化问题，取决于选择率、基数、列数量、数据类型等工作负载因素，以及内存带宽等硬件因素 [1]。VIP 的设计与具体物化策略正交，可以支持多种策略。

### 3.2 压缩

现代分析型数据库会直接在压缩列上求值选择谓词 [39]。字典编码为每列维护排序后的不同值字典，并用字典索引替换列值；若有 `n` 个不同值，每个索引需要 $\lceil\log n\rceil$ 位。字典索引有多种位存储方式 [38]，VIP 在此使用 horizontal bit packing [49]。在这种方案下仍可短路，但由于压缩数据布局可能没有对齐，不一定总能跳过完整缓存行。

原文展示了一个子算子：它解包字典索引的位，并在不解引用字典的情况下直接求值谓词。对每 16 个 32 位索引，只需 5 条 SIMD 指令和 2 个预计算 permutation mask 即可完成解包。谓词在 SIMD 寄存器中直接求值。

**代码清单：压缩 32 位整数列的谓词子算子 `select_int32_compressed`。**

```cpp
void select_int32_compressed(const void* data_in, [...] size_t dict_bits) {
  [...]  // showing only the innermost loop for the ">" predicate on 16 tuples
  size_t j = _tzcnt_u64(m);  // compute the offset of 16 tuples out of 256
  __m512i x = _mm512_loadu_si512(data + dict_bits * 2 * j);  // load compressed
  // isolate the lower and upper 32-bit word per compressed index
  __m512i x1 = _mm512_permutevar_epi32(m_per_1, x);
  __m512i x2 = _mm512_permutevar_epi32(m_per_2, x);
  x1 = _mm512_srlv_epi32(x1, m_srl);  // align the lower 32-bit word
  x2 = _mm512_sllv_epi32(x2, m_sll);  // align the upper 32-bit word
  // merge the aligned lower and upper 32-bit word, and clear high-order bits
  x = _mm512_ternarylogic_epi32(x1, x2, m_max, 168);
  bitmap_out[j] = _mm512_cmpgt_epi32_mask(x, m_con); [...] }  // the predicate
```

原文形参名为 `data_in`，可见函数体却使用未在片段中声明的 `data`；其余依赖量可能位于开头的 `[...]` 中，以上按原文保留。

对包含大量不同值的列，解引用大型字典可能和一次哈希连接一样昂贵。因此，压缩应在不需要慢速解压时使用。使用同一字典压缩的属性可以在不解压的情况下连接。另一方面，对聚合函数中使用的唯一数值列进行压缩，会增加解压开销。

### 3.3 哈希连接

哈希连接常被作为独立算子用 key-rid 对优化。虽然这种设置下可以达到很好性能，但结果可能误导，主要因为它忽略 late materialization 成本 [45]。此外，若连接涉及复合键，或连接键不一定是 32 位整数，许多优化要么不再适用，要么效率大幅降低；现实实现还必须支持多种数据类型、复合键和附加的非等值谓词。

VIP 的哈希连接流程如下。首先，对出现在等值谓词中的各列计算哈希；然后以哈希值而不是实际列执行哈希连接，从而把包括复合键在内的任意数据类型映射为整数。哈希连接产生指向两侧输入中已连接元组的 rid 列表，再用这些 rid 访问实际列并求值全部连接谓词（包括非等值谓词），写回合格元组的 rid。最后，可以把合格 rid 作为连接输出供之后解引用，也可以像选择扫描的 payload 那样立即物化 payload 列。

当同一条 scatter 指令的多个 SIMD lane 写入同一内存位置时会发生冲突。VIP 使用特殊 SIMD 指令在寄存器内执行全对全比较来检测冲突；若没有这些指令，这一步需要 $O(W^2)$ 次标量比较或 $O(W)$ 次 SIMD 比较。也可用 gather 和 scatter 检测冲突 [34]，但会增加缓存访问次数。

构建哈希表时，VIP 使用连接键列的哈希值，桶位置由哈希值掩码得到，不重新哈希。哈希表桶保存 `hash` 和 `rid`。构建子算子每轮最多处理 16 个哈希值，使用 SIMD lane 装载新值、计算桶位置、gather 现有桶、检查空桶、检测 lane 冲突，再把 key-rid 对 scatter 到表中。

**代码清单：用连接键哈希值构建哈希表的 `build_hashes` 子算子。**

```cpp
typedef struct { uint32_t hash; int32_t rid; } join_bucket_t;
void build_hashes(const uint32_t* hashes, size_t tuples,  // the hash values
    join_bucket_t* hash_table, size_t buckets) {  // the hash table
  const __m512i m_inc = _mm512_set_epi32(15,14,[...],0); [...]  // constants
  // scalar and SIMD registers holding the overall state of the function
  __m512i key, rid, loc; size_t i = 0, j = 16; __mmask16 k = 0xFFFF;
  while (i + j <= tuples) {  // process (up to) 16 hash values per iteration
    // replace finished SIMD lanes with new hash values from the input column
    key = _mm512_mask_expandloadu_epi32(key, k, &hashes[i]);
    __m512i inc = _mm512_add_epi32(m_inc, _mm512_set1_epi32(i)); i += j;
    rid = _mm512_mask_expand_epi32(rid, k, inc);  // generate inner rids
    loc = [...];  // compute the bucket location and gather hash table rids
    __m512i rid_H = _mm512_i32gather_epi32(loc, &hash_table[0].rid, 8);
    k = _mm512_cmplt_epi32_mask(rid_H, m_0);  // find empty hash table buckets
    __m512i con = _mm512_conflict_epi32(loc);  // detect conflicting lanes
    k = _mm512_mask_testn_epi32_mask(k, con, con);
    j = _mm_popcnt_u64(k);  // count lanes that can be reused
    // pack 32-bit keys and rids to 64-bit pairs and scatter to hash table
    __m512i buc_L = _mm512_permutex2var_epi32(key, m_pak_1, rid);
    __m512i buc_H = _mm512_permutex2var_epi32(key, m_pak_2, rid);
    _mm512_mask_i32loscatter_epi64(hash_table, k, loc, buc_L, 8);
    loc = _mm512_alignr_epi32(loc, loc, 8);
    _mm512_mask_i32loscatter_epi64(hash_table, k >> 8, loc, buc_H, 8); }
  [...] }  // build the last (15 or less) hash values using scalar code
```

探测时，VIP 也每轮处理多个哈希值，使用 SIMD lane 重用机制处理未完成探测。它不能在一般连接中使用不允许重复键的 cuckoo hashing [32]，因为即使外键连接中内侧键唯一，不同内侧键仍可能映射到此处用作哈希表键的同一哈希值。某些情形可通过选择合适哈希函数保证无冲突，例如输入列总宽度不超过 3 字节时，32 位 FNV 哈希值不会冲突。

**代码清单：探测哈希表的 `probe_hashes` 子算子。**

```cpp
size_t probe_hashes(const uint32_t* hashes, size_t tuples,  // the hash values
    const join_bucket_t* hash_table, size_t buckets,  // the hash table
    int32_t* inner_rids, int32_t* outer_rids) {  // inner and outer side rids
  [...] while (i + j <= tuples) {  // process (up to) 16 tuples per iteration
    // load new keys (hash values) from input while also reusing SIMD lanes
    key = _mm512_mask_expandloadu_epi32(key, k, &hashes[i]);
    __m512i inc = _mm512_add_epi32(m_inc, _mm512_set1_epi32(i)); i += j;
    rid = _mm512_mask_expand_epi32(rid, k, inc);  // generate outer rids
    loc = [...];  // gather hash table buckets of packed key-rid pairs
    __m512i buc_L = _mm512_i32logather_epi64(loc, hash_table, 8);
    loc = _mm512_alignr_epi32(loc, loc, 8);
    __m512i buc_H = _mm512_i32logather_epi64(loc, hash_table, 8);
    // unpack key-rid pairs to keys and (implicitly generated) rids
    __m512i key_H = _mm512_permutex2var_epi32(buc_L, m_unp_1, buc_H);
    __m512i rid_H = _mm512_permutex2var_epi32(buc_L, m_unp_2, buc_H);
    k = _mm512_cmpeq_epi32_mask(key, key_H);  // compare the keys
    _mm512_mask_compressstoreu_epi32(&outer_rids[o], k, rid);
    _mm512_mask_compressstoreu_epi32(&inner_rids[o], k, rid_H);
    o += _mm_popcnt_u64(k);  // append inner & outer rids
    k = _mm512_cmplt_epi32_mask(rid_H, m_0);  // detect empty bucket lanes
    j = _mm_popcnt_u64(k); }  // count empty bucket lanes to be replaced
  [...]  // process the last (15 or less) tuples using scalar code
  return o; }  // return the total number of matching tuples
```

在宁愿探测较慢缓存、也不愿分区事实表的情形 [30]，VIP 还可支持预取：此时使用标量代码和原子操作构建共享哈希表，构建成本无关紧要。在另一些更适合用分区哈希连接避免缓存未命中的情形 [29]，每个线程持有私有哈希表，无需原子操作。

哈希探测后，VIP 用 rid 列表解引用各列并求值谓词。由于连接会持续分区到内侧表放入缓存，且哈希分区函数不同于连接使用的哈希函数，因此哈希冲突很少。若连接谓词是合取式，子算子逐个求值谓词并过滤 rid 列表；其中通过重新求值等值谓词来消解哈希冲突。求值完全部连接谓词后，系统可以物化 rid，也可以物化一组 payload。

### 3.4 分区

分区可用于哈希连接和分组聚合，以避免缓存未命中。VIP 连续存储分区输出，因此先计算 histogram：从 key 列加载并哈希下一块元组，根据分区数把哈希转换为 partition id，再递增计数器。为了避免 SIMD scatter 冲突，histogram 针对 $W$ 个 SIMD lane 复制 $W$ 份 [34]。

**代码清单：更新分区 histogram 的 `histogram` 子算子。**

```cpp
void histogram(const uint32_t* hashes, int32_t* histogram_x16,
    uint8_t* pids, int bit_lo, int bit_hi) {  // bit range
  const __m512i m_1 = _mm512_set1_epi32(1); [...]
  for (size_t i = 0; i != tuples; i += 16) {  // 16 SIMD lanes
    __m512i p = _mm512_load_epi32(&hashes[i]);  // load hash values
    p = _mm512_srl_epi32(p, m_srl);  // get partition id from hash value
    p = _mm512_sll_epi32(p, m_sll);
    _mm_stream_si128(&pids[i], _mm512_cvtepi32_epi8(p));
    __m512i o = _mm512_add_epi32(p, m_rep);  // get offsets
    __m512i c = _mm512_i32gather_epi32(off, histogram_x16, 4);
    c = _mm512_add_epi32(c, m_1);  // increment the histogram counters
    _mm512_i32scatter_epi32(histogram_x16, o, c, 4); } [...] }
```

原文可见函数形参没有 `tuples`，函数体却使用它；gather 使用 `off`，而相邻可见变量是 `o`。以上按原文保留。

为了预计算分区输出边界，系统先跨线程计算 histogram 的 prefix sum [43]，再用下面的子算子计算每个元组的输出偏移并把它留在缓存中。后续逐列 shuffle payload 时可复用这些偏移，避免重复计算。

**代码清单：计算每个元组输出偏移的 `shuffle_core` 子算子。**

```cpp
void shuffle_core(const uint8_t* pids, size_t tuples,  // partition ids
    int32_t* partition_offset,  // the latest the output offset per partition
    int8_t* conflict_offset,  // compute the serialization offset per tuple
    int32_t* output_offset) { [...]  // compute the output offset per tuple
  for (size_t i = 0; i != tuples; i += 16) {  // 16 SIMD lanes
    // load partition ids and gather the output offset per partition
    __m512i p = _mm512_cvtepu8_epi32(_mm_load_si128(&pids[i]));
    __m512i o = _mm512_i32gather_epi32(p, partition_offset, 4);
    __m512i s = [...];  // serialize conflicts (9 instructions)
    _mm_store_si128(&conflict_offset[i],_mm512_cvtepi32_epi8(s));
    o = _mm512_add_epi32(o, s);  // update and store the offsets per tuple
    _mm512_store_epi32(&output_offset[i], off);  // output offset per tuple
    o = _mm512_add_epi32(o, m_1);  // update the per-partition output offsets
    _mm512_i32scatter_epi32(partition_offset, p, o, 4); } [...] }
```

原文在 store 行使用 `off`，而相邻可见向量变量是 `o`；以上按原文保留。

除了输出偏移，VIP 还保存用于串行化 scatter 冲突的偏移 [34]。若 SIMD lane $i$ 和 $j$ 指向同一分区 $p$， $i$ 的偏移为 $o$， $j$ 的偏移则通过加上自身为 1 的串行化偏移变为 $o+1$。系统用 conflict-detection SIMD 指令生成 lane 间全对全冲突 bitmap，再逐 lane 统计置位数。

计算偏移后，VIP 对下一块元组一次 shuffle 一个列，并从缓存重新加载输出偏移和串行化偏移。直接 scatter 到输出会造成过多 cache conflict [43]，因此先写入 cache-resident buffer；某个分区的 buffer 填满后，再用 non-temporal store 批量 flush，以免污染缓存 [34, 36, 48]。每个分区的 buffer 为两条 cache line：下半区填满后写出，并把上半区的数据移到下半区。

填满每个分区 buffer 所需的值数取决于列的数据类型；子算子按数据类型特化，因此该逻辑是硬编码的。有时即使数据类型相同也会继续特化：长字符串每轮以一个元组为单位横向 shuffle，使用连续 SIMD load/store；短字符串则用 gather/scatter 纵向 shuffle。下面给出 32 位整数列的实现。

**代码清单：32 位整数列的 `shuffle_int32` 子算子。**

```cpp
void shuffle_int32(const uint8_t* pids, size_t tuples,
    const int8_t* conflict_offsets, const int32_t* output_offsets,
    const int32_t* in, int32_t* buf, int32_t* out) { [...]
  for (size_t i = 0; i != tuples; i += 16) {  // 16 SIMD lanes
    __m512i o = _mm512_load_epi32(&output_offsets[i]);
    __m512i s = _mm512_cvtepu8_epi32(_mm_load_si128(&conflict_offsets[i]));
    o = _mm512_sub_epi32(o, s);  // remove serialization offset
    o = _mm512_and_epi32(o, m_15);  // determine buffer slot
    o = _mm512_add_epi32(o, s);  // add serialization offset
    __mmask16 k = _mm512_cmpeq_epi32_mask(o, m_15);  // partitions to flush
    __m512i p = _mm512_cvtepu8_epi32(_mm_load_si128(&pids[i]));
    o = _mm512_or_epi32(o, _mm512_slli_epi32(p, 5));  // offset in buffers
    __m512i v = _mm512_stream_load_si512(&in[i]);  // load data from column
    _mm512_i32scatter_epi32(buf, o, v, 4);  // store column data to buffers
    if (_mm512_kortestz(k, k)) continue;  // skip if no buffers are full
    uint64_t m = k;  // bitmask of lanes with full buffers to be flushed
    do {  // flush one full buffer at a time to memory using streaming stores
      size_t j = i + _tzcnt_u64(m);  // tuple location in input column
      size_t o = output_offsets[j];  // tuple location in partitioned output
      int32_t* b = &buf[pids[j] << 5];  // pick buffer to flush
      __m512i x1 = _mm512_load_si512(b);  // load buffer data
      __m512i x2 = _mm512_load_si512(b + 16);
      _mm512_stream_si512(&out[o - 15], x1);  // flush lower half of buffer
      _mm512_store_si512(b, x2);  // overwrite lower half with upper half
    } while (m = _blsr_u64(m)); }  // get next set bit of mask
  [...] }  // process the last (up to 15) tuples in scalar code
```

在分区哈希连接中，每个线程负责分区一部分输入。若所需分区数超过保证缓存感知执行的 fanout，系统像 LSB radix sort 一样分多趟完成 [43]。一旦分区数超过线程数，便以类似 NUMA shuffle 的方式在线程间 shuffle 数据 [36]；随后可继续分区，直到内侧表的各分区能够放入缓存。最后，每个线程对本地分区执行最终哈希连接。

若要确定 $2^k$ 个分区中分区 $p$ 的边界，系统不显式保存 histogram，而是对连接键列进行二分搜索：现场重新计算哈希值、以 $2^k-1$ 做掩码，分别查找哈希 $p$ 和 $p+1$ 的第一次出现位置。

### 3.5 分组聚合

VIP 的 group-by aggregation 分为多步：（i）估算 group 数；（ii）为缓存感知执行对输入分区；（iii）确定每个元组的 group id（gid）；（iv）计算中间表达式；（v）用 gid 更新部分聚合。连接以较小输入的大小决定分区数，而 group-by 需要估算 group 数。VIP 使用 PCSA 算法 [10] 估算 group 数，该算法可拆成完全向量化的 VIP 子算子；其核心操作是 `b |= h & -h`，其中 `b` 是 PCSA bitmap，`h` 是哈希值。

系统据此决定实现 cache-resident execution 所需的分区数。若不分区，每个线程处理本地元组，结束时同步合并部分聚合；若分区，则生成多于线程数的分区，再把每个分区交给 NUMA 距离最近的线程处理。

可选分区完成后，主 group-by 算子的第一步是把 group-by key 的哈希值映射到 gid。哈希表保存 `(hash, gid)` 对；每个 group 起初由唯一哈希值标识。VIP 逐列计算每个输入元组的 group-by hash，并在 cuckoo table 的两个候选桶中查找匹配；若没有匹配，就创建 group、分配下一个隐式 gid，并保存当前元组的 rid。

![图 2：将 hash 映射到 group id 的示例。](assets/figure-02-hash-to-gids.png)

下面的子算子使用 group-by 列的 hash 生成 gid。为降低代码复杂度，原文省略了向表中插入新 group 的部分。由于 cuckoo hash table 的插入本身可能失败 [32]，也可能低估 group 数，系统设置阈值；达到阈值后会扩容并从头重建 hash table。

**代码清单：把 group-by hash 映射为 gid 的 `hashes_to_gids` 子算子。**

```cpp
typedef struct { uint32_t hash; int32_t gid; } aggr_bucket_t;
size_t hashes_to_gids(const uint32_t* hashes, int32_t* gids, size_t tuples,
    size_t groups, int32_t* rids, aggr_bucket_t* hash_table, int log_buckets) {
  const __m512i m_inc = _mm512_set_epi32(15,[...],1,0); [...]  // constants
  __m512i key, gid, loc; __mmask16 k = 0xFFFF;  // initially use all lanes
  size_t i = 0, j = 16, g = 0, k = [...];  // hash table rebuild threshold
  while ((i = i + j) <= tuples) {  // 16 SIMD lanes
    if (--k == 0) { [...] }  // resize and rebuild the entire hash table
    key = _mm512_mask_loadu_epi32(key, k, &hashes[i - 16]);  // load hashes
    // compare the hash values across all lanes using conflict detection
    __m512i con = _mm512_conflict_epi32(key);
    __mmask16 k1 = _mm512_testn_epi32_mask(con, con);
    __m512i loc_1 = [...], loc_2 = [...];  // compute hash bucket locations
    // use alternative hash function for displaced tuples as per cuckoo hashing
    loc = _mm512_ternarylogic_epi32(loc, loc_1, loc_2, 150);
    loc = _mm512_mask_mov_epi32(loc, k1, loc_1);  // 1st hash bucket location
    // gather 16 hash buckets for lanes with unique hash
    __m512i buc_L, buc_H;  // load buckets from hash table
    buc_L = _mm512_mask_i32gather_epi64(buc_L, k3, hash_table, loc_1, 8);
    loc_1 = _mm512_alignr_epi32(loc_1, loc_1, 8);
    buc_H = _mm512_mask_i32gather_epi64(buc_H, k3 >> 8, hash_table, loc_1, 8);
    [...]  // unpack buckets to hashes (key_H) and gids (gid_H)
    // determine the lanes that need to gather the 2nd cuckoo hash bucket
    k2 = _mm512_mask_cmpge_epi32_mask(k1, gid_H, m_0);
    k2 = _mm512_mask_cmpneq_epi32_mask(k2, key, key_H);
    k2 = _mm512_kand(k2, k);  // 2nd hash bucket location
    loc = _mm512_mask_mov_epi32(loc, k2, loc_2);
    buc_L = _mm512_mask_i32logather_epi64(buc_L, k3, loc, hash_table, 8);
    loc = _mm512_alignr_epi32(loc, loc, 8);
    buc_H = _mm512_mask_i32logather_epi64(buc_H, k3 >> 8, loc, hash_table, 8);
    [...]  // re-unpack to hashes (key_H) and gids (gid_H)
    // find the leftmost lane with the same hash value in the SIMD register
    con = _mm512_and_epi32(con, _mm512_sub_epi32(m_0, con));
    con = _mm512_sub_epi32(m_31, _mm512_lzcnt_epi32(con));
    con = _mm512_mask_blend_epi32(k2, con, m_inc);
    // determine lanes with hashes that need to be scattered to the hash table
    k3 = _mm512_cmpge_epi32_mask(gid_H, m_0)
    k = _mm512_mask_cmpneq_epi32_mask(k3, key, key_H);
    k = _mm512_kor(_mm512_kand(k, k2), _mm512_kandn(k3, k2));
    if (!_mm512_kortestz(k, k)) {  // check if there are no new groups
      // copy gid from lestmost lane with same hash and store gids in order
      _mm512_storeu_epi32(&gids[i - 16], _mm512_permutevar_epi32(con, gid_H));
      j = 16, k = _mm512_kxnor(k, k);  // reuse all lanes
    } else { [...] }}  // create new gids, append rids, and update hash table
  [...] return g; }  // process the last tuples and return the number of groups
```

原文可见片段在同一作用域先声明 `__mmask16 k`，随后又声明 `size_t ... k = [...]`；`k3 = _mm512_cmpge_epi32_mask(...)` 行没有分号，注释还写成 `lestmost`。`loc`、`k2`、`k3`、`key_H` 和 `gid_H` 等依赖可能位于 `[...]` 中，以上均按原文保留。

与 join 不同，这里显式使用 cuckoo hashing，以输入顺序探测 hash 并映射到 gid [34]。唯一 hash 到 gid 的映射仍可能因 hash collision 而错误，即使分区后碰撞已很少。连接通过重新求值包括等值条件在内的谓词解决碰撞；聚合则用每组第一个元组的 rid 解引用 group-by 列，验证同组列值是否一致。系统对每个 payload 列扫描一次，把最新列值与该组首元组的列值比较；若不匹配，就沿着表示同一 hash 下不同 group 的 gid-rid 对链表继续比较。找到匹配便改写当前元组的 gid，否则向同 hash 的 group 列表追加新的 gid-rid 对。

![图 3：解决 group-by hash 冲突的示例。](assets/figure-03-resolve-collisions.png)

VIP 使用类型专用子算子解决 group-by 列的 hash collision：顺序加载 group-by 列和 gid，用 gid gather 每组第一个元组的 rid，再用 rid gather 定义该组的列值；不匹配时分支到标量代码创建新 group。

处理聚合函数时，gid 直接作为映射索引。多列函数以 block-at-a-time 方式计算；例如 `sum(x*y)` 先为下一块元组计算 `x*y`，保存中间结果，再更新部分和。为了避免冲突，commutative aggregate 的数组像分区 histogram 一样复制。下面的子算子计算整数列的 `min()`；若只有一个 group 或没有 group-by，则直接在寄存器中更新聚合值。

**代码清单：更新复制的部分最小值的 `update_min_int32` 子算子。**

```cpp
void update_min_int32(const int32_t* data, const int32_t* gids,
    size_t tuples, float* min_x16, size_t groups) {
  const __m512i m_inc = _mm512_set_epi32(15,14,[...],1,0);
  for (size_t i = 0; i != tuples; i += 16) {  // 16 SIMD lanes
    __m512i val = _mm512_load_si512(&data[i]);  // load data from column
    __m512i gid = _mm512_loadu_si512(&gids[i]);  // load gids from cache
    // compute the offset of (replicated) partial aggregates from the gid
    __m512i loc = _mm512_or_epi32(_mm512_slli_epi32(gid, 4), m_inc);
    __m512i min = _mm512_i32gather_epi32(loc, min_x16, 4);  // load the min
    __mmask16 k = _mm512_cmplt_epi32_mask(val, min);  // store back if smaller
    _mm512_mask_i32scatter_epi32(min_x16, k, loc, val, 4); }}
```

原文把 `min_x16` 声明为 `float*`，却用 `epi32` gather/scatter 作为 32 位整数聚合值；`groups` 在可见片段中也未使用。以上按原文保留。

如果输入已分区，每个线程处理不同分区，并在处理完该分区所有元组前把 hash 到 gid 的哈希表、每组 rid 和部分聚合保持在缓存中，然后在本地合并部分聚合。如果输入未分区，每个线程按块处理元组，并把部分聚合保持在缓存中；随后使用专用哈希表跨线程链接部分聚合，最后分发并合并这些部分聚合。

## 4. 实验评测

实验平台是 Intel Xeon Phi 7210 Knights Landing CPU。这是一代依赖高级 AVX-512 SIMD 指令提升每核心性能的众核 CPU，相比主流 CPU 可在芯片上放入更多较小核心。该 CPU 有 64 个 1.3 GHz 核心和 4 路 SMT。16 GB 高带宽片上 MCDRAM 的 load、store、copy 带宽分别为 295、220、170 GB/s；192 GB DDR4 DRAM 的对应带宽分别为 70、41、34 GB/s。实验在 Linux 3.10 上使用 ICC 18 和 `-O3` 编译。

所有实验都把 VIP 与查询专用、手工优化的标量代码比较，后者模拟最新代码生成查询引擎。基线通过一次流水线处理一个元组、且不发生函数调用来实现寄存器驻留执行 [31]。这个标量、寄存器驻留、row-at-a-time 模型与 VIP 的 SIMD、解释式、block-at-a-time 模型形成鲜明对比。实验忽略基线的编译时间，这有利于基线，因为 VIP 不在运行时编译代码。

### 4.1 TPC-H Q19 的复杂选择

![图 4：TPC-H Q19 对 part 表执行选择时的谓词表达式求值树（选择率 0.24%）。](assets/figure-04-q19-predicate-tree.png)

![图 5：TPC-H Q19 part 表选择吞吐。](assets/figure-05-q19-selection.png)

我们选择 TPC-H 中谓词组合最复杂的选择：Q19 中对 `part` 表的选择。表达式树按选择率排列，既不是 CNF 也不是 DNF。`p_brand` 和 `p_container` 是 `char(10)`，分别有 25 和 40 个不同值；`p_size` 是 32 位整数，有 50 个不同值。压缩后，这三列分别只需 5、6、5 位，每个元组 footprint 从 24 字节降到 2 字节。payload 列是 `p_partkey`，只为通过选择的 0.24% 元组访问。

实验改变数据集的规模因子（SF）；在 SF=10000 时，未压缩数据超过 MCDRAM（HBW）容量。VIP 在压缩和未压缩数据上都超过基线，速度提升 2.1 到 4.5 倍，其中在 MCDRAM 上扫描未压缩数据的加速最高。复杂谓词数量突出显示了 VIP 设计的效率：它用缓存中的 bitmap 处理复杂表达式，而不依赖查询专用编译。由于 Q19 中多数谓词选择率较高，无论是否处理压缩数据，短路求值对性能都至关重要。

### 4.2 TPC-H 核心表哈希连接

![图 6：TPC-H 最大表上的 hash join 吞吐。](assets/figure-06-hash-joins.png)

我们评测 TPC-H 核心表连接；这些连接位于大多数含连接的 TPC-H 查询的核心，其 payload 是继续与较小维度表连接所用的外键。在 DRAM（LBW）上，相比 MCDRAM（HBW），实验使用更少的分区趟数和更大的 fanout：

```sql
select l_partkey, l_suppkey, o_custkey
from lineitem, orders
where l_orderkey = o_orderkey;

select l_orderkey, l_partkey, l_suppkey
from lineitem, partsupp
where l_partkey = ps_partkey
  and l_suppkey = ps_suppkey;
```

基线使用查询专用哈希桶布局物化 payload，并在内侧键唯一时遇到第一个匹配就停止探测。VIP 支持持续分区，直到内侧表能放入缓存，并按元组块执行哈希连接以保持缓存驻留。在快速内存（HBW）上，VIP 对 `lineitem` 与 `orders` 的连接快 1.8 到 2 倍，对 `lineitem` 与 `partsupp` 的连接快 1.6 到 1.7 倍。复合键连接加速较小，因为 VIP 的设计会在用哈希值连接后，通过 rid 分别验证复合键的每一列。在慢速内存（LBW）上，两种方法相当：分区方法因多趟访问而受内存带宽限制，基线则受缓存未命中限制。SF=100 时，哈希表略大于 L2 cache 并引发大量 cache conflict，因而基线明显较慢；把哈希表大小扩大 4 倍后，能够达到图中 SF=300 所示的吞吐。

### 4.3 TPC-H Q1 的分组聚合

![图 7：TPC-H Q1 分组聚合吞吐。](assets/figure-07-q1-groupby.png)

对分组聚合，我们使用 TPC-H Q1。每列使用能容纳值域的最小数据类型。基线一次处理一个元组，并为每个线程更新私有哈希表。VIP 对下一个元组块一次计算一个表达式。传统 column-at-a-time 执行 [27] 会在每个列上的每个算子之后物化中间结果，而 VIP 的各算子从不把中间结果物化到缓存外。VIP 还能复用 Q1 聚合函数中的公共子表达式，例如：

```sql
sum(l_extendedprice * (1 - l_discount)),
sum(l_extendedprice * (1 - l_discount) * (1 + l_tax))
```

结果显示，无论内存类型如何，VIP 快 2.7 到 3.2 倍。估计 group 的过程在这里快一个数量级。我们还执行了去掉 group-by 子句的同一查询；此时两种方法都把部分聚合保存在寄存器中。VIP 为下一块元组分别计算每个表达式和聚合，基线则一次处理一个元组并同时计算其全部聚合。VIP 在两种内存上仍快 3.6 到 4.3 倍。

## 5. 未来工作

本文评测使用的众核 CPU 依赖高级 SIMD 指令实现高性能。然而，众核 CPU 和协处理器不像主流 CPU 那样普及，也未必会作为独立平台长期商业化。我们计划在最新主流 CPU 上评测 VIP，因为这些 CPU 也支持 AVX-512，并进一步研究如何让 VIP 适配主流 CPU 的新硬件特性。

## 6. 结论

本文提出 VIP，一个从预编译数据并行子算子自底向上构建、并完全用 SIMD 实现的查询引擎。VIP 设计可适应现代硬件特性，例如利用众核 CPU 的高带宽片上内存来支持缓存感知执行。

早期工作只关注排序或哈希连接等单个数据库算子的部分 SIMD 实现，并假设 key-rid 对及特定物化策略等有利输入设置；与之不同，VIP 支持全部基础数据库算子——选择、哈希连接、分组聚合——以及任意数量列、多种数据类型、压缩和复杂谓词或表达式。基于配备最新 AVX-512 SIMD 指令的最新一代众核 CPU，实验显示 VIP 超过了模拟最新代码生成查询引擎的查询专用手工优化代码，而且不计后者的运行时编译开销；VIP 中不存在这项开销。总体而言，VIP 是朝着基于高级 SIMD 向量化、并充分利用现代 CPU 所提供其他高级硬件特性的现实查询执行迈出的一步。


## 参考文献

- [1] D. Abadi, D. Myers, D. DeWitt, and S. Madden. Materialization strategies in a column-oriented DBMS. In ICDE, pages 466-475, 2007.
- [2] C. Balkesen, G. Alonso, J. Teubner, and M. T. Ozsu. Multicore, main-memory joins: Sort vs. hash revisited. PVLDB, 7(1):85-96, Sept. 2013.
- [3] C. Balkesen, J. Teubner, G. Alonso, and M. T. Ozsu. Main-memory hash joins on multi-core cpus: Tuning to the underlying hardware. In ICDE, pages 362-373, 2013.
- [4] S. Blanas, Y. Li, and J. Patel. Design and evaluation of main memory hash join algorithms for multi-core CPUs. In SIGMOD, pages 37-48, 2011.
- [5] P. A. Boncz, M. Zukowski, and N. Nes. MonetDB/X100: Hyper-pipelining query execution. In CIDR, 2005.
- [6] X. Cheng, B. He, X. Du, and C. T. Lau. A study of main-memory hash joins on many-core processor: A case with Intel Knights Landing architecture. In CIKM, pages 657-666, 2017.
- [7] J. Chhugani, A. D. Nguyen, V. W. Lee, W. Macy, M. Hagog, Y.-K. Chen, A. Baransi, S. Kumar, and P. Dubey. Efficient implementation of sorting on multi-core SIMD CPU architecture. In VLDB, pages 1313-1324, 2008.
- [8] A. Costea, A. Ionescu, B. Răducanu, M. Switakowski, C. Bârca, J. Sompolski, A. Luszczak, M. Szafrański, G. de Nijs, and P. Boncz. Vectorh: Taking SQL-on-Hadoop to the next level. In SIGMOD, pages 1105-1117, 2016.
- [9] B. Dageville, T. Cruanes, M. Zukowski, V. Antonov, A. Avanes, J. Bock, J. Claybaugh, D. Engovatov, M. Hentschel, J. Huang, A. W. Lee, A. Motivala, A. Q. Munir, S. Pelley, P. Povinec, G. Rahn, S. Triantafyllis, and P. Unterbrunner. The Snowflake elastic data warehouse. In SIGMOD, pages 215-226, 2016.
- [10] P. Flajolet and G. N. Martin. Probabilistic counting algorithms for data base applications. J. Comput. Syst. Sci., 31(2):182-209, Sept. 1985.
- [11] G. Fowler, L. C. Noll, K.-P. Vo, and D. Eastlake. The FNV non-cryptographic hash algorithm. Technical report, 2017. http://www.ietf.org/internet-drafts/draft-eastlake-fnv-13.txt.
- [12] G. Graefe. Volcano: An extensible and parallel query evaluation system. TKDE, 6(1):120-135, Feb. 1994.
- [13] A. Gupta, D. Agarwal, D. Tan, J. Kulesza, R. Pathak, S. Stefani, and V. Srinivasan. Amazon redshift and the case for simpler data warehouses. In SIGMOD, pages 1917-1923, 2015.
- [14] H. Inoue, T. Moriyama, H. Komatsu, and T. Nakatani. AA-sort: A new parallel sorting algorithm for multi-core SIMD processors. In PACT, pages 189-198, 2007.
- [15] H. Inoue, M. Ohara, and K. Taura. Faster set intersection with SIMD instructions by reducing branch mispredictions. PVLDB, 8(3):293-304, Nov. 2014.
- [16] H. Inoue and K. Taura. SIMD- and cache-friendly algorithm for sorting an array of structures. PVLDB, 8(11):1274-1285, July 2015.
- [17] S. Jha, B. He, M. Lu, X. Cheng, and H. P. Huynh. Improving main memory hash joins on Intel Xeon Phi processors: An experimental approach. PVLDB, 8(6):642-653, Feb. 2015.
- [18] T. Kersten, V. Leis, A. Kemper, T. Neumann, A. Pavlo, and P. Boncz. Everything you always wanted to know about compiled and vectorized queries but were afraid to ask. PVLDB, 11(13):2209-2222, Sept. 2018.
- [19] C. Kim, T. Kaldewey, V. W. Lee, E. Sedlar, A. D. Nguyen, N. Satish, J. Chhugani, A. Di Blas, and P. Dubey. Sort vs. hash revisited: fast join implementation on modern multi-core CPUs. PVLDB, 2(2):1378-1389, Aug. 2009.
- [20] K. Krikellas, S. Viglas, and M. Cintra. Generating code for holistic query evaluation. In ICDE, pages 613-624, 2010.
- [21] H. Lang, A. Kipf, L. Passing, P. Boncz, T. Neumann, and A. Kemper. Make the most out of your simd investments: Counter control flow divergence in compiled query pipelines. In DaMoN, 2018.
- [22] H. Lang, T. Mühlbauer, F. Funke, P. A. Boncz, T. Neumann, and A. Kemper. Data blocks: Hybrid OLTP and OLAP on compressed storage using both vectorization and compilation. In SIGMOD, pages 311-326, 2016.
- [23] H. Lang, T. Neumann, A. Kemper, and P. Boncz. Performance-optimal filtering: Bloom overtakes cuckoo at high throughput. PVLDB, 12(5):502-515, Jan. 2019.
- [24] V. Leis, P. Boncz, A. Kemper, and T. Neumann. Morsel-driven parallelism: A NUMA-aware query evaluation framework for the many-core age. In SIGMOD, pages 743-754, 2014.
- [25] Y. Li and J. M. Patel. BitWeaving: Fast scans for main memory data processing. In SIGMOD, pages 289-300, 2013.
- [26] Y. Li and J. M. Patel. WideTable: An accelerator for analytical data processing. PVLDB, 7(10):907-918, June 2014.
- [27] S. Manegold, P. Boncz, and M. Kersten. Optimizing database architecture for the new bottleneck: memory access. J. VLDB, 9(3):231-246, 2000.
- [28] S. Manegold, P. Boncz, and M. Kersten. What happens during a join? dissecting CPU and memory optimization effects. In VLDB, pages 339-350, 2000.
- [29] S. Manegold, P. Boncz, and M. Kersten. Optimizing main-memory join on modern hardware. TKDE, 14(4):709-730, July 2002.
- [30] P. Menon, T. C. Mowry, and A. Pavlo. Relaxed operator fusion for in-memory databases: Making compilation, vectorization, and prefetching work together at last. PVLDB, 11(1):1-13, Sept. 2017.
- [31] T. Neumann. Efficiently compiling efficient query plans for modern hardware. PVLDB, 4(9):539-550, June 2011.
- [32] R. Pagh and F. F. Rodler. Cuckoo hashing. J. Algorithms, 51(2):122-144, May 2004.
- [33] H. Pirk, O. Moll, M. Zaharia, and S. Madden. Voodoo - a vector algebra for portable database performance on modern hardware. PVLDB, 9(14):1707-1718, Oct. 2016.
- [34] O. Polychroniou, A. Raghavan, and K. A. Ross. Rethinking SIMD vectorization for in-memory databases. In SIGMOD, pages 1493-1508, 2015.
- [35] O. Polychroniou and K. A. Ross. High throughput heavy hitter aggregation for modern simd processors. In DaMoN, 2013.
- [36] O. Polychroniou and K. A. Ross. A comprehensive study of main-memory partitioning and its application to large-scale comparison- and radix-sort. In SIGMOD, pages 755-766, 2014.
- [37] O. Polychroniou and K. A. Ross. Vectorized Bloom filters for advanced SIMD processors. In DaMoN, 2014.
- [38] O. Polychroniou and K. A. Ross. Efficient lightweight compression alongside fast scans. In DaMoN, 2015.
- [39] V. Raman, G. Attaluri, R. Barber, N. Chainani, D. Kalmuk, V. KulandaiSamy, J. Leenstra, S. Lightstone, S. Liu, G. M. Lohman, T. Malkemus, R. Mueller, I. Pandis, B. Schiefer, D. Sharpe, R. Sidle, A. Storm, and L. Zhang. DB2 with BLU acceleration: So much more than just a column store. PVLDB, 6(11):1080-1091, Aug. 2013.
- [40] K. A. Ross. Selection conditions in main memory. TODS, 29(1):132-161, Mar. 2004.
- [41] K. A. Ross. Efficient hash probes on modern processors. In ICDE, pages 1297-1301, 2007.
- [42] P. Roy, J. Teubner, and G. Alonso. Efficient frequent item counting in multi-core hardware. In KDD, pages 1451-1459, 2012.
- [43] N. Satish, C. Kim, J. Chhugani, A. D. Nguyen, V. W. Lee, D. Kim, and P. Dubey. Fast sort on CPUs and GPUs: a case for bandwidth oblivious SIMD sort. In SIGMOD, pages 351-362, 2010.
- [44] B. Schlegel, T. Karnagel, T. Kiefer, and W. Lehner. Scalable frequent itemset mining on many-core processors. In DaMoN, 2013.
- [45] S. Schuh, X. Chen, and J. Dittrich. An experimental comparison of thirteen relational equi-joins in main memory. In SIGMOD, pages 1961-1976, 2016.
- [46] E. Sitaridi, O. Polychroniou, and K. A. Ross. SIMD-accelerated regular expression matching. In DaMoN, 2016.
- [47] M. Stonebraker, D. J. Abadi, A. Batkin, X. Chen, M. Cherniack, M. Ferreira, E. Lau, A. Lin, S. Madden, E. O'Neil, P. O'Neil, A. Rasin, N. Tran, and S. Zdonik. C-store: a column-oriented DBMS. In VLDB, pages 553-564, 2005.
- [48] J. Wassenberg and P. Sanders. Engineering a multi core radix sort. In EuroPar, pages 160-169, 2011.
- [49] T. Willhalm, N. Popovici, Y. Boshmaf, H. Plattner, A. Zeier, and J. Schaffner. SIMD-scan: ultra fast in-memory table scan using on-chip vector processing units. PVLDB, 2(1):385-394, Aug. 2009.
- [50] J. Zhou and K. A. Ross. Implementing database operations using SIMD instructions. In SIGMOD, pages 145-156, 2002.
