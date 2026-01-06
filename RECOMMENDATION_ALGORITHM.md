# 推荐算法详解

## 算法概述

这个推荐系统使用**基于嵌入向量相似度 + 时间衰减权重**的方法来推荐 ArXiv 论文。

## 算法流程

### 1. 数据准备阶段

#### 1.1 Zotero 语料库（你的论文库）
- 从 Zotero 获取所有论文（conferencePaper、journalArticle、preprint）
- 只保留有摘要的论文
- 按添加时间排序：**从新到旧**

#### 1.2 ArXiv 候选论文
- 从 ArXiv RSS Feed 获取新发布的论文
- 根据 `ARXIV_QUERY` 参数筛选类别（如：cs.AI+cs.CV+cs.LG+cs.CL）
- 只获取标记为 "new" 的论文（当天新发布的）

### 2. 特征提取阶段

使用 **Sentence Transformer** 模型将文本转换为向量：

- **模型**: `avsolatorio/GIST-small-Embedding-v0`
- **Zotero 论文**: 使用论文的 `abstractNote`（摘要）生成向量
- **ArXiv 论文**: 使用论文的 `summary`（摘要）生成向量

```python
corpus_feature = encoder.encode([paper['data']['abstractNote'] for paper in corpus])
candidate_feature = encoder.encode([paper.summary for paper in candidate])
```

### 3. 相似度计算阶段

计算每个 ArXiv 候选论文与所有 Zotero 论文的相似度：

```python
sim = encoder.similarity(candidate_feature, corpus_feature)
# 结果形状: [n_candidate, n_corpus]
# 例如: 100篇候选论文 × 254篇Zotero论文 = 100×254的相似度矩阵
```

### 4. 时间衰减权重

**核心思想**: 最近添加的论文更能反映你当前的研究兴趣

#### 权重计算公式：
```python
time_decay_weight = 1 / (1 + np.log10(np.arange(len(corpus)) + 1))
time_decay_weight = time_decay_weight / time_decay_weight.sum()  # 归一化
```

**权重特点**:
- 第1篇（最新）论文权重最高
- 随着索引增加，权重按对数函数递减
- 所有权重归一化后总和为 1

**示例**（假设有5篇论文）:
- 论文1（最新）: 权重 ≈ 0.35
- 论文2: 权重 ≈ 0.25
- 论文3: 权重 ≈ 0.18
- 论文4: 权重 ≈ 0.13
- 论文5（最旧）: 权重 ≈ 0.09

### 5. 最终评分计算

对每个候选论文，计算加权平均相似度：

```python
scores = (sim * time_decay_weight).sum(axis=1) * 10
```

**计算过程**:
1. 将相似度矩阵的每一行（一个候选论文）与时间衰减权重相乘
2. 按列求和，得到该候选论文与所有 Zotero 论文的加权平均相似度
3. 乘以 10 进行缩放（便于显示）

**数学表达**:
```
score(候选论文i) = Σ(similarity(候选论文i, Zotero论文j) × weight(j)) × 10
```

### 6. 排序与筛选

- 按分数从高到低排序
- 返回前 `MAX_PAPER_NUM` 篇（默认50篇）

## 算法特点

### ✅ 优点
1. **个性化**: 基于你的 Zotero 库，反映你的研究兴趣
2. **时效性**: 时间衰减权重让最近添加的论文影响更大
3. **语义理解**: 使用嵌入向量捕获论文的语义相似度，不仅仅是关键词匹配

### ⚠️ 局限性
1. **简单加权**: 只是简单的加权平均，没有考虑更复杂的因素
2. **摘要依赖**: 完全依赖摘要质量，如果摘要不准确会影响推荐
3. **类别限制**: 只能推荐 ArXiv 上你指定的类别

## 推荐分数含义

- **分数范围**: 通常在 0-10 之间
- **分数越高**: 与你的 Zotero 论文库越相似，越可能符合你的兴趣
- **分数计算**: 加权平均相似度 × 10

## 示例

假设你的 Zotero 库有：
- 5篇关于"深度学习"的论文（最近添加）
- 10篇关于"计算机视觉"的论文（较旧）

ArXiv 上有一篇新论文：
- 标题: "Deep Learning for Image Recognition"
- 摘要: 关于深度学习和图像识别

**计算过程**:
1. 该论文与"深度学习"论文相似度: 0.85（高）
2. 该论文与"计算机视觉"论文相似度: 0.70（中）
3. 由于"深度学习"论文权重更高，最终分数会偏向这些论文的相似度
4. 最终分数可能: (0.85×0.35 + 0.70×0.25 + ...) × 10 ≈ 7.5

