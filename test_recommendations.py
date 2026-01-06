#!/usr/bin/env python3
"""测试推荐功能"""
import os
import sys
from dotenv import load_dotenv
import arxiv
import feedparser
from loguru import logger

load_dotenv()

ARXIV_QUERY = os.getenv('ARXIV_QUERY', 'cs.AI+cs.CV+cs.LG+cs.CL')

logger.info("=" * 60)
logger.info("测试 ArXiv 论文获取")
logger.info("=" * 60)

# 测试 1: 检查 RSS Feed
logger.info(f"\n1. 测试 RSS Feed: {ARXIV_QUERY}")
try:
    feed_url = f"https://rss.arxiv.org/atom/{ARXIV_QUERY}"
    logger.info(f"Feed URL: {feed_url}")
    feed = feedparser.parse(feed_url)
    
    if feed.feed.get('title'):
        logger.info(f"Feed 标题: {feed.feed.title}")
        if 'Feed error for query' in feed.feed.title:
            logger.error("❌ Feed 查询错误！")
            sys.exit(1)
    
    logger.info(f"✓ Feed 解析成功")
    logger.info(f"  找到 {len(feed.entries)} 个条目")
    
    # 统计新论文
    new_papers = []
    for entry in feed.entries:
        if hasattr(entry, 'arxiv_announce_type') and entry.arxiv_announce_type == 'new':
            paper_id = entry.id
            if paper_id.startswith("oai:arXiv.org:"):
                paper_id = paper_id.removeprefix("oai:arXiv.org:")
            new_papers.append(paper_id)
    
    logger.info(f"  其中 {len(new_papers)} 篇是新论文")
    
    if len(new_papers) == 0:
        logger.warning("⚠️  今天没有新论文（可能是周末或节假日）")
        logger.info("   尝试获取最近的论文...")
        # 尝试获取最近的论文
        new_papers = []
        for entry in feed.entries[:10]:  # 取前10篇
            paper_id = entry.id
            if paper_id.startswith("oai:arXiv.org:"):
                paper_id = paper_id.removeprefix("oai:arXiv.org:")
            new_papers.append(paper_id)
        logger.info(f"  使用最近的 {len(new_papers)} 篇论文进行测试")
    
    if len(new_papers) > 0:
        logger.info(f"\n  示例论文 ID: {new_papers[:5]}")
    
except Exception as e:
    logger.error(f"❌ Feed 解析失败: {e}")
    sys.exit(1)

# 测试 2: 尝试获取论文详情
logger.info(f"\n2. 测试 ArXiv API 获取论文详情")
if len(new_papers) == 0:
    logger.warning("⚠️  跳过此测试（没有论文 ID）")
else:
    try:
        client = arxiv.Client(num_retries=3, delay_seconds=5)
        test_ids = new_papers[:3]  # 只测试前3篇
        logger.info(f"  尝试获取 {len(test_ids)} 篇论文: {test_ids}")
        
        search = arxiv.Search(id_list=test_ids)
        results = list(client.results(search))
        
        logger.info(f"✓ 成功获取 {len(results)} 篇论文详情")
        for i, paper in enumerate(results, 1):
            logger.info(f"  {i}. {paper.title[:60]}...")
            logger.info(f"     ID: {paper.get_short_id()}")
            logger.info(f"     摘要长度: {len(paper.summary)} 字符")
    except Exception as e:
        logger.error(f"❌ 获取论文详情失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

logger.info("\n" + "=" * 60)
logger.info("测试完成！")
logger.info("=" * 60)

