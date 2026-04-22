# 单票策略研究工作台

一个面向 A 股单票研究的 AI 辅助量化工作台，支持数据导入、规则回测、参数实验、实验留痕与 AI 报告闭环。

## 当前能力

- FastAPI 后端
  - CSV 上传、校验报告与数据预览
  - A 股交易规则约束
  - 网格策略回测
  - 仅分钟级可用的部分仓位做 T 回测
  - 买入持有基准与超额收益
  - 异步参数实验任务
  - Qwen / OpenAI 兼容式 AI 报告，带本地模板回退
  - SQLite 持久化数据集、回测、实验、报告与任务状态
- Next.js 前端
  - `/lab` 中文工作台
  - `/experiments` 实验历史页
  - 本地 CSV 导入
  - 内置 SVG 图表
  - JSON / Markdown / PNG / PDF 导出
  - “应用 AI 建议”回填参数并继续实验

## 目录结构

```text
backend/
  app/
    main.py
    datasets.py
    engine.py
    jobs.py
    reporting.py
    storage.py
  tests/
    test_engine.py

frontend/
  app/
  components/
  lib/
```

## 后端启动

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

默认地址是 `http://127.0.0.1:8000`。

## 前端启动

```powershell
cd frontend
cmd /c npm.cmd install
cmd /c npm.cmd run dev
```

默认地址是 `http://127.0.0.1:3000`，并请求 `http://127.0.0.1:8000`。

注意：项目根目录目前没有 `package.json`，所以不能在根目录直接执行 `npm run dev`。

正确方式是分开启动：

```powershell
cd backend
uvicorn app.main:app --reload

cd ..\frontend
cmd /c npm.cmd run dev
```

如果要切换前端请求地址：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
cmd /c npm.cmd run dev
``` 

## AI 报告配置

后端会按下面的优先级读取模型配置：

1. `CHAT_*`
2. `OPENAI_*`
3. 都没有时使用本地规则模板报告

### Qwen / DashScope 兼容模式

```powershell
$env:CHAT_PROVIDER="qwen"
$env:CHAT_API_KEY="sk-..."
$env:CHAT_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:CHAT_MODEL="qwen-plus"
uvicorn app.main:app --reload
```

接口调用走的是 OpenAI-compatible `POST /chat/completions`。

### OpenAI 兼容模式

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_MODEL="gpt-4.1-mini"
uvicorn app.main:app --reload
```

## 运行测试

```powershell
cd backend
python -m unittest tests.test_engine
python -m unittest tests.test_reporting
```

## 说明

- V1 定位是研究与验证工具，不是实盘交易系统。
- 部分仓位做 T 默认只对分钟级数据开放，避免在日线数据上做伪回测。
- 成交语义固定为 `signal_on_close_fill_next_open`。
