---
paper_id: random-sampling-with-a-reservoir
title: Random Sampling with a Reservoir
language: zh-CN
source: source.pdf
---

# Random Sampling with a Reservoir（中文译文）

## 译者说明

本文依据同目录的 `source.pdf` 翻译。章节、图表、公式、算法、代码与参考文献按原文结构保留。

Jeffrey Scott Vitter

布朗大学

## 摘要

我们提出若干快速算法，用于从由 $N$ 条记录组成的总体中无放回地选取 $n$ 条记录的随机样本，其中 $N$ 的值事先未知。本文的主要结果是算法 Z 的设计与分析；它以一次遍历、常数空间和 $O(n(1+\log(N/n)))$ 的期望时间完成抽样，而这一时间在常数因子的意义下是最优的。文中还考察了若干优化，它们共同使该算法朴素版本的速度提升一个数量级。我们给出一个纳入这些修改、适合一般用途的高效 Pascal 风格实现。理论结果和经验结果表明，算法 Z 显著优于当时已有的方法。

**CR 分类与主题描述词：** G.3［计算数学］：概率与统计——概率算法、随机数生成、统计软件；G.4［计算数学］：数学软件——算法分析

**一般术语：** 算法、设计、性能、理论

**其他关键词与短语：** 算法分析、优化、随机抽样、拒绝法、蓄水池

## 1. 引言

随机抽样是计算机科学、统计学和工程领域许多计算机应用的基础。问题是从大小为 $N$ 的集合中无放回地选出大小为 $n$ 的随机样本。例如，我们可能想从 $N$ 条记录的总体中随机抽取 $n$ 条记录，我们也可能需要从集合 $\lbrace 1,2,\ldots,N\rbrace$ 中随机抽取 $n$ 个整数。

当 $N$ 的值事先已知时，人们已经为这个问题开发出许多算法 [1, 2, 3, 6, 7, 8, 10]。本文中，我们研究一个很不相同的问题：当 $N$ 未知且无法高效确定时如何抽样。例如，要从长度不确定的磁带所保存的记录中抽样，就会遇到这个问题。一种做法是在第一遍扫描中确定 $N$，再于第二遍扫描中使用文献 [10] 的方法之一。然而，预先确定 $N$ 并不总是切实可行，甚至可能根本做不到。以磁带为例，额外遍历一遍磁带可能代价很高。

因此，我们把范围限制为：在不知道 $N$ 的情况下，只按顺序遍历记录文件一遍。文献 [10] 中的强大技术可用来为该问题导出若干新的快速算法。本文的主要结果是算法 Z 的设计与分析；它以最优时间和常数空间完成抽样。算法 Z 比当时使用的抽样方法快得多。

我们在本文比较算法时采用的性能度量是中央处理器（CPU）时间。输入/输出（I/O）时间则不计，理由如下：该问题的任何算法都可以用我们在第 3 节提出的框架实现。该框架利用磁盘的随机访问能力以及现代磁带机的快速前进能力，大幅减少 I/O 时间；无论使用哪一种算法，所得 I/O 时间都相同。剩余瓶颈通常是 CPU 时间。我们提出的算法显著缩短了 CPU 时间，使之不再成为瓶颈。

事实证明，所有只遍历文件一遍的抽样方法都可以刻画为蓄水池算法。下一节我们定义我们所说的蓄水池算法，并讨论此前解决这一问题的首选方法——算法 R。第 3 节我们提出描述蓄水池算法的新框架，并推导所需 CPU 时间的下界。第 4 节提出并分析算法 X 和 Y。主要结果算法 Z 在第 5 节给出。第 6 节我们给出若干优化，把算法 Z 朴素版本的 CPU 时间缩短约 8 倍。第 7 节进行理论分析。第 8 节给出纳入第 6 节优化的算法 Z 高效实现。表 I 汇总这些算法的性能。

第 9 节的经验计时支持理论结果，并表明算法 Z 大幅优于其他方法。在 VAX 11/780 上，算法 R、X、Z 的优化 FORTRAN 77 实现所需 CPU 时间（微秒）分别约为 $160N$、 $40N$ 和 $950n\ln(N/n)-1250n$。第 10 节总结我们的结果。

**表 I　算法 R、X、Y、Z 的性能**

| 算法 | 均匀随机变量的平均个数 | 平均 CPU 时间 |
| --- | ---: | ---: |
| R | $N-n$ | $O(N)$ |
| X | $\approx 2n\ln(N/n)$ | $O(N)$ |
| Y | $\approx 2n\ln(N/n)$ | $O\left(n^2\left(1+\log(N/n)\log\log(N/n)\right)\right)$ |
| Z | $\approx 3n\ln(N/n)$ | $O\left(n\left(1+\log(N/n)\right)\right)$ |

### 首页出版与版权信息

本研究部分得到 NSF 研究资助 MCS-81-05324 和 DCR-84-03613、IBM 研究合同、IBM Faculty Development Award，以及 ONR 与 DARPA 在合同 N00014-83-K-0146 和 ARPA Order No. 4786 下的支持。本研究的扩展摘要见文献 [11]。

通信地址：Department of Computer Science, Brown University, Providence, RI 02912。

在复制品不为直接商业利益制作或分发、复制品载有 ACM 版权声明以及出版物标题和日期，并注明复制已获 Association for Computing Machinery 许可的条件下，可以免费复制本文全部或部分内容。其他复制或再出版须缴费和/或取得明确许可。

© 1985 ACM 0098-3500/85/0300-0037 \$00.75。

发表于 *ACM Transactions on Mathematical Software*，第 11 卷第 1 期，1985 年 3 月，第 37–57 页。

## 2. 蓄水池算法与算法 R

我们在本文研究的所有算法都是蓄水池算法的实例。下一节我们将看到，这个抽样问题的每一种算法都必定是某种蓄水池算法。蓄水池算法的基本思想是选取一个大小至少为 $n$ 的样本，再从中生成大小为 $n$ 的随机样本。蓄水池算法定义如下。

**定义 1。** 任何蓄水池算法的第一步都是把文件的前 $n$ 条记录放入一个“蓄水池”。其余记录按顺序处理；只有处理到某条记录时，才能把它选入蓄水池。如果一个算法保持如下不变式，它就是蓄水池算法：每处理完一条记录，都能从蓄水池的当前状态中抽取出处理至今所有记录的一个大小为 $n$ 的真正随机样本。

顺序遍历文件结束时，必须从蓄水池中抽取最终随机样本。蓄水池可能相当大，因此这个过程可能很昂贵。最高效的蓄水池算法——包括我们在本文讨论的算法——通过始终在蓄水池中维护 $n$ 个指定的候选记录来避免这一步；这些候选记录构成处理至今所有记录的真正随机样本。当一条记录被选入蓄水池时，它成为候选记录并替换原候选记录之一；顺序遍历结束时，把当前的 $n$ 个候选记录作为最终样本输出。

算法 R（由 Alan Waterman 提出的一种蓄水池算法）的工作方式如下。处理文件中的第 $t+1$ 条记录时，其中 $t\ge n$， $n$ 个候选记录构成前 $t$ 条记录的随机样本。在前 $t+1$ 条记录中大小为 $n$ 的随机样本里，第 $t+1$ 条记录出现的概率为 $n/(t+1)$，所以以概率 $n/(t+1)$ 把它设为候选记录。它所替换的候选记录从原有 $n$ 个候选记录中随机选取。容易看出，所得 $n$ 个候选记录构成前 $t+1$ 条记录的随机样本。

完整算法如下。当前 $n$ 个候选记录保存在数组 $C$ 的位置 $C[0],C[1],\ldots,C[n-1]$ 中。内建布尔函数 `eof` 在到达文件末尾时返回 `true`。随机数生成器 `RANDOM` 返回单位区间中的一个实数。过程调用 `READ_NEXT_RECORD(R)` 读取文件中的下一条记录并存入记录 $R$。过程调用 `SKIP_RECORDS(k)` 读过（即跳过）文件中的接下来 $k$ 条记录。

```text
{把前 n 条记录设为样本候选记录}
for j := 0 to n - 1 do READ_NEXT_RECORD(C[j]);
t := n;                         {t 是处理至今的记录数}
while not eof do                {处理其余记录}
    begin
    t := t + 1;
    M := TRUNC(t × RANDOM());   {M 在 0 ≤ M ≤ t - 1 中均匀随机}
    if M < n then               {让下一条记录成为候选并随机替换一个候选}
        READ_NEXT_RECORD(C[M])
    else                        {跳过下一条记录}
        SKIP_RECORDS(1)
    end;
```

到达文件末尾时，数组 $C$ 中的 $n$ 个候选记录构成文件全部 $N$ 条记录的真正随机样本。

如果内存不足以保存 $n$ 个候选记录，可以如下修改算法。蓄水池顺序存放在辅助存储器上；指向当前候选记录的指针保存在我们称为 $I$ 的内存数组中。（我们假设空间足以保存 $n$ 个指针。）假设算法执行过程中记录 $R'$ 被选为候选，用来替换由 $I[k]$ 指向的记录 $R$。原文随后写道：把记录 $R$ 顺序写入辅助存储器，并令 `I[k]` 指向 $R$；这与前句中的 $R'$ 以及紧随其后的代码可能不一致。可用下面的代码替换上述代码最初的 `for` 循环：

```text
for j := 0 to n - 1 do
    begin
    把第 j 条记录复制到辅助存储器；
    令 I[j] 指向第 j 条记录；
    end;
```

程序语句 `READ_NEXT_RECORD(C[M])` 应替换为：

```text
begin
把下一条记录复制到辅助存储器；
令 I[M] 指向该记录
end
```

按顺序取回记录可以加快从辅助存储器取得最终样本的速度。具体做法是对指针 $I[1],I[2],\ldots,I[n]$ 排序。由于排序可以在内存中完成，所以应当很快。

算法结束时，蓄水池中记录数的平均值为

$$
n+\sum _ {n\le t\lt N}\frac{n}{t+1}
=n(1+H _ N-H _ n)
\approx n\left(1+\ln\frac{N}{n}\right).
\tag{2.1}
$$

记号 $H _ k$ 表示“第 $k$ 个调和数”，定义为 $\sum _ {1\le i\le k}1/i$。对上述推导略作修改可知，在已经处理 $t$ 条记录之后，随后被选入蓄水池的记录数平均为

$$
n(H _ N-H _ t)\approx n\ln\frac{N}{t}.
\tag{2.2}
$$

算法 R 显然以 $O(N)$ 时间运行，因为必须扫描整个文件，而每条记录可在常数时间内处理。利用我们在下一节开发的框架可以容易地重写该算法，使 I/O 时间从 $O(N)$ 降为 $O(n(1+\log(N/n)))$。

## 3. 我们的蓄水池算法框架

该抽样问题对算法的限制是：记录必须按顺序读取，并且每条最多读取一次。这意味着，该问题的任何算法都必须维护一个蓄水池，其中包含处理至今所有记录的一个大小为 $n$ 的随机样本。这为我们给出下面的推广。

**定理 1。** 该抽样问题的每一种算法都是某种蓄水池算法。

我们用 $t$ 表示处理至今的记录数。如果文件包含 $t+1$ 条记录，则每条记录进入大小为 $n$ 的真正随机样本的概率都是 $n/(t+1)$。这意味着，应当以至少 $n/(t+1)$ 的概率把第 $t+1$ 条记录选入蓄水池。因此，蓄水池的平均大小必须至少与算法 R 一样大，即 $n(1+H _ N-H _ n)\approx n(1+\ln(N/n))$。这给出了完成抽样所需时间的下界。

我们在本文中用来开发比算法 R 更快的蓄水池算法的框架，围绕下面的随机变量展开。

**定义 2。** 随机变量 $\mathcal{S}(n,t)$ 定义为：在下一条记录被选入蓄水池之前，文件中跳过的记录数；其中 $n$ 是样本大小， $t$ 是处理至今的记录数。为简化记号，我们经常把 $\mathcal{S}(n,t)$ 简写成 $\mathcal{S}$，此时参数 $n$ 和 $t$ 是隐含的。

我们的蓄水池算法的基本思想是反复生成 $\mathcal{S}$，跳过这么多条记录，再把下一条记录选入蓄水池。与算法 R 一样，我们在蓄水池中维护 $n$ 个候选记录。起初，我们把前 $n$ 条记录选作候选，并令 $t:=n$。我们的蓄水池算法具有以下基本框架：

```text
while not eof do                       {处理其余记录}
    begin
    生成独立随机变量 S(n,t)；
    SKIP_RECORDS(S);                   {跳过接下来的 S 条记录}
    if not eof then
        begin                          {让下一条记录成为候选并随机替换一个候选}
        M := TRUNC(n × RANDOM());      {M 在 0 ≤ M ≤ n - 1 中均匀分布}
        READ_NEXT_RECORD(C[M])
        end
    t := t + S + 1;
    end;
```

我们的各个抽样算法之间的区别在于如何生成 $\mathcal{S}$。算法 R 可以放进这个框架：它用 $O(\mathcal{S})$ 时间和 $O(\mathcal{S})$ 次 `RANDOM` 调用生成 $\mathcal{S}$。我们在本文提出的三个新算法——X、Y、Z——生成 $\mathcal{S}$ 的速度都比算法 R 快。第 5–9 节讨论的算法 Z 平均以常数时间生成 $\mathcal{S}$，因而由式 (2.1)，其平均运行时间为 $O(n(1+\log(N/n)))$。根据我们在上面推导的下界，这在常数因子的意义下是最优的。

$\mathcal{S}(n,t)$ 的取值范围是非负整数集合。对于 $s\ge0$，其分布函数 $F(s)=\mathrm{Prob}\lbrace \mathcal{S}\le s\rbrace$ 可以写成两种形式：

$$
F(s)=1-\frac{t^{\mathit{fall}(n)}}{(t+s+1)^{\mathit{fall}(n)}}
=1-\frac{(t+1-n)^{\mathit{rise}(s+1)}}{(t+1)^{\mathit{rise}(s+1)}}.
\tag{3.1}
$$

下文用 $a^{\mathit{fall}(b)}$ 表示原文带下划线的“下降幂”记号，其值为 $a(a-1)\cdots(a-b+1)=a!/(a-b)!$；相应地，用 $a^{\mathit{rise}(b)}$ 表示原文带上划线的“上升幂”记号，其值为 $a(a+1)\cdots(a+b-1)=(a+b-1)!/(a-1)!$。对于 $s\ge0$，概率函数 $f(s)=\mathrm{Prob}\lbrace \mathcal{S}=s\rbrace$ 对应的两种表达式为

$$
f(s)=\frac{n}{t+s+1}\frac{t^{\mathit{fall}(n)}}{(t+s)^{\mathit{fall}(n)}}
=\frac{n}{t-n}\frac{(t-n)^{\mathit{rise}(s+1)}}{(t+1)^{\mathit{rise}(s+1)}}.
\tag{3.2}
$$

$\mathcal{S}$ 的期望值为

$$
\mathrm{expected}(\mathcal{S})
=nt^{\mathit{fall}(n)}\sum _ {0\le s}\frac{s}{(t+s+1)^{\mathit{fall}(n+1)}}
=\frac{t-n+1}{n-1}.
\tag{3.3}
$$

可以用分部求和推导该式：

$$
\sum _ {a\le s\lt b}u(s)\thinspace \Delta v(s)
=\left.u(s)v(s)\right| _ a^b
-\sum _ {a\le s\lt b}v(s+1)\thinspace \Delta u(s),
$$

其中 $\Delta u(s)=u(s+1)-u(s)$。我们取 $u=s$， $\Delta v=1/(t+s+1)^{\mathit{fall}(n+1)}$。 $\mathcal{S}$ 的标准差约等于 $\mathrm{expected}(\mathcal{S})$，但略大一些。

每选中一个候选记录，就生成一个随机变量 $\mathcal{S}$。如果最后选中的候选不是文件中的第 $N$ 条记录，就要额外生成一次 $\mathcal{S}$ 才能越过文件末尾；这种情况的概率为 $1-n/N$。把这一点与式 (2.2) 结合，我们发现：在已经处理 $t$ 条记录后， $\mathcal{S}$ 的平均生成次数为 $n(H _ N-H _ t)+1-n/N$。

## 4. 算法 X 与 Y

本节我们使用上一节开发的框架来开发两个新算法。为了生成服从分布 $F(s)$ 的独立随机变量 $\mathcal{S}$，我们可以先生成独立均匀随机变量 $\mathcal{U}$，再把 $\mathcal{S}$ 设为满足 $\mathcal{U}\le F(s)$ 的最小 $s\ge0$。把式 (3.1) 代入 $F(s)$，停止条件等价于

$$
\frac{(t+1-n)^{\mathit{rise}(s+1)}}{(t+1)^{\mathit{rise}(s+1)}}\le1-\mathcal{U}.
$$

由于 $\mathcal{U}$ 独立且均匀分布， $1-\mathcal{U}$ 也独立且均匀分布。因此，我们可以把不等式中的 $1-\mathcal{U}$ 换成一个独立均匀随机变量，我们称为 $\mathcal{V}$。新的停止条件是

$$
\frac{(t+1-n)^{\mathit{rise}(s+1)}}{(t+1)^{\mathit{rise}(s+1)}}\le\mathcal{V}.
\tag{4.1}
$$

### 算法 X

算法 X 用简单的顺序搜索找出满足式 (4.1) 的最小 $s\ge0$：

```text
V := RANDOM();  {V 在单位区间上均匀分布}
顺序搜索满足 (t + 1 - n)^(overline(s + 1)) /
              (t + 1)^(overline(s + 1)) ≤ V 的最小 s ≥ 0；
S := s;
```

我们把式 (4.1) 左端记为 $H(s)$。该方法之所以快，是因为可以从 $H(s)$ 在常数时间内算出 $H(s+1)$；顺序搜索需要 $O(\mathcal{S}+1)$ 时间。当 $n=1$ 时，式 (3.3) 表明 $\mathrm{expected}(\mathcal{S})$ 无界，因此不应使用算法 X。若 $n\gt 1$，算法 X 的总运行时间平均为 $O(\sum\mathcal{S})=O(N)$。算法 R 和 X 的执行时间都是 $O(N)$，但算法 X 快数倍，因为每生成一次 $\mathcal{S}$，它只调用一次 `RANDOM`，而不是调用 $O(\mathcal{S})$ 次。算法 X 的 Pascal 风格代码出现在第 8 节算法 Z 实现的第一部分。

### 算法 Y

寻找满足式 (4.1) 的最小 $s$，另一种方法是二分搜索；更好的方法是采用 Newton 插值法的一个变体，算法 Y 便以后一种方法为基础。

我们要找的 $s$ 是方程

$$
H(s)\approx\mathcal{V}
$$

的“近似根”。这里我们使用离散版 Newton 法。我们不用 $H(s)$ 的导数，而使用差分函数

$$
\Delta H(s)=H(s+1)-H(s)=-f(s+1).
$$

我们可以证明，Newton 法在 $O(1+\log\log\mathcal{S})$ 次迭代内收敛并给出 $\mathcal{S}$ 的值。（我们约定当 $\mathcal{S}\le b$ 时定义 $\log\log\mathcal{S}=0$，其中 $b$ 是对数的底。）每次迭代都要计算 $H(s)$ 和 $\Delta H(s)$，耗时 $O(n)$。总运行时间由下面的定理给出。

**定理 2。** 用算法 Y 完成抽样的平均运行时间为

$$
O\left(n^2\left(1+\log\frac{N}{n}\log\log\frac{N}{n}\right)\right).
$$

**证明。** 根据上述讨论，算法 Y 的运行时间为

$$
O\left(n\sum _ {1\le i\le\mathcal{T}}(1+\log\log\mathcal{S} _ i)\right),
\tag{4.2}
$$

其中 $\mathcal{S} _ i$ 表示生成的第 $i$ 个 $\mathcal{S}$ 值， $\mathcal{T}$ 表示算法终止前 $\mathcal{S}$ 的生成次数。用概率论术语说， $\mathcal{T}$ 是有界停止时刻，因为必有 $\mathcal{T}\le N-n$。我们把 $1+\log\log\mathcal{S} _ i$ 记为 $\mathcal{L} _ i$。随机变量 $\mathcal{L} _ 1,\mathcal{L} _ 2,\mathcal{L} _ 3,\ldots$ 并不相互独立，因为 $\mathcal{S}$ 的分布函数 $F(s)$ 取决于 $t$ 的当前值。不过，我们可以用随机变量 $\mathcal{L}' _ i=1+\log\log\mathcal{S}(n,N-1)$ 来“界定”每个 $\mathcal{L} _ i$，并令 $\mathcal{L}' _ 1,\mathcal{L}' _ 2,\mathcal{L}' _ 3,\ldots$ 相互独立。我们所谓“界定”，是指 $\mathcal{L}' _ i$ 的分布函数处处大于 $\mathcal{L} _ i$ 的分布函数。如果我们设想用算法 X 或 Y 以及同一个 $\mathcal{V}$ 值，分别先生成 $\mathcal{S} _ i$ 和 $\mathcal{S}(n,N-1)$，这一条件保证 $\mathcal{L} _ i\le\mathcal{L}' _ i$。因此我们可以用下式界定式 (4.2)：

$$
O\left(n\sum _ {1\le i\le\mathcal{T}}(1+\mathcal{L}' _ i)\right).
\tag{4.3}
$$

随机变量 $\mathcal{L}' _ 1,\mathcal{L}' _ 2,\mathcal{L}' _ 3,\ldots$ 独立同分布。我们可以应用 Wald 引理的经典形式（见 [5]），把式 (4.3) 的平均值界定为

$$
O\left(\mathrm{expected}(\mathcal{T})\left(1+\mathrm{expected}(\log\log\mathcal{S}(n,N-1))\right)\right).
\tag{4.4}
$$

我们在上一节末尾已经证明

$$
\mathrm{expected}(\mathcal{T})
=n(H _ N-H _ n)+1-\frac{n}{N}
=O\left(n\left(1+\log\frac{N}{n}\right)\right).
$$

由 Jensen 不等式（见 [4]），当 $n\gt 1$ 时，我们有

$$
\begin{aligned}
\mathrm{expected}(\log\log\mathcal{S}(n,N-1))
&\le\log\log\left(\mathrm{expected}(\mathcal{S}(n,N-1))\right)\\
&=\log\log\frac{N-n}{n-1}\\
&=O\left(\log\log\frac{N}{n}\right).
\end{aligned}
$$

对于 $n=1$，我们可以证明 $\mathrm{expected}(\log\log\mathcal{S}(1,N-1))=O(1)$。综合这些结果，我们可以用 $O(n^2(1+\log(N/n)\log\log(N/n)))$ 界定式 (4.4)。证毕。

使用高阶差分可以获得比 Newton 法更高阶的收敛；高阶差分定义为

$$
\Delta^kH(s)=\Delta^{k-1}H(s+1)-\Delta^{k-1}H(s).
$$

当 $k\gt 1$ 时，每个差分 $\Delta^kH(s)$ 都能从一个低一阶差分用下式在常数时间内算出：

$$
\Delta^kH(s)=-\left(\frac{n+k-1}{t+s+k+1}\right)\Delta^{k-1}H(s).
$$

也许可以把 $k$ 选得足够大，使生成 $\mathcal{S}$ 只需常数次迭代。这样总运行时间将由 $O((k+n)n(1+\log(N/n)))$ 界定。 $k$ 至少为 $\log^{\ast}(N/n)$，其中 $\log^{\ast}x$ 定义为：从参数 $x$ 开始反复应用对数函数，直到结果不大于 1 所需的次数。不过，相关开销很可能太大，因而不切实际。下一节给出一种快得多的算法。

## 5. 算法 Z

算法 Z 遵循我们在第 3 节所述的一般框架。利用 von Neumann 拒绝—接受法的一个修改版本，可以平均在常数时间内生成跳跃随机变量 $\mathcal{S}(n,t)$。主要思想是：我们可以先生成一个快速近似，再“校正”它，使最终分布成为所需的分布 $F(s)$，从而快速生成 $\mathcal{S}$。

我们假设我们拥有一个可以快速生成的连续随机变量 $\mathcal{X}$，它的分布能很好地近似 $F(s)$。我们以 $g(x)$ 表示 $\mathcal{X}$ 的概率密度函数。我们选择常数 $c\ge1$，使得对所有 $x\ge0$ 都有

$$
f(\lfloor x\rfloor)\le c g(x).
\tag{5.1}
$$

我们通过生成相互独立的 $\mathcal{X}$ 和单位区间上的均匀随机变量 $\mathcal{U}$ 来生成 $\mathcal{S}$。如果 $\mathcal{U}\gt f(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$（这以很低的概率发生），我们就拒绝 $\lfloor\mathcal{X}\rfloor$，重新生成新的 $\mathcal{X}$ 和 $\mathcal{U}$。当条件 $\mathcal{U}\le f(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$ 最终成立时，我们接受 $\lfloor\mathcal{X}\rfloor$，并令 $\mathcal{S}:=\lfloor\mathcal{X}\rfloor$。下面的引理容易证明，证明留给读者；它表明该过程有效。

**引理 1。** 按上述方式生成的随机变量 $\mathcal{S}$ 具有式 (3.1) 给出的分布。

这一过程的瓶颈是计算 $f(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$；用式 (3.2) 计算需 $O(\min\lbrace n,\lfloor\mathcal{X}\rfloor+1\rbrace )$ 时间。大多数时候，我们可以用计算更快的函数 $h(s)$ 近似 $f(s)$ 来避免该计算，并且我们让所有 $s\ge0$ 都满足

$$
h(s)\le f(s).
\tag{5.2}
$$

如果 $\mathcal{U}\le h(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$，由传递性我们可得 $\mathcal{U}\le f(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$，所以我们可以接受 $\lfloor\mathcal{X}\rfloor$。只有当 $\mathcal{U}\gt h(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$ 时才必须计算 $f(\lfloor\mathcal{X}\rfloor)$，而这种情况概率很小。该技术有时称为挤压法，因为我们对所有 $x$ 都有 $h(\lfloor x\rfloor)\le f(\lfloor x\rfloor)\le c g(x)$。

由于计算这些函数有开销，当 $t\le Tn$（ $T\gt 1$ 为常数）时，拒绝法生成 $\mathcal{S}$ 比算法 X 使用的方法慢。 $T$ 的典型取值范围预计为 10–40。例如，在第 8、9 节所述实现中，我们采用 $T\approx22$。算法 Z 生成 $\mathcal{S}(n,t)$ 的轮廓如下：

```text
if t ≤ T × n then 使用算法 X 的内循环生成 S
else begin
    repeat
        生成密度函数为 g(x) 的独立随机变量 X；
        U := RANDOM();                       {U 在单位区间上均匀分布}
        if U ≤ h(floor(X))/(c g(X)) then break loop
    until U ≤ f(floor(X))/(c g(X));
    S := floor(X)
    end;
```

开发算法 Z 的难点，是为参数 $g(x)$（ $\mathcal{X}$ 的密度函数）、 $c$ 和 $h(s)$ 找到能带来快速运行时间的适当选择。下面这些选择似乎效果最好：

$$
\begin{aligned}
g(x)&=\frac{n}{t+x}\left(\frac{t}{t+x}\right)^n, &&x\ge0;\\
c&=\frac{t+1}{t-n+1};\\
h(s)&=\frac{n}{t+1}\left(\frac{t-n+1}{t+s-n+1}\right)^{n+1}, &&x\ge0.
\end{aligned}
\tag{5.3}
$$

式 (5.3) 最后一行的定义对象是 $h(s)$，但该行末尾标出的定义域是 $x\ge0$。

随机变量 $\mathcal{X}$ 并不是常见分布，但可在常数时间内快速生成。我们以 $G(x)$ 表示 $\mathcal{X}$ 的分布函数。我们有

$$
G(x)=\mathrm{Prob}\lbrace \mathcal{X}\le x\rbrace
=∫ _ 0^x g(x)\thinspace dx
=1-\left(\frac{t}{t+x}\right)^n.
\tag{5.4}
$$

容易证明，我们可以令 $\mathcal{X}=G^{-1}(\mathcal{V})$ 或 $\mathcal{X}=G^{-1}(e^{-\mathcal{Y}})$ 来生成具有分布 $G(x)$ 的随机变量 $\mathcal{X}$，其中 $\mathcal{V}$ 在 $[0,1]$ 上均匀分布， $\mathcal{Y}$ 服从指数分布。我们代入式 (5.4)，得到

$$
G^{-1}(y)=t\left((1-y)^{-1/n}-t\right).
$$

上式末项为 $-t$；紧随其后的式 (5.5) 末项则为 $-1$。由于 $\mathcal{V}$ 均匀分布时 $1-\mathcal{V}$ 也均匀分布，我们可令

$$
\mathcal{X}:=t(\mathcal{V}^{-1/n}-1)
\qquad\text{或}\qquad
\mathcal{X}:=t(e^{-\mathcal{Y}/n}-1)
\tag{5.5}
$$

原文称上式可用来生成 $\mathcal{X}$；原文此处负指数与前述生成推导及 $\mathcal{X}\ge0$ 可能不一致。

下面的引理表明，式 (5.3) 的参数选择满足式 (5.1) 和 (5.2) 的要求。

**引理 2。** 式 (5.3) 对 $g(x)$、 $c$ 和 $h(s)$ 的选择满足

$$
h(s)\le f(s)\le c g(s+1).
$$

这满足条件 (5.2)。又因为 $g(x)$ 单调递减，所以也蕴含条件 (5.1)。

**证明。** 我们先证明第一个不等式。我们有

$$
\begin{aligned}
h(s)
&=\frac{n}{t+1}\left(\frac{t-n+1}{t+s-n+1}\right)^{n+1}\\
&=\frac{n(t-n+1)}{(t+1)(t+s-n+1)}
  \left(\frac{t-n+1}{t+s-n+1}\right)^n.
\end{aligned}
$$

第一个商可由 $n/(t+s+1)$ 界定，因为容易证明

$$
(t+s-n+1)(t+1)\ge(t+s+1)(t-n+1).
$$

类似地，我们可以用 $t^{\mathit{fall}(n)}/(t+s)^{\mathit{fall}(n)}$ 界定第二个商，因为对于 $0\le k\le n-1$，我们有

$$
\frac{t-n+1}{t+s-n+1}\le\frac{t-k}{t+s-k}.
$$

结合式 (3.2)，即得第一个不等式。引理 2 的第二个不等式可用同样方法证明：

$$
f(s)=\frac{n}{t+s+1}\frac{t^{\mathit{fall}(n)}}{(t+s)^{\mathit{fall}(n)}}
=\frac{n}{t+s-n+1}\frac{t^{\mathit{fall}(n)}}{(t+s+1)^{\mathit{fall}(n)}}.
$$

第一个商可由 $n(t+1)/((t+s+1)(t-n+1))$ 界定，因为

$$
(t+s-n+1)(t+1)\ge(t+s+1)(t-n+1).
$$

第二个商可由 $(t/(t+s+1))^n$ 界定，因为对于 $0\le k\le n-1$，

$$
\frac{t-k}{t+s+1-k}\le\frac{t}{t+s+1}.
$$

由式 (5.3)，第二个不等式得证。证毕。

## 6. 优化算法 Z

本节中，我们给出三种优化，能显著改善算法 Z 朴素版本的运行时间。第 8 节的算法 Z 实现纳入了这些修改。

**阈值优化。** 我们在上一节已经介绍这项重要优化，并把它纳入基本算法。我们用常数参数 $T$ 决定如何生成 $\mathcal{S}$：若 $t\le Tn$，用算法 X 的内循环生成 $\mathcal{S}$；否则采用拒绝—接受法。 $T$ 通常取 10–40。第 8、9 节所述实现中， $T\approx22$ 效果最好，运行时间约缩短为四分之一。第 7.3 节给出一些理论分析。不过，这项优化还有一个更根本的重要理由（因此我们把它作为基本算法的一部分）：它能防止浮点溢出。第 8 节还会讨论数值问题。

**`RANDOM` 优化。** 本节其余部分讨论更复杂的技术，用来消除代价高昂的数学子程序调用。我们首先考虑的优化使我们可以把 `RANDOM` 调用次数削减三分之一以上。每次用式 (5.5) 生成 $\mathcal{X}$，都需要生成一个独立均匀随机变量（或者生成指数随机变量，而后者通常也要先生成均匀随机变量）。我们把这个随机变量称为 $\mathcal{V}$。除第一次生成 $\mathcal{X}$ 外，我们可以利用上一轮循环的 $\mathcal{U}$ 和 $\mathcal{X}$，独立地计算 $\mathcal{V}$（进而计算 $\mathcal{X}$），从而避免一次 `RANDOM` 调用。上一轮循环的结束原因有三种： $\mathcal{U}\le q _ 1$、 $q _ 1\lt \mathcal{U}\le q _ 2$ 或 $q _ 2\lt \mathcal{U}$，其中

$$
q _ 1=\frac{h(\lfloor\mathcal{X}\rfloor)}{c g(\mathcal{X})},
\qquad
q _ 2=\frac{f(\lfloor\mathcal{X}\rfloor)}{c g(\mathcal{X})}.
$$

我们可把下一轮循环的 $\mathcal{V}$ 计算为

$$
\mathcal{V}:=
\begin{cases}
\mathcal{U}/q _ 1, & \mathcal{U}\le q _ 1;\\
(\mathcal{U}-q _ 1)/(q _ 2-q _ 1), & q _ 1\lt \mathcal{U}\le q _ 2;\\
(\mathcal{U}-q _ 2)/(1-q _ 2), & q _ 2\lt \mathcal{U}.
\end{cases}
\tag{6.1}
$$

我们把根据独立性的定义和 $\mathcal{V}$ 的定义证明下面的引理留作读者练习。

**引理 3。** 由式 (6.1) 计算的 $\mathcal{V}$ 是均匀随机变量；它独立于此前 $\mathcal{X}$ 的所有取值，也独立于每个 $\mathcal{X}$ 是否被接受。

也可以用类似技巧计算 $\mathcal{M}$ 而不调用 `RANDOM`，但额外工作似乎不值得。更大的节省来自下一项优化。

**子程序优化。** 我们把 $x^y$ 形式的运算次数减半，可以让算法 Z 提速将近 2 倍；这里 $x,y$ 或为实数（浮点数），或为大整数。计算 $x^y=\exp(y\ln x)$ 会隐式调用数学库子程序 `EXP`（指数）和 `LOG`（对数）。它虽然是常数时间运算，但这个常数远大于乘法或除法的耗时。

算法 Z 的朴素实现每轮循环需要两个 $x^y$ 形式的运算：一个用式 (5.5) 从 $\mathcal{V}$ 计算 $\mathcal{X}$，另一个计算

$$
\frac{h(\lfloor\mathcal{X}\rfloor)}{c g(\mathcal{X})}
=\frac{(t-n+1)^2(t+\mathcal{X})}{(t+1)^2(t+\lfloor\mathcal{X}\rfloor-n+1)}
\left(
\frac{(t-n+1)(t+\mathcal{X})}{(t+\lfloor\mathcal{X}\rfloor-n+1)t}
\right)^n.
\tag{6.2}
$$

（计算 $f(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$ 也需要一个 $x^y$ 形式的运算，但正如我们将在下一节看到，该计算很少执行。）我们不再检验“ $\mathcal{U}\le h(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$ 是否成立”，而是采用等价检验：

$$
\left(
\frac{\mathcal{U}(t+1)^2(t+\lfloor\mathcal{X}\rfloor-n+1)}
     {(t-n+1)^2(t+\mathcal{X})}
\right)^{1/n}
\le
\frac{(t-n+1)(t+\mathcal{X})}
     {(t+\lfloor\mathcal{X}\rfloor-n+1)t}.
\tag{6.3}
$$

该检验以高概率为真。若为真，我们就把 $\mathcal{W}$ 设为右端除以左端所得的商。所得随机变量 $\mathcal{W}$ 与 $\mathcal{V}^{-1/n}$ 同分布。因此，我们可以不用 $x^y$ 形式的运算，而令

$$
\mathcal{X}:=t(\mathcal{W}-1).
\tag{6.4}
$$

读者可将此式与式 (5.5) 比较。因此，我们每轮循环通常只需要一次而不是两次 $x^y$ 形式的运算。

用检验 (6.3) 代替朴素的“ $\mathcal{U}\le h(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$ 是否成立”还有一个重要副作用：它消除了式 (6.2) 中可能出现的浮点溢出。在实际实现中，启用子程序优化时不应使用完整的 `RANDOM` 优化。`RANDOM` 优化的 $\mathcal{U}\le q _ 1$ 情形已包含在子程序优化中；式 (6.1) 的另两种情形很少发生，而且启用子程序优化时，实现它们代价很高。

## 7. 算法 Z 的理论分析

本节我们通过分析证明，算法 Z 生成的随机变量平均数以及期望运行时间在常数因子的意义下都是最优的。最后，我们给出理论依据，说明为何上一节阈值优化的参数 $T$ 应设为常数。

### 7.1 `RANDOM` 的平均调用次数

我们将证明：根据是否使用 `RANDOM` 优化，算法 Z 对随机数生成器的期望调用次数分别以约 $3n\ln(N/n)$ 和 $2n\ln(N/n)$ 为界。这表明 `RANDOM` 优化把 `RANDOM` 调用次数减少三分之一。

我们用“算法 Z 的朴素版本”表示纯拒绝技术，连阈值优化也不使用。我们定义 $RAND(n,t,N)$ 为：在已经处理 $t\le N$ 条记录时，算法 Z 的朴素版本完成其余抽样所需的 `RANDOM` 期望调用次数。类似地，我们定义 $OPT(n,t,N)$ 为：从已经处理 $t\le N$ 条记录之处开始，使用 `RANDOM` 优化时 `RANDOM` 的平均调用次数。

**定理 3。** 在已经处理 $n+2\le t\le N$ 条记录后，算法 Z 朴素版本执行余下抽样时，`RANDOM` 的期望调用次数满足

$$
RAND(n,t,N)\le n\left(\frac{2(n+1)}{t-n-1}+3(H _ N-H _ t)\right).
\tag{7.1}
$$

**证明。** 证明的基本思想是：生成 $\mathcal{S}$ 平均约需 $3+2n/t$ 次 `RANDOM` 调用。我们在第 3 节末尾已经证明， $\mathcal{S}$ 的平均生成次数为 $n(H _ N-H _ t)+1-n/N$。直观上，`RANDOM` 总调用次数因而约为 $3n(H _ N-H _ t)$。证明的主要障碍在于，算法执行期间 $t$ 不断增长。

算法 Z 的朴素版本每次需要生成 $\mathcal{U}$、 $\mathcal{X}$ 或 $\mathcal{M}$ 时，都调用一次 `RANDOM`。第 3 节末尾已经证明， $\mathcal{M}$ 的平均生成次数为 $n(H _ N-H _ t)$。让我们把 $UV(n,t,N)$ 定义为 $\mathcal{U}$ 或 $\mathcal{V}$ 的平均生成次数，其中 $\mathcal{V}$ 是生成 $\mathcal{X}$ 时隐含使用的均匀随机变量。为了证明定理，只需证明

$$
UV(n,t,N)\le2n\left(\frac{n+1}{t-n-1}+H _ N-H _ t\right)+2.
\tag{7.2}
$$

我们对 $t$ 使用归纳法。当 $t=N$ 时，我们有 $UV(n,N,N)=0$，式 (7.2) 显然成立。现在让我们假设式 (7.2) 对 $t+1,t+2,\ldots,N$ 成立；我们将证明它对 $t$ 仍成立。

每执行一次 `repeat` 循环体， $\mathcal{U}$ 和 $\mathcal{V}$ 都各生成一次。生成 $\mathcal{S}(n,t)$ 所需 `repeat` 循环的平均迭代次数是 $1/(1-r)$，其中 $r$ 是拒绝概率。我们有

$$
r=∫ _ 0^\infty g(x)\left(1-\frac{f(\lfloor x\rfloor)}{c g(x)}\right)dx
=1-\frac{1}{c}.
$$

结合两式，我们发现每生成一次 $\mathcal{S}(n,t)$，`repeat` 循环平均迭代 $1/(1-r)=c$ 次，因而产生 $2c$ 次 `RANDOM` 调用。利用归纳假设，我们有

$$
\begin{aligned}
UV(n,t,N)
&\le2c+\sum _ {0\le s\lt N-t}f(s)UV(n,t+s+1,N)\\
&\le\frac{2(t+1)}{t-n+1}
+\sum _ {0\le s\lt N-t}\frac{nt^{\mathit{fall}(n)}}{(t+s+1)^{\mathit{fall}(n+1)}}
\left(2n\left(\frac{n+1}{t+s-n}+H _ N-H _ {t+s+1}\right)+2\right)\\
&\le\frac{2(t+1)}{t-n+1}
+2n^2(n+1)t^{\mathit{fall}(n)}\sum _ {0\le s\lt N-t}\frac{1}{(t+s+1)^{\mathit{fall}(n+2)}}\\
&\quad+2nt^{\mathit{fall}(n)}(nH _ N+1)\sum _ {0\le s\lt N-t}\frac{1}{(t+s+1)^{\mathit{fall}(n+1)}}\\
&\quad+2n^2t^{\mathit{fall}(n)}\sum _ {0\le s\lt N-t}\frac{H _ {t+s+1}}{(t+s+1)^{\mathit{fall}(n+1)}}.
\end{aligned}
$$

原文此处正号与前一行展开及随后 $-2nH _ {t+1}$ 可能不一致。

三个求和都可用第 3 节末尾讨论的分部求和得到闭式。对第一个求和，我们取 $u=1$、 $\Delta v=1/(t+s+1)^{\mathit{fall}(n+2)}$；对第二个求和，我们取 $u=1$、 $\Delta v=1/(t+s+1)^{\mathit{fall}(n+1)}$；对第三个求和，我们取 $u=H _ {t+s+1}$、 $\Delta v=1/(t+s+1)^{\mathit{fall}(n+1)}$。代入这些求和的值，并用 0 界定较小项之和，我们得到

$$
\begin{aligned}
UV(n,t,N)
&\le\frac{2(t+1)}{t-n+1}+\frac{2n^2}{t-n}+2nH _ N+2-2nH _ {t+1}-\frac{2(t-n+1)}{t+1}\\
&=\frac{2n}{t-n+1}+\frac{2n^2}{t-n}+2n(H _ N-H _ t)+2\\
&\le2n\left(\frac{n+1}{t-n}+H _ N-H _ t\right)+2.
\end{aligned}
$$

这就证明了式 (7.2)，从而完成定理 3 的证明。证毕。

**推论 1。** 使用阈值优化的算法 Z，其 `RANDOM` 平均调用次数由下式界定：

$$
\begin{cases}
2n(H _ N-H _ n)+1-\frac{n}{N}, & Tn\ge N;\\
n\left(\frac{2(n+1)}{Tn-n-1}+3H _ N-H _ {Tn}-2H _ n\right)+3-\frac1T, & Tn\le N.
\end{cases}
\tag{7.3}
$$

**证明。** 当 $Tn\ge N$ 时，始终使用算法 X 的方法生成 $\mathcal{S}$。 $\mathcal{S}$ 的生成次数为 $n(H _ N-H _ n)+1-n/N$。每次生成 $\mathcal{S}$ 都要调用两次 `RANDOM`，以生成 $\mathcal{U}$ 和 $\mathcal{M}$，但最后一次生成 $\mathcal{S}$ 时可能例外。如果文件第 $N$ 条记录是最后一个选入蓄水池的记录（概率为 $n/N$），则必须生成 $\mathcal{M}$；否则，最后生成的 $\mathcal{S}$ 会越过文件中剩余记录，无须生成 $\mathcal{M}$。 $Tn\ge N$ 情形的公式立即得到。

当 $Tn\le N$ 时，前 $Tn$ 条记录用算法 X 的方法处理。算法余下部分的拒绝技术至多调用 $RAND(n,Tn,N)$ 次 `RANDOM`。我们假定 $T$ 足够大，使 $Tn\ge n+2$；实际实现总是如此。将 $Tn\ge N$ 情形与定理 3 结合即得结论。证毕。

**定理 4。** 让我们考虑算法 Z 朴素版本的一个修改版，其中只使用 `RANDOM` 优化。在已经处理 $t\ge n+2$ 条记录后，执行余下抽样时 `RANDOM` 的期望调用次数满足

$$
OPT(n,t,N)\le n\left(\frac{n+1}{t-n-1}+2(H _ N-H _ t)\right)+2.
\tag{7.4}
$$

**证明。** 经过这一修改，除第一次生成 $\mathcal{X}$ 外，生成 $\mathcal{X}$ 不再调用 `RANDOM`。这使 $UV(n,t,N)$ 降为原值的一半再加 1。由定理 3 的证明立即得到结论。证毕。

下面的推论由定理 4 得出，方式与推论 1 由定理 3 得出的方式相同。

**推论 2。** 同时使用阈值优化和 `RANDOM` 优化的算法 Z，其 `RANDOM` 平均调用次数由下式界定：

$$
\begin{cases}
2n(H _ N-H _ n)+1-\frac{n}{N}, & Tn\ge N;\\
n\left(\frac{n+1}{Tn-n-1}+2(H _ N-H _ n)\right)+3-\frac1T, & Tn\le N.
\end{cases}
\tag{7.5}
$$

### 7.2 平均运行时间

我们将证明算法 Z 的平均执行时间为 $O(n(1+\log(N/n)))$；根据第 3 节开头的讨论，这在常数因子的意义下是最优的。我们定义 $TIME(n,t,N)$ 为：已经处理 $t$ 条记录时，算法 Z 的朴素版本完成剩余抽样所需的期望执行时间。

**定理 5。** 已经处理 $t\le N$ 条记录后，算法 Z 朴素版本的期望运行时间为

$$
TIME(n,t,N)=O\left(n\left(1+\log\frac{N}{t}\right)\right).
$$

**证明。** 让我们先假设 $n\ge2$， $n=1$ 的情形稍后讨论。算法 Z 中唯一一次执行耗时超过常数的语句，是 `repeat` 循环中的检验“ $\mathcal{U}\le f(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$ 是否成立”，因为它要求计算 $f(\lfloor\mathcal{X}\rfloor)$；按原文所引式 (5.1)，该计算耗时 $O(\min\lbrace n,\lfloor\mathcal{X}\rfloor+1\rbrace )$。每生成一次 $\mathcal{S}$，算法 X 中的每条语句平均最多执行 $c=(t+1)/(t-n+1)$ 次。由定理 3 的证明，扣除执行 `repeat` 循环检验的时间后，算法 Z 的总运行时间由下式界定：

$$
O\left(n\left(\frac{n+1}{t-n-1}+H _ N-H _ t\right)\right)
=O\left(n\left(1+\log\frac{N}{t}\right)\right).
$$

证明的困难部分，是当 $t$ 不断增长时，对算法全过程中计算 $f(\lfloor\mathcal{X}\rfloor)$ 所花的执行时间进行界定。对某个小常数 $d\ge0$，每次计算的时间由 $d\min\lbrace n,\lfloor\mathcal{X}\rfloor+1\rbrace \le d(\lfloor\mathcal{X}\rfloor+1)$ 界定。检验“ $\mathcal{U}\le h(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$ 是否成立”为假的概率——也就是接下来必须计算 $f(\lfloor\mathcal{X}\rfloor)$ 的概率——是 $1-h(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))$。因此，对 $\mathcal{S}$ 的一次生成，我们可将计算 $f(\lfloor\mathcal{X}\rfloor)$ 所花的时间界定为

$$
\begin{aligned}
c∫ _ 0^\infty d(x+1)g(x)\left(1-\frac{h(x)}{c g(x)}\right)dx
&=cd∫ _ 0^\infty(x+1)g(x)\thinspace dx\\
&\quad-d∫ _ 0^\infty(x+1)h(x)\thinspace dx
\end{aligned}
$$

界定。第一个积分等于

$$
cd(\mathrm{expected}(\mathcal{X})+1)
=\frac{t+1}{t-n+1}\thinspace d\thinspace \frac{t+n-1}{n-1};
$$

第二个积分等于

$$
d\thinspace \frac{t(t-n+1)}{(n-1)(t+1)}.
$$

经过一些代数化简，第一个积分减去第二个积分之差可由

$$
3cd+\frac{2cd}{n-1}
$$

界定。由式 (7.2) 的推导可知，算法全过程中计算 $f(\lfloor\mathcal{X}\rfloor)$ 的总耗时至多为

$$
\left(3+\frac{2}{n-1}\right)d
\left(n\left(\frac{n+1}{t-n-1}+H _ N-H _ t\right)+1\right)
=O\left(n\left(1+\log\frac{N}{t}\right)\right).
$$

这完成了 $n\ge2$ 情形的证明。

我们将在第 8 节看到，主要由于数值原因，当 $n=1$ 时不应直接使用算法 Z。此时，我们改为用算法 Z 对一个较大但仍很小的 $n$ 值运行，比如 $n _ 0=5$，得到大小为 $n _ 0$ 的随机样本。生成这个样本后，我们可以用下一节给出的简单 $O(n _ 0)$ 时间过程，从中恢复大小为 $n$ 的随机样本。因此我们有

$$
TIME(1,t,N)=TIME(n _ 0,t,N)+O(n _ 0).
$$

这完成定理 5 的证明。证毕。

下面的推论表明，算法 Z 在常数因子的意义下达到最优时间。

**推论 3。** 使用阈值优化的算法 Z，其平均运行时间为

$$
O\left(n\left(1+\log\frac{N}{n}\right)\right).
$$

使用 `RANDOM` 优化或子程序优化，还会再把运行时间缩短某个常数因子。

### 7.3 阈值

在第 6 节讨论的阈值优化中，我们先用算法 X 的方法生成 $\mathcal{S}$，直到 $t$ 足够大，此后我们改用拒绝技术生成 $\mathcal{S}$。此前曾建议使用一个常数，我们称之为 $T$：当 $t\ge Tn$ 时，从算法 X 切换到拒绝技术。本节我们说明为什么阈值点近似是 $n$ 的线性函数。

用算法 X 的方法生成 $\mathcal{S}$ 所需平均时间大约为

$$
d _ 1\mathrm{expected}(\mathcal{S})
=d _ 1\frac{t-n+1}{n-1}
\approx\frac{d _ 1t}{n},
\tag{7.6}
$$

其中 $d _ 1\gt 0$ 是某个小常数。（ $\mathrm{expected}(\mathcal{S})$ 的公式见式 (3.3)。）我们可以应用定理 5 证明中的技术，界定拒绝技术生成 $\mathcal{S}$ 所需的平均时间。为了生成 $\mathcal{S}$，`repeat` 循环体平均生成 $c\approx1+n/t$ 次。以概率 $1-h(\lfloor\mathcal{X}\rfloor)/(c g(\mathcal{X}))\approx n/t$，我们必须计算 $f(\lfloor\mathcal{X}\rfloor)$；该计算平均至多耗时 $O(\mathrm{expected}(\mathcal{S}))=O(t/n)$。综合这些因素，拒绝技术生成 $\mathcal{S}$ 所需平均时间大约为

$$
d _ 2\left(1+\frac{n}{t}\right)
\left(d _ 3\left(1-\frac{n}{t}\right)+d _ 4\frac{n}{t}\frac{t}{n}\right)
=\Theta(1),
\tag{7.7}
$$

其中 $d _ 2,d _ 3,d _ 4\gt 0$ 是适当的小常数。因此，式 (7.6) 与 (7.7) 相等时的 $t$ 值为 $\Theta(n)$。

在接下来两节讨论的实现中，把 $T$ 初始化为 22 似乎效果最好。 $T$ 的典型取值预计在 10–40 之间。

## 8. 算法 Z 的实现

本节我们给出算法 Z 的一个高效 Pascal 风格实现。该程序纳入第 6 节讨论的阈值优化、`RANDOM` 优化和子程序优化。在 $t\gt \mathit{thresh}$ 之前使用算法 X 的方法，其中 $\mathit{thresh}=T\times n$。常数 $T$ 应初始化为 10–40 之间的某个整数；在下一节描述的计时中， $T$ 初始化为 22 时性能最好。

这里使用少量非标准记号：保留字 `loop` 与 `end loop` 之间的语句构成循环体；执行 `break loop` 会使控制流退出该循环。符号 × 表示乘法，代码记号 x ↑ y 表示 $x^y$，空实参括号用于调用无参数函数。

当 $y$ 是实数或大整数时， $x^y$ 形式的运算用数学库子程序 `EXP` 和 `LOG` 计算为 EXP(y × LOG(x))。变量 $\mathcal{W},\mathcal{X},\mathcal{U},\mathit{lhs},\mathit{rhs},y,\mathit{quot}$ 的类型为实数；其他所有变量的类型均为整数。

随机数生成器 `RANDOM` 不接受参数，返回范围 $(0,1)$ 中的均匀随机变量。我们用 $u$ 表示 `RANDOM` 返回的最小数， $\mathtt{max\verb0_0int}$ 表示整数变量能保存的最大数， $\mathtt{max\verb0_0real}$ 表示实数变量能保存的最大数。为防止整数溢出和浮点溢出，我们必须有

$$
Nu^{-1/n}\lt \mathtt{max\verb0_0int}
\qquad\text{且}\qquad
Nu^{-1/n}\lt \mathtt{max\verb0_0real}.
$$

例如，这保证随机变量 $\mathcal{S}$ 和 $\mathcal{X}$ 能存入相应变量，也保证在病态情况下计算 $f(\lfloor\mathcal{X}\rfloor)$ 不会溢出。

在多数计算机上，可用如下方式轻松满足这些条件。先得到 $N$ 的某个上界，即使很宽松也可以。接着，把刚得到的上界代入 $N$，确定同时满足两个条件的最小 $n$。让我们把这个值称为 $n _ 0$；通常 $n _ 0$ 应当很小。若所需样本大小 $n\lt n _ 0$，解决办法是递归应用蓄水池抽样的基本思想。我们首先运行算法 Z，取得大小为 $n _ 0$ 的随机样本。然后我们用下面的简单过程，从大小为 $n _ 0$ 的随机样本中生成大小为 $n$ 的随机样本：

```text
for j := 0 to n0 - 1 do already_selected := false;
num_selected := 0;
while num_selected < n do
    begin
    M := TRUNC(n0 × RANDOM());
    if not already_selected[M] then
        begin
        OUTPUT(C[M]);
        already_selected[M] := true;
        num_selected := num_selected + 1
        end
    end
```

首行写成 `already_selected := false`，没有数组下标；后续检验与赋值则使用 `already_selected[M]`。该过程也可以换成文献 [10] 给出的任一种顺序抽样方法。

下面给出算法 Z 的优化代码。程序第一部分本质上是算法 X 的代码，由它执行抽样直到 $t$ 足够大。

```text
{把前 n 条记录设为样本候选记录}
for j := 0 to n - 1 do READ_NEXT_RECORD(C[j]);
t := n;                                         {t 是处理至今的记录数}

{用算法 X 的方法处理记录，直到 t 足够大}
thresh := T × n;
num := 0;                                       {num 等于 t - n}
while not eof and (t ≤ thresh) do
    begin
    V := RANDOM();                              {生成 V}
    S := 0;
    t := t + 1; num := num + 1;
    quot := num/t;
    while quot > V do                           {找出满足 (4.1) 的最小 S}
        begin
        S := S + 1;
        t := t + 1; num := num + 1;
        quot := (quot × num)/t
        end;
    SKIP_RECORDS(S);                            {跳过接下来的 S 条记录}
    if not eof then
        begin                                   {让下一条记录成为候选并随机替换一个候选}
        M := TRUNC(n × RANDOM());               {M 在 0 ≤ M ≤ n - 1 中均匀分布}
        READ_NEXT_RECORD(C[M])
        end
    end;

{用拒绝技术处理其余记录}
W := EXP(-LOG(RANDOM())/n);                     {生成 W}
term := t - n + 1;                              {term 始终等于 t - n + 1}
while not eof do
    begin
    loop
        {生成 U 和 X}
        U := RANDOM();
        X := t × (W - 1.0);
        S := TRUNC(X);                          {暂令 S 等于 floor(X)}
        {按 (6.3) 的方式检验 U ≤ h(S)/(c g(X))}
        lhs := EXP(LOG(((U × (((t + 1)/term) ↑ 2)) × (term + S))/(t + X))/n);
        rhs := (((t + X)/(term + S)) × term)/t;
        if lhs ≤ rhs then
            begin W := rhs/lhs; break loop end;
        {检验 U ≤ f(S)/(c g(X))}
        y := ((U × (t + 1))/term) × (t + S + 1)/(t + X);
        if n < S then begin denom := t; numer_lim := term + S end
        else begin denom := t - n + S; numer_lim := t + 1 end;
        for numer := t + S downto numer_lim do
            begin y := (y × numer)/denom; denom := denom - 1 end;
        W := EXP(-LOG(RANDOM())/n);              {预先生成 W}
        if EXP(LOG(y)/n) ≤ (t + X)/t then break loop
    end loop;
    SKIP_RECORDS(S);                            {跳过接下来的 S 条记录}
    if not eof then
        begin                                   {让下一条记录成为候选并随机替换一个候选}
        M := TRUNC(n × RANDOM());               {M 在 0 ≤ M ≤ n - 1 中均匀分布}
        READ_NEXT_RECORD(C[M])
        end;
    t := t + S + 1;
    term := term + S + 1
    end;
```

## 9. 经验比较

本节给出算法 R、X、Z 在 VAX 11/780 计算机上的经验计时结果。为了获得高速度，程序用 FORTRAN 77 编写。随机数生成器采用与文献 [9] 所述方法类似的、与机器无关的线性同余法版本。算法 X 和 Z 的程序是上一节代码的直接翻译。对于算法 R，我们把基本代码放入第 3 节讨论的框架中进行优化。

这些算法的运行时间（微秒）如下：

$$
\begin{aligned}
&\approx160N &&\text{（算法 R）},\\
&\approx40N &&\text{（算法 X）},\\
&\approx950n\ln\frac{N}{n}-1250n &&\text{（算法 Z）}.
\end{aligned}
$$

当 $n$ 非常小或非常大时，算法 R 和 X 的实际计时高得多。算法 Z 的公式通过最小二乘曲线拟合得到。

计时覆盖很大范围的 $n$ 和 $N$。表 II 给出的值具有代表性，所有时间单位均为秒。当 $N=10^7$ 时，算法 R 需要约 26 分钟 CPU 时间，算法 X 约需 6 分钟，而算法 Z 只需几秒。

**表 II　算法 R、X、Z 的计时（秒）**

| $N$ | $n$ | 算法 R | 算法 X | 算法 Z |
| ---: | ---: | ---: | ---: | ---: |
| $10^6$ | $10^1$ | 171 | 41 | 0.1 |
| $10^6$ | $10^2$ | 153 | 35 | 0.8 |
| $10^6$ | $10^3$ | 155 | 37 | 5 |
| $10^6$ | $10^4$ | 158 | 47 | 31 |
| $10^6$ | $10^5$ | 176 | 95 | 96 |
| $10^7$ | $10^1$ | 1595 | 430 | 0.1 |
| $10^7$ | $10^2$ | 1590 | 356 | 1 |
| $10^7$ | $10^3$ | 1553 | 371 | 8 |
| $10^7$ | $10^4$ | 1560 | 387 | 55 |
| $10^7$ | $10^5$ | 1604 | 500 | 303 |

为了理解这些 CPU 计时的相对量级，我们考虑 $N=10^7,n=10^2$ 示例对应的 I/O 时间，并假设平均记录大小为 15–20 字节。文件总大小约为 150–200 MB。IBM 3380 磁盘驱动器的读写速率为每秒 6 MB，IBM 3420 Model 8 磁带机的读写速率为每秒 1.25 MB。3380 大约可保存 800 MB，而 3420 使用的磁带大约可保存 180 MB。

在磁盘情形下，顺序读取该文件约需 30 秒。不过，我们为本文开发的算法不必读取所有记录；一次可以跳过多条记录。如果记录长度固定，I/O 操作将降为大约 $n\ln(N/n)$ 次短距离寻道和读取，对应的 I/O 时间不到 2 秒。即使记录长度可变，也可以把每个磁道中的记录数存入磁道头；跳跃时连续读取磁道头，直到找到目标磁道。所得 I/O 时间显著少于 30 秒。该示例相应的 CPU 时间为：1590 秒（算法 R）、356 秒（算法 X）和 1 秒（算法 R）；最后一项的算法名称与表 II 所示对应项不一致。

在磁带示例中，顺序读取约需 150 秒。不过，磁带机可以利用快速前进功能，以更高速度跳过不需要的记录，因此 I/O 时间可以减少；记录长度固定时尤其如此。CPU 时间与上面相同。

在较小示例中，算法 X 的 CPU 时间可能小到与所需 I/O 时间近似；但内部处理与 I/O 可能无法重叠，所以总运行时间可能是 I/O 时间的两倍。算法 Z 的优势在于，其 CPU 时间可以忽略不计。它足够快，即使 $N$ 的值已知也仍有用。

## 10. 结果总结

在本文中，我们考虑了从包含 $N$ 条记录的文件中选取大小为 $n$ 的随机样本的算法，其中算法不知道 $N$ 的值。我们证明，任何按顺序处理文件的此类抽样算法都可以刻画为蓄水池算法。蓄水池算法的区别性特征是：在顺序遍历文件期间取得一个大小至少为 $n$ 的样本，再从这个较大样本中随机选 $n$ 条记录，得到最终样本。所有蓄水池算法都需要

$$
\Omega\left(n\left(1+\log\frac{N}{t}\right)\right)
$$

时间。该总结句的分母是 $t$，与前文下界中使用的 $n$ 不同。

本文的主要结果是算法 Z 的设计与分析。它使用拒绝—接受技术，在常数因子的意义下以最优时间完成抽样。若干优化把朴素版本的运行时间缩短约 8 倍。在 VAX 11/780 上测得的 CPU 时间表明，算法 Z 显著快于当时使用的蓄水池抽样算法。第 8 节给出了适合一般用途的算法 Z 高效 Pascal 风格实现。

## 参考文献

1. Bentley, J. L. Personal communication, Apr. 1983; see [11].
2. Ernvall, J., and Nevalainen, O. An algorithm for unbiased random sampling. *Comput. J.* 25, 1 (Jan. 1982), 45–47.
3. Fan, C. T., Muller, M. E., and Rezucha, I. Development of sampling plans by using sequential (item by item) selection techniques and digital computers. *Am. Stat. Assoc. J.* 57 (June 1962), 387–402.
4. Feller, W. *An Introduction to Probability Theory and Its Applications*, vol. I, 3rd ed. Wiley, 1968.
5. Feller, W. *An Introduction to Probability Theory and Its Applications*, vol. II, 2nd ed. Wiley, 1971.
6. Jones, T. G. A note on sampling a tape file. *Commun. ACM* 5, 6 (June 1962), 343.
7. Kawarasaki, J., and Sibuya, M. Random numbers for simple random sampling without replacement. *Keio Math. Sem. Rep.* No. 7 (1982), 1–9.
8. Knuth, D. E. *The Art of Computer Programming*, vol. 2: *Seminumerical Algorithms*, 2nd ed. Addison-Wesley, Reading, Mass., 1981.
9. Sedgewick, R. *Algorithms*. Addison-Wesley, Reading, Mass., 1981.
10. Vitter, J. S. Faster methods for random sampling. *Commun. ACM* 27, 7 (July 1984), 703–718.
11. Vitter, J. S. Optimum algorithms for two random sampling problems. In *Proceedings of the 24th Annual IEEE Symposium on Foundations of Computer Science* (Tucson, Az., Nov. 7–9), IEEE, New York, 1983, pp. 65–75.

1984 年 2 月收到；1984 年 10 月接受。
