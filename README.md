# 个人健身 Agent

基于 Streamlit + LangChain + 小米 MiMo 的个人健身训练助手。支持对话生成计划、今日打卡、历史进度。

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

2. 配置 API Key：

```bash
cp .env.example .env
# 编辑 .env：
# MIMO_API_KEY=...          # 教练对话 / 文字记账
# DOUBAO_API_KEY=...        # 饮食拍照识别（火山方舟）
# DOUBAO_MODEL=ep-xxxx 或 doubao-seed-2-0-lite-260428
```

在 [MiMo 开放平台](https://platform.xiaomimimo.com) 创建 MiMo Key；在 [火山方舟](https://console.volcengine.com/ark) 创建豆包视觉模型 Key。

3. 启动：

```bash
streamlit run app.py
# 默认 http://localhost:8502
```

## 功能

- **首页**：今日训练概览、近 7 天完成情况
- **教练对话**：训练计划 / 改练 / 文字与拍照饮食记账
- **今日训练**：按计划打卡，记录重量/次数/RPE
- **训练计划**：手动编辑一周模板（增删动作、改组数）
- **饮食管理**：查看饮食进度与明细
- **每日报告**：晚上生成当日训练+饮食复盘并入库
- **历史进度**：日历视图查看训练日，点击日期看当日详情
- **设置**：个人画像与数据库初始化

## 技术栈

- LLM：MiMo (`mimo-v2.5-pro`)，OpenAI 兼容接口
- Agent：LangChain `create_agent`（tool-calling 循环）
- 存储：本地 SQLite（`data/fitness.db`）
