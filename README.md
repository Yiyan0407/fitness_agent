# 个人健身 Agent

基于 Streamlit + LangChain + 小米 MiMo 的个人健身训练助手。支持多账户、对话生成计划、今日打卡、历史进度。

## 环境要求

- Python 3.9+
- 小米 MiMo API Key（[开放平台](https://platform.xiaomimimo.com)）

## 快速开始

1. 用 conda 创建环境并安装依赖：

```bash
conda create -n fitness_agent python=3.11 -y
conda activate fitness_agent
pip install -r requirements.txt
```

2. 配置环境变量：

```bash
cp .env.example .env
# 编辑 .env：
# ADMIN_PASSWORD=...   # 新建账户时必填的管理员密码
# MIMO_API_KEY=...     # 教练对话 / 文字记账 / 饮食拍照（同一 Key）
# 可选：MIMO_VISION_MODEL=mimo-v2.5
```

在 [MiMo 开放平台](https://platform.xiaomimimo.com) 创建 API Key 即可（教练用 `mimo-v2.5-pro`，拍照用全模态 `mimo-v2.5`）。

3. 启动：

```bash
streamlit run app.py
# 默认 http://localhost:8502
```

首次启动不会预建账户，在登录页用管理员密码「新建账户」即可。

## 功能

- **登录 / 多账户**：用户名 + 个人密码；新建账户需 `ADMIN_PASSWORD`
- **首页**：今日训练概览、近 7 天完成情况
- **教练对话**：训练计划 / 改练 / 文字与拍照饮食记账
- **今日训练**：按计划打卡，记录重量/次数/RPE
- **训练计划**：手动编辑一周模板；动作库可搜、可看示范图
- **饮食管理**：查看饮食进度与明细
- **每日报告**：晚上生成当日训练+饮食复盘并入库
- **历史进度**：日历视图查看训练日，点击日期看当日详情
- **设置**：个人画像与数据库初始化

## 动作库与配图

- 本地库：`data/exercises.json`（约 900+ 动作，含中英文名、肌群、器械、要点、示范图 URL）
- 配图来自开源 [free-exercise-db](https://github.com/yuhonas/free-exercise-db)（jsDelivr CDN），**查看配图需要联网**
- 设置里的器械条件（如「家庭哑铃杠铃」）会映射到动作库标签，教练筛选可用
- 重新生成动作库：

```bash
python scripts/build_exercises.py
```

## 技术栈

- LLM：MiMo (`mimo-v2.5-pro`)，OpenAI 兼容接口
- Agent：LangChain `create_agent`（tool-calling 循环）
- 存储：账户元数据 `data/accounts.db`；每账户独立 SQLite `data/users/<用户名>/fitness.db`
