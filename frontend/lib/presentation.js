const STRATEGY_LABELS = {
  grid: "网格策略",
  partial_t0: "部分仓位做T",
};

const TIMEFRAME_LABELS = {
  "1d": "日线",
  "15m": "15分钟",
  "1m": "1分钟",
};

const ADJUSTMENT_LABELS = {
  forward_adjusted: "前复权",
  backward_adjusted: "后复权",
  "": "不复权",
};

const VALIDATION_STATUS_LABELS = {
  valid: "校验通过",
  invalid: "校验失败",
};

const MARKET_REGIME_LABELS = {
  range_bound: "震荡行情",
  trend_up: "上行趋势",
  trend_down: "下行趋势",
  high_volatility: "高波动行情",
  mixed: "混合行情",
};

const RISK_LEVEL_LABELS = {
  high: "高",
  medium: "中",
  low: "低",
};

const ACTION_LABELS = {
  increase: "提高",
  decrease: "降低",
  inspect: "参考",
};

const REFERENCE_MODE_LABELS = {
  prev_close: "昨收",
  moving_average: "均线",
  intraday_vwap: "日内均价",
};

const PARAM_LABELS = {
  base_price: "基准价",
  grid_step_pct: "网格间距",
  grid_levels: "网格层数",
  order_amount: "单格金额",
  max_position_pct: "最大仓位",
  take_profit_pct: "止盈阈值",
  stop_loss_pct: "止损阈值",
  base_position_pct: "底仓比例",
  active_position_pct: "机动仓比例",
  buy_trigger_pct: "买入阈值",
  sell_trigger_pct: "卖出阈值",
  mean_revert_target_pct: "回归止盈",
  reference_mode: "参考基线",
  initial_cash: "初始资金",
  fee_rate: "手续费率",
  slippage_rate: "滑点率",
  lot_size: "最小成交单位",
};

const KNOWN_DIRECT_ERRORS = new Map([
  ["Dataset not found.", "未找到数据集。"],
  ["Backtest not found.", "未找到回测结果。"],
  ["Experiment not found.", "未找到实验记录。"],
  ["Report not found.", "未找到分析报告。"],
  ["Job not found.", "未找到任务记录，可能已过期。"],
  ["Request failed", "请求失败，请稍后重试。"],
  ["Chart is not ready yet.", "图表尚未准备好，暂时无法导出。"],
]);


function hasChinese(text) {
  return /[\u4e00-\u9fa5]/.test(text);
}


function looksLikePercentKey(key) {
  return key.endsWith("_pct") || key.endsWith("_rate");
}


export function formatStrategyLabel(value) {
  return STRATEGY_LABELS[value] || value || "--";
}


export function formatTimeframeLabel(value) {
  return TIMEFRAME_LABELS[value] || value || "--";
}


export function formatAdjustmentLabel(value) {
  return ADJUSTMENT_LABELS[value ?? ""] || value || "未设置";
}


export function formatValidationLabel(value) {
  return VALIDATION_STATUS_LABELS[value] || value || "--";
}


export function formatMarketRegimeLabel(value) {
  return MARKET_REGIME_LABELS[value] || value || "--";
}


export function formatRiskLevelLabel(value) {
  return RISK_LEVEL_LABELS[value] || value || "--";
}


export function formatActionLabel(value) {
  return ACTION_LABELS[value] || value || "--";
}


export function formatReferenceModeLabel(value) {
  return REFERENCE_MODE_LABELS[value] || value || "--";
}


export function formatParamLabel(key) {
  return PARAM_LABELS[key] || key;
}


export function formatNumber(value, digits = 2) {
  return typeof value === "number" ? value.toLocaleString("zh-CN", { maximumFractionDigits: digits }) : "--";
}


export function formatPercent(value, digits = 2) {
  return typeof value === "number" ? `${(value * 100).toFixed(digits)}%` : "--";
}


export function formatDateLabel(value, timeframe = "1d") {
  if (!value) {
    return "--";
  }
  if (timeframe === "1d") {
    return value.slice(5, 10);
  }
  return value.slice(5, 16).replace("T", " ");
}


export function formatReasonLabel(reason) {
  if (!reason) {
    return "--";
  }
  if (reason.startsWith("grid_buy_level_")) {
    return `网格买入 ${reason.replace("grid_buy_level_", "L")}`;
  }
  if (reason.startsWith("grid_sell_level_")) {
    return `网格卖出 ${reason.replace("grid_sell_level_", "L")}`;
  }
  const direct = {
    initial_base_position: "初始底仓建仓",
    active_deviation_buy: "机动仓偏离买入",
    active_deviation_sell: "机动仓偏离卖出",
    active_mean_revert_take_profit: "机动仓回归止盈",
    active_stop_loss: "机动仓止损",
    risk_take_profit: "组合止盈",
    risk_stop_loss: "组合止损",
  };
  return direct[reason] || reason;
}


export function formatParamValue(key, value) {
  if (Array.isArray(value)) {
    return value.map((item) => formatParamValue(key, item)).join(" / ");
  }
  if (typeof value === "number") {
    if (looksLikePercentKey(key)) {
      return formatPercent(value, value < 0.1 ? 2 : 1);
    }
    if (Number.isInteger(value)) {
      return formatNumber(value, 0);
    }
    return formatNumber(value, 4);
  }
  if (key === "reference_mode") {
    return formatReferenceModeLabel(value);
  }
  return value ?? "--";
}


export function formatParamEntries(params) {
  return Object.entries(params || {})
    .map(([key, value]) => `${formatParamLabel(key)}：${formatParamValue(key, value)}`)
    .join(" / ");
}


export function translateError(rawMessage) {
  const message = `${rawMessage || ""}`.trim();
  if (!message) {
    return "请求失败，请稍后重试。";
  }
  if (hasChinese(message)) {
    return message;
  }
  if (KNOWN_DIRECT_ERRORS.has(message)) {
    return KNOWN_DIRECT_ERRORS.get(message);
  }
  if (message.includes("Failed to fetch") || message.includes("NetworkError")) {
    return "无法连接后端接口，请确认 API 服务已启动。";
  }
  if (message.includes("Daily datasets must declare an adjustment mode")) {
    return "日线数据必须声明复权方式。";
  }
  if (message.includes("Missing required columns:")) {
    return `CSV 缺少必需字段：${message.replace("Missing required columns:", "").trim()}`;
  }
  if (message.includes("Timestamps must be strictly ascending")) {
    return "CSV 时间列必须按升序排列。";
  }
  if (message.includes("Duplicate timestamps detected")) {
    return "CSV 中存在重复时间戳，请清理后重试。";
  }
  if (message.includes("invalid OHLCV relationships")) {
    return "CSV 中存在异常的 OHLCV 数据，请检查开高低收与成交量。";
  }
  if (message.includes("does not support timeframe")) {
    return "当前策略不支持所选数据周期。";
  }
  if (message.includes("Choose a CSV file first")) {
    return "请先选择 CSV 文件。";
  }
  if (message.includes("Chart is not ready")) {
    return "图表尚未准备好，暂时无法导出。";
  }
  return `操作失败：${message}`;
}
