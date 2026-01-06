from flask import Flask, render_template, jsonify, request, Response, stream_with_context, session, redirect, url_for
from flask_cors import CORS
import os
from dotenv import load_dotenv
from pyzotero import zotero
from recommender import rerank_paper
from paper import ArxivPaper
import arxiv
import feedparser
from datetime import datetime
from loguru import logger
import json
import time
import hashlib
from pathlib import Path
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-this-in-production')
CORS(app, supports_credentials=True)

# 配置
ARXIV_QUERY = os.getenv('ARXIV_QUERY', 'cs.AI+cs.CV+cs.LG+cs.CL')
MAX_PAPER_NUM = int(os.getenv('MAX_PAPER_NUM', '50'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '50'))  # ArXiv API 批次大小
CACHE_ENABLED = os.getenv('CACHE_ENABLED', 'true').lower() == 'true'
FETCH_CODE_URL = os.getenv('FETCH_CODE_URL', 'false').lower() == 'true'  # 是否获取代码链接（会慢很多）
CACHE_DIR = Path(__file__).parent / 'cache'
CACHE_DIR.mkdir(exist_ok=True)

# 获取当前用户的 Zotero 配置
def get_user_zotero_config():
    """从 session 获取用户的 Zotero 配置"""
    return {
        'zotero_id': session.get('zotero_id'),
        'zotero_key': session.get('zotero_key')
    }

def get_user_cache_dir():
    """获取当前用户的缓存目录"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    user_cache_dir = CACHE_DIR / 'user' / str(user_id)
    user_cache_dir.mkdir(parents=True, exist_ok=True)
    return user_cache_dir

def get_cache_key():
    """生成缓存键（基于用户 ID 和 Zotero ID）"""
    user_id = session.get('user_id')
    zotero_id = session.get('zotero_id')
    if not user_id or not zotero_id:
        return None
    key_str = f"{user_id}_{zotero_id}"
    return hashlib.md5(key_str.encode()).hexdigest()

def get_cache_path():
    """获取缓存文件路径"""
    user_cache_dir = get_user_cache_dir()
    if not user_cache_dir:
        return None
    cache_key = get_cache_key()
    if not cache_key:
        return None
    return user_cache_dir / f"zotero_cache_{cache_key}.json"

def get_recommendations_cache_key(arxiv_query, date_range=None, selected_paper_keys=None):
    """生成推荐结果缓存键"""
    user_id = session.get('user_id')
    zotero_id = session.get('zotero_id')
    if not user_id or not zotero_id:
        return None
    keys_str = ','.join(sorted(selected_paper_keys)) if selected_paper_keys else 'all'
    key_str = f"{user_id}_{zotero_id}_{arxiv_query}_{date_range or 'all'}_{keys_str}"
    return hashlib.md5(key_str.encode()).hexdigest()

def get_recommendations_cache_path(arxiv_query, date_range=None, selected_paper_keys=None):
    """获取推荐结果缓存文件路径"""
    user_cache_dir = get_user_cache_dir()
    if not user_cache_dir:
        return None
    cache_key = get_recommendations_cache_key(arxiv_query, date_range, selected_paper_keys)
    if not cache_key:
        return None
    return user_cache_dir / f"recommendations_cache_{cache_key}.json"

# 实现缓存验证和更新逻辑
def check_cache_validity(cache_data):
    """检查缓存有效性，如果文章有更新则返回 False"""
    if not cache_data:
        return False
    
    cached_at = cache_data.get('cached_at')
    if not cached_at:
        return False
    
    # 检查缓存是否过期（24小时）
    try:
        cached_time = datetime.fromisoformat(cached_at)
        if (datetime.now() - cached_time).total_seconds() > 24 * 3600:
            return False
    except:
        return False
    
    return True

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('zotero_id') or not session.get('zotero_key'):
            return jsonify({'success': False, 'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated_function

def load_recommendations_cache(arxiv_query, date_range=None, selected_paper_keys=None):
    """加载推荐结果缓存"""
    if not CACHE_ENABLED:
        return None
    
    cache_path = get_recommendations_cache_path(arxiv_query, date_range, selected_paper_keys)
    if not cache_path or not cache_path.exists():
        return None
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            # 检查缓存是否过期（24小时）
            cached_at = datetime.fromisoformat(cache_data.get('cached_at', ''))
            if (datetime.now() - cached_at).total_seconds() > 24 * 3600:
                return None
            logger.info(f"从缓存加载推荐结果（{len(cache_data.get('papers', []))} 篇）")
            return cache_data
    except Exception as e:
        logger.warning(f"加载推荐缓存失败: {e}")
        return None

def save_recommendations_cache(arxiv_query, date_range, papers, selected_paper_keys=None):
    """保存推荐结果缓存"""
    if not CACHE_ENABLED:
        return
    
    cache_path = get_recommendations_cache_path(arxiv_query, date_range, selected_paper_keys)
    if not cache_path:
        return
    
    try:
        zotero_id = session.get('zotero_id')
        cache_data = {
            'papers': papers,
            'arxiv_query': arxiv_query,
            'date_range': date_range,
            'selected_paper_keys': selected_paper_keys,
            'cached_at': datetime.now().isoformat(),
            'zotero_id': zotero_id
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.info(f"✓ 推荐结果已缓存（{len(papers)} 篇）")
    except Exception as e:
        logger.warning(f"保存推荐缓存失败: {e}")

def load_cache():
    """加载缓存"""
    if not CACHE_ENABLED:
        return None
    
    cache_path = get_cache_path()
    if not cache_path or not cache_path.exists():
        return None
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            logger.info(f"从缓存加载 {len(cache_data.get('corpus', []))} 篇论文")
            return cache_data
    except Exception as e:
        logger.warning(f"加载缓存失败: {e}")
        return None

def save_cache(corpus, collections):
    """保存缓存"""
    if not CACHE_ENABLED:
        return
    
    cache_path = get_cache_path()
    if not cache_path:
        return
    
    try:
        # 将 collections 字典转换为列表以便 JSON 序列化
        collections_list = list(collections.values()) if isinstance(collections, dict) else collections
        
        zotero_id = session.get('zotero_id')
        cache_data = {
            'corpus': corpus,
            'collections': collections_list,
            'cached_at': datetime.now().isoformat(),
            'zotero_id': zotero_id
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logger.info(f"✓ 缓存已保存（{len(corpus)} 篇论文）")
    except Exception as e:
        logger.warning(f"保存缓存失败: {e}")

def get_item_hash(item):
    """生成论文的哈希值（基于 key, version, title, paths）"""
    key = item.get('key', '')
    version = item.get('data', {}).get('version', 0)
    title = item.get('data', {}).get('title', '')
    paths = item.get('paths', [])
    
    hash_str = f"{key}_{version}_{title}_{'|'.join(sorted(paths))}"
    return hashlib.md5(hash_str.encode()).hexdigest()

def get_zotero_corpus(force_refresh=False):
    """获取 Zotero 语料库（带缓存）"""
    config = get_user_zotero_config()
    zotero_id = config.get('zotero_id')
    zotero_key = config.get('zotero_key')
    
    if not zotero_id or not zotero_key:
        return [], {}
    
    # 尝试从缓存加载
    if not force_refresh:
        cache_data = load_cache()
        if cache_data:
            # 检查缓存是否属于当前用户
            if cache_data.get('zotero_id') == zotero_id:
                # 检查缓存有效性
                if check_cache_validity(cache_data):
                    corpus = cache_data.get('corpus', [])
                    collections = cache_data.get('collections', {})
                    
                    # 将 collections 从列表转换回字典格式
                    if isinstance(collections, list):
                        collections = {c['key']: c for c in collections}
                    elif not isinstance(collections, dict):
                        collections = {}
                    
                    logger.info(f"✓ 使用缓存数据（{len(corpus)} 篇论文，跳过 API 调用）")
                    return corpus, collections
                else:
                    logger.info("缓存已过期，将重新获取")
            else:
                logger.info("缓存用户 ID 不匹配，将重新获取")
    
    # 从 API 获取完整数据
    logger.info("从 Zotero API 获取数据...")
    zot = zotero.Zotero(zotero_id, 'user', zotero_key)
    collections = zot.everything(zot.collections())
    collections = {c['key']: c for c in collections}
    
    corpus = zot.everything(zot.items(itemType='conferencePaper || journalArticle || preprint'))
    corpus = [c for c in corpus if c['data'].get('abstractNote', '').strip()]
    
    def get_collection_path(col_key: str) -> str:
        if p := collections[col_key]['data'].get('parentCollection'):
            return get_collection_path(p) + '/' + collections[col_key]['data']['name']
        else:
            return collections[col_key]['data']['name']
    
    for c in corpus:
        paths = [get_collection_path(col) for col in c['data'].get('collections', [])]
        c['paths'] = paths
    
    # 保存缓存
    save_cache(corpus, collections)
    
    return corpus, collections

def format_zotero_item(item):
    """格式化 Zotero 项目"""
    data = item['data']
    creators = data.get('creators', [])
    authors = []
    for creator in creators:
        if creator:
            if 'firstName' in creator and 'lastName' in creator:
                name = f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
                if name:
                    authors.append(name)
            elif 'name' in creator:
                authors.append(creator['name'])
    
    return {
        'key': item.get('key', ''),
        'title': data.get('title', 'Untitled'),
        'authors': authors if authors else ['Unknown'],
        'abstract': data.get('abstractNote', ''),
        'date': data.get('date', ''),
        'dateAdded': data.get('dateAdded', ''),
        'collections': item.get('paths', []),
        'url': data.get('url', ''),
        'itemType': data.get('itemType', ''),
    }

@app.route('/')
def index():
    """主页面"""
    return render_template('index.html')

@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.json
        zotero_id = data.get('zotero_id', '').strip()
        zotero_key = data.get('zotero_key', '').strip()
        
        if not zotero_id or not zotero_key:
            return jsonify({'success': False, 'error': 'Zotero ID 和 API Key 不能为空'}), 400
        
        # 验证 Zotero 凭证（通过尝试获取 collections 来验证）
        try:
            zot = zotero.Zotero(zotero_id, 'user', zotero_key)
            # 尝试获取 collections 来验证凭证是否有效
            # 只获取第一个 collection，如果成功说明凭证有效
            collections = zot.collections(limit=1)
        except Exception as e:
            logger.error(f"Zotero 登录验证失败: {e}")
            error_msg = str(e)
            if '403' in error_msg or 'Forbidden' in error_msg:
                return jsonify({'success': False, 'error': 'Zotero API Key 无效或权限不足'}), 401
            elif '404' in error_msg or 'Not Found' in error_msg:
                return jsonify({'success': False, 'error': 'Zotero ID 不存在'}), 401
            else:
                return jsonify({'success': False, 'error': f'Zotero 凭证验证失败: {error_msg}'}), 401
        
        # 生成用户 ID（基于 Zotero ID）
        user_id = hashlib.md5(f"{zotero_id}_{zotero_key[:10]}".encode()).hexdigest()
        
        # 保存到 session
        session['user_id'] = user_id
        session['zotero_id'] = zotero_id
        session['zotero_key'] = zotero_key
        
        logger.info(f"用户登录成功: Zotero ID {zotero_id}, User ID {user_id}")
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'zotero_id': zotero_id
        })
    except Exception as e:
        logger.error(f"登录错误: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出"""
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """获取登录状态"""
    if session.get('zotero_id') and session.get('zotero_key'):
        return jsonify({
            'success': True,
            'logged_in': True,
            'zotero_id': session.get('zotero_id'),
            'user_id': session.get('user_id')
        })
    return jsonify({
        'success': True,
        'logged_in': False
    })

@app.route('/api/zotero/papers')
@login_required
def get_zotero_papers():
    """获取 Zotero 论文列表"""
    try:
        corpus, collections = get_zotero_corpus()
        papers = [format_zotero_item(item) for item in corpus]
        
        # 按收藏夹分组
        papers_by_collection = {}
        for paper in papers:
            if paper['collections']:
                for collection in paper['collections']:
                    if collection not in papers_by_collection:
                        papers_by_collection[collection] = []
                    papers_by_collection[collection].append(paper)
            else:
                if '未分类' not in papers_by_collection:
                    papers_by_collection['未分类'] = []
                papers_by_collection['未分类'].append(paper)
        
        return jsonify({
            'success': True,
            'papers': papers,
            'papersByCollection': papers_by_collection,
            'total': len(papers)
        })
    except Exception as e:
        logger.error(f"Error fetching Zotero papers: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/zotero/collections')
@login_required
def get_zotero_collections():
    """获取 Zotero 收藏夹列表"""
    try:
        corpus, collections = get_zotero_corpus()
        
        # 获取所有收藏夹路径
        collection_paths = set()
        for item in corpus:
            collection_paths.update(item.get('paths', []))
        
        return jsonify({
            'success': True,
            'collections': sorted(list(collection_paths))
        })
    except Exception as e:
        logger.error(f"Error fetching collections: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/zotero/refresh', methods=['POST'])
@login_required
def refresh_zotero_cache():
    """强制刷新 Zotero 缓存"""
    try:
        corpus, collections = get_zotero_corpus(force_refresh=True)
        return jsonify({
            'success': True,
            'message': f'已刷新缓存，共 {len(corpus)} 篇论文',
            'count': len(corpus)
        })
    except Exception as e:
        logger.error(f"Error refreshing cache: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/zotero/clear-cache', methods=['POST'])
@login_required
def clear_zotero_cache():
    """清除 Zotero 缓存"""
    try:
        cache_path = get_cache_path()
        if cache_path and cache_path.exists():
            cache_path.unlink()
            return jsonify({
                'success': True,
                'message': '缓存已清除'
            })
        else:
            return jsonify({
                'success': True,
                'message': '缓存不存在'
            })
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def send_progress(message, progress=None):
    """发送进度更新"""
    data = {'message': message}
    if progress is not None:
        data['progress'] = progress
    return f"data: {json.dumps(data)}\n\n"

@app.route('/api/recommendations/stream')
@login_required
def get_recommendations_stream():
    """使用 SSE 流式获取推荐文章"""
    # 获取请求参数
    arxiv_query = request.args.get('arxiv_query', ARXIV_QUERY)
    date_range = request.args.get('date_range', None)  # 格式: "2025-01-01,2025-01-06"
    force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
    selected_paper_keys_str = request.args.get('selected_paper_keys', None)
    
    # 解析选中的文章 key 列表
    selected_paper_keys = None
    if selected_paper_keys_str:
        selected_paper_keys = [k.strip() for k in selected_paper_keys_str.split(',') if k.strip()]
        if len(selected_paper_keys) == 0:
            selected_paper_keys = None
    
    def generate():
        try:
            # 检查缓存
            if not force_refresh:
                cache_data = load_recommendations_cache(arxiv_query, date_range, selected_paper_keys)
                if cache_data:
                    # 获取参考文章数量（从缓存中读取或重新计算）
                    corpus, _ = get_zotero_corpus()
                    if selected_paper_keys:
                        corpus = [item for item in corpus if item.get('key') in selected_paper_keys]
                    reference_count = len(corpus)
                    
                    yield send_progress("✓ 使用缓存的推荐结果", 100)
                    yield f"data: {json.dumps({'success': True, 'papers': cache_data['papers'], 'total': len(cache_data['papers']), 'cached': True, 'reference_count': reference_count})}\n\n"
                    return
            
            # 步骤 1: 获取 Zotero 语料库
            yield send_progress("正在加载你的 Zotero 论文库...", 10)
            corpus, _ = get_zotero_corpus()
            
            if not corpus:
                yield send_progress("Zotero 库为空，无法生成推荐", 100)
                yield f"data: {json.dumps({'success': False, 'error': 'Zotero 库为空'})}\n\n"
                return
            
            # 如果指定了选中的文章，进行过滤
            if selected_paper_keys:
                original_count = len(corpus)
                corpus = [paper for paper in corpus if paper.get('key') in selected_paper_keys]
                yield send_progress(f"✓ 已加载 {len(corpus)} 篇选中的 Zotero 论文（从 {original_count} 篇中筛选）", 20)
            else:
                yield send_progress(f"✓ 已加载 {len(corpus)} 篇 Zotero 论文", 20)
            
            if not corpus:
                yield send_progress("没有选中的文章，无法生成推荐", 100)
                yield f"data: {json.dumps({'success': False, 'error': '没有选中的文章'})}\n\n"
                return
            
            time.sleep(0.1)  # 让前端有时间显示
            
            # 步骤 2: 获取 ArXiv RSS Feed
            yield send_progress(f"正在从 ArXiv RSS Feed 获取论文列表（类别: {arxiv_query}）...", 30)
            client = arxiv.Client(num_retries=10, delay_seconds=10)
            feed = feedparser.parse(f"https://rss.arxiv.org/atom/{arxiv_query}")
            
            if feed.feed.get('title') and 'Feed error for query' in feed.feed.title:
                raise Exception(f"Invalid ARXIV_QUERY: {arxiv_query}")
            
            papers = []
            all_paper_ids = []
            new_paper_count = 0
            
            # 首先尝试获取新论文
            for entry in feed.entries:
                if hasattr(entry, 'arxiv_announce_type') and entry.arxiv_announce_type == 'new':
                    paper_id = entry.id
                    if paper_id.startswith("oai:arXiv.org:"):
                        paper_id = paper_id.removeprefix("oai:arXiv.org:")
                    all_paper_ids.append(paper_id)
                    new_paper_count += 1
            
            if len(all_paper_ids) == 0:
                yield send_progress("今天没有新论文，使用最近的论文...", 35)
                for entry in feed.entries:
                    paper_id = entry.id
                    if paper_id.startswith("oai:arXiv.org:"):
                        paper_id = paper_id.removeprefix("oai:arXiv.org:")
                    if 'v' in paper_id:
                        paper_id = paper_id.rsplit('v', 1)[0]
                    all_paper_ids.append(paper_id)
                yield send_progress(f"从 RSS Feed 找到 {len(feed.entries)} 篇论文，将处理全部 {len(all_paper_ids)} 篇", 38)
            else:
                yield send_progress(f"✓ 从 ArXiv RSS Feed 找到 {new_paper_count} 篇新论文（共 {len(feed.entries)} 篇），将处理全部", 38)
            
            # 处理所有论文，不再限制为 100 篇
            yield send_progress(f"将处理 {len(all_paper_ids)} 篇候选论文", 40)
            time.sleep(0.1)
            
            # 步骤 3: 分批获取论文详情
            total_batches = (len(all_paper_ids) + BATCH_SIZE - 1) // BATCH_SIZE
            yield send_progress(f"开始获取论文详情，共 {total_batches} 批，每批 {BATCH_SIZE} 篇...", 42)
            time.sleep(0.1)
            
            for i in range(0, len(all_paper_ids), BATCH_SIZE):
                batch_num = i // BATCH_SIZE + 1
                progress = 40 + int((batch_num / total_batches) * 30)
                yield send_progress(f"正在获取第 {batch_num}/{total_batches} 批论文详情...", progress)
                
                try:
                    batch_ids = all_paper_ids[i:i+BATCH_SIZE]
                    search = arxiv.Search(id_list=batch_ids)
                    batch = [ArxivPaper(p) for p in client.results(search)]
                    papers.extend(batch)
                    yield send_progress(f"✓ 已获取 {len(papers)}/{len(all_paper_ids)} 篇论文详情（批次 {batch_num}/{total_batches}）", progress)
                except Exception as e:
                    logger.warning(f"获取批次 {batch_num} 失败: {e}")
                    yield send_progress(f"⚠️ 批次 {batch_num} 获取失败，继续处理...", progress)
                    continue
                time.sleep(0.1)
            
            if not papers:
                yield send_progress("❌ 无法获取 ArXiv 论文详情", 100)
                yield f"data: {json.dumps({'success': False, 'error': '无法获取 ArXiv 论文'})}\n\n"
                return
            
            yield send_progress(f"✓ 成功获取 {len(papers)} 篇论文详情", 70)
            time.sleep(0.1)
            
            # 步骤 4: 计算推荐分数
            yield send_progress(f"正在计算推荐分数（{len(papers)} 篇候选论文 vs {len(corpus)} 篇 Zotero 论文）...", 75)
            papers = rerank_paper(papers, corpus)
            max_score = papers[0].score if papers else 0
            yield send_progress(f"✓ 推荐分数计算完成（最高分: {max_score:.2f}）", 85)
            time.sleep(0.1)
            
            # 步骤 5: 格式化结果
            papers = papers[:MAX_PAPER_NUM]
            yield send_progress(f"正在整理推荐结果（将返回前 {len(papers)} 篇）...", 90)
            time.sleep(0.1)
            
            formatted_papers = []
            for i, paper in enumerate(papers, 1):
                authors = [f"{a.name}" for a in paper.authors]
                
                # 只在启用时才获取 code_url（会很慢）
                code_url = None
                if FETCH_CODE_URL:
                    try:
                        code_url = paper.code_url
                    except Exception as e:
                        logger.debug(f"Failed to get code_url for {paper.arxiv_id}: {e}")
                        code_url = None
                
                formatted_papers.append({
                    'title': paper.title,
                    'authors': authors,
                    'abstract': paper.summary,
                    'arxiv_id': paper.arxiv_id,
                    'pdf_url': paper.pdf_url,
                    'code_url': code_url,
                    'score': round(paper.score, 2) if paper.score else 0,
                    'date': datetime.now().strftime('%Y-%m-%d')
                })
                
                # 更新进度（如果获取 code_url）
                if FETCH_CODE_URL and i % 10 == 0:
                    progress = 90 + int((i / len(papers)) * 5)
                    yield send_progress(f"正在获取代码链接 ({i}/{len(papers)})...", progress)
            
            yield send_progress(f"✓ 完成！共推荐 {len(formatted_papers)} 篇论文", 100)
            time.sleep(0.1)
            
            # 保存缓存
            save_recommendations_cache(arxiv_query, date_range, formatted_papers, selected_paper_keys)

            # 发送最终结果（包含参考文章数量）
            yield f"data: {json.dumps({'success': True, 'papers': formatted_papers, 'total': len(formatted_papers), 'cached': False, 'reference_count': len(corpus)})}\n\n"
            
        except Exception as e:
            logger.error(f"Error fetching recommendations: {e}")
            yield send_progress(f"发生错误: {str(e)}", 100)
            yield f"data: {json.dumps({'success': False, 'error': str(e)})}\n\n"
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/recommendations')
def get_recommendations():
    """获取推荐文章（兼容旧接口）"""
    try:
        # 获取 Zotero 语料库
        corpus, _ = get_zotero_corpus()
        
        if not corpus:
            return jsonify({
                'success': True,
                'papers': [],
                'message': 'Zotero 库为空，无法生成推荐'
            })
        
        # 获取 ArXiv 论文
        logger.info("正在获取 ArXiv 论文...")
        client = arxiv.Client(num_retries=10, delay_seconds=10)
        feed = feedparser.parse(f"https://rss.arxiv.org/atom/{ARXIV_QUERY}")
        
        if feed.feed.get('title') and 'Feed error for query' in feed.feed.title:
            raise Exception(f"Invalid ARXIV_QUERY: {ARXIV_QUERY}")
        
        papers = []
        all_paper_ids = []
        
        # 首先尝试获取新论文
        for entry in feed.entries:
            if hasattr(entry, 'arxiv_announce_type') and entry.arxiv_announce_type == 'new':
                paper_id = entry.id
                if paper_id.startswith("oai:arXiv.org:"):
                    paper_id = paper_id.removeprefix("oai:arXiv.org:")
                all_paper_ids.append(paper_id)
        
        logger.info(f"找到 {len(all_paper_ids)} 篇新论文")
        
        # 如果没有新论文（可能是周末或节假日），使用最近的论文
        if len(all_paper_ids) == 0:
            logger.info("今天没有新论文，使用最近的论文...")
            for entry in feed.entries:  # 处理所有论文
                paper_id = entry.id
                if paper_id.startswith("oai:arXiv.org:"):
                    paper_id = paper_id.removeprefix("oai:arXiv.org:")
                # 移除版本号（如 v1, v2）
                if 'v' in paper_id:
                    paper_id = paper_id.rsplit('v', 1)[0]
                all_paper_ids.append(paper_id)
            logger.info(f"使用最近的 {len(all_paper_ids)} 篇论文")
        
        # 处理所有论文，不再限制数量
        
        for i in range(0, len(all_paper_ids), BATCH_SIZE):
            try:
                batch_ids = all_paper_ids[i:i+BATCH_SIZE]
                batch_num = i // BATCH_SIZE + 1
                logger.debug(f"正在获取批次 {batch_num}，包含 {len(batch_ids)} 篇论文")
                search = arxiv.Search(id_list=batch_ids)
                batch = [ArxivPaper(p) for p in client.results(search)]
                papers.extend(batch)
                logger.info(f"成功获取 {len(batch)} 篇论文（批次 {batch_num}，总计 {len(papers)} 篇）")
            except Exception as e:
                logger.warning(f"获取批次 {batch_num} 失败: {e}")
                logger.debug(f"失败的论文 ID: {all_paper_ids[i:i+BATCH_SIZE]}")
                continue
        
        if not papers:
            return jsonify({
                'success': True,
                'papers': [],
                'message': '无法获取 ArXiv 论文，请稍后重试'
            })
        
        # 重新排序
        logger.info(f"正在计算推荐分数（{len(papers)} 篇候选论文，{len(corpus)} 篇 Zotero 论文）...")
        papers = rerank_paper(papers, corpus)
        logger.info(f"推荐分数计算完成，最高分: {papers[0].score if papers else 0:.2f}")
        
        # 限制数量
        papers = papers[:MAX_PAPER_NUM]
        
        # 格式化输出
        formatted_papers = []
        for paper in papers:
            authors = [f"{a.name}" for a in paper.authors]
            
            # 只在启用时才获取 code_url（会很慢）
            code_url = None
            if FETCH_CODE_URL:
                try:
                    code_url = paper.code_url
                except Exception as e:
                    logger.debug(f"Failed to get code_url for {paper.arxiv_id}: {e}")
                    code_url = None
            
            formatted_papers.append({
                'title': paper.title,
                'authors': authors,
                'abstract': paper.summary,
                'arxiv_id': paper.arxiv_id,
                'pdf_url': paper.pdf_url,
                'code_url': code_url,
                'score': round(paper.score, 2) if paper.score else 0,
                'date': datetime.now().strftime('%Y-%m-%d')
            })
        
        return jsonify({
            'success': True,
            'papers': formatted_papers,
            'total': len(formatted_papers)
        })
    except Exception as e:
        logger.error(f"Error fetching recommendations: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
