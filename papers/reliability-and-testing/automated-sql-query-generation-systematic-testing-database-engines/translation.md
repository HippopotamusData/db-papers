---
paper_id: automated-sql-query-generation-systematic-testing-database-engines
title: Automated SQL Query Generation for Systematic Testing of Database Engines
language: zh-CN
source: source.pdf
---

# Automated SQL Query Generation for Systematic Testing of Database Engines（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

## 作者与机构

- Shadi Abdul Khalek，美国得克萨斯大学奥斯汀分校电气与计算机工程系，Austin, TX, USA；`shadi@mail.utexas.edu`
- Sarfraz Khurshid，美国得克萨斯大学奥斯汀分校电气与计算机工程系，Austin, TX, USA；`khurshid@ece.utexas.edu`

## 出版与许可信息

本文发表于 ASE ’10（2010 年 9 月 20–24 日，比利时安特卫普）。原文许可声明允许为个人或课堂用途免费制作本文全部或部分内容的数字或纸质副本，条件是副本不得为牟利或商业利益制作或分发，并须在首页保留许可声明和完整引文；以其他方式复制、再出版、发布到服务器或重新分发到列表，需要事先取得明确许可和/或付费。原文版权行：Copyright 2010 ACM 978-1-4503-0116-9/10/09 ...\$10.00。

## 摘要

本文提出一种新方法，用于生成语法和语义均正确的 SQL 查询，以测试关系数据库系统。我们利用基于 SAT 的 Alloy 工具集，把生成有效 SQL 查询的问题归约为 SAT 问题。该方法把 SQL 查询约束转换成 Alloy 模型，由此能够生成传统基于文法的生成器无法自动生成的有效查询。

给定数据库模式，我们的新方法与此前的 ADUSA 工作相结合，可以自动生成：（1）用于测试、语法和语义均有效的 SQL 查询；（2）用于填充测试数据库的输入数据；（3）在生成数据上执行给定查询的预期结果。

实验结果表明，我们不仅能自动生成可发现数据库引擎缺陷的有效查询，还能把本工作与此前的 ADUSA 工作结合起来，自动生成输入查询和表，以及预期的查询执行输出，从而实现数据库引擎的自动化测试。

**类别与主题描述符：** D.2.5 [测试与调试]：测试工具；H.2.3 [数据库管理]：语言 - SQL。

**一般术语：** 验证。

**关键词：** SQL；自动查询生成；数据库管理；Alloy。

## 1. 引言

软件测试是验证软件质量最常用的方法。然而，测试通常需要大量人工，其成本往往超过软件开发成本的一半。测试需要复杂输入的应用程序，例如数据库管理系统（DBMS）或编译器，尤其昂贵。自动化能够显著降低测试成本，还能支持系统化测试，从而大幅提高测试有效性。

本文提出一种新的、基于 SAT 的方法，用于自动化数据库管理系统的系统化测试。测试 DBMS 有三个基本步骤：（1）根据数据库模式生成测试查询；（2）生成一组测试数据库（表）；（3）生成预言机，以验证 DBMS 在输入数据库上执行查询所得的结果。以往工作分别研究过这三个步骤，但很大程度上彼此孤立 [7, 8]。原则上可以用蛮力方式组合现有方法来自动化 DBMS 测试，但得到的框架不太可能实用：它会生成数量大到难以承受的测试用例，其中很大一部分冗余或无效，造成大量无谓开销。文献 [6] 等方法面向带基数约束的查询生成；但查询生成器与数据生成器的集成仍然要么是特化的 [8]，要么有时根本无法实现 [6]。一些学术和商业工具研究测试数据库生成问题 [9, 10, 12]，但并不支持查询生成或测试预言机生成。近期的查询感知输入生成工作 [5] 以参数化 SQL 查询为输入，生成输入表和参数值，却不生成预言机。近期方法还提出了查询感知数据库生成 [11, 13]：它们利用查询信息约束数据生成器，使生成的数据库在执行查询时产生有意义的结果。查询感知生成在 DBMS 和数据库应用测试中日益流行 [14, 15]，但仍要求人工提供查询。

随机查询生成器（Random Query Generator，RQG）[4] 是一种流行的查询生成框架，它沿用生成式文法的思路，以 SQL 文法为查询生成基础。给定一套文法，RQG 生成随机查询，并在两个或更多数据库上运行测试、比较结果，从而测试数据库。因为查询完全按文法生成，它会产生大量无效查询和冗余查询。此外，很难验证生成的查询在语法上正确，有时甚至不可能保证这一点 [4]。

本工作的关键认识是，由 SAT 支撑的关系引擎能为统一方法提供可靠而实用的基础；这种方法可以支持 DBMS 测试的三个基本步骤，并生成质量更高的测试套件：生成的查询有效，生成的数据库状态是查询感知的，预期输出则代表有意义的执行。因此，每个测试用例都会检查 DBMS 的某项核心功能。

本文作出以下贡献：

- **基于约束的查询生成。** 我们提出一个利用 Alloy 工具集对实用 SQL 子集的语言约束建模，并自动生成满足这些约束的有效查询的框架。
- **将 SAT 用于查询生成。** 我们提出 SAT 的一种非常规用途：求解 SQL 语言的语法和语义约束，把查询枚举为测试输入。
- **案例研究。** 我们通过案例研究评估本方法，展示它在 DBMS 测试自动化中的作用。

## 2. 示例

本节给出一个简单的自动 SQL 查询生成示例；传统基于文法的生成器无法生成这类查询。我们说明输入数据库模式，以及本方法针对该模式生成的 SQL 查询。

考虑图 1 所示的数据库模式。主键约束、外键约束等 SQL 语句，以及其他不影响 SQL 查询生成的语句，都与本文所解决的问题无关，因而被本方法忽略。图 1 中的 SQL 语句创建两个关系（亦称表）：（1）`students` 表有两个属性，即 `int` 类型的 `id` 和 `varchar` 类型的 `name`；（2）`grades` 表有三个属性，即表示学生 ID 号的 `int` 类型 `studentID`、表示课程 ID 号的 `int` 类型 `courseID`，以及表示该学生在这门课中所得成绩的 `int` 类型 `grade`。

**图 1：数据库模式示例。**

```sql
CREATE TABLE students(
    id int,
    name varchar(50)
);

CREATE TABLE grades(
    studetnID int,
    courseID int,
    grade int
);
```

考虑这样一个 SQL 文法子集：从一个表或两个交叉连接的表中选择至多两个表属性。文法的终结符串是表名和属性名：`students`、`grades`、`id`、`name`、`sID` 和 `courseID`。此外，我们允许在选择字段时使用聚合函数，并只允许 `MAX` 和 `MIN` 两个聚合函数。这个示例所用的 SQL 查询文法如下：

```text
QUERY ::= SELECT FROM
SELECT ::= 'SELECT' selectTerm+
FROM ::= 'FROM' (table | table JOIN table)
selectTerm ::= term | agg(term)
table ::= 'students' | 'grades'
term ::= 'id' | 'name' | 'studentID' | 'courseID' | 'grade'
agg ::= 'MAX' | 'MIN'
```

为这套 SQL 文法自动生成完整 Alloy 模型后，基于 SAT 的 Alloy Analyzer 会把所有 Alloy 公式转换成布尔公式，并枚举满足模型的所有可能解。我们把输出交给具体化程序，将 Alloy 实例转换成完整 SQL 查询。对于本例文法，在最多两个 `SELECT` 项、最多两个 `FROM` 表和两个聚合函数的条件下，Alloy Analyzer 会生成 186 个互不等价的实例[^1]，正好对应预期的 SQL 查询数量。随后，我们自动把每个 Alloy 实例转换成一条 SQL 查询。图 2 是本方法生成的一部分 SQL 查询样例。

**图 2：本方法生成的 SQL 查询。**

```sql
SELECT courseID, studetnID FROM GRADES, STUDENT;
SELECT MAX (courseID), MAX (NAME) FROM GRADES, STUDENT;
SELECT MIN (courseID), MIN (NAME) FROM GRADES, STUDENT;
SELECT courseID FROM GRADES, STUDENT;
SELECT MAX (courseID), MIN (NAME) FROM GRADES, STUDENT;
SELECT MAX (NAME), MIN (courseID) FROM GRADES, STUDENT;
SELECT courseID, MIN (NAME) FROM GRADES, STUDENT;
SELECT courseID, MAX (NAME) FROM GRADES, STUDENT;
SELECT NAME, MAX (courseID) FROM GRADES, STUDENT;
SELECT NAME FROM STUDENT;
SELECT MIN (NAME) FROM STUDENT;
SELECT id FROM STUDENT;
SELECT MAX (NAME), MIN (id) FROM STUDENT;
SELECT MAX (id), MIN (NAME) FROM STUDENT;
SELECT id, MAX (NAME) FROM STUDENT;
...
```

[^1]: 如果两条查询的区别仅在于 `SELECT` 项或 `FROM` 表的顺序，就认为它们彼此同构。

## 3. 框架

本节讨论本方法的一般算法。我们考虑 SQL 查询文法的一个子集；所支持的完整文法见图 3。

**图 3：所支持的 SQL 文法。**

```text
QUERY ::= SELECT FROM WHERE GROUP_BY HAVING
SELECT ::= 'SELECT' selectTerm+
selectTerm ::= term | aggregate(term)
FROM ::= 'FROM' (table | table JOIN table)
WHERE ::= 'WHERE' term operator (term | value)
GROUP_BY ::= 'GROUP BY' term
HAVING ::= 'HAVING' term operator value
aggregate ::= 'MAX' | 'MIN' | 'AVG' | 'COUNT'
operator ::= '<' | '<=' | '>' | '>=' | '='
```

Alloy 可以用来建立关系数据库模式的模型[^2]。以第 2 节的示例为例，表模式如图 1 所示。本方法生成一份 Alloy 规约，表示 `students` 和 `grades` 两个表及其各自的属性。为了系统化地为所有表生成 Alloy 模型，我们在 Alloy 中对表和字段的一般表示建模如下：

```alloy
abstract sig FieldNames {}
abstract sig FieldTypes {}
abstract sig Field {
    name : one FieldNames,
    type : one FieldTypes
}
abstract sig TableNames {}
abstract sig Table {
    name : one TableNames,
    fields : some Field
}
```

我们为所有聚合创建一个抽象签名，再用希望采用的聚合函数扩展该签名，从而为聚合函数建模。若像示例文法那样考虑 `MIN` 和 `MAX`，则用以下 Alloy 代码对查询生成中使用的聚合建模：

```alloy
abstract sig AggregateNames {}
one sig MAX extends AggregateNames {}
one sig MIN extends AggregateNames {}
```

[^2]: 关于 Alloy 和 Alloy Analyzer 的详细信息见 [2, 3]。

在 Alloy 中建立 SQL 文法模型，需要把 `SELECT` 和 `FROM` 两部分分别建模为独立实体，以保证生成语法正确的查询。建立查询文法的 Alloy 模型后，我们向模型添加约束，从而剪除无用或语义错误的查询。以下 Alloy 代码为 `SELECT` 和 `FROM` 两部分建模：

```alloy
sig term {
    field : one Field,
    agg : lone AggregateNames
}
one sig SELECT {
    fields : some term
}
one sig FROM {
    tables: some Table
}
```

本方法读取数据库模式，自动为表和字段生成签名及约束。首先，我们用表示数据库模式中所有字段名和表名的元素填充 `FieldNames` 与 `TableNames`。我们使用 `extends` 关键字扩展模型中已有的签名。由于这些元素在查询中使用时是单例，未使用时为空，因此还采用了多重性 `lone`。以下 Alloy 代码涵盖本例中生成查询时可能用到的全部字段名和表名：

```alloy
lone sig id, name, studentID, courseID, grade
    extends FieldNames {}
one sig students, grades extends TableNames {}
```

随后，我们自动为表中每个字段创建签名。这些签名扩展 `Field` 类型。此外，对于扩展得到的每种 `Field` 类型，我们都会显式设置关系约束，明确指定每个字段的名称和类型。类似地，对模式中的每个表，我们创建一个扩展 `Table` 类型的签名。

这为生成语法正确的 SQL 查询提供了骨架；我们再向模型添加约束，强制生成语义正确的查询。这里列举其中一些约束。为保证只有 `FROM` 子句所选表中的属性才能出现在 `SELECT` 子句中，我们向模型加入以下 Alloy 事实：

```alloy
fact field_in_table {
    all f: term.field | some t: FROM.tables |
        f in t.fields
}
```

类似地，为保证同一个属性在 `SELECT` 子句中只被选择一次，我们加入以下 Alloy 事实：

```alloy
fact unique_select_terms {
    all a, b : SELECT.fields.term |
        (a.field = b.field and a.agg = b.agg) => a=b
}
```

## 4. 案例研究

本节讨论该框架在不同案例研究中的使用。我们基于 SQL 文法的不同子集执行 SQL 查询生成任务。

### 4.1 自动查询生成

在每个案例研究中，我们都用本方法枚举给定模式下所有可能的有效查询，并把方法应用于 SQL 文法的不同子集进行比较。我们仍使用图 1 中由 `student` 和 `grades` 两个表组成的模式。所考虑的 SQL 文法子集见表 1。案例 1 只包含 `SELECT` 和 `FROM` 子句。每项测试又考虑两种情形：（1）`FROM` 部分最多一个表；（2）`FROM` 部分最多两个表。因此，（1）生成的查询包含在（2）之中。

**表 1：每个案例研究使用的 SQL 文法。星号表示各案例共用的终结符值。**

| 案例 | SQL 文法 |
| --- | --- |
| 1 | `QUERY ::= SELECT FROM`<br>`SELECT ::= 'SELECT' selectTerm+`<br>`FROM ::= 'FROM' (table \| table JOIN table)` |
| 2 | `QUERY ::= SELECT FROM WHERE`<br>`SELECT ::= 'SELECT' selectTerm+`<br>`FROM ::= 'FROM' (table \| table JOIN table)`<br>`WHERE ::= 'WHERE' term operator (term \| value)` |
| 3 | `QUERY ::= SELECT FROM GROUP_BY HAVING`<br>`SELECT ::= 'SELECT' selectTerm+`<br>`FROM ::= 'FROM' (table \| table JOIN table)`<br>`GROUP_BY ::= 'GROUP BY' term`<br>`HAVING ::= 'HAVING' term operator value` |
| * | `selectTerm ::= term \| agg(term)`<br>`term ::= 'id' \| 'name' \| 'studentID' \| 'courseID' \| 'grade'`<br>`agg ::= 'MAX' \| 'MIN'`<br>`table ::= 'students' \| 'grades'` |

表 2 给出了结果。案例 2 的查询总数急剧增长，原因在于 `WHERE` 子句可以包含来自表、且不受 `SELECT` 语句约束的项，而每个项又可以与另一项或一个值建立关系，所以可能的查询数量增加。案例 3 在 `FROM` 部分最多使用一个表时生成的查询最少，因为所有生成的查询都必须满足 `GROUP BY` 和 `HAVING` 两项约束。在案例 3 的文法中，`GROUP BY` 和 `HAVING` 子句都是必选项，这限制了输出空间。

**表 2：各案例研究的求解时间。** `#Tables` 是 `FROM` 部分允许的最大表数；主变量和总变量是生成布尔公式时使用的 Alloy 变量；子句是布尔子句；求解时间是 SAT 为布尔公式生成第一个可能解所用的时间（后续解耗时可忽略）；每查询具体化时间是本方法把一个 Alloy 实例具体化为 SQL 查询的处理时间，单位为毫秒；`#Queries` 是相应案例研究生成的查询总数。

| 案例 | #Tables | 主变量 | 总变量 | 子句 | 求解时间 | 每查询具体化时间 | #Queries |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 1 | 155 | 1586 | 2648 | 375 | 4.03 | 66 |
| 1 | 2 | 155 | 1586 | 2652 | 343 | 3.53 | 186 |
| 2 | 1 | 247 | 3013 | 5135 | 390 | 3.86 | 3456 |
| 2 | 2 | 247 | 3011 | 5129 | 422 | 5.13 | 27081 |
| 3 | 1 | 263 | 3209 | 5524 | 437 | 4.61 | 26 |
| 3 | 2 | 263 | 3210 | 5528 | 422 | 4.08 | 76 |

### 4.2 与 ADUSA 集成

自动生成语法和语义均有效的 SQL 查询，其动机之一是自动化数据库测试的三个基本步骤。我们此前的“使用 SAT 的自动化数据库测试”（Automated Database Testing Using SAT，ADUSA）工作 [1] 采用基于模型的测试来完成：（1）查询感知数据库生成，即构造覆盖多种查询执行场景的实用测试输入套件；（2）测试预言机生成，即验证所生成数据库上的查询执行结果。ADUSA 的输入为：（1）数据库模式；（2）SQL 查询。它用有意义的数据填充数据库，并用自动生成的预言机验证查询在该数据库上的执行结果。

本方法填补了 ADUSA 需要用户提供 SQL 查询这一缺口。给定输入模式，本方法自动生成用于测试的有效 SQL 查询，再由 ADUSA 把这些查询与模式一起用于数据库系统的黑盒测试。两种方法都以 Alloy 和 SAT 为基础，因而可以合并 Alloy 模型，减少求解模型所用的变量数。ADUSA 生成的测试发现并复现了 Oracle 11g、MySQL 4.0 和 HSQLDB（注入缺陷）中的缺陷 [1]。

## 5. 未来工作与结论

本方法展示了如何用 Alloy 和 Alloy Analyzer 对 SQL 查询文法的一个子集及其约束建模，确保生成查询的语法和语义有效。该方法可以扩展；我们能够系统化地增加对更大 SQL 文法子集的支持。例如，本文展示了如何把表属性类型集成进框架；这些类型可以用来为 `WHERE`、`GROUP BY` 和 `HAVING` 子句添加类型检查约束。SQL 事务文法也可以扩展。可以通过把文法修改为如下形式，引入 `DELETE` 语句：

```sql
DELETE FROM TABLE WHERE term in
    (SELECT term FROM table WHERE condition)
```

被删除的项必须与所选项相同，这一约束很容易用 Alloy 表达。还可以扩展嵌套 `SELECT` 语句，只需保证内部 `SELECT` 语句可以访问外部 `SELECT` 的项，而反向访问不成立。

综上，本文提出一种新的 SQL 查询生成方法，以自动化 DBMS 测试。该方法自动生成语法和语义均有效的 SQL 查询。与此前的 ADUSA 工作结合后，我们能够生成：（1）测试 SQL 查询；（2）查询感知输入数据库；（3）用于验证查询执行结果的测试预言机。

本方法利用基于 SAT 的 Alloy 工具集。我们在 Alloy 中系统化地建立 SQL 查询模型，添加约束以确保查询具有语义，再用 Alloy Analyzer 从模型中生成可能的测试查询。

我们比较了本方法针对不同 SQL 文法子集的输出。该框架与此前工作结合后，可以在不同数据库引擎中发现新缺陷并复现缺陷。

## 致谢

本工作部分受 NSF 资助，项目编号为 IIS-0438967、CCF-0845628 和 CNS-0958231；同时受 AFOSR 资助，项目编号为 FA9550-09-1-0351。

## 6. 参考文献

- [1] Shadi A. Khalek, Bassem Elkarablieh, Y. O. Laleye, and Sarfraz Khurshid. Query-Aware Test Generation Using a Relational Constraint Solver. In *ASE '08: Proceedings of the 2008 23rd IEEE/ACM International Conference on Automated Software Engineering*, pages 238-247, 2008.
- [2] Daniel Jackson. Alloy: A lightweight object modeling notation. *ACM Transactions on Software Engineering and Methodology (TOSEM)*, 11(2), April 2002.
- [3] Emina Torlak and Daniel Jackson. Kodkod: A relational model finder. In *Tools and Algorithms for the Construction and Analysis of Systems*, Vol. 4424, pages 632-647. 2007.
- [4] MySQL Forge Random Query Generator. <http://forge.mysql.com/wiki/RandomQueryGenerator/>.
- [5] Margus Veanes, Nikolai Tillmann, and Jonathan de Halleux. Qex: Symbolic SQL Query Explorer. Microsoft Research Technical Report MSR-TR-2009-2015, October 2009.
- [6] Nicolas Bruno, Surajit Chaudhuri, and Dilys Thomas. Generating queries with cardinality constraints for DBMS testing. *IEEE Transactions on Knowledge and Data Engineering*, 18(12):1721-1725, 2006.
- [7] Donald R. Slutz. Massive stochastic testing of SQL. In *VLDB '98, Proceedings of 24rd International Conference on Very Large Data Bases, August 24-27, 1998, New York City, New York, USA*, pages 618-622. Morgan Kaufmann, 1998.
- [8] Meikel Poess and Jr. John M. Stephens. Generating thousand benchmark queries in seconds. In *VLDB '2004: Proceedings of the Thirtieth International Conference on Very Large Data Bases*, pages 1045-1053, 2004.
- [9] Nicolas Bruno and Surajit Chaudhuri. Flexible database generators. In *VLDB '05: Proceedings of the 31st International Conference on Very Large Data Bases*, pages 1097-1107. VLDB Endowment, 2005.
- [10] Kenneth Houkjaer, Kristian Torp, and Rico Wind. Simple and realistic data generation. In *VLDB '06: Proceedings of the 32nd International Conference on Very Large Data Bases*, pages 1243-1246. VLDB Endowment, 2006.
- [11] Carsten Binnig, Donald Kossmann, and Eric Lo. Reverse query processing. In *ICDE*, pages 506-515. IEEE, 2007.
- [12] IBM DB2. Test database generator. <http://www.ibm.com/software/data/db2imstools/db2tools/db2tdbg/>.
- [13] Carsten Binnig, Donald Kossmann, Eric Lo, and M. Tamer Özsu. Qagen: generating query-aware test databases. In *SIGMOD Conference*, pages 341-352, 2007.
- [14] Michael Emmi, Rupak Majumdar, and Koushik Sen. Dynamic test input generation for database applications. In *ISSTA '07: Proceedings of the 2007 International Symposium on Software Testing and Analysis*, pages 151-162, 2007.
- [15] David Willmor and Suzanne M. Embury. An intensional approach to the specification of test cases for database applications. In *ICSE '06: Proceeding of the 28th International Conference on Software Engineering*, pages 102-111, New York, NY, USA, 2006. ACM.
