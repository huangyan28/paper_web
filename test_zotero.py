#!/usr/bin/env python3
"""测试 Zotero 连接"""
import os
from dotenv import load_dotenv
from pyzotero import zotero

load_dotenv()

zotero_id = os.getenv('ZOTERO_ID')
zotero_key = os.getenv('ZOTERO_KEY')

if not zotero_id or not zotero_key:
    print("错误：请在 .env 文件中设置 ZOTERO_ID 和 ZOTERO_KEY")
    exit(1)

print(f"正在连接到 Zotero (ID: {zotero_id})...")
try:
    zot = zotero.Zotero(zotero_id, 'user', zotero_key)
    
    # 测试获取用户信息
    print("✓ Zotero 连接成功！")
    
    # 获取论文数量
    items = zot.everything(zot.items(itemType='conferencePaper || journalArticle || preprint'))
    print(f"✓ 找到 {len(items)} 篇论文")
    
    # 获取有摘要的论文
    items_with_abstract = [item for item in items if item['data'].get('abstractNote', '').strip()]
    print(f"✓ 其中 {len(items_with_abstract)} 篇有摘要")
    
    # 获取收藏夹
    collections = zot.everything(zot.collections())
    print(f"✓ 找到 {len(collections)} 个收藏夹")
    
    print("\n✅ Zotero 配置正确，可以正常使用！")
    
except Exception as e:
    print(f"❌ 连接失败：{e}")
    exit(1)

