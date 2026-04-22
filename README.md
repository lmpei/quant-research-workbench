# AI 单票策略研究工作台

一个面向 **A 股单票策略研究** 的 AI 辅助工作台，围绕 **网格交易** 与 **部分仓位做T** 两类规则策略，把数据导入、回测验证、参数实验、实验留痕、AI 分析和导出结果串成一个完整研究闭环。

## 项目定义

这个项目不是实盘交易系统，也不是聊天式量化助手。  
它的定位是：

> 一个 AI 参与研究闭环的单票策略研究系统，围绕网格交易和部分仓位做T两类规则策略，完成了数据、回测、实验、留痕、分析和导出的全流程工程化。

## 核心亮点

- A 股研究约束明确：`100 股一手`、`卖出印花税`、`T+1 可卖`、`手续费 / 滑点`
- 成交语义固定：`signal_on_close_fill_next_open`
- 双案例预置演示：
  - `比亚迪日线 + 网格策略`
  - `比亚迪15分钟 + 部分仓位做T`
- AI 不是聊天框，而是研究闭环助手：
  - 生成中文分析报告
  - 识别风险与失效场景
  - 推荐下一轮参数实验
  - 一键回填 AI 建议
- 完整导出链路：
  - 图表 PNG
  - 研究快照 JSON
  - 报告 Markdown / PDF

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
    test_reporting.py

frontend/
  app/
  components/
  lib/

docs/
  项目说明.md
  演示脚本.md
```

## 快速启动

在项目根目录执行：

```powershell
cmd /c npm.cmd install
npm run dev
```

这会同时启动：

- 前端：`http://127.0.0.1:3000`
- 后端：`http://127.0.0.1:8000`

## 分开启动

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 前端

```powershell
cd frontend
cmd /c npm.cmd install
cmd /c npm.cmd run dev
```

如果要自定义前端请求地址：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8000"
cmd /c npm.cmd run dev
```

## AI 报告配置

后端按以下优先级读取模型配置：

1. `CHAT_*`
2. `OPENAI_*`
3. 两者都没有时回退到本地规则模板报告

### Qwen / DashScope 兼容模式

```powershell
$env:CHAT_PROVIDER="qwen"
$env:CHAT_API_KEY="sk-..."
$env:CHAT_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:CHAT_MODEL="qwen-plus"
uvicorn app.main:app --reload
```

接口走 OpenAI-compatible `POST /chat/completions`。

### OpenAI 兼容模式

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_MODEL="gpt-4.1-mini"
uvicorn app.main:app --reload
```

## 运行测试

在项目根目录执行：

```powershell
npm run test:backend
npm run build
```

或直接执行：

```powershell
npm test
```

## 文档

- [项目说明](docs/项目说明.md)
- [演示脚本](docs/演示脚本.md)

## 说明

- 产品边界锁定为研究工具，不提供模拟下单或实盘执行入口。
- `partial_t0` 只允许分钟级数据，避免在日线上做伪做T回测。
- 默认双案例用于面试展示，也可继续导入自定义 CSV 做扩展研究。
