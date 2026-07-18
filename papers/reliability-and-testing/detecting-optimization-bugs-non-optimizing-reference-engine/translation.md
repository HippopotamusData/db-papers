---
paper_id: detecting-optimization-bugs-non-optimizing-reference-engine
title: Detecting Optimization Bugs in Database Engines via Non-Optimizing Reference Engine Construction
language: zh-CN
source: source.pdf
---

# Detecting Optimization Bugs in Database Engines via Non-Optimizing Reference Engine Construction（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者

- Manuel Rigger（`manuel.rigger@inf.ethz.ch`），苏黎世联邦理工学院计算机科学系，瑞士苏黎世
- Zhendong Su（`zhendong.su@inf.ethz.ch`），苏黎世联邦理工学院计算机科学系，瑞士苏黎世

## 出版信息

arXiv:2007.08292v1 [cs.SE]，16 Jul 2020。

Manuel Rigger and Zhendong Su. 2020. “Detecting Optimization Bugs in Database Engines via Non-Optimizing Reference Engine Construction.” Proceedings of the 28th ACM Joint European Software Engineering Conference and Symposium on the Foundations of Software Engineering（ESEC/FSE ’20），November 8–13, 2020，Virtual Event, USA。ACM，New York, NY, USA，13 pages。doi:[10.1145/3368089.3409710](https://doi.org/10.1145/3368089.3409710)。

## 版权与许可

在副本不用于营利或商业优势、且首页保留本通知和完整引文的前提下，可免费为个人或课堂用途制作本文全部或部分内容的数字或纸质副本。由其他权利人拥有的组成部分版权必须受到尊重；注明出处的摘要摘录被允许。其他复制、再版、张贴到服务器或向列表再分发的行为，必须事先获得明确许可并且/或者付费。许可请求请发送至 `permissions@acm.org`。

ESEC/FSE ’20，November 8–13, 2020，Virtual Event, USA。© 2020，版权由所有者/著作权人持有；出版权许可给 ACM。ACM ISBN 978-1-4503-7043-1/20/11，定价 \$15.00。DOI：[10.1145/3368089.3409710](https://doi.org/10.1145/3368089.3409710)。

## 摘要

数据库管理系统（DBMS）无处不在。为了高效访问数据，它们会应用复杂的优化。错误的优化可能导致逻辑错误（logic bugs），使查询计算出不正确的结果集。本文提出非优化参考引擎构造（Non-Optimizing Reference Engine Construction，NoREC），一种用于检测 DBMS 优化错误的全自动方法。

概念上，该方法希望用同一 DBMS 的优化版本和非优化版本分别求值一个查询，再检测两者所返回结果集的差异；这种差异表明 DBMS 中存在错误。获得 DBMS 的非优化版本很有挑战，因为 DBMS 通常只提供有限的优化控制能力。本文的核心洞见是：一个给定的、可能随机生成的优化查询，可以改写为 DBMS 无法优化的查询。求值这个未优化查询，实际上就对应于由一个非优化参考引擎执行原查询。

我们在 PostgreSQL、MariaDB、SQLite 和 CockroachDB 四个广泛使用的 DBMS 上开展了大规模测试，发现其最新版本中 159 个此前未知的错误，其中 141 个已被开发者修复。在这些错误中，51 个是优化错误，其余是错误类和崩溃类问题。结果表明，NoREC 有效、通用且实现成本低，因而适合在实践中广泛应用。

**CCS 概念：**

- 信息系统 → 数据库查询处理
- 软件及其工程 → 软件测试与调试

**关键词：** 数据库测试、DBMS 测试、查询优化器错误、测试预言

## 1. 引言

DBMS 是许多系统的重要组成部分。为了满足不断增长的性能需求，人们对查询求值应用了日益复杂的优化 [18, 35, 39, 60]。不出所料，查询优化器通常被视为 DBMS 中最复杂的组件，也构成重大的正确性挑战 [20, 21]。优化器中的实现错误可能导致逻辑错误，即 DBMS 对给定查询返回错误的结果集。本文专门把查询优化器中的逻辑错误称为优化错误（optimization bugs）。

最近提出的 Pivoted Query Synthesis（PQS）用于处理 DBMS 中的逻辑错误 [46]。其核心思想是根据一个随机选择的支点行（pivot row）验证 DBMS：为该行生成一个预期能够取回它的查询。PQS 已在广泛使用的 DBMS 中有效发现许多错误，但一个显著缺点是实现成本高；具体而言，为了判断随机生成的表达式是否求值为 TRUE，该技术需要重新实现 DBMS 所提供的运算符和函数。由于 PQS 只考虑单行，它也无法检测重复行被错误取回或遗漏之类的错误。

另一个成功检测 DBMS 逻辑错误的技术由 RAGS 系统实现 [50]。它以差分测试（differential testing）[36] 为基础：生成一个查询并发送给多个 DBMS；如果这些 DBMS 对输出意见不一，预计至少有一个 DBMS 受到错误影响。RAGS 研究指出，这种技术的一个显著缺点是只能用于 SQL 很小的公共核心，因为各 DBMS 支持的运算符和类型不同，即便公共运算符在不同 DBMS 之间也存在细微的语义差异 [50]。

本文提出非优化参考引擎构造（NoREC），一种新的、通用且成本较低的 DBMS 优化错误检测技术。其高层思想是比较 DBMS 优化版本的结果与同一 DBMS 不执行任何优化的版本的结果。获得这种非优化版本很有挑战。许多 DBMS 虽提供一些优化控制选项，但这些选项能力有限且因 DBMS 而异。事后补加这种选项也是一种可能，但所需实现工作和领域知识都很多，既不切实际又容易出错。

因此，我们提出把给定查询重写为预期不会被 DBMS 优化的形式。既要保证翻译结果与原查询相同，又要使优化无法应用，这样的翻译机制并不显然。我们的关键洞见是：可以把一个带 `WHERE` 子句、会被 DBMS 大量优化并作为高效查询计划构造基础的查询，转换为在表的每条记录上求值 `WHERE` 谓词、因而无法得到有意义优化的查询。第一个查询取回的记录数必须等于第二个查询中 `WHERE` 谓词求值为 TRUE 的次数；结果不同就表明 DBMS 存在错误。

### 示例：SQLite 中的 LIKE/GLOB 优化错误

**Listing 1：SQLite 的 LIKE/GLOB 优化错误。**

```sql
CREATE TABLE t0(c0 UNIQUE);
INSERT INTO t0 VALUES (-1);

SELECT * FROM t0 WHERE t0.c0 GLOB '-*'; -- {}
SELECT t0.c0 GLOB '-*' FROM t0;         -- {TRUE}
```

Listing 1 根据我们在 SQLite 中发现的一个错误说明了这一思想：一次优化使一行记录被错误地从结果集中遗漏。初始数据库只有一条记录；我们生成查询 1，其随机 `WHERE` 条件为 `t0.c0 GLOB '-*'`。`GLOB` 是正则表达式运算符，而 `'-*'` 应匹配一个 `-` 以及随后任意数量的字符。`WHERE`（以及 `JOIN`）子句对性能至关重要，因而会被 DBMS 优化。在本例中，SQLite 应用了 LIKE 优化 [54]，利用由 `UNIQUE` 约束隐式创建的索引——一种用于高效查找的辅助数据结构——执行范围搜索，让执行引擎跳过无关记录。出乎意料的是，尽管唯一记录符合指定表达式，这项优化却使 DBMS 漏取了它。

接着，我们把第一个查询翻译成查询 2，使 DBMS 不太可能优化它：把 `WHERE` 谓词直接移到 `SELECT` 关键字之后，使查询在表的每条记录上求值该谓词。我们预期表达式求值为 TRUE 的次数等于第一个查询实际取回的记录数。然而在本例中，表达式对数据库中的唯一记录求值为 TRUE。DBMS 只能对第一个查询有意义地应用错误优化，不能对第二个查询这样做。我们向 SQLite 开发者报告了这个错误，他们很快修复了它。

我们在 SQLancer 中实现了 NoREC；该工具可从 <https://github.com/sqlancer> 获取。[^1] 为了证明方法的通用性，我们在 SQLite、MariaDB、PostgreSQL 和 CockroachDB 四个广泛使用的生产级 DBMS 上评估了 NoREC。在历时 5 个月、旨在证明方法有效性并最大化现实影响的广泛测试活动中，我们发现 159 个此前未知的错误，其中许多相当严重；随后 141 个得到修复，14 个得到确认。它们包括 51 个优化错误、23 个崩溃错误、27 个断言失败和 58 个错误类问题。尽管 SQLite 已经过 PQS 的广泛测试，NoREC 仍在其中发现 100 多个额外错误，证明了 NoREC 的有效性。

DBMS 开发者非常认可我们的工作。例如，SQLite 网站在介绍这次成功的测试活动时指出 [52]：Rigger 的工作当时尚未发表，而在发表之后，它或许会像 Zalewski 发明 AFL 和基于剖析的模糊测试一样具有影响力。我们相信，NoREC 的简单性、有效性和低实现成本将促使它得到广泛采用。总而言之，本文贡献如下：

- 提出一种基于新测试预言（test oracle）的 DBMS 优化错误检测技术 NoREC。
- 在 SQLancer 中实现 NoREC。
- 通过大规模评估发现超过 150 个常用 DBMS 新错误。

[^1]: 另有一份为长期归档准备的工件 [45]。

## 2. 背景

### 数据库管理系统与 SQL

DBMS 以数据模型为基础，数据模型抽象描述数据如何组织。多数广泛使用的 DBMS 都基于 Codd 提出的关系数据模型 [14]；按照 DB-Engines 排名 [17]，最流行的十种 DBMS 中有七种以它为基础。本文主要旨在测试这类关系 DBMS。SQL [10] 以关系代数 [15] 为基础，是关系 DBMS 中最常用于创建数据库和表、插入行、操纵及检索数据的语言。NoREC 不直接适用于 NoSQL DBMS，因为它们通常有自己的查询语言或只支持 SQL 子集；但是，它适用于较新一代的 NewSQL DBMS：这类系统试图达到 NoSQL DBMS 的可扩展性，同时以 SQL 作为查询语言 [41]。

### 自动化测试

本文聚焦自动化测试：尽管它不能保证错误不存在，却是发现错误的有效实用手段 [27]。自动化测试方法有两个关键组件。第一，有效测试用例必须对受测系统的重要部分施压，才能发现其中的错误。第二，需要一个测试预言来判断某个测试用例是否按预期执行。人们已经提出多种数据库生成器 [4, 7, 23, 26, 32, 38] 和查询生成器 [2, 9, 30, 37, 42, 49, 58] 来生成有效测试用例，但测试预言受到的关注较少。本文提出一种有效且成本较低的测试预言，用于检测 DBMS 逻辑错误。

### DBMS 中的优化

数十年的研究一直致力于查询优化 [19, 22]。每种 DBMS 通常都提供查询优化器：它检查查询，可能对其化简，并把查询高效地映射到物理访问上，例如从若干可用访问路径中选择一条 [48]。考虑 Listing 1 中的两个查询。众所周知，查询优化带来的主要性能收益源于确定如何高效取回数据库记录。因此，查询优化器会把优化工作集中于化简查询 1 的 `WHERE` 子句，并据此创建高效查询计划。在查询 2 中，谓词对结果集的每一行求值一次，因而几乎没有有意义的优化空间。下文将详细说明我们如何利用这一观察，把优化查询翻译成优化较少的查询。

### 差分测试

差分测试 [36] 把单个输入传给多个预期产生相同输出的系统；如果这些系统对输出意见不一，就检测到了其中至少一个系统的错误。Slutz 在 RAGS 系统中将该技术用于测试 DBMS：生成 SQL 查询、发送给多个 DBMS，再观察输出集的差异 [50]。尽管效果良好，该研究仍指出，不同 DBMS 之间很小的公共核心和各种差异构成挑战。事实上，DBMS 支持的 SQL 方言通常不同：它们偏离标准，并提供 DBMS 特有的扩展 [46]。

例如，CockroachDB 开发者曾说明，不能使用最接近它的 PostgreSQL 做差分测试预言 [29]：要有正确性预言就得有一个已知正确工作的 SQL 引擎，但他们恰恰是在试图破坏这种引擎；CockroachDB 与 PostgreSQL 的语义和 SQL 支持略有不同，生成在两者上执行完全相同的查询既困难，又无法使用 CockroachDB 的完整语法。本文提出一种用于构建这种“已知正确工作的 SQL 引擎”的方法，即构建预期不含优化错误的引擎。下面说明为何差分测试并不能直接实现这一点。

### 控制 DBMS 优化

一种显然却不可行的优化错误检测方案，是在禁用和启用 DBMS 优化时各执行一次 SQL 查询，从而通过结果集的错误偏差实现差分测试。这种技术已用于编译器 [33, 61]，即分别在没有和带有优化标志时编译程序。对 DBMS 而言，大多数优化无法禁用。DBMS 通常提供一些运行时和编译时选项，用于控制运算符和优化的行为，但这些选项通常非常有限。例如，应用于 Listing 1 查询的 LIKE 优化无法禁用；SQLite 只提供一个选项，用来控制该运算符是否忽略字符串大小写。类似地，一些 DBMS 允许为给定查询指定优化器提示 [8]，但这同样不能覆盖许多优化。修改 DBMS 以为所有优化提供配置选项虽有可能，却需要 DBMS 特有知识和大量实现工作。

## 3. 方法

为了发现 DBMS 中的优化错误，我们提出 NoREC。其核心洞见是：可以把一个会被 DBMS 优化的给定查询转换为另一个无法得到有效优化的查询。为简洁起见，我们把可能被 DBMS 优化的查询称为优化查询（optimized query），把没有优化或优化较少的查询称为未优化查询（unoptimized query）。虽然翻译步骤不能保证完全没有优化，但我们发现这一技术在实践中广泛适用，足以禁用相关优化。

### 3.1 方法总览

图 1 展示了本方法。在步骤 1 中，我们随机生成如下形式的优化查询：

```sql
SELECT * FROM t0 WHERE ϕ;
```

多数优化都应用于数据过滤，例如查询 `WHERE` 子句所表达的过滤；因此，我们预期随机生成的查询可能被 DBMS 优化。图中数据库只包含表 `t0`，其中保存记录 `r1`、`r2` 和 `r3`。假设 DBMS 正常工作，结果集应为 `rs1`，由记录 `r1` 和 `r3` 组成。但错误优化可能导致某条记录被遗漏或错误取回；图中的 `rs2` 错误地多包含了 `r2`。

在步骤 2 中，我们把优化查询翻译为如下形式的未优化查询：

```sql
SELECT (ϕ IS TRUE) FROM t0;
```

这个查询没有 `WHERE` 条件。因此，DBMS 必须取回所选表中的每条记录，实际上禁用了大多数原本可以应用的优化。此外，该查询把 $\phi$ 作为布尔谓词，在表中每条记录上求值。对于优化查询结果集中的每条记录——也就是 `WHERE` 子句求值为 TRUE 的记录——这个谓词也应求值为 TRUE，因为无论谓词用在何处，它都必须一致地产生相同值。因此，结果集必须包含两个 TRUE 和一个 FALSE。

在步骤 3 中，我们把两个查询都交给 DBMS，并比较两个结果集，即把 `rs1` 或 `rs2` 与 `rs3` 比较。对优化查询，我们计算记录数：正确执行时 $|rs1|=2$，错误执行时 $|rs2|=3$。对未优化查询，我们计算结果集中 TRUE 值的数量，即 $|\sigma _ {\mathrm{column1}=\mathrm{TRUE}}(rs3)|=2$；该数量应等于优化查询取回的记录数。错误执行时 $2 \ne 3$，NoREC 因而检测到查询优化器中的错误。

![图 1：本方法的核心是把优化查询（步骤 1）翻译为未优化查询（步骤 2），从而自动检测优化错误（步骤 3）。](./assets/figure-01.png)

**图 1：** 本方法的核心是把优化查询（步骤 1）翻译为未优化查询（步骤 2），从而自动检测优化错误（步骤 3）。`t0` 是数据库中的表；`rs1`、`rs2` 和 `rs3` 是 DBMS 返回的结果集。谓词 $\phi$ 是随机的，但一经生成便保持不变。

需要注意，我们只考虑优化查询结果集的基数，以及未优化查询中表达式对多少行求值为 TRUE，而不验证完整内容。经验证据表明，这已经足以发现所有优化错误。为求完整，§3.3 还说明如何扩展 NoREC 以验证记录内容。

### 3.2 查询翻译

把优化查询翻译成未优化查询是一种直接的自动过程。如图 1 步骤 2 所示，需要把 `WHERE` 子句的条件移到 `SELECT` 语句之后，使其在表的每一行上执行。下文说明如何扩展基本方法以覆盖更多 DBMS 特性。

**多个表。** `FROM` 子句可以指定多个取回记录的表，通常用 `WHERE` 子句中的谓词连接这些表。虽然此前的例子只涉及一个表，本方法无需任何修改即可直接应用于多个表。

**连接子句。** 除 `WHERE` 子句外，也可以用 `JOIN` 子句连接两个表。例如，Listing 2 的查询 1 包含一个（内）`JOIN` 和一个 `LEFT JOIN`。内连接的 `ON` 子句规定，只取回来自两个表且条件求值为 TRUE 的那些记录，这就像把谓词写在 `WHERE` 子句中一样。`LEFT JOIN` 会取回内连接取回的所有记录；此外，它还取回左表中在右表里没有匹配项的所有记录，并把从右表选择的列视为 NULL。这两类连接以及其他类型的连接，例如 `NATURAL JOIN`、`RIGHT JOIN` 和 `FULL JOIN`，在翻译时都可以保持不变。

**Listing 2：转换时复制 JOIN 子句。**

```sql
SELECT *
FROM t0
LEFT JOIN t1 ON t0.c0 = t1.c0
JOIN t2 ON t2.c0 > t0.c1
WHERE t2.c0 = 5;

SELECT ((t2.c0 = 5) IS TRUE)
FROM t0
LEFT JOIN t1 ON t0.c0 = t1.c0
JOIN t2 ON t2.c0 > t0.c1;
```

查询 2 展示了翻译结果：只有 `WHERE` 条件 `t2.c0 = 5` 被移到 `SELECT` 子句之后，两个 `JOIN` 均原样复制。另一种可能发现更多连接错误的策略，是同时移动它们的 `ON` 子句；这需要把一个查询翻译为多个未优化查询，详见 §5。

**`ORDER BY`。** `ORDER BY` 子句不影响结果集的基数。因此，翻译时未优化查询可以省略或替换它，以测试与该特性相关的错误。

**`GROUP BY`。** `GROUP BY` 子句对值相同的记录分组，常与聚合函数和窗口函数结合使用。如果优化查询中存在该子句，可以把它复制到未优化查询。此时还需要再加一个查询，利用聚合函数把每个分组中表达式求值为 TRUE 的记录数相加，见 §3.3。

### 3.3 计数

图 1 的步骤 3 没有展示如何计算优化查询和未优化查询的计数。我们采用不同策略。朴素方案是遍历结果集来计数，适用于两个查询。第二种更高效的策略依赖 DBMS 提供的聚合函数来取得计数；性能收益取决于数据库行数等多个参数。然而，查询复杂度增加可能使优化不再适用，从而漏掉错误。为平衡性能与发现错误的能力，我们交替使用两种策略。

**优化查询。** Listing 3 展示两种计算图 1 优化查询计数的方法。查询 1 是朴素方案：DBMS 返回结果集 `rs`，SQLancer 遍历它来确定计数。查询 2 使用 `COUNT(*)`，依靠 DBMS 统计记录数。这样做更高效，因为 DBMS 可能优化查询，也因为它避免了跨越 DBMS 与 SQLancer 边界的开销 [5]；SQLancer 只需从 DBMS 返回的单行结果集 `rs` 中取出计数。

**Listing 3：优化查询的两种计数策略。**

```sql
SELECT * FROM t0 WHERE ϕ -- while (rs.next()) count++
SELECT COUNT(*) FROM t0 WHERE ϕ -- count = rs.getInt(1)
```

**未优化查询。** 对未优化查询，我们假设：既然 DBMS 无法优化该查询，它也无法优化应用于其上的聚合函数。使用聚合函数更高效，因此我们只采用这一个策略，见 Listing 4。`SUM()` 把谓词值相加，其中 TRUE 解释为 1，FALSE 和 NULL 解释为 0。PostgreSQL、CockroachDB 等 DBMS 不提供从布尔值到整数的隐式转换，需要额外的显式转换。

**Listing 4：用聚合函数计算未优化查询的计数。**

```sql
SELECT SUM(count) FROM (SELECT ϕ IS TRUE) AS count FROM t0
-- count = rs.getInt(1)
```

> 译注：Listing 4 按论文版面原样转录；原文将右括号与别名排在 `FROM t0` 之前。其上下文表达的意图是用派生表中的 `count` 列求和。

**记录内容。** 基本思想可以扩展为检查记录内容。为此，步骤 2 生成的查询除谓词外还必须列出每一列。然后在步骤 3 中，把未优化查询里谓词求值为 TRUE 的记录与优化查询取回的记录比较。不过，取回并比较结果集意味着必须采用较慢的朴素策略。检查记录内容使我们在一个 SQLite 扩展中额外发现了一个错误，尽管它并非优化器错误。我们推测这一扩展没有更有效，是因为尚未发现会转换所取内容的优化。此外，DBMS 虽可能返回基数正确但内容错误的结果集，经验证据却表明这类错误不太可能发生。

### 3.4 边界情况与限制

我们测试了各 DBMS 功能的一个大型子集，并在此过程中识别出一般性限制以及三个需要本方法特别处理的 SQLite 边界情况。我们不认为这些限制是根本性的，因为它们没有妨碍本方法发现错误。

**歧义查询。** SQL 查询可能有歧义，因而 DBMS 可能对优化查询和未优化查询返回不同结果；这也是此前工作的一个挑战 [30]。实践中，我们发现子查询尤其容易出问题，特别是在把可能返回多行的子查询结果与一个值比较时。因此，我们决定禁用子查询生成，并把无歧义子查询的生成留作未来工作。

**非确定性函数。** 查询即使没有歧义，也可能因非确定性函数而在优化查询与未优化查询之间产生不同结果。这类函数包括随机数生成器和返回当前时间的函数。为了防止误报，我们禁用了它们的生成。

**短路求值。** 本方法不适合检测“优化掉”异常或错误的优化缺陷，因为 SQL 没有规定 `AND` 和 `OR` 运算符是否必须短路。我们发现 DBMS 对优化查询与未优化查询可能采用不一致的处理。考虑谓词 $\phi _ {\mathrm{ok}}\ \mathrm{AND}\ \phi _ {\mathrm{err}}$，其中 $\phi _ {\mathrm{err}}$ 一旦执行就会报错。如果先执行 $\phi _ {\mathrm{ok}}$ 且结果为 FALSE，DBMS 可能不再求值 $\phi _ {\mathrm{err}}$，语句便不会出错；否则，执行 $\phi _ {\mathrm{err}}$ 就会报错。因此，本方法无法检测那些使预期错误不再发生的错误优化。

**其他特性。** 本方法既不直接适用于 `DISTINCT` 子句，也不直接适用于聚合函数、窗口函数等跨多条记录计算结果的查询；这也是 PQS 的一项限制。这些特性同样会被优化，因而其实现也可能存在优化错误。我们相信，把优化查询翻译为未优化查询的高层思想可以扩展到这些场景。

**SQLite 中的数值比较。** 三个 SQLite 边界情况之一是：SQLite3 认为表示同一个值的浮点数和整数相等；即便使用 `DISTINCT` 关键字时也是如此，从而造成不一致结果。在 Listing 5 中，视图 `v0` 的 `DISTINCT` 只取回两条记录中的一条；具体是哪一条没有规定，而且优化查询与未优化查询取到的记录不同。查询 1 取到 `0`，字符串拼接得到 `00.1`，求值为 TRUE；查询 2 从视图取到 `0.0`，拼接得到 `0.00.1`，求值为 FALSE。由于这类误报在 SQLite3 中很少见，而且其他 DBMS 中不存在，我们起初手工过滤它们，后来增加一个选项，避免在视图中生成 `DISTINCT`。

**Listing 5：视图中的 `DISTINCT` 可能导致 SQLite 结果不一致。**

```sql
CREATE TABLE t0(c0);
INSERT INTO t0(c0) VALUES (0.0), (0);
CREATE VIEW v0(c0) AS SELECT DISTINCT c0 FROM t0;

SELECT COUNT(*) FROM v0 WHERE v0.c0 || 0.1; -- 1
SELECT (v0.c0 || 0.1) IS TRUE FROM v0;      -- 0
```

**SQLite 的输入列。** `dbstat` 扩展把 `stat.aggregate = 1` 当作配置输入。该谓词放在 `WHERE` 中会改变虚表行为并返回一行，放在 `SELECT` 列表中则不再作为输入，因而不返回记录。SQLancer 会避免为这个特定列生成设置配置的子句。

**Listing 6：SQLite 输入列可能改变查询行为。**

```sql
CREATE VIRTUAL TABLE stat USING dbstat;

SELECT * FROM stat WHERE stat.aggregate = 1; -- fetches one record
SELECT stat.aggregate = 1 FROM stat; -- FALSE
```

**SQLite 中歧义的 `GROUP BY`。** 第三个 SQLite 边界情况是视图中的歧义 `GROUP BY`；它与其他特性结合时会造成问题，例如 Listing 7 中的优化器提示。我们测试的所有其他 DBMS 都禁止这种歧义 `GROUP BY`，并在创建视图时报错。整个测试期间，这种情况很少出现，所以我们没有在 SQLancer 中处理它。

**Listing 7：歧义 `GROUP BY` 可能导致 SQLite 结果不一致。**

```sql
CREATE TABLE t0(c0, c1, c2, PRIMARY KEY(c2)) WITHOUT ROWID;
CREATE INDEX i0 ON t0(CAST(c1 AS INT));
CREATE VIEW v0 AS SELECT 0, c0 FROM t0 GROUP BY 1 HAVING c2;
INSERT INTO t0(c2) VALUES('');
INSERT INTO t0(c1, c2) VALUES(1, 1);

SELECT * FROM v0 WHERE UNLIKELY(1); -- {}
SELECT UNLIKELY(1) FROM v0;         -- TRUE
```

### 3.5 查询与数据库生成

面向不同工作负载和目的的随机或定向数据库生成 [4, 7, 23, 26, 32, 38] 与查询生成 [2, 9, 30, 37, 42, 49, 58] 已得到广泛探索，不是本文贡献。NoREC 可以基于任何随机生成或现有数据库应用，也可接入任何能避免生成 §3.4 边界情况、或忽略这些情况所产生错误的随机查询生成器。因此，下面只为完整起见说明我们的数据库和查询生成器。

本文的数据库和查询生成以 SQLancer [46] 为基础；我们扩展它以覆盖其他 DBMS，即 CockroachDB 和 MariaDB，以及更多 SQL 特性，例如额外的数据类型、运算符和函数。SQLancer 随机创建表和索引、插入数据，并更新和删除数据，由此生成数据库并对 DBMS 施压，以提高发现错误的概率。

SQLancer 随机查询生成的核心是随机表达式生成；我们把这些表达式用于 `WHERE` 和 `JOIN` 子句。SQLancer 以启发式方式从适用选项中选择一个来生成表达式。适用选项取决于具体 DBMS，因为各 DBMS 支持的运算符和执行的隐式转换不同。表达式生成以相应 DBMS 的语法和当前数据库的 schema 为基础，从而生成对列和表的有效引用。

## 4. 评估

评估旨在证明本方法的有效性和通用性。为此，我们在 SQLite、MariaDB、PostgreSQL 和 CockroachDB 四个广泛使用的 DBMS 上测试 NoREC。作为这项工作的一部分，我们为 SQLancer 增加了 MariaDB 和 CockroachDB 的数据库与查询生成器，并增强了 SQLite 和 PostgreSQL 的对应组件，见 §3.5。为了最大化现实影响，我们在 5 个月内投入大量时间和精力，发现 159 个真实且此前未知的错误。我们还分析错误报告，以进一步理解 NoREC 能发现哪些类型的错误。由于 PQS 是关系最密切的工作，我们也比较了 PQS 与 NoREC。

### 4.1 方法论

**受测 DBMS。** 我们集中测试 SQLite、PostgreSQL、MariaDB 和 CockroachDB 四种重要且广泛使用的 DBMS，见表 1。按照 DB-Engines 排名 [17]、Stack Overflow 年度开发者调查 [40] 和 GitHub 数据，它们都属于最流行、最广泛使用的 DBMS。

SQLite 是总体部署最广泛的 DBMS，主要 Web 浏览器、手机和嵌入式系统都使用它。SQLite 项目推测，有超过一万亿个 SQLite 数据库正在活跃使用 [53]。MySQL 在多数流行度排名中名列前茅；但其二进制和源码只为发布版本提供，而版本通常每 2–3 个月发布一次。这使得过滤触发同一个底层错误的测试用例很繁琐，此前工作也指出过这一点 [46]。此外，PQS 发现的错误只有一部分得到修复，测试该 DBMS 的激励较弱。因此，我们决定测试 MySQL 的分支 MariaDB；它采用开源开发流程。MariaDB 与 MySQL 共享大量代码，所以我们相信，测试 MySQL 会得到相似结果。

PostgreSQL 同样很流行；它似乎比多数其他 DBMS 更稳健，PQS 工作只在其中发现一个逻辑错误 [46]。CockroachDB [56] 是一种较新的商业 NewSQL DBMS [41]。它在 GitHub 上得到很多关注并且非常流行，尽管在其他流行度排名中位置较低。本文只测试 CockroachDB 的免费社区版，不测试商业企业版。

**表 1：被测 DBMS 的流行度、规模与首次发布时间。**

| DBMS | DB-Engines 排名 | Stack Overflow 排名 | GitHub Stars | 代码行数 | 首次发布 |
| --- | ---: | ---: | ---: | ---: | ---: |
| SQLite | 11 | 4 | 1.5k | 0.3M | 2000 |
| MariaDB | 13 | 7 | 3.2k | 3.6M | 2009 |
| PostgreSQL | 4 | 2 | 6.3k | 1.4M | 1996 |
| CockroachDB | 75 | - | 17.7k | 1.1M | 2015 |

**测试重点。** 开发者响应时间是决定我们把测试精力集中在哪个 DBMS 上的重要因素。SQLite 开发者修复错误最为积极，通常在我们报告后的数小时内修复。因此，我们在 SQLite 上投入的时间远多于其他 DBMS。除 SQLite 核心外，我们还测试源码所含、但必须在构建时启用的三个重要扩展。全文搜索（FTS）扩展受到安全研究人员的深入研究 [57]，因为 Google Chrome 等软件会启用它。R-Tree 是一种重要的空间对象索引结构，旨在高效支持范围查询 [25]。DBSTAT 是一个虚表，可查询 SQLite 数据库的内容信息。

我们也投入大量精力测试 PostgreSQL，却没有找到有意思的错误，因而开发者响应时间并不重要。CockroachDB 开发者迅速确认我们的错误，并在数日内修复其中许多，特别是查询优化器错误。MariaDB 开发者同样迅速确认错误，但只修复了一个。由于难以过滤重复项，我们报告最初一批错误后就停止测试 MariaDB。

**现有测试工作。** 所有受测 DBMS 都经过广泛测试。SQLite 和 CockroachDB 对其测试工作有公开说明，可以代表性地展示这一点。SQLite 的测试工作或许最令人印象深刻，并记录在 SQLite 主页 [52]。SQLite 开发者遵循受 DO-178B 指南启发的设计流程 [59]；该指南关注某些航空系统所用安全关键软件的安全性。他们实现 100% 的修改条件/判定覆盖（modified condition/decision coverage）[59]，这意味着每个分支都至少被走到和落空一次。此外，他们还采用内存不足测试、I/O 错误测试、崩溃测试、复合故障测试、模糊测试和动态分析 [52]。

CockroachDB 同样是一个有意思的目标：开发者投入大量精力开发和使用自动测试技术，并把它们作为持续集成的一部分运行。例如，他们在 CockroachDB 上运行基于语法的模糊器，3 年内发现了 70 个崩溃、挂起等错误 [28, 29]。他们还把 SQLSmith 移植到 Go，作为另一个查询生成器使用，又发现 40 多个错误 [29]。不过，正如开发者指出的，这类模糊测试“无法推断正确性”[29]；NoREC 正是填补这个空白。收到我们的错误报告后，他们积极增强测试基础设施，结合领域知识和随机测试技术寻找相似的正确性错误。

**测试方法。** 我们迭代实现本方法，并在每轮迭代后把它应用于受测 DBMS。通常，我们先为随机查询生成器增加一项新特性，例如新运算符，或为数据库生成器增加一项新特性，例如新数据类型，然后继续测试 DBMS。有些错误在实现一项特性后数秒内就被发现，另一些则在数周后才出现。

发现错误后，我们会缩减测试用例。尽管已经有人提出专用查询缩减器 [30, 50]，我们发现最初为缩减 C/C++ 程序开发的 C-Reduce [43] 已经足以满足需求。我们还会手工进一步缩减和规范化测试用例，以降低开发者的调试成本。排除潜在重复后，我们在错误跟踪器或邮件列表上报告问题；如果认为错误可能涉及安全问题，则私下报告。本文重点是优化错误，没有分析任何潜在安全问题。在错误修复之前，我们尽量避免生成会触发它的模式。我们为测试、分类和报告错误投入了大量时间和精力，总计提交 168 份错误报告。由于工具是迭代实现并部署的，我们无法提供总运行时间或效率的详细统计。

### 4.2 代表性错误

下面选取 NoREC 发现的若干错误，以直观展示它能找到哪些有意思的问题。这一选择必然有偏：我们还发现许多不那么有意思的错误，也有其他有意思的错误因篇幅所限而未能列出。完整错误清单收录于随论文提供的补充材料中。为简洁起见，如果未优化查询能够从优化查询直接推导，我们就省略它。在 Listings 8–13 的行尾，前一个结果集是实际得到的错误结果，后一个是预期结果。

#### 4.2.1 SQLite 错误

**错误的 `IN` 优化。** SQL 的 `IN` 运算符可检查左侧的值是否包含在右侧的值集合中。SQLite 此前实现过一项优化，把 `X IN (Y)` 形式的表达式转换为 `X=Y`；这里 `Y` 是单个值。对 `=` 运算符，SQLite 会根据操作数的 affinity（例如列类型）执行隐式类型转换，但 `IN` 运算符不应执行这种转换。因此，我们发现该优化在存在 affinity 转换时并不正确，见 Listing 8：它使 SQLite 错误地把字符串 `'1'` 转换为整数，从而意外取回一条记录。

**Listing 8：`IN` 优化与 affinity 表达式错误。**

```sql
CREATE TABLE t0(c0 INT UNIQUE);
INSERT INTO t0(c0) VALUES (1);

SELECT * FROM t0 WHERE '1' IN (t0.c0); -- {1}    {}
```

我们还发现其他与 affinity 转换有关的相似错误，例如常量传播中的一个错误。我们认为 affinity 转换很难推理，而这些发现似乎证明该机制容易出错。

**交换运算符时忽略 `COLLATE`。** 我们发现一个错误：交换运算符两侧后，原本不适用的部分索引却被错误匹配，见 Listing 9。`COLLATE NOCASE` 子句规定，在字符串比较中使用该列时应忽略字符串大小写；但由于 `c1` 列在左侧且没有 `COLLATE`，比较应区分大小写。因此，小写字符 `a` 被认为大于大写字符 `B`，谓词应求值为 TRUE；然而该记录并未被取回。

**Listing 9：运算符交换导致错误使用 partial index。**

```sql
CREATE TABLE t0(c0 COLLATE NOCASE, c1);
CREATE INDEX i0 ON t0(0) WHERE c0 >= c1;
INSERT INTO t0 VALUES('a', 'B');

SELECT * FROM t0 WHERE t0.c1 <= t0.c0; -- {}    {a|B}
```

错误原因是 SQLite 交换了运算符，同时更新了表达式的 `COLLATE`，随后使表达式匹配到部分索引；但系统没有保留足够信息来验证表达式是否确实满足该索引的适用条件。修复方案是增加逻辑来维护这些信息。

#### 4.2.2 CockroachDB 错误

**向量化引擎错误。** 我们发现 11 个与 CockroachDB 向量化引擎有关的错误，Listing 10 展示其中之一。由于两个表连接时没有过滤任何记录，实际上计算的是表的笛卡尔积，查询应取回两条记录： $|t0|\times|t1|=2\times1=2$。然而，实际只取回一条记录。根本原因是向量化执行引擎在执行哈希连接时，错误处理了两个表之间为空的等值连接列集合。

**Listing 10：向量化引擎错误导致记录遗漏。**

```sql
SET SESSION VECTORIZE=experimental_on;
CREATE TABLE t1(c0 INT);
CREATE TABLE t0(c0 INT UNIQUE);
INSERT INTO t1(c0) VALUES (0);
INSERT INTO t0(c0) VALUES (NULL), (NULL);

SELECT * FROM t0, t1 WHERE t0.c0 IS NULL;
-- {NULL|0}    {NULL|0, NULL|0}
```

**过滤条件处理错误。** 我们发现一个错误，暴露出 CockroachDB 在极少数情况下会错误处理 `CHECK` 约束；这些约束用于细化过滤条件中的取值范围。结果是 Listing 11 的查询错误取回一条记录，尽管谓词应求值为 NULL。这个具体错误通过补上一条缺失的规范化规则修复，而底层原因则在后续提交中通过扩展并重构 CockroachDB 的索引约束库得到修复。

**Listing 11：过滤器处理错误导致意外取回记录。**

```sql
CREATE TABLE t0(c0 BOOL UNIQUE, c1 BOOL CHECK (true));
INSERT INTO t0(c0) VALUES (true);

SELECT *
FROM t0
WHERE t0.c0
  AND (false NOT BETWEEN SYMMETRIC t0.c0 AND NULL AND true);
-- {TRUE}    {}
```

#### 4.2.3 MariaDB 错误

**错误的字符串范围扫描。** 我们在 MariaDB 中发现一个错误：索引上的范围扫描被错误地用于字符串比较，见 Listing 12。MariaDB 开发者解释说，优化器为范围扫描错误构造了 `NULL < x <= 0`，但正确上界应为 2，因而只取回一行。原因是换行符 `\n` 之类的空白字符被不一致地处理。这个错误也影响 MySQL，并且是我们报告后唯一由 MariaDB 开发者修复的错误。

**Listing 12：range scan 错误导致记录遗漏。**

```sql
CREATE TABLE t0(c0 INT UNIQUE);
INSERT INTO t0 VALUES(NULL), (NULL), (NULL), (NULL), (1), (0);

SELECT * FROM t0 WHERE c0 < '\n2'; -- {0}    {0, 1}
```

**错误的数值比较。** 我们发现一个错误：把浮点数与建有索引的整数列比较时得到错误结果，见 Listing 13。比较 `0.5=c0` 应求值为 FALSE，因为隐式类型转换后 `c0` 应求值为 `1.0`，而 $0.5 \ne 1.0$。然而，该查询意外取回表中的唯一记录。这个错误很快得到确认，并在 MariaDB 与 MySQL 上都能复现，但当时尚未修复。

**Listing 13：浮点数与整数列比较意外求值为 TRUE。**

```sql
CREATE TABLE t0(c0 INT);
INSERT INTO t0 VALUES (1);
CREATE INDEX i0 ON t0(c0);

SELECT * FROM t0 WHERE 0.5 = c0; -- {1}    {}
```

### 4.3 错误总览

**总体错误统计。** 表 2 展示我们所报告错误的数量与状态。在 168 份错误报告中，159 份是此前未知的真实错误。141 个错误通过代码修改得到处理，表明开发者认真对待了我们的报告；14 个得到确认但尚未处理，另有 3 份报告通过文档修改得到处理。9 份报告不是真实错误：其中 7 份或者是我们认为意外、开发者却认为符合预期的内部错误，或者源于我们当时尚不了解的 §3.4 方法限制。由于我们始终测试各 DBMS 的最新版本，只有 2 个错误最终被认定为已知错误。

**表 2：159 个真实错误的状态统计。**

| DBMS | 已修复 | 已确认 | 按预期工作 | 重复 |
| --- | ---: | ---: | ---: | ---: |
| SQLite | 110 | 0 | 6 | 0 |
| MariaDB | 1 | 5 | 0 | 1 |
| PostgreSQL | 5 | 2 | 1 | 0 |
| CockroachDB | 28 | 7 | 0 | 1 |

**测试预言。** 表 3 展示用于发现错误的预言。本文重点 NoREC 预言发现 51 个错误。此外，我们在创建数据库或向 DBMS 发送查询时通过意外内部错误发现 58 个错误；具体做法是为每条 SQL 语句标注一份预期错误清单 [46]。SQLancer 本身也隐式充当基于语法的模糊器，发现许多崩溃错误。我们构建 SQLite 和 PostgreSQL 的调试版本，发现 27 个调试断言失败；还在发布构建中发现 23 个崩溃错误，其中也包括挂起，但这些错误不一定存在于 DBMS 的正式发布版本中。

**表 3：按测试预言与错误表现分类的错误数。**

| DBMS | 逻辑错误 | 内部错误 | 发布构建崩溃 | 调试断言失败 |
| --- | ---: | ---: | ---: | ---: |
| SQLite | 39 | 30 | 15 | 26 |
| MariaDB | 5 | 0 | 1 | 0 |
| PostgreSQL | 0 | 4 | 3 | 1 |
| CockroachDB | 7 | 24 | 4 | 0 |

**附加子句。** §3.2 提到可以选择生成 `ORDER BY` 和 `GROUP BY` 子句，进一步对查询优化器施压。`ORDER BY` 子句帮助发现 1 个逻辑错误和 1 个崩溃错误；`GROUP BY` 子句帮助发现 1 个错误类问题。总体而言，这两个子句对 NoREC 发现错误的能力贡献不大；不过，实现它们所需工作很少，仍可能值得保留。

**SQLite。** 我们在 SQLite 中发现的错误最多，这符合预期，因为我们在其上投入最多精力。在所统计的 110 个 SQLite 错误中，71 个影响 SQLite 核心；13 个影响 R-Tree，24 个影响 FTS，2 个影响 DBSTAT。需要注意，一些扩展错误实际上影响虚表这一通用基础，而这些扩展和其他扩展都建立在虚表之上。

我们测试 SQLite 期间，开发者把 generated columns（根据其他列计算得到的列）支持 [51] 合入 trunk。该特性合入后、正式发布前，我们发现其中 22 个错误，为其正确性作出重要贡献。除逻辑错误外，还有 26 个错误表现为调试断言失败。这个较高数量可以用 PQS 等此前工作没有测试这些特性来解释。一些断言并不表示 SQLite 核心的真实错误，而是表明 SQLite 自身测试逻辑遗漏了边界情况 [55]。发布构建中的崩溃数量也令人意外，因为 PQS 在 SQLite 中只发现 2 个崩溃错误 [46]。一个主要原因就是 generated columns，我们在其中发现 9 个崩溃错误。除此之外，还发现 1 个 FTS 挂起、1 个涉及触发器的错误、2 个 R-Tree 错误和 2 个窗口函数错误。

**PostgreSQL。** 尽管我们投入大量精力测试 PostgreSQL，却只发现 8 个错误，而且没有一个是优化错误。这与此前发现一致：例如，PQS 在该 DBMS 中只找到一个逻辑错误 [46]。我们认为，一个重要原因是 PostgreSQL 对可接受输入的限制比其他 DBMS 严格得多。SQLite 首席开发者 Richard Hipp 也指出，PostgreSQL 是一种高质量 DBMS，错误很少；其非常细致的同行评审流程可能是原因之一 [59]。

**CockroachDB。** 我们在 CockroachDB 中发现 35 个错误，其中 15 份报告依赖实验特性，11 个错误影响向量化引擎，见 Listing 10。在 24 个错误类问题中，17 个是内部错误：执行时会显示堆栈跟踪和错误报告位置，同时服务器仍能响应。根据我们的报告，CockroachDB 开发者积极增加测试基础设施并审查代码，以检测相似错误，表明他们认真对待这些报告。例如，其中一份重复报告对应的开放问题明确说明，该问题是根据我们此前的一份报告发现的。

**MariaDB。** 我们在 MariaDB 中发现 6 个错误。MariaDB 开发者迅速确认全部错误，其中 3 个也在 MySQL 上复现；但是，3 个月内只有一个得到修复，所以我们停止测试 MariaDB。由于投入的测试时间很少，我们相信本方法还能在其中发现更多错误。

### 4.4 与 PQS 的比较

PQS 是当时发现 DBMS 逻辑错误的先进方法，因此我们希望比较它与 NoREC 的有效性。我们预期 PQS 能发现范围更广的错误，因为 NoREC 的目标是优化错误。据我们所知，没有其他可公开获取、能够检测 DBMS 逻辑错误的工具可供比较。

**评估挑战。** 由于若干原因，公平比较 PQS 与 NoREC 的有效性很困难。首先，PQS 实现成本很高，使其只能覆盖相应 DBMS 所支持 SQL 方言的核心子集 [46]。例如，在 PQS 中，单个比较运算符就超过 200 行代码，因为它需要支持任意数据类型之间的比较；对 SQLite、MySQL 等 DBMS，这还涉及隐式转换。相比之下，NoREC 预言的实现不足 200 行代码，同时还能发现复杂运算符和函数的优化错误。尽管如此，我们认为，公平的有效性评估不应考虑各方法所投入的实现时间。

另一个挑战是两项评估测试的 DBMS 集合不同。PQS 与 NoREC 都测试了 SQLite 和 PostgreSQL，但 PQS 还测试 MySQL，而 NoREC 测试 MariaDB 和 CockroachDB。因此，我们无法进行自动比较。

**方法。** 为公平比较，我们进行人工的定量和定性分析。我们注意到，只要 PQS 能复现某个错误，NoREC 测试用例通常可以直接转换为能够触发它的等价 PQS 用例：保留谓词位于 `WHERE` 子句中的原查询，再检查是否能选择一个适用的支点行。反过来，PQS 测试用例通常也能通过未优化查询翻译步骤转换为等价的 NoREC 测试用例。根据这一观察，我们尽可能手工创建等价测试用例，并在发现该错误的 DBMS 版本上执行。

虽然不能完全排除因为漏看另一条可复现查询而造成的误分类，我们认为多数案例都很清楚。比较只考虑由 NoREC 预言发现的错误；内部错误和崩溃预计都可以由两种方法触发。总体而言，我们调查了两组问题：（1）NoREC 预言发现的 51 个错误是否也能由 PQS 发现；（2）PQS 发现的 61 个错误是否也能由 NoREC 发现。

**只有 NoREC 能发现的错误。** PQS 可以检测 NoREC 所发现错误的 56.9%。具体而言，NoREC 检测到 4 个结果集意外包含或遗漏重复记录的错误；PQS 在概念上无法检测这类错误，因为它只验证一个随机选择、与其他重复行无法区分的记录是否属于结果集。NoREC 还通过用于行计数的聚合函数，即 `SUM` 和 `COUNT`，触发 5 个错误。PQS 的主要预言依赖于每次只检查一行，因此在概念上难以检测与这些聚合函数有关的错误。

另有 13 个案例会错误地多取记录。PQS 没有检测到这类错误，因为它只检查支点行是否被错误遗漏。我们认为这不是 PQS 的根本限制：可以扩展 PQS，让它生成保证排除支点行的查询，从而检测这类错误。考虑这一扩展后，PQS 理论上可以检测 NoREC 所发现错误的 82.4%。需要注意，有些其他错误仍必须由接近完整的 PQS 实现才能检测；由于多少实现工作算“过多”存在争议，本分析没有把这一限制计入。

**只有 PQS 能发现的错误。** NoREC 总计可以发现 PQS 所发现错误的 52.7%。PQS 能发现而 NoREC 不能发现的最大类别，来自运算符、函数和其他特性在优化与未优化情况下都实现错误，尤其是 SQLite 的 affinity 转换。NoREC 漏掉 18 个这样的错误。另有 3 个错误依赖 `DISTINCT` 查询，而 NoREC 忽略了这种查询；未来可以通过在未优化路径中把它翻译为 `GROUP BY` 子句来支持。

PQS 与 NoREC 一样，通常无法检测聚合函数中的错误，因为它只在单个支点行上运行；但当表只有一行时，PQS 仍可检测，因此发现了 3 个这样的错误。PQS 还通过用于高效检查成员关系的 `INTERSECT` 发现 1 个错误，这类似于 NoREC 用聚合函数计数。另有 1 个错误由 `LEFT JOIN` 的 `ON` 子句谓词触发；NoREC 没有发现，因为翻译时原样复制 left join 和谓词。如 §5 所述，可以实现更多连接翻译方案来增强 NoREC。

**讨论。** 比较表明，PQS 能发现一些 NoREC 无法发现的错误；NoREC 也能发现 PQS 无法发现的类别，例如重复记录，但它主要局限于优化错误。PQS 的实现开销显著：对每一个要测试的 DBMS，都需要实现每一个待测运算符和函数。NoREC 则只依赖直接的翻译过程，适用于任何能够处理 §3.4 所述限制的数据库与查询生成器。低实现成本使 NoREC 成功发现范围广泛的优化错误，即便是刚刚由 PQS 全面测试过的 SQLite 也不例外。

因此，我们设想把两种方法结合起来测试 DBMS。PQS 可以测试许多基础运算符和函数；作为精确预言，它能帮助建立 ground truth。然后，可以用 NoREC 找出 PQS 未全面测试区域中仍残留的优化错误。

## 5. 讨论

**DBMS 开发者的反馈。** 多种 DBMS 的开发者都告诉我们，他们认可这些错误报告。SQLite 主页甚至在 <https://www.sqlite.org/testing.html> 特别强调我们的工作：它指出，多数模糊器只寻找断言故障、崩溃、未定义行为或其他容易检测的异常，而 Manuel Rigger 的模糊器能够找到 SQLite 计算错误答案的情况；许多发现是涉及类型转换、affinity 转换和未发布特性的隐蔽边界情况，但仍是真实且重要的错误，SQLite 开发者也感谢这些发现。页面最后判断，Rigger 的工作发表后可能像 Zalewski 发明 AFL 和基于剖析的模糊测试一样具有影响力。

**错误的重要性。** 我们相信，发现的许多严重错误很可能影响真实用户；同时也承认，另一些错误只能由不太可能出现的运算符或特性组合触发。由于这些 DBMS 使用广泛，即便看似不重要的错误也可能影响用户。SQLite 邮件列表提供了一个证据：某位用户报告，一个带复杂 `WHERE` 谓词的查询返回错误结果。另一位用户质疑这种写法时，报告者解释说 [13]：自己可能不会这样写，但代码生成器会这样写，甚至写得更复杂；该例正是从 Django ORM 查询集的 `.exclude(nullable_joined_table__column=1)` 简化而来。

该错误已在最新开发版本中修复，因为我们此前报告过同一个底层错误 [44]。我们是用一个视图上的查询和谓词 `NOTNULL NOTNULL` 发现它的；程序员同样不太可能手写这种形式。我们推测还有其他用户可能受到这类看似冷僻的错误影响；而当查询由中间件生成时，定位根因尤其困难。

**连接处理。** 翻译过程原样保留 `JOIN` 子句，见 §3.2。这使我们发现了一些连接处理错误；但若同时把连接谓词转换为 `SELECT` 后的条件，可能发现更多错误。对内连接，转换很直接：可以把 `ON` 谓词 $\phi_1$ 与 `WHERE` 谓词 $\phi_2$ 转换为 $\phi_1\ \mathrm{AND}\ \phi_2$。其他连接更复杂。例如，对于 `LEFT JOIN`，一个简单的 `SELECT` 语句将不再足够，而需要组合多条查询的结果。我们认为增加 `JOIN` 子句翻译策略可能有用，并把它留作未来工作。

**代码覆盖率与性能。** 乍看之下，评估 NoREC 所达到的代码覆盖率和运行时性能似乎很有意义，但两者都无法解释本方法为何有效。就覆盖率而言，此前研究发现，代码覆盖率对 DBMS 模糊测试不是特别有用，因为查询优化器等核心组件很快就能达到高覆盖率 [30]。而且，即使 SQLite 开发者的测试套件已达到 100% MC/DC 覆盖，我们仍能在 SQLite 中发现错误。

查询生成和翻译的运行时开销可以忽略，因此我们没有详细测量。运行时间主要由两部分决定：DBMS 处理所生成查询的时间，以及与 DBMS 通信的时间。SQLite 的通信开销低于其他 DBMS，因为 SQLite 是嵌入式 DBMS，运行在 SQLancer 的应用进程内。

**错误类型。** 159 个真实错误中有 51 个是优化错误。我们认为这类错误最严重，因为开发者很可能觉察不到它们。崩溃、断言失败和错误类问题占总体的很大一部分，但基于语法的模糊器等现有方法也能发现它们；而且，这些错误通常会使 DBMS 终止，从而明确向用户表明 DBMS 无法处理给定查询。一种可能的结论是，本测试方法也检测到了模糊器通常能发现的错误，而这些错误可能比逻辑错误更常见或更容易发现；不过，我们并不知道错误总数的 ground truth。

**全自动方法。** 我们称 NoREC 为全自动方法，因为它反复生成测试用例并验证结果集，无需任何人工交互即可发现错误。如 §3.4 所述，必须特别处理一些边界情况，确保只报告真实错误。当 NoREC 检测到错误时，最好缩减生成的测试用例，使其最小化。在评估中，我们先自动缩减测试用例，再尝试手工进一步缩减；我们认为手工缩减并非必需，只是便于 DBMS 开发者调试。报告错误前，我们还手工检查错误跟踪器，以降低重复报告的概率。实践中，可以让 NoREC 报告一个错误后暂停，待错误修复再继续运行。

## 6. 相关工作

**DBMS 差分测试。** 差分测试用系统的多个版本执行给定输入，借助不同输出来发现其中一个系统的错误。与变形测试类似，差分测试已在许多领域证明有效 [6, 16, 31, 33, 36, 61]。Slutz 首次在 RAGS 工具中把它用于 DBMS：在多个不同 DBMS 上执行查询并比较结果集 [50]。该方法非常有效，却只能用于 SQL 很小的公共子集。Gu 等人使用选项和提示强制生成不同查询计划，再根据每个计划的估算代价评定优化器准确性 [24]。Jinho 等人在 APOLLO 系统中使用差分测试，在 DBMS 的旧版本和新版本上执行同一 SQL 查询，从而发现性能回退错误 [30]；他们在 SQLite 和 PostgreSQL 中发现 10 个此前未知的性能回退错误。本文虽使用变形测试发现优化错误，从概念上看，也可以理解为比较 DBMS 的优化版本与非优化版本，由此实现差分测试。

**用于测试 DBMS 的其他正确性预言。** Pivoted Query Synthesis（PQS）是当时测试 DBMS 逻辑错误的先进方法，也是关系最密切的工作 [46]。它既是一种自动测试方法，也是一种预言；核心思想是根据随机选择的支点行测试 DBMS 的正确性。PQS 已在广泛使用的 DBMS 中发现近 100 个错误，证明它非常有效。不过，由于实现成本很高，测试 DBMS 支持的所有运算符和函数可能并不可行。NoREC 主要用于发现优化错误，即 PQS 所面向的逻辑错误的一个子类。它实现成本低，因而能在实现 PQS 代价过高的组件中发现错误。

ADUSA [32] 是一种查询感知数据库生成器，同时生成输入数据和查询的预期结果，因而也处理 DBMS 测试预言问题。它把 schema 和查询翻译成 Alloy 规范，再对其求解。该方法能复现 MySQL、HSQLDB 的多种已知或注入错误，并在 Oracle Database 中发现一个新错误。我们认为，基于求解器的方法开销很大，可能妨碍它们发现更多 DBMS 错误。

**随机与定向查询。** 人们已经为错误发现、基准测试等目的提出许多查询生成器。SQLsmith 是广泛使用的开源随机查询生成器，已在常用 DBMS 中发现 100 多个错误 [49]。Bati 等人提出基于遗传算法、结合执行反馈生成查询的方法 [2]。SQLFUZZ [30] 也利用执行反馈，并且只使用所有受测 DBMS 都支持的特性来随机生成查询。Khalek 等人提出一种基于求解器的方法，同时生成语法和语义均有效的查询 [1]。为子表达式生成满足基数约束的查询在计算上很困难 [9, 37]，因此又出现多种生成定向查询的启发式和近似方案 [9, 37, 42, 58]。这些随机查询生成器都能发现 DBMS 崩溃、挂起等错误；与本文测试预言结合后，它们也能发现逻辑错误。

**随机与定向数据库。** 人们提出了许多自动生成数据库的方法。给定查询和一组约束，QAGen [4, 34] 把传统查询处理与符号执行结合起来，生成符合期望查询结果的数据库。Reverse Query Processing 接收查询和期望结果集，再生成可能产生该结果集的数据库 [3]。前述 ADUSA 也是查询感知数据库生成器 [32]。Gray 等人讨论了一组采用并行算法、快速生成十亿级记录数据库的技术 [23]。DGL 是一种领域特定语言，以可组合的迭代器为基础，生成遵循不同分布和跨表相关性的输入数据 [7]。Neufeld 等人从表约束推导生成器公式，再把公式翻译为生成算子，从而为带约束的表生成测试数据 [38]。改进数据库生成可能让 NoREC 发现更多错误。

**变形测试。** 本方法以变形测试为基础 [11]。变形测试根据系统的一次输入和输出生成一个结果已知的新输入，从而处理测试预言问题；它已成功应用于多个领域 [12, 47]。该方法的核心是变形关系，可由此推断预期结果。本文把翻译机制与计数机制结合起来，建立一种专门面向优化错误检测的变形关系。变形测试的一个限制是无法建立 ground truth。对 NoREC 而言，这意味着未优化查询和优化查询可能都产生错误结果，见 §4.4；类似地，也可能是优化查询算出了正确结果，而未优化查询错误。

## 7. 结论

本文提出一种通用且高度有效的 DBMS 错误检测方法，称为非优化参考引擎构造（NoREC）。其核心洞见是：可以把给定的优化查询翻译成未优化查询，从而构造一个测试预言，通过比较两个查询的结果集来检测优化错误。

我们相信，NoREC 为 DBMS 正确性测试提供了坚实基础；其基本思想还可以采用额外或替代的查询翻译策略来扩展，例如翻译 `JOIN` 子句的谓词。另一个例子是在仍应产生相同结果的前提下用其他方式转换查询，例如交换可交换运算符的两个操作数。此外，把 NoREC 与更好的数据库和查询生成器结合，还可以提高其效率与有效性。

## 致谢

我们感谢 DBMS 开发者验证和修复错误报告，也感谢匿名审稿人、Martin Kersten 以及 ETH Zurich AST Lab 成员的反馈。

## 参考文献

- [1] Shadi Abdul Khalek and Sarfraz Khurshid. 2010. Automated SQL Query Generation for Systematic Testing of Database Engines. In Proceedings of the IEEE/ACM International Conference on Automated Software Engineering (Antwerp, Belgium) (ASE '10). ACM, New York, NY, USA, 329-332. https://doi.org/10.1145/1858996.1859063
- [2] Hardik Bati, Leo Giakoumakis, Steve Herbert, and Aleksandras Surna. 2007. A Genetic Approach for Random Testing of Database Systems. In Proceedings of the 33rd International Conference on Very Large Data Bases (Vienna, Austria) (VLDB '07). VLDB Endowment, 1243-1251.
- [3] Carsten Binnig, Donald Kossmann, and Eric Lo. 2007. Reverse Query Processing. Proceedings - International Conference on Data Engineering, 506-515. https://doi.org/10.1109/ICDE.2007.367896
- [4] Carsten Binnig, Donald Kossmann, Eric Lo, and M. Tamer Özsu. 2007. QAGen: Generating Query-Aware Test Databases. In Proceedings of the 2007 ACM SIGMOD International Conference on Management of Data (Beijing, China) (SIGMOD '07). Association for Computing Machinery, New York, NY, USA, 341-352. https://doi.org/10.1145/1247480.1247520
- [5] Carl Friedrich Bolz, Darya Kurilova, and Laurence Tratt. 2016. Making an Embedded DBMS JIT-friendly. In 30th European Conference on Object-Oriented Programming, ECOOP 2016, July 18-22, 2016, Rome, Italy. 4:1-4:24. https://doi.org/10.4230/LIPIcs.ECOOP.2016.4
- [6] Robert Brummayer and Armin Biere. 2009. Fuzzing and Delta-Debugging SMT Solvers. In Proceedings of the 7th International Workshop on Satisfiability Modulo Theories (Montreal, Canada) (SMT '09). Association for Computing Machinery, New York, NY, USA, 1-5. https://doi.org/10.1145/1670412.1670413
- [7] Nicolas Bruno and Surajit Chaudhuri. 2005. Flexible Database Generators. In Proceedings of the 31st International Conference on Very Large Data Bases (Trondheim, Norway) (VLDB '05). VLDB Endowment, 1097-1107.
- [8] Nicolas Bruno, Surajit Chaudhuri, and Ravi Ramamurthy. 2009. Power Hints for Query Optimization. In Proceedings of the 2009 IEEE International Conference on Data Engineering (ICDE '09). IEEE Computer Society, USA, 469-480. https://doi.org/10.1109/ICDE.2009.68
- [9] Nicolas Bruno, Surajit Chaudhuri, and Dilys Thomas. 2006. Generating Queries with Cardinality Constraints for DBMS Testing. IEEE Trans. on Knowl. and Data Eng. 18, 12 (Dec. 2006), 1721-1725. https://doi.org/10.1109/TKDE.2006.190
- [10] Donald D. Chamberlin and Raymond F. Boyce. 1974. SEQUEL: A Structured English Query Language. In Proceedings of the 1974 ACM SIGFIDET (Now SIGMOD) Workshop on Data Description, Access and Control (Ann Arbor, Michigan) (SIGFIDET '74). ACM, New York, NY, USA, 249-264. https://doi.org/10.1145/800296.811515
- [11] Tsong Y Chen, Shing C Cheung, and Shiu Ming Yiu. 1998. Metamorphic testing: a new approach for generating next test cases. Technical Report. Technical Report HKUST-CS98-01, Department of Computer Science, Hong Kong.
- [12] Tsong Yueh Chen, Fei-Ching Kuo, Huai Liu, Pak-Lok Poon, Dave Towey, T. H. Tse, and Zhi Quan Zhou. 2018. Metamorphic Testing: A Review of Challenges and Opportunities. ACM Comput. Surv. 51, 1, Article 4 (Jan. 2018), 27 pages. https://doi.org/10.1145/3143561
- [13] And Clover. 2019. Bug submission: left join filter on negated expression including NOTNULL. https://www.mail-archive.com/sqlite-users@mailinglists.sqlite.org/msg117434.html
- [14] E. F. Codd. 1970. A Relational Model of Data for Large Shared Data Banks. Commun. ACM 13, 6 (June 1970), 377-387. https://doi.org/10.1145/362384.362685
- [15] E. F. Codd. 1972. Relational Completeness of Data Base Sublanguages. IBM Corporation.
- [16] Pascal Cuoq, Benjamin Monate, Anne Pacalet, Virgile Prevosto, John Regehr, Boris Yakobowski, and Xuejun Yang. 2012. Testing Static Analyzers with Randomly Generated Programs. In Proceedings of the 4th International Conference on NASA Formal Methods (Norfolk, VA) (NFM '12). Springer-Verlag, Berlin, Heidelberg, 120-125. https://doi.org/10.1007/978-3-642-28891-3_12
- [17] DB-Engines. 2019. DB-Engines Ranking (July 2019). https://db-engines.com/en/ranking
- [18] Bailu Ding, Sudipto Das, Wentao Wu, Surajit Chaudhuri, and Vivek Narasayya. 2018. Plan Stitch: Harnessing the Best of Many Plans. Proc. VLDB Endow. 11, 10 (June 2018), 1123-1136. https://doi.org/10.14778/3231751.3231761
- [19] Ramez Elmasri and Sham Navathe. 2017. Fundamentals of database systems. Vol. 7. Pearson.
- [20] Leo Giakoumakis and César A Galindo-Legaria. 2008. Testing SQL Server's Query Optimizer: Challenges, Techniques and Experiences. IEEE Data Eng. Bull. 31, 1 (2008), 36-43.
- [21] Torsten Grabs, Steve Herbert, and Xin (Shin) Zhang. 2008. Testing Challenges for Extending SQL Server's Query Processor: A Case Study. In Proceedings of the 1st International Workshop on Testing Database Systems (Vancouver, British Columbia, Canada) (DBTest '08). Association for Computing Machinery, New York, NY, USA, Article 2, 6 pages. https://doi.org/10.1145/1385269.1385272
- [22] Goetz Graefe. 1993. Query evaluation techniques for large databases. ACM Computing Surveys (CSUR) 25, 2 (1993), 73-169.
- [23] Jim Gray, Prakash Sundaresan, Susanne Englert, Ken Baclawski, and Peter J. Weinberger. 1994. Quickly Generating Billion-Record Synthetic Databases. SIGMOD Rec. 23, 2 (May 1994), 243-252. https://doi.org/10.1145/191843.191886
- [24] Zhongxian Gu, Mohamed A. Soliman, and Florian M. Waas. 2012. Testing the Accuracy of Query Optimizers. In Proceedings of the Fifth International Workshop on Testing Database Systems (Scottsdale, Arizona) (DBTest '12). ACM, New York, NY, USA, Article 11, 6 pages. https://doi.org/10.1145/2304510.2304525
- [25] Antonin Guttman. 1984. R-Trees: A Dynamic Index Structure for Spatial Searching. In Proceedings of the 1984 ACM SIGMOD International Conference on Management of Data (Boston, Massachusetts) (SIGMOD '84). Association for Computing Machinery, New York, NY, USA, 47-57. https://doi.org/10.1145/602259.602266
- [26] Kenneth Houkjær, Kristian Torp, and Rico Wind. 2006. Simple and Realistic Data Generation. In Proceedings of the 32nd International Conference on Very Large Data Bases (Seoul, Korea) (VLDB '06). VLDB Endowment, 1243-1246.
- [27] William E. Howden. 1978. Theoretical and Empirical Studies of Program Testing. In Proceedings of the 3rd International Conference on Software Engineering (Atlanta, Georgia, USA) (ICSE '78). IEEE Press, Piscataway, NJ, USA, 305-311.
- [28] Matt Jibson. 2016. Testing Random, Valid SQL in CockroachDB. https://www.cockroachlabs.com/blog/testing-random-valid-sql-in-cockroachdb/
- [29] Matt Jibson. 2019. SQLsmith: Randomized SQL Testing in CockroachDB. https://www.cockroachlabs.com/blog/sqlsmith-randomized-sql-testing/
- [30] Jinho Jung, Hong Hu, Joy Arulraj, Taesoo Kim, and Woonhak Kang. 2019. APOLLO: Automatic Detection and Diagnosis of Performance Regressions in Database Systems. Proc. VLDB Endow. 13, 1 (Sept. 2019), 57-70. https://doi.org/10.14778/3357377.3357382
- [31] Timotej Kapus and Cristian Cadar. 2017. Automatic Testing of Symbolic Execution Engines via Program Generation and Differential Testing. In Proceedings of the 32Nd IEEE/ACM International Conference on Automated Software Engineering (Urbana-Champaign, IL, USA) (ASE 2017). IEEE Press, Piscataway, NJ, USA, 590-600.
- [32] S. A. Khalek, B. Elkarablieh, Y. O. Laleye, and S. Khurshid. 2008. Query-Aware Test Generation Using a Relational Constraint Solver. In Proceedings of the 2008 23rd IEEE/ACM International Conference on Automated Software Engineering (ASE '08). IEEE Computer Society, Washington, DC, USA, 238-247. https://doi.org/10.1109/ASE.2008.34
- [33] Vu Le, Mehrdad Afshari, and Zhendong Su. 2014. Compiler Validation via Equivalence Modulo Inputs. In Proceedings of the 35th ACM SIGPLAN Conference on Programming Language Design and Implementation (Edinburgh, United Kingdom) (PLDI '14). ACM, New York, NY, USA, 216-226. https://doi.org/10.1145/2594291.2594334
- [34] Eric Lo, Carsten Binnig, Donald Kossmann, M. Tamer Özsu, and Wing-Kai Hon. 2010. A framework for testing DBMS features. The VLDB Journal 19, 2 (01 Apr 2010), 203-230. https://doi.org/10.1007/s00778-009-0157-y
- [35] Ryan Marcus, Parimarjan Negi, Hongzi Mao, Chi Zhang, Mohammad Alizadeh, Tim Kraska, Olga Papaemmanouil, and Nesime Tatbul. 2019. Neo: A Learned Query Optimizer. Proc. VLDB Endow. 12, 11 (July 2019), 1705-1718. https://doi.org/10.14778/3342263.3342644
- [36] William M McKeeman. 1998. Differential testing for software. Digital Technical Journal 10, 1 (1998), 100-107.
- [37] Chaitanya Mishra, Nick Koudas, and Calisto Zuzarte. 2008. Generating Targeted Queries for Database Testing. In Proceedings of the 2008 ACM SIGMOD International Conference on Management of Data (Vancouver, Canada) (SIGMOD '08). ACM, New York, NY, USA, 499-510. https://doi.org/10.1145/1376616.1376668
- [38] Andrea Neufeld, Guido Moerkotte, and Peter C. Lockemann. 1993. Generating Consistent Test Data: Restricting the Search Space by a Generator Formula. The VLDB Journal 2, 2 (April 1993), 173-214.
- [39] Thomas Neumann and Bernhard Radke. 2018. Adaptive Optimization of Very Large Join Queries. In Proceedings of the 2018 International Conference on Management of Data (Houston, TX, USA) (SIGMOD '18). Association for Computing Machinery, New York, NY, USA, 677-692. https://doi.org/10.1145/3183713.3183733
- [40] Stack Overflow. 2019. Developer Survey Results 2019. https://insights.stackoverflow.com/survey/2019
- [41] Andrew Pavlo and Matthew Aslett. 2016. What's Really New with NewSQL? SIGMOD Rec. 45, 2 (Sept. 2016), 45-55. https://doi.org/10.1145/3003665.3003674
- [42] Meikel Poess and John M. Stephens. 2004. Generating Thousand Benchmark Queries in Seconds. In Proceedings of the Thirtieth International Conference on Very Large Data Bases - Volume 30 (Toronto, Canada) (VLDB '04). VLDB Endowment, 1045-1053.
- [43] John Regehr, Yang Chen, Pascal Cuoq, Eric Eide, Chucky Ellison, and Xuejun Yang. 2012. Test-Case Reduction for C Compiler Bugs. In Proceedings of the 33rd ACM SIGPLAN Conference on Programming Language Design and Implementation (Beijing, China) (PLDI '12). Association for Computing Machinery, New York, NY, USA, 335-346. https://doi.org/10.1145/2254064.2254104
- [44] Manuel Rigger. 2019. LEFT JOIN in view malfunctions with NOTNULL. https://www.sqlite.org/src/tktview?name=c31034044b
- [45] Manuel Rigger and Zhendong Su. 2020. ESEC/FSE 20 Artifact for "Detecting Optimization Bugs in Database Engines via Non-Optimizing Reference Engine Construction". https://doi.org/10.5281/zenodo.3947858
- [46] Manuel Rigger and Zhendong Su. 2020. Testing Database Engines via Pivoted Query Synthesis.
- [47] Sergio Segura and Zhi Quan Zhou. 2018. Metamorphic Testing 20 Years Later: A Hands-on Introduction. In Proceedings of the 40th International Conference on Software Engineering: Companion Proceedings (Gothenburg, Sweden) (ICSE '18). Association for Computing Machinery, New York, NY, USA, 538-539. https://doi.org/10.1145/3183440.3183468
- [48] P. Griffiths Selinger, M. M. Astrahan, D. D. Chamberlin, R. A. Lorie, and T. G. Price. 1979. Access Path Selection in a Relational Database Management System. In Proceedings of the 1979 ACM SIGMOD International Conference on Management of Data (Boston, Massachusetts) (SIGMOD '79). Association for Computing Machinery, New York, NY, USA, 23-34. https://doi.org/10.1145/582095.582099
- [49] Andreas Seltenreich. 2019. SQLSmith. https://github.com/anse1/sqlsmith
- [50] Donald R Slutz. 1998. Massive stochastic testing of SQL. In VLDB, Vol. 98. 618-622.
- [51] SQLite3. 2020. Generated Columns. https://sqlite.org/gencol.html
- [52] SQLite3. 2020. How SQLite Is Tested. https://www.sqlite.org/testing.html
- [53] SQLite3. 2020. Most Widely Deployed and Used Database Engine. https://www.sqlite.org/mostdeployed.html
- [54] SQLite3. 2020. The SQLite Query Optimizer Overview. https://www.sqlite.org/optoverview.html
- [55] SQLite3. 2020. The Use Of assert() In SQLite. https://www.sqlite.org/assert.html
- [56] Rebecca Taft, Irfan Sharif, Andrei Matei, Nathan VanBenschoten, Jordan Lewis, Tobias Grieger, Kai Niemi, Andy Woods, Anne Birzin, Raphael Poss, Paul Bardea, Amruta Ranade, Ben Darnell, Bram Gruneir, Justin Jaffray, Lucy Zhang, and Peter Mattis. 2020. CockroachDB: The Resilient Geo-Distributed SQL Database. In Proceedings of the 2020 ACM SIGMOD International Conference on Management of Data (Portland, OR, USA) (SIGMOD '20). International Foundation for Autonomous Agents and Multiagent Systems, Richland, SC, 1493-1509. https://doi.org/10.1145/3318464.3386134
- [57] Tencent Blade Team. 2019. Magellan 2.0. https://blade.tencent.com/magellan2/index_en.html
- [58] Manasi Vartak, Venkatesh Raghavan, and Elke A. Rundensteiner. 2010. QRelX: Generating Meaningful Queries That Provide Cardinality Assurance. In Proceedings of the 2010 ACM SIGMOD International Conference on Management of Data (Indianapolis, Indiana, USA) (SIGMOD '10). Association for Computing Machinery, New York, NY, USA, 1215-1218. https://doi.org/10.1145/1807167.1807323
- [59] Marianne Winslett and Vanessa Braganholo. 2019. Richard Hipp Speaks Out on SQLite. SIGMOD Rec. 48, 2 (Dec. 2019), 39-46. https://doi.org/10.1145/3377330.3377338
- [60] Chenggang Wu, Alekh Jindal, Saeed Amizadeh, Hiren Patel, Wangchao Le, Shi Qiao, and Sriram Rao. 2018. Towards a Learning Optimizer for Shared Clouds. Proc. VLDB Endow. 12, 3 (Nov. 2018), 210-222. https://doi.org/10.14778/3291264.3291267
- [61] Xuejun Yang, Yang Chen, Eric Eide, and John Regehr. 2011. Finding and Understanding Bugs in C Compilers. In Proceedings of the 32Nd ACM SIGPLAN Conference on Programming Language Design and Implementation (San Jose, California, USA) (PLDI '11). ACM, New York, NY, USA, 283-294. https://doi.org/10.1145/1993498.1993532
