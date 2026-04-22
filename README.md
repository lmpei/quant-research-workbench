# AI 单票策略研究工作台

一个面向 A 股单票策略研究的 AI 辅助工作台，围绕网格交易与部分仓位做 T 两类规则策略，把数据导入、回测验证、参数实验、实验留痕、AI 分析和导出结果串成完整闭环。

## 当前开发端口

- 前端工作台：`http://127.0.0.1:3101`
- 后端 API：`http://127.0.0.1:8100`
- 健康检查：`http://127.0.0.1:8100/api/health`
- 系统状态：`http://127.0.0.1:8100/api/system/status`
- 接口文档：`http://127.0.0.1:8100/docs`

这样做是为了避免你同时打开多个项目时，和常见的 `3000 / 8000` 默认端口互相冲突。

## 一键启动

在项目根目录执行：

```powershell
cmd /c npm.cmd install
npm run dev
```

这会同时启动：

- 前端：`http://127.0.0.1:3101`
- 后端：`http://127.0.0.1:8100`

## 分开启动

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

### 前端

```powershell
cd frontend
cmd /c npm.cmd install
cmd /c npm.cmd run dev
```

如果你要改前端请求地址：

```powershell
$env:NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:8100"
cmd /c npm.cmd run dev
```

## AI 报告配置

后端按以下优先级读取模型配置：

1. `CHAT_*`
2. `OPENAI_*`
3. 都没有时退回本地规则模板报告

### Qwen / DashScope

```powershell
$env:CHAT_PROVIDER="qwen"
$env:CHAT_API_KEY="sk-..."
$env:CHAT_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:CHAT_MODEL="qwen-plus"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

### OpenAI 兼容模式

```powershell
$env:OPENAI_API_KEY="sk-..."
$env:OPENAI_MODEL="gpt-4.1-mini"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8100
```

## 运行测试

在项目根目录执行：

```powershell
npm run test:backend
npm run build
```

或者直接：

```powershell
npm test
```

## 文档

- [项目说明](docs/项目说明.md)
- [演示脚本](docs/演示脚本.md)

## 说明

- 产品边界锁定为研究工具，不提供模拟下单或实盘执行入口。
- `partial_t0` 只允许分钟级数据，避免在日线上做伪做 T 回测。
- 后端根路径 `/` 现在会返回接口入口说明，不再是 `Not Found`。
