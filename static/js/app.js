// 全局状态
let zoteroPapers = [];
let zoteroPapersByCollection = {};
let currentCollection = 'all';

// ArXiv 类别选项（人工智能理工科相关）
const ARXIV_CATEGORIES = [
    { value: 'cs.AI', label: '人工智能 (cs.AI)' },
    { value: 'cs.CV', label: '计算机视觉 (cs.CV)' },
    { value: 'cs.LG', label: '机器学习 (cs.LG)' },
    { value: 'cs.CL', label: '自然语言处理 (cs.CL)' },
    { value: 'cs.NE', label: '神经网络 (cs.NE)' },
    { value: 'cs.RO', label: '机器人学 (cs.RO)' },
    { value: 'cs.SY', label: '系统与控制 (cs.SY)' },
    { value: 'cs.IT', label: '信息论 (cs.IT)' },
    { value: 'cs.DS', label: '数据结构与算法 (cs.DS)' },
    { value: 'cs.CR', label: '密码学与安全 (cs.CR)' },
    { value: 'cs.CC', label: '计算复杂性 (cs.CC)' },
    { value: 'cs.MA', label: '多智能体系统 (cs.MA)' },
    { value: 'cs.SI', label: '社交和信息网络 (cs.SI)' },
    { value: 'cs.MM', label: '多媒体 (cs.MM)' },
    { value: 'cs.DC', label: '分布式计算 (cs.DC)' },
    { value: 'stat.ML', label: '统计机器学习 (stat.ML)' },
    { value: 'math.OC', label: '优化与控制 (math.OC)' },
    { value: 'eess.IV', label: '图像与视频处理 (eess.IV)' },
    { value: 'eess.SP', label: '信号处理 (eess.SP)' },
    { value: 'cs.PL', label: '编程语言 (cs.PL)' }
];

// 默认选中的类别
const DEFAULT_CATEGORIES = ['cs.AI', 'cs.CV', 'cs.LG', 'cs.CL'];

// 推荐设置状态
let recommendationSettings = {
    arxivQuery: 'cs.AI+cs.CV+cs.LG+cs.CL',
    dateRange: null,
    selectedPaperKeys: null,  // 选中的文章 key 列表，null 表示全部选中
    lastSettings: null  // 用于检测设置是否改变
};

// 初始化 ArXiv 类别多选框
function initArxivCategories() {
    const container = document.getElementById('arxiv-categories');
    if (!container) return;
    
    // 获取当前选中的类别（从默认值或设置中）
    const currentQuery = recommendationSettings.arxivQuery || 'cs.AI+cs.CV+cs.LG+cs.CL';
    const selectedCategories = currentQuery.split('+').map(c => c.trim());
    
    // 渲染类别选项
    container.innerHTML = ARXIV_CATEGORIES.map(category => {
        const isChecked = selectedCategories.includes(category.value);
        return `
            <label class="category-checkbox-label">
                <input type="checkbox" 
                       class="category-checkbox" 
                       value="${category.value}" 
                       ${isChecked ? 'checked' : ''}
                       onchange="window.updateArxivQuery()">
                <span>${category.label}</span>
            </label>
        `;
    }).join('');
    
    // 更新 arxivQuery
    window.updateArxivQuery();
}

// 更新 ArXiv 查询字符串（从多选框获取）
window.updateArxivQuery = function() {
    const checkboxes = document.querySelectorAll('.category-checkbox:checked');
    const selectedValues = Array.from(checkboxes).map(cb => cb.value);
    
    if (selectedValues.length === 0) {
        recommendationSettings.arxivQuery = '';
    } else {
        recommendationSettings.arxivQuery = selectedValues.join('+');
    }
};

// 全选/全不选 ArXiv 类别
window.selectAllCategories = function(select) {
    const checkboxes = document.querySelectorAll('.category-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = select;
    });
    window.updateArxivQuery();
};

// 检查登录状态并初始化
document.addEventListener('DOMContentLoaded', async () => {
    await checkAuthStatus();
});

// 检查登录状态
async function checkAuthStatus() {
    try {
        const response = await fetch('/api/auth/status');
        const data = await response.json();
        
        if (data.logged_in) {
            // 已登录，显示主界面
            showMainInterface(data.zotero_id);
        } else {
            // 未登录，显示登录界面
            showLoginInterface();
        }
    } catch (error) {
        console.error('检查登录状态失败:', error);
        showLoginInterface();
    }
}

// 显示登录界面
function showLoginInterface() {
    document.getElementById('login-modal').style.display = 'flex';
    document.getElementById('main-container').style.display = 'none';
    
    // 绑定登录表单
    const loginForm = document.getElementById('login-form');
    loginForm.onsubmit = async (e) => {
        e.preventDefault();
        await handleLogin();
    };
}

// 显示主界面
function showMainInterface(zoteroId) {
    document.getElementById('login-modal').style.display = 'none';
    document.getElementById('main-container').style.display = 'block';
    document.getElementById('user-zotero-id').textContent = `Zotero ID: ${zoteroId}`;
    
    // 初始化主界面功能
    initTabs();
    initArxivCategories();
    loadZoteroPapers();
    setupEventListeners();
}

// 处理登录
async function handleLogin() {
    const zoteroId = document.getElementById('zotero-id').value.trim();
    const zoteroKey = document.getElementById('zotero-key').value.trim();
    const errorEl = document.getElementById('login-error');
    
    if (!zoteroId || !zoteroKey) {
        errorEl.textContent = '请输入 Zotero ID 和 API Key';
        errorEl.style.display = 'block';
        return;
    }
    
    try {
        errorEl.style.display = 'none';
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                zotero_id: zoteroId,
                zotero_key: zoteroKey
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showMainInterface(data.zotero_id);
        } else {
            errorEl.textContent = data.error || '登录失败';
            errorEl.style.display = 'block';
        }
    } catch (error) {
        errorEl.textContent = `登录错误: ${error.message}`;
        errorEl.style.display = 'block';
    }
}

// 处理登出
async function handleLogout() {
    try {
        await fetch('/api/auth/logout', {
            method: 'POST',
            credentials: 'include'
        });
        showLoginInterface();
        // 清空表单
        document.getElementById('login-form').reset();
    } catch (error) {
        console.error('登出失败:', error);
    }
}

// 标签页切换
function initTabs() {
    const navButtons = document.querySelectorAll('.nav-btn');
    const tabContents = document.querySelectorAll('.tab-content');
    
    navButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            
            // 关闭之前的 EventSource 连接
            if (window.currentEventSource) {
                window.currentEventSource.close();
                window.currentEventSource = null;
            }
            
            // 更新按钮状态
            navButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // 更新内容显示
            tabContents.forEach(content => content.classList.remove('active'));
            document.getElementById(`${tab}-tab`).classList.add('active');
            
            // 如果是推荐标签页且还没有加载，则加载
            if (tab === 'recommendations') {
                // 确保文章选择器已加载
                if (zoteroPapers.length > 0) {
                    loadPaperSelection();
                }
                // 如果还没有推荐结果，则加载
                if (document.getElementById('recommendations-papers').children.length === 0) {
                    loadRecommendations(false);  // 不强制刷新，使用缓存
                }
            }
        });
    });
}

// 设置事件监听器
function setupEventListeners() {
    // 收藏夹筛选
    const collectionSelect = document.getElementById('collection-select');
    collectionSelect.addEventListener('change', (e) => {
        currentCollection = e.target.value;
        renderZoteroPapers();
    });
    
    // 切换设置面板
    const toggleSettingsBtn = document.getElementById('toggle-settings');
    const settingsPanel = document.getElementById('recommendations-settings');
    if (toggleSettingsBtn && settingsPanel) {
        toggleSettingsBtn.addEventListener('click', () => {
            settingsPanel.style.display = settingsPanel.style.display === 'none' ? 'block' : 'none';
        });
    }
    
    // 应用设置
    const applySettingsBtn = document.getElementById('apply-settings');
    if (applySettingsBtn) {
        applySettingsBtn.addEventListener('click', () => {
            applyRecommendationSettings();
        });
    }
    
    // 重置设置
    const resetSettingsBtn = document.getElementById('reset-settings');
    if (resetSettingsBtn) {
        resetSettingsBtn.addEventListener('click', () => {
            resetRecommendationSettings();
        });
    }
    
    // 刷新推荐
    const refreshBtn = document.getElementById('refresh-recommendations');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            // 关闭之前的连接
            if (window.currentEventSource) {
                window.currentEventSource.close();
                window.currentEventSource = null;
            }
            // 清空之前的结果
            document.getElementById('recommendations-papers').innerHTML = '';
            loadRecommendations(true);  // 强制刷新
        });
    }
    
    // 全选文章
    const selectAllBtn = document.getElementById('select-all-papers');
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', () => {
            window.selectAllPapers(true);
        });
    }
    
    // 全不选文章
    const deselectAllBtn = document.getElementById('deselect-all-papers');
    if (deselectAllBtn) {
        deselectAllBtn.addEventListener('click', () => {
            window.selectAllPapers(false);
        });
    }
}

// 加载 Zotero 论文
async function loadZoteroPapers() {
    const loadingEl = document.getElementById('zotero-loading');
    const papersEl = document.getElementById('zotero-papers');
    const emptyEl = document.getElementById('zotero-empty');
    
    try {
        loadingEl.style.display = 'flex';
        papersEl.innerHTML = '';
        emptyEl.style.display = 'none';
        
        const response = await fetch('/api/zotero/papers');
        const data = await response.json();
        
        if (data.success) {
            zoteroPapers = data.papers;
            zoteroPapersByCollection = data.papersByCollection;
            
            // 更新收藏夹选择器
            updateCollectionSelect();
            
            // 渲染论文
            renderZoteroPapers();
            
            // 加载文章选择器（在 Zotero 论文加载完成后，但 loadPaperSelection 现在会直接调用 API，所以这里可以省略）
            // loadPaperSelection();  // 现在 loadPaperSelection 会直接调用 API，不需要等待
        } else {
            throw new Error(data.error || '加载失败');
        }
    } catch (error) {
        console.error('Error loading Zotero papers:', error);
        papersEl.innerHTML = `<div class="empty-state"><p>加载失败: ${error.message}</p></div>`;
        // 即使加载失败，也尝试加载文章选择器（可能使用空列表）
        loadPaperSelection();
    } finally {
        loadingEl.style.display = 'none';
    }
}

// 更新收藏夹选择器
function updateCollectionSelect() {
    const select = document.getElementById('collection-select');
    const collections = Object.keys(zoteroPapersByCollection).sort();
    
    // 保留"所有收藏夹"选项
    select.innerHTML = '<option value="all">所有收藏夹</option>';
    
    collections.forEach(collection => {
        const option = document.createElement('option');
        option.value = collection;
        option.textContent = `${collection} (${zoteroPapersByCollection[collection].length})`;
        select.appendChild(option);
    });
}

// 渲染 Zotero 论文
function renderZoteroPapers() {
    const papersEl = document.getElementById('zotero-papers');
    const emptyEl = document.getElementById('zotero-empty');
    
    let papersToShow = [];
    
    if (currentCollection === 'all') {
        papersToShow = zoteroPapers;
    } else {
        papersToShow = zoteroPapersByCollection[currentCollection] || [];
    }
    
    if (papersToShow.length === 0) {
        papersEl.innerHTML = '';
        emptyEl.style.display = 'block';
        return;
    }
    
    emptyEl.style.display = 'none';
    papersEl.innerHTML = papersToShow.map(paper => `
        <div class="paper-card">
            <h3 class="paper-title">${escapeHtml(paper.title)}</h3>
            <div class="paper-authors">${paper.authors.join(', ')}</div>
            <p class="paper-abstract">${escapeHtml(paper.abstract || '暂无摘要')}</p>
            <div class="paper-meta">
                <div>
                    <div class="paper-date">${formatDate(paper.dateAdded || paper.date)}</div>
                    ${paper.collections.length > 0 ? `<div class="paper-collection" style="margin-top: 8px;">${escapeHtml(paper.collections[0])}</div>` : ''}
                </div>
            </div>
            ${paper.url ? `<div class="paper-actions"><a href="${paper.url}" target="_blank" class="btn btn-primary">查看原文</a></div>` : ''}
        </div>
    `).join('');
}

// 加载文章选择器（直接调用 API，不依赖全局变量，可以更快加载）
async function loadPaperSelection() {
    const container = document.getElementById('paper-selection-container');
    if (!container) return;
    
    // 如果已经有数据且已加载过，直接使用全局变量（避免重复请求）
    if (zoteroPapers.length > 0 && container.innerHTML && !container.innerHTML.includes('正在加载')) {
        return;
    }
    
    container.innerHTML = '<div class="paper-selection-loading">正在加载文章列表...</div>';
    
    try {
        // 直接调用 API（后端有缓存，应该很快）
        const response = await fetch('/api/zotero/papers');
        const data = await response.json();
        
        if (!data.success) {
            throw new Error(data.error || '加载失败');
        }
        
        const papers = data.papers;
        
        // 按收藏夹分组
        const papersByCollection = {};
        const uncategorized = [];
        
        papers.forEach(paper => {
            if (paper.collections && paper.collections.length > 0) {
                paper.collections.forEach(collection => {
                    if (!papersByCollection[collection]) {
                        papersByCollection[collection] = [];
                    }
                    papersByCollection[collection].push(paper);
                });
            } else {
                uncategorized.push(paper);
            }
        });
        
        // 渲染文章选择器
        let html = '';
        
        // 渲染有收藏夹的文章
        Object.keys(papersByCollection).sort().forEach(collection => {
            const papers = papersByCollection[collection];
            html += `
                <div class="collection-group" data-collection="${escapeHtml(collection)}">
                    <div class="collection-header" onclick="window.toggleCollectionExpand('${escapeHtml(collection)}')">
                        <span class="collection-expand-icon">▶</span>
                        <input type="checkbox" class="collection-checkbox" 
                               data-collection="${escapeHtml(collection)}" 
                               checked
                               onclick="event.stopPropagation();"
                               onchange="window.toggleCollection('${escapeHtml(collection)}', this.checked)">
                        <span class="collection-name">${escapeHtml(collection)}</span>
                        <span class="collection-count">${papers.length} 篇</span>
                    </div>
                    <div class="collection-papers" style="display: none;">
                        ${papers.map(paper => `
                            <div class="paper-item">
                                <input type="checkbox" class="paper-checkbox" 
                                       data-paper-key="${paper.key}" 
                                       checked
                                       onchange="window.updatePaperSelection()">
                                <div class="paper-info">
                                    <div class="paper-info-title">${escapeHtml(paper.title)}</div>
                                    <div class="paper-info-meta">${paper.authors.join(', ')}</div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        });
        
        // 渲染未分类的文章
        if (uncategorized.length > 0) {
            html += `
                <div class="collection-group" data-collection="未分类">
                    <div class="collection-header" onclick="window.toggleCollectionExpand('未分类')">
                        <span class="collection-expand-icon">▶</span>
                        <input type="checkbox" class="collection-checkbox" 
                               data-collection="未分类" 
                               checked
                               onclick="event.stopPropagation();"
                               onchange="window.toggleCollection('未分类', this.checked)">
                        <span class="collection-name">未分类</span>
                        <span class="collection-count">${uncategorized.length} 篇</span>
                    </div>
                    <div class="collection-papers" style="display: none;">
                        ${uncategorized.map(paper => `
                            <div class="paper-item">
                                <input type="checkbox" class="paper-checkbox" 
                                       data-paper-key="${paper.key}" 
                                       checked
                                       onchange="window.updatePaperSelection()">
                                <div class="paper-info">
                                    <div class="paper-info-title">${escapeHtml(paper.title)}</div>
                                    <div class="paper-info-meta">${paper.authors.join(', ')}</div>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }
        
        container.innerHTML = html || '<div class="paper-selection-loading">暂无文章</div>';
        
        // 初始化选中状态（全部选中）
        window.updatePaperSelection();
    } catch (error) {
        console.error('Error loading paper selection:', error);
        container.innerHTML = `<div class="paper-selection-loading">加载失败: ${error.message}</div>`;
    }
};

// 切换收藏夹展开/收起（暴露到全局作用域，供 HTML 调用）
window.toggleCollectionExpand = function(collectionName) {
    const collectionGroup = document.querySelector(`[data-collection="${escapeHtml(collectionName)}"]`);
    if (!collectionGroup) return;
    
    const papersContainer = collectionGroup.querySelector('.collection-papers');
    const expandIcon = collectionGroup.querySelector('.collection-expand-icon');
    
    if (papersContainer && expandIcon) {
        const isExpanded = papersContainer.style.display !== 'none';
        papersContainer.style.display = isExpanded ? 'none' : 'block';
        expandIcon.textContent = isExpanded ? '▶' : '▼';
    }
};

// 切换收藏夹选择（暴露到全局作用域，供 HTML 调用）
window.toggleCollection = function(collectionName, checked) {
    const collectionGroup = document.querySelector(`[data-collection="${escapeHtml(collectionName)}"]`);
    if (!collectionGroup) return;
    
    const checkboxes = collectionGroup.querySelectorAll('.paper-checkbox[data-paper-key]');
    checkboxes.forEach(cb => {
        cb.checked = checked !== undefined ? checked : !cb.checked;
    });
    
    // 更新收藏夹复选框状态
    const collectionCheckbox = collectionGroup.querySelector('.collection-checkbox');
    if (collectionCheckbox) {
        collectionCheckbox.checked = Array.from(checkboxes).every(cb => cb.checked);
    }
    
    window.updatePaperSelection();
};;

// 全选/全不选文章（暴露到全局作用域）
window.selectAllPapers = function(select) {
    // 先展开所有收藏夹，确保所有复选框都可见
    const collectionsToExpand = [];
    document.querySelectorAll('.collection-papers').forEach(container => {
        if (container.style.display === 'none' || container.style.display === '') {
            const collectionGroup = container.closest('.collection-group');
            if (collectionGroup) {
                const collectionName = collectionGroup.dataset.collection;
                collectionsToExpand.push(collectionName);
                // 直接设置显示，不等待动画
                container.style.display = 'block';
                const expandIcon = collectionGroup.querySelector('.collection-expand-icon');
                if (expandIcon) {
                    expandIcon.textContent = '▼';
                }
            }
        }
    });
    
    // 立即更新复选框状态（不等待动画）
    const checkboxes = document.querySelectorAll('.paper-checkbox[data-paper-key]');
    checkboxes.forEach(cb => {
        cb.checked = select;
    });
    
    // 更新收藏夹复选框状态
    document.querySelectorAll('.collection-checkbox').forEach(cb => {
        cb.checked = select;  // 直接设置为 select 状态
    });
    
    // 更新文章选择状态
    window.updatePaperSelection();
};

// 更新文章选择状态（暴露到全局作用域，供 HTML 调用）
window.updatePaperSelection = function() {
    const checkboxes = document.querySelectorAll('.paper-checkbox[data-paper-key]');
    const selectedKeys = Array.from(checkboxes)
        .filter(cb => cb.checked)
        .map(cb => cb.dataset.paperKey);
    
    // 如果全部选中，设置为 null（表示使用全部）
    const allKeys = Array.from(checkboxes).map(cb => cb.dataset.paperKey);
    if (selectedKeys.length === allKeys.length) {
        recommendationSettings.selectedPaperKeys = null;
    } else {
        recommendationSettings.selectedPaperKeys = selectedKeys;
    }
    
    // 更新收藏夹复选框状态
    document.querySelectorAll('.collection-checkbox').forEach(cb => {
        const collectionName = cb.dataset.collection;
        const collectionGroup = document.querySelector(`[data-collection="${escapeHtml(collectionName)}"]`);
        if (collectionGroup) {
            const paperCheckboxes = collectionGroup.querySelectorAll('.paper-checkbox[data-paper-key]');
            cb.checked = Array.from(paperCheckboxes).every(pcb => pcb.checked);
        }
    });
};

// 应用推荐设置
function applyRecommendationSettings() {
    // 从多选框获取选中的类别
    window.updateArxivQuery();
    const arxivQuery = recommendationSettings.arxivQuery;
    
    if (!arxivQuery) {
        alert('请至少选择一个 ArXiv 类别');
        return;
    }
    
    const dateStart = document.getElementById('date-range-start').value;
    const dateEnd = document.getElementById('date-range-end').value;
    
    // 更新文章选择
    window.updatePaperSelection();
    
    // 更新设置
    recommendationSettings.arxivQuery = arxivQuery;
    recommendationSettings.dateRange = (dateStart && dateEnd) ? `${dateStart},${dateEnd}` : null;
    
    // 检查设置是否改变
    const selectedKeysStr = recommendationSettings.selectedPaperKeys 
        ? recommendationSettings.selectedPaperKeys.sort().join(',') 
        : 'all';
    const currentSettings = `${arxivQuery}_${recommendationSettings.dateRange || 'all'}_${selectedKeysStr}`;
    const settingsChanged = recommendationSettings.lastSettings !== currentSettings;
    
    if (settingsChanged) {
        recommendationSettings.lastSettings = currentSettings;
        // 关闭之前的连接
        if (window.currentEventSource) {
            window.currentEventSource.close();
            window.currentEventSource = null;
        }
        // 清空之前的结果
        document.getElementById('recommendations-papers').innerHTML = '';
        // 重新加载推荐
        loadRecommendations(false);
        // 关闭设置面板
        document.getElementById('recommendations-settings').style.display = 'none';
    } else {
        alert('设置未改变，无需重新推荐');
    }
}

// 重置推荐设置
function resetRecommendationSettings() {
    // 重置 ArXiv 类别多选框（选中默认类别）
    const checkboxes = document.querySelectorAll('.category-checkbox');
    checkboxes.forEach(cb => {
        cb.checked = DEFAULT_CATEGORIES.includes(cb.value);
    });
    window.updateArxivQuery();
    
    // 重置日期范围
    document.getElementById('date-range-start').value = '';
    document.getElementById('date-range-end').value = '';
    recommendationSettings.dateRange = null;
    recommendationSettings.selectedPaperKeys = null;
    recommendationSettings.lastSettings = null;

    // 重置文章选择（全选）
    window.selectAllPapers(true);
}

// 加载推荐论文（使用 SSE 流式更新）
function loadRecommendations(forceRefresh = false) {
    const loadingEl = document.getElementById('recommendations-loading');
    const papersEl = document.getElementById('recommendations-papers');
    const emptyEl = document.getElementById('recommendations-empty');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const progressStats = document.getElementById('progress-stats');
    
    // 重置状态
    loadingEl.style.display = 'flex';
    papersEl.innerHTML = '';
    emptyEl.style.display = 'none';
    const infoEl = document.getElementById('recommendation-info');
    if (infoEl) infoEl.style.display = 'none';
    progressBar.style.width = '0%';
    progressText.textContent = '正在初始化...';
    progressStats.textContent = '';
    statsCache = {}; // 重置统计缓存
    
    // 构建请求 URL
    const params = new URLSearchParams({
        arxiv_query: recommendationSettings.arxivQuery,
        force_refresh: forceRefresh ? 'true' : 'false'
    });
    
    if (recommendationSettings.dateRange) {
        params.append('date_range', recommendationSettings.dateRange);
    }
    
    // 添加选中的文章 key 列表
    if (recommendationSettings.selectedPaperKeys && recommendationSettings.selectedPaperKeys.length > 0) {
        params.append('selected_paper_keys', recommendationSettings.selectedPaperKeys.join(','));
    }
    
    // 使用 EventSource 接收 SSE 流
    const eventSource = new EventSource(`/api/recommendations/stream?${params.toString()}`);
    
    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            // 更新进度
            if (data.progress !== undefined) {
                progressBar.style.width = data.progress + '%';
            }
            
            if (data.message) {
                progressText.textContent = data.message;
                
                // 从消息中提取统计信息
                updateProgressStats(data.message);
            }
            
            // 检查是否完成
            if (data.success !== undefined) {
                eventSource.close();
                loadingEl.style.display = 'none';
                
                if (data.success) {
                    if (data.papers && data.papers.length > 0) {
                        renderRecommendations(data.papers);
                        
                        // 显示参考文章信息和缓存提示
                        const infoEl = document.getElementById('recommendation-info');
                        if (infoEl) {
                            let infoText = '';
                            if (data.reference_count) {
                                infoText = `📚 使用了 ${data.reference_count} 篇 Zotero 文章作为参考`;
                            }
                            if (data.cached) {
                                if (infoText) {
                                    infoText += ' • ';
                                }
                                infoText += '💾 显示的是缓存的推荐结果';
                            }
                            if (infoText) {
                                infoEl.textContent = infoText;
                                infoEl.style.display = 'block';
                            } else {
                                infoEl.style.display = 'none';
                            }
                        }
                    } else {
                        emptyEl.style.display = 'block';
                        emptyEl.innerHTML = `<p>${data.message || '暂无推荐'}</p>`;
                        const infoEl = document.getElementById('recommendation-info');
                        if (infoEl) infoEl.style.display = 'none';
                    }
                } else {
                    papersEl.innerHTML = `<div class="empty-state"><p>加载失败: ${data.error || '未知错误'}</p></div>`;
                    const infoEl = document.getElementById('recommendation-info');
                    if (infoEl) infoEl.style.display = 'none';
                }
            }
        } catch (error) {
            console.error('Error parsing SSE data:', error);
        }
    };
    
    eventSource.onerror = function(error) {
        console.error('SSE error:', error);
        eventSource.close();
        loadingEl.style.display = 'none';
        papersEl.innerHTML = `<div class="empty-state"><p>连接中断，请重试</p></div>`;
    };
    
    // 存储 eventSource 以便在需要时关闭
    window.currentEventSource = eventSource;
}

// 渲染推荐论文
function renderRecommendations(papers) {
    const papersEl = document.getElementById('recommendations-papers');
    
    papersEl.innerHTML = papers.map(paper => `
        <div class="paper-card">
            <h3 class="paper-title">${escapeHtml(paper.title)}</h3>
            <div class="paper-authors">${paper.authors.join(', ')}</div>
            <p class="paper-abstract">${escapeHtml(paper.abstract || '暂无摘要')}</p>
            <div class="paper-meta">
                <div>
                    <div class="recommendation-score">⭐ 推荐度: ${paper.score}</div>
                    <div class="paper-date" style="margin-top: 8px;">${formatDate(paper.date)}</div>
                </div>
            </div>
            <div class="paper-actions">
                <a href="${paper.pdf_url}" target="_blank" class="btn btn-primary">查看 PDF</a>
                ${paper.code_url ? `<a href="${paper.code_url}" target="_blank" class="btn btn-secondary">代码</a>` : ''}
                <a href="https://arxiv.org/abs/${paper.arxiv_id}" target="_blank" class="btn btn-secondary">ArXiv</a>
            </div>
        </div>
    `).join('');
}

// 更新进度统计信息
let statsCache = {}; // 缓存统计信息，避免重复显示

function updateProgressStats(message) {
    const progressStats = document.getElementById('progress-stats');
    const stats = [];
    
    // 提取 Zotero 论文数（参考文章数量）
    // 匹配格式：已加载 X 篇 Zotero 论文
    const zoteroMatch1 = message.match(/(\d+)\s*篇\s*Zotero\s*论文/);
    if (zoteroMatch1) {
        statsCache.zotero = zoteroMatch1[1];
    }
    
    // 匹配格式：已加载 X 篇选中的 Zotero 论文（从 Y 篇中筛选）
    const zoteroMatch2 = message.match(/已加载\s*(\d+)\s*篇\s*(?:选中的\s*)?Zotero\s*论文/);
    if (zoteroMatch2) {
        statsCache.zotero = zoteroMatch2[1];
    }
    
    // 提取 ArXiv RSS Feed 信息
    const rssMatch = message.match(/(\d+)\s*篇\s*(?:新论文|论文)/);
    if (rssMatch && message.includes('RSS Feed')) {
        statsCache.arxivRSS = rssMatch[1];
    }
    
    // 提取候选论文数
    const candidateMatch = message.match(/(\d+)\s*篇\s*候选论文/);
    if (candidateMatch) {
        statsCache.candidates = candidateMatch[1];
    }
    
    // 提取批次信息
    const batchMatch = message.match(/(\d+)\/(\d+)\s*批/);
    if (batchMatch) {
        statsCache.batch = `${batchMatch[1]}/${batchMatch[2]}`;
    }
    
    // 提取已获取数量
    const fetchedMatch = message.match(/(\d+)\/(\d+)\s*篇\s*论文详情/);
    if (fetchedMatch) {
        statsCache.fetched = `${fetchedMatch[1]}/${fetchedMatch[2]}`;
    }
    
    // 提取计算推荐分数的信息（包含参考文章数量）
    const calcMatch = message.match(/(\d+)\s*篇\s*候选论文\s*vs\s*(\d+)\s*篇\s*Zotero/);
    if (calcMatch) {
        statsCache.candidates = calcMatch[1];
        statsCache.zotero = calcMatch[2];
    }
    
    // 提取最高分
    const scoreMatch = message.match(/最高分[:\s]+([\d.]+)/);
    if (scoreMatch) {
        statsCache.maxScore = scoreMatch[1];
    }
    
    // 提取推荐数量
    const recommendMatch = message.match(/共推荐\s*(\d+)\s*篇/);
    if (recommendMatch) {
        statsCache.recommended = recommendMatch[1];
    }
    
    // 构建统计信息显示
    // 参考文章数量（Zotero）优先显示
    if (statsCache.zotero) {
        stats.push(`参考: ${statsCache.zotero} 篇`);
    }
    
    if (statsCache.arxivRSS) {
        stats.push(`ArXiv RSS: ${statsCache.arxivRSS} 篇`);
    }
    

    
    if (statsCache.candidates) {
        stats.push(`候选: ${statsCache.candidates} 篇`);
    }
    
    if (statsCache.batch) {
        stats.push(`批次: ${statsCache.batch}`);
    }
    
    if (statsCache.fetched) {
        stats.push(`已获取: ${statsCache.fetched}`);
    }
    
    if (statsCache.maxScore) {
        stats.push(`最高分: ${statsCache.maxScore}`);
    }
    
    if (statsCache.recommended) {
        stats.push(`推荐: ${statsCache.recommended} 篇`);
    }
    
    if (stats.length > 0) {
        progressStats.textContent = stats.join(' • ');
    }
}

// 工具函数
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatDate(dateString) {
    if (!dateString) return '未知日期';
    try {
        const date = new Date(dateString);
        return date.toLocaleDateString('zh-CN', {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        });
    } catch (e) {
        return dateString;
    }
}

