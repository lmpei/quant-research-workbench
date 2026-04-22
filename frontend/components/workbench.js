"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { api, downloadJson, downloadText, exportSvgToPng } from "../lib/api";
import {
  formatActionLabel,
  formatAdjustmentLabel,
  formatDateLabel,
  formatMarketRegimeLabel,
  formatNumber,
  formatParamEntries,
  formatParamLabel,
  formatPercent,
  formatReasonLabel,
  formatRiskLevelLabel,
  formatStrategyLabel,
  formatTimeframeLabel,
  formatValidationLabel,
  translateError,
} from "../lib/presentation";


const defaultConfig = {
  initial_cash: 100000,
  fee_rate: 0.0003,
  slippage_rate: 0.0005,
  lot_size: 100,
  max_position_pct: 0.8,
  risk_control_enabled: true,
  execution_mode: "signal_on_close_fill_next_open",
  benchmark_mode: "buy_and_hold",
};

const defaultGridParams = {
  base_price: 210,
  grid_step_pct: 0.02,
  grid_levels: 6,
  order_amount: 25000,
  max_position_pct: 0.8,
  take_profit_pct: 0.08,
  stop_loss_pct: 0.12,
};

const defaultT0Params = {
  base_position_pct: 0.7,
  active_position_pct: 0.3,
  buy_trigger_pct: 0.008,
  sell_trigger_pct: 0.008,
  mean_revert_target_pct: 0.004,
  stop_loss_pct: 0.015,
  reference_mode: "prev_close",
};

const defaultSweepInputs = {
  grid: {
    grid_step_pct: "0.015,0.02,0.025",
    grid_levels: "4,6,8",
    order_amount: "20000,25000,30000",
  },
  partial_t0: {
    buy_trigger_pct: "0.006,0.008,0.01",
    mean_revert_target_pct: "0.003,0.004,0.006",
    active_position_pct: "0.2,0.3,0.4",
  },
};

const commonConfigFields = [
  { key: "initial_cash", label: "初始资金", step: 1000 },
  { key: "fee_rate", label: "手续费率", step: 0.0001 },
  { key: "slippage_rate", label: "滑点率", step: 0.0001 },
  { key: "lot_size", label: "最小成交单位", step: 100 },
  { key: "max_position_pct", label: "最大仓位", step: 0.01 },
];

const gridFieldDefs = [
  { key: "base_price", label: "基准价", step: 0.01 },
  { key: "grid_step_pct", label: "网格间距", step: 0.001 },
  { key: "grid_levels", label: "网格层数", step: 1 },
  { key: "order_amount", label: "单格金额", step: 1000 },
  { key: "take_profit_pct", label: "止盈阈值", step: 0.01 },
  { key: "stop_loss_pct", label: "止损阈值", step: 0.01 },
];

const t0FieldDefs = [
  { key: "base_position_pct", label: "底仓比例", step: 0.01 },
  { key: "active_position_pct", label: "机动仓比例", step: 0.01 },
  { key: "buy_trigger_pct", label: "买入阈值", step: 0.001 },
  { key: "sell_trigger_pct", label: "卖出阈值", step: 0.001 },
  { key: "mean_revert_target_pct", label: "回归止盈", step: 0.001 },
  { key: "stop_loss_pct", label: "止损阈值", step: 0.001 },
];

const referenceModeOptions = [
  { value: "prev_close", label: "昨收" },
  { value: "moving_average", label: "均线" },
  { value: "intraday_vwap", label: "日内均价" },
];


function parseGridField(rawValue) {
  return rawValue
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => Number(item))
    .filter((item) => !Number.isNaN(item));
}


function numericPatch(current, changes) {
  const next = { ...current };
  changes.forEach((change) => {
    if (typeof next[change.parameter] !== "number") {
      return;
    }
    if (change.action === "increase") {
      next[change.parameter] = Number((next[change.parameter] * 1.15).toFixed(6));
    }
    if (change.action === "decrease") {
      next[change.parameter] = Number((next[change.parameter] * 0.85).toFixed(6));
    }
  });
  return next;
}


function buildSeriesPath(values, width, height, padding) {
  if (!values.length) {
    return "";
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const safeMax = max === min ? max + 1 : max;
  const stepX = values.length > 1 ? (width - padding * 2) / (values.length - 1) : 0;
  return values
    .map((value, index) => {
      const x = padding + index * stepX;
      const y = height - padding - ((value - min) / (safeMax - min)) * (height - padding * 2);
      return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
}


function ChartPanel({ id, title, labels, series, markers = [], timeframe = "1d" }) {
  const width = 920;
  const height = 228;
  const padding = 24;
  const mergedValues = series.flatMap((item) => item.values).filter((value) => typeof value === "number");
  const min = mergedValues.length ? Math.min(...mergedValues) : 0;
  const max = mergedValues.length ? Math.max(...mergedValues) : 1;
  const safeMax = max === min ? max + 1 : max;
  const stepX = labels.length > 1 ? (width - padding * 2) / (labels.length - 1) : 0;

  return (
    <div className="chart-card">
      <div className="chart-head">
        <strong>{title}</strong>
        <span>
          {labels.length} 个点位 · 区间 {formatNumber(min)} - {formatNumber(max)}
        </span>
      </div>
      <svg id={id} className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <rect x="0" y="0" width={width} height={height} fill="url(#chart-bg)" rx="20" />
        <defs>
          <linearGradient id="chart-bg" x1="0%" x2="100%" y1="0%" y2="100%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="100%" stopColor="#f4efe5" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
          const y = padding + tick * (height - padding * 2);
          return <line key={tick} x1={padding} x2={width - padding} y1={y} y2={y} className="chart-grid" />;
        })}
        {series.map((item) => (
          <path
            key={item.name}
            d={buildSeriesPath(item.values, width, height, padding)}
            fill="none"
            stroke={item.color}
            strokeWidth="3"
            strokeLinecap="round"
          />
        ))}
        {markers.map((marker) => {
          const x = padding + marker.index * stepX;
          const y = height - padding - ((marker.value - min) / (safeMax - min || 1)) * (height - padding * 2);
          return (
            <g key={`${marker.index}-${marker.value}-${marker.side}`}>
              <circle cx={x} cy={y} r="5" fill={marker.side === "buy" ? "#1f7a5e" : "#c06538"} stroke="#fff" strokeWidth="2" />
            </g>
          );
        })}
        {labels.length > 1
          ? [0, Math.floor(labels.length / 2), labels.length - 1].map((index) => {
              const x = padding + index * stepX;
              return (
                <text key={index} x={x} y={height - 6} className="chart-axis-label" textAnchor={index === 0 ? "start" : index === labels.length - 1 ? "end" : "middle"}>
                  {formatDateLabel(labels[index], timeframe)}
                </text>
              );
            })
          : null}
      </svg>
      <div className="chart-legend">
        {series.map((item) => (
          <span key={item.name}>
            <i style={{ background: item.color }} />
            {item.name}
          </span>
        ))}
      </div>
    </div>
  );
}


function Field({ label, value, onChange, type = "number", step = "any", disabled = false }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        disabled={disabled}
        step={step}
        type={type}
        value={value}
        onChange={(event) => onChange(type === "number" ? Number(event.target.value) : event.target.value)}
      />
    </label>
  );
}


function SelectField({ label, value, onChange, options, disabled = false }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        {options.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </select>
    </label>
  );
}


function MetricCard({ label, value, tone = "default" }) {
  return (
    <div className={`metric-card metric-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}


function TableEmpty({ message }) {
  return <div className="empty-card">{message}</div>;
}


function renderFieldGroup(formState, setFormState, definitions) {
  return (
    <div className="form-grid">
      {definitions.map((item) => (
        <Field
          key={item.key}
          label={item.label}
          step={item.step}
          value={formState[item.key]}
          onChange={(value) => setFormState((current) => ({ ...current, [item.key]: value }))}
        />
      ))}
    </div>
  );
}


export default function Workbench() {
  const [datasets, setDatasets] = useState([]);
  const [datasetId, setDatasetId] = useState("");
  const [datasetDetail, setDatasetDetail] = useState(null);
  const [strategyType, setStrategyType] = useState("grid");
  const [config, setConfig] = useState(defaultConfig);
  const [gridParams, setGridParams] = useState(defaultGridParams);
  const [t0Params, setT0Params] = useState(defaultT0Params);
  const [sweepInputs, setSweepInputs] = useState(defaultSweepInputs);
  const [backtest, setBacktest] = useState(null);
  const [activeExperiment, setActiveExperiment] = useState(null);
  const [experiments, setExperiments] = useState([]);
  const [report, setReport] = useState(null);
  const [activeTab, setActiveTab] = useState("price");
  const [leftTab, setLeftTab] = useState("research");
  const [status, setStatus] = useState("正在加载研究工作台...");
  const [busy, setBusy] = useState({ upload: false, run: false, sweep: false, report: false });
  const [upload, setUpload] = useState({
    name: "",
    symbol: "",
    timeframe: "1d",
    adjustment: "forward_adjusted",
    file: null,
  });
  const [jobs, setJobs] = useState({ sweep: null, report: null });

  const currentParams = strategyType === "grid" ? gridParams : t0Params;
  const strategyDisabled = strategyType === "partial_t0" && datasetDetail?.timeframe === "1d";
  const selectedChartId = activeTab === "price" ? "price-chart-svg" : "equity-chart-svg";
  const summary = backtest?.summary;

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (!datasetId) {
      return;
    }
    let active = true;
    api(`/api/datasets/${datasetId}`)
      .then((payload) => {
        if (!active) {
          return;
        }
        setDatasetDetail(payload);
        setStatus("");
      })
      .catch((error) => {
        if (!active) {
          return;
        }
        setStatus(translateError(error.message));
      });
    return () => {
      active = false;
    };
  }, [datasetId]);

  useEffect(() => {
    if (!jobs.sweep && !jobs.report) {
      return undefined;
    }

    const timer = setInterval(async () => {
      try {
        if (jobs.sweep) {
          const job = await api(`/api/jobs/${jobs.sweep}`);
          if (job.status === "completed") {
            const detail = await api(`/api/experiments/${job.result_ref.experiment_id}`);
            setActiveExperiment(detail);
            setJobs((current) => ({ ...current, sweep: null }));
            setBusy((current) => ({ ...current, sweep: false }));
            setStatus("参数实验已完成，可点击结果回填参数。");
            loadExperiments();
          }
          if (job.status === "failed") {
            setJobs((current) => ({ ...current, sweep: null }));
            setBusy((current) => ({ ...current, sweep: false }));
            setStatus(translateError(job.error_text || "参数实验失败。"));
          }
        }
        if (jobs.report) {
          const job = await api(`/api/jobs/${jobs.report}`);
          if (job.status === "completed") {
            const detail = await api(`/api/reports/${job.result_ref.report_id}`);
            setReport(detail);
            setJobs((current) => ({ ...current, report: null }));
            setBusy((current) => ({ ...current, report: false }));
            setStatus("AI 分析报告已生成。");
          }
          if (job.status === "failed") {
            setJobs((current) => ({ ...current, report: null }));
            setBusy((current) => ({ ...current, report: false }));
            setStatus(translateError(job.error_text || "报告生成失败。"));
          }
        }
      } catch (error) {
        setStatus(translateError(error.message));
      }
    }, 1400);

    return () => clearInterval(timer);
  }, [jobs]);

  async function loadAll() {
    const [datasetResult, experimentResult] = await Promise.allSettled([loadDatasets(), loadExperiments()]);
    const rejection = [datasetResult, experimentResult].find((item) => item.status === "rejected");
    if (rejection) {
      setStatus(translateError(rejection.reason?.message));
    }
  }

  async function loadDatasets() {
    const items = await api("/api/datasets");
    setDatasets(items);
    if (!datasetId && items[0]) {
      const preferred = items.find((item) => item.dataset_id === "ds_demo_byd_1d") || items[0];
      setDatasetId(preferred.dataset_id);
    }
    if (!items.length) {
      setStatus("暂无数据集，请先导入 CSV。");
    }
  }

  async function loadExperiments() {
    const items = await api("/api/experiments");
    setExperiments(items);
  }

  async function runBacktest() {
    if (!datasetId) {
      setStatus("请先选择数据集。");
      return;
    }
    if (strategyDisabled) {
      setStatus("部分仓位做T策略仅支持分钟级数据。");
      return;
    }
    setBusy((current) => ({ ...current, run: true }));
    setStatus("正在运行单次回测...");
    try {
      const payload = await api("/api/backtests/run", {
        method: "POST",
        body: JSON.stringify({
          dataset_id: datasetId,
          strategy_type: strategyType,
          backtest_config: config,
          strategy_params: currentParams,
        }),
      });
      setBacktest(payload);
      setReport(null);
      setStatus("回测完成，可继续查看图表或生成分析报告。");
    } catch (error) {
      setStatus(translateError(error.message));
    } finally {
      setBusy((current) => ({ ...current, run: false }));
    }
  }

  async function runSweep() {
    if (!datasetId) {
      setStatus("请先选择数据集。");
      return;
    }
    if (strategyDisabled) {
      setStatus("部分仓位做T策略仅支持分钟级数据。");
      return;
    }
    const source = sweepInputs[strategyType];
    const paramGrid = Object.fromEntries(Object.entries(source).map(([key, value]) => [key, parseGridField(value)]));
    setBusy((current) => ({ ...current, sweep: true }));
    setStatus("正在提交参数实验...");
    try {
      const job = await api("/api/backtests/sweep", {
        method: "POST",
        body: JSON.stringify({
          dataset_id: datasetId,
          strategy_type: strategyType,
          backtest_config: config,
          base_strategy_params: currentParams,
          param_grid: paramGrid,
          ranking_metric: "risk_adjusted_return",
        }),
      });
      setJobs((current) => ({ ...current, sweep: job.job_id }));
    } catch (error) {
      setBusy((current) => ({ ...current, sweep: false }));
      setStatus(translateError(error.message));
    }
  }

  async function generateReport() {
    if (!backtest) {
      setStatus("请先运行回测，再生成 AI 分析报告。");
      return;
    }
    setBusy((current) => ({ ...current, report: true }));
    setStatus("正在生成 AI 分析报告...");
    try {
      const job = await api("/api/reports/generate", {
        method: "POST",
        body: JSON.stringify({
          dataset_id: datasetId,
          backtest_id: backtest.backtest_id,
          experiment_id: activeExperiment?.experiment_id || null,
          report_type: "strategy_analysis",
        }),
      });
      setJobs((current) => ({ ...current, report: job.job_id }));
    } catch (error) {
      setBusy((current) => ({ ...current, report: false }));
      setStatus(translateError(error.message));
    }
  }

  async function uploadDataset(event) {
    event.preventDefault();
    if (!upload.file) {
      setStatus("请先选择 CSV 文件。");
      return;
    }
    setBusy((current) => ({ ...current, upload: true }));
    setStatus("正在上传并校验数据集...");
    try {
      const formData = new FormData();
      formData.append("name", upload.name || upload.file.name.replace(".csv", ""));
      formData.append("symbol", upload.symbol || "CUSTOM");
      formData.append("timeframe", upload.timeframe);
      if (upload.adjustment) {
        formData.append("adjustment", upload.adjustment);
      }
      formData.append("file", upload.file);
      const payload = await api("/api/datasets/upload", { method: "POST", body: formData });
      await loadDatasets();
      setDatasetId(payload.dataset_id);
      setLeftTab("research");
      setStatus(`数据集“${payload.name}”上传成功。`);
    } catch (error) {
      setStatus(translateError(error.message));
    } finally {
      setBusy((current) => ({ ...current, upload: false }));
    }
  }

  function applyRun(run) {
    if (strategyType === "grid") {
      setGridParams((current) => ({ ...current, ...run.params }));
    } else {
      setT0Params((current) => ({ ...current, ...run.params }));
    }
    setStatus("已将该组参数回填到当前表单。");
  }

  function applyAiSuggestions() {
    if (!report) {
      setStatus("请先生成 AI 分析报告。");
      return;
    }
    const changes = report.structured_recommendations?.recommended_param_changes || [];
    const next = report.next_experiments?.[0];
    const reference = changes.find((item) => item.parameter === "best_run_reference" && item.value);
    if (reference?.value) {
      if (strategyType === "grid") {
        setGridParams((current) => ({ ...current, ...reference.value }));
      } else {
        setT0Params((current) => ({ ...current, ...reference.value }));
      }
    } else if (strategyType === "grid") {
      setGridParams((current) => numericPatch(current, changes));
    } else {
      setT0Params((current) => numericPatch(current, changes));
    }
    if (next?.parameters) {
      setSweepInputs((current) => ({
        ...current,
        [strategyType]: {
          ...current[strategyType],
          ...Object.fromEntries(Object.entries(next.parameters).map(([key, value]) => [key, value.join(",")])),
        },
      }));
    }
    setLeftTab("manage");
    setStatus("已将 AI 建议回填到参数和实验面板。");
  }

  function exportSnapshot() {
    downloadJson("quant-research-snapshot.json", {
      dataset: datasetDetail,
      backtest,
      experiment: activeExperiment,
      report,
    });
    setStatus("当前研究快照已导出为 JSON。");
  }

  function exportReport() {
    if (!report) {
      setStatus("请先生成分析报告。");
      return;
    }
    downloadText("strategy-report.md", report.raw_markdown, "text/markdown;charset=utf-8");
    setStatus("分析报告已导出为 Markdown。");
  }

  async function exportChart() {
    try {
      await exportSvgToPng(selectedChartId, `${activeTab === "price" ? "price" : "equity"}-chart.png`);
      setStatus("图表已导出为 PNG。");
    } catch (error) {
      setStatus(translateError(error.message));
    }
  }

  const priceLabels = useMemo(
    () => (datasetDetail?.candles || []).map((item) => item.datetime),
    [datasetDetail],
  );

  const priceValues = useMemo(
    () => (datasetDetail?.candles || []).map((item) => item.close),
    [datasetDetail],
  );

  const tradeMarkers = useMemo(() => {
    if (!datasetDetail?.candles || !backtest?.trades) {
      return [];
    }
    const indexByDatetime = Object.fromEntries(datasetDetail.candles.map((item, index) => [item.datetime, index]));
    return backtest.trades
      .map((trade) => ({
        index: indexByDatetime[trade.datetime],
        value: trade.price,
        side: trade.side,
      }))
      .filter((item) => typeof item.index === "number");
  }, [datasetDetail, backtest]);

  const equityLabels = useMemo(
    () => (backtest?.timeseries?.equity_curve || []).map((item) => item.datetime),
    [backtest],
  );

  const strategyOptions = [
    { value: "grid", label: formatStrategyLabel("grid") },
    { value: "partial_t0", label: formatStrategyLabel("partial_t0") },
  ];

  const uploadTimeframeOptions = [
    { value: "1d", label: "日线" },
    { value: "15m", label: "15分钟" },
    { value: "1m", label: "1分钟" },
  ];

  const adjustmentOptions = [
    { value: "forward_adjusted", label: "前复权" },
    { value: "backward_adjusted", label: "后复权" },
    { value: "", label: "不复权" },
  ];

  return (
    <main className="lab-shell">
      <header className="app-topbar">
        <div className="brand-block">
          <p className="eyebrow">AI辅助单票量化研究</p>
          <div className="brand-row">
            <h1>策略研究工作台</h1>
            <span className="subtle-tag">A股单票 · 研究用途 · 首屏优化</span>
          </div>
        </div>

        <div className="topbar-right">
          <div className="topbar-controls">
            <SelectField
              label="当前数据集"
              value={datasetId}
              onChange={setDatasetId}
              options={datasets.map((item) => ({
                value: item.dataset_id,
                label: `${item.name} · ${formatTimeframeLabel(item.timeframe)}`,
              }))}
            />
            <SelectField label="策略类型" value={strategyType} onChange={setStrategyType} options={strategyOptions} />
          </div>
          <div className="toolbar-actions">
            <button onClick={runBacktest} disabled={busy.run}>
              {busy.run ? "回测中..." : "运行回测"}
            </button>
            <button onClick={runSweep} disabled={busy.sweep}>
              {busy.sweep ? "实验中..." : "参数实验"}
            </button>
            <button onClick={generateReport} disabled={busy.report}>
              {busy.report ? "生成中..." : "生成 AI 报告"}
            </button>
            <button className="ghost-button" onClick={exportSnapshot}>
              导出 JSON
            </button>
            <button className="ghost-button" onClick={exportChart}>
              导出图表
            </button>
            <button className="ghost-button" onClick={exportReport}>
              导出报告
            </button>
            <button className="ghost-button" onClick={() => window.print()}>
              导出 PDF
            </button>
            <Link className="ghost-button" href="/experiments">
              实验历史
            </Link>
          </div>
        </div>
      </header>

      {status ? <div className="status-banner">{status}</div> : null}
      {strategyDisabled ? <div className="warning-banner">部分仓位做T策略仅支持分钟级数据，当前日线数据下不会执行该策略。</div> : null}

      <section className="workspace-grid">
        <aside className="workspace-panel">
          <div className="panel-topline">
            <strong>配置面板</strong>
            <span>{leftTab === "research" ? "研究配置" : "导入与实验"}</span>
          </div>
          <div className="segment-tabs">
            <button className={leftTab === "research" ? "segment-button active" : "segment-button"} onClick={() => setLeftTab("research")}>
              研究配置
            </button>
            <button className={leftTab === "manage" ? "segment-button active" : "segment-button"} onClick={() => setLeftTab("manage")}>
              导入与实验
            </button>
          </div>
          <div className="panel-scroll">
            {leftTab === "research" ? (
              <>
                <section className="panel-section">
                  <div className="section-head">
                    <h2>当前数据</h2>
                    <span>{datasetDetail?.rows ? `${formatNumber(datasetDetail.rows, 0)} 条` : "--"}</span>
                  </div>
                  <div className="dataset-chip-row">
                    <span className="chip">{datasetDetail?.symbol || "--"}</span>
                    <span className="chip">{formatTimeframeLabel(datasetDetail?.timeframe)}</span>
                    <span className="chip">{formatAdjustmentLabel(datasetDetail?.adjustment)}</span>
                  </div>
                  <div className="info-stack">
                    <p>
                      <strong>区间：</strong>
                      {datasetDetail?.start_at ? `${formatDateLabel(datasetDetail.start_at, datasetDetail.timeframe)} 至 ${formatDateLabel(datasetDetail.end_at, datasetDetail.timeframe)}` : "--"}
                    </p>
                    <p>
                      <strong>校验：</strong>
                      {formatValidationLabel(datasetDetail?.validation_status)}
                    </p>
                    <p>
                      <strong>预期间隔：</strong>
                      {datasetDetail?.validation_report?.expected_interval || "--"}
                    </p>
                    {datasetDetail?.validation_report?.warnings?.length ? (
                      <p>
                        <strong>提示：</strong>
                        {datasetDetail.validation_report.warnings.join("；")}
                      </p>
                    ) : null}
                  </div>
                </section>

                <section className="panel-section">
                  <div className="section-head">
                    <h2>通用回测参数</h2>
                    <span>统一成交语义</span>
                  </div>
                  {renderFieldGroup(config, setConfig, commonConfigFields)}
                  <div className="note-box">
                    信号在当前 bar 收盘判定，按下一根 bar 开盘成交，并计入手续费与滑点。
                  </div>
                </section>

                <section className="panel-section">
                  <div className="section-head">
                    <h2>{formatStrategyLabel(strategyType)}参数</h2>
                    <span>{strategyDisabled ? "当前不可执行" : "可直接运行"}</span>
                  </div>
                  {strategyType === "grid" ? (
                    renderFieldGroup(gridParams, setGridParams, gridFieldDefs)
                  ) : (
                    <>
                      {renderFieldGroup(t0Params, setT0Params, t0FieldDefs)}
                      <SelectField
                        label="参考基线"
                        value={t0Params.reference_mode}
                        onChange={(value) => setT0Params((current) => ({ ...current, reference_mode: value }))}
                        options={referenceModeOptions}
                      />
                    </>
                  )}
                </section>
              </>
            ) : (
              <>
                <form className="panel-section" onSubmit={uploadDataset}>
                  <div className="section-head">
                    <h2>CSV 导入</h2>
                    <span>本地优先</span>
                  </div>
                  <Field
                    label="数据集名称"
                    type="text"
                    value={upload.name}
                    onChange={(value) => setUpload((current) => ({ ...current, name: value }))}
                  />
                  <Field
                    label="股票代码"
                    type="text"
                    value={upload.symbol}
                    onChange={(value) => setUpload((current) => ({ ...current, symbol: value }))}
                  />
                  <SelectField
                    label="数据周期"
                    value={upload.timeframe}
                    onChange={(value) => setUpload((current) => ({ ...current, timeframe: value }))}
                    options={uploadTimeframeOptions}
                  />
                  <SelectField
                    label="复权方式"
                    value={upload.adjustment}
                    onChange={(value) => setUpload((current) => ({ ...current, adjustment: value }))}
                    options={adjustmentOptions}
                  />
                  <label className="field">
                    <span>CSV 文件</span>
                    <input type="file" accept=".csv" onChange={(event) => setUpload((current) => ({ ...current, file: event.target.files?.[0] || null }))} />
                  </label>
                  <button type="submit" disabled={busy.upload}>
                    {busy.upload ? "上传中..." : "上传数据集"}
                  </button>
                </form>

                <section className="panel-section">
                  <div className="section-head">
                    <h2>参数实验</h2>
                    <span>以当前参数为基线</span>
                  </div>
                  <div className="form-grid">
                    {Object.entries(sweepInputs[strategyType]).map(([key, value]) => (
                      <Field
                        key={key}
                        label={formatParamLabel(key)}
                        type="text"
                        value={value}
                        onChange={(nextValue) =>
                          setSweepInputs((current) => ({
                            ...current,
                            [strategyType]: { ...current[strategyType], [key]: nextValue },
                          }))
                        }
                      />
                    ))}
                  </div>
                  <div className="note-box">
                    多个参数值请使用逗号分隔，例如：<code>0.01,0.015,0.02</code>
                  </div>
                </section>

                <section className="panel-section">
                  <div className="section-head">
                    <h2>当前研究摘要</h2>
                    <span>用于面试演示</span>
                  </div>
                  <div className="info-stack">
                    <p>
                      <strong>默认策略：</strong>
                      {formatStrategyLabel(strategyType)}
                    </p>
                    <p>
                      <strong>参数基线：</strong>
                      {formatParamEntries(currentParams)}
                    </p>
                    <p>
                      <strong>已保存实验：</strong>
                      {formatNumber(experiments.length, 0)} 组
                    </p>
                  </div>
                </section>
              </>
            )}
          </div>
        </aside>

        <section className="workspace-panel center-panel">
          <div className="panel-topline">
            <strong>行情与回测</strong>
            <span>
              {datasetDetail ? `${datasetDetail.name} · ${formatStrategyLabel(strategyType)}` : "等待选择数据集"}
            </span>
          </div>
          <div className="tab-strip">
            <button className={activeTab === "price" ? "active" : ""} onClick={() => setActiveTab("price")}>
              行情与买卖点
            </button>
            <button className={activeTab === "equity" ? "active" : ""} onClick={() => setActiveTab("equity")}>
              净值与回撤
            </button>
          </div>

          <div className="chart-stage">
            {activeTab === "price" ? (
              priceValues.length ? (
                <ChartPanel
                  id="price-chart-svg"
                  title="行情走势与买卖标记"
                  labels={priceLabels}
                  timeframe={datasetDetail?.timeframe || "1d"}
                  series={[{ name: "收盘价", color: "#c67b34", values: priceValues }]}
                  markers={tradeMarkers}
                />
              ) : (
                <TableEmpty message="当前数据集暂无可绘制的行情数据。" />
              )
            ) : backtest ? (
              <ChartPanel
                id="equity-chart-svg"
                title="策略净值与基准对比"
                labels={equityLabels}
                timeframe={datasetDetail?.timeframe || "1d"}
                series={[
                  { name: "策略净值", color: "#1f7a5e", values: backtest.timeseries.equity_curve.map((item) => item.value) },
                  { name: "基准净值", color: "#8f5a3a", values: backtest.timeseries.benchmark_curve.map((item) => item.value) },
                ]}
              />
            ) : (
              <TableEmpty message="运行回测后，可查看策略净值与基准对比图。" />
            )}
          </div>

          <section className="panel-section trade-pane">
            <div className="section-head">
              <h2>成交明细</h2>
              <span>{backtest?.trades?.length ? `${backtest.trades.length} 笔成交` : "暂无成交"}</span>
            </div>
            {backtest?.trades?.length ? (
              <div className="table-scroll">
                <table className="trade-table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>方向</th>
                      <th>价格</th>
                      <th>数量</th>
                      <th>费用</th>
                      <th>现金</th>
                      <th>原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtest.trades.map((trade) => (
                      <tr key={trade.trade_id}>
                        <td>{formatDateLabel(trade.datetime, datasetDetail?.timeframe || "1d")}</td>
                        <td>{trade.side === "buy" ? "买入" : "卖出"}</td>
                        <td>{formatNumber(trade.price, 3)}</td>
                        <td>{trade.quantity}</td>
                        <td>{formatNumber(trade.fee + trade.tax, 2)}</td>
                        <td>{formatNumber(trade.cash_after, 2)}</td>
                        <td>{formatReasonLabel(trade.reason)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <TableEmpty message="运行回测后，这里会显示完整成交明细。" />
            )}
          </section>
        </section>

        <aside className="workspace-panel right-panel">
          <section className="panel-section">
            <div className="section-head">
              <h2>指标摘要</h2>
              <span>{summary ? formatStrategyLabel(backtest.strategy_type) : "等待回测"}</span>
            </div>
            {summary ? (
              <div className="metric-grid">
                <MetricCard label="总收益率" value={formatPercent(summary.total_return)} tone="green" />
                <MetricCard label="最大回撤" value={formatPercent(summary.max_drawdown)} tone="red" />
                <MetricCard label="胜率" value={formatPercent(summary.win_rate)} />
                <MetricCard label="超额收益" value={formatPercent(summary.excess_return)} tone="green" />
                <MetricCard label="换手率" value={formatNumber(summary.turnover_ratio, 2)} />
                <MetricCard label="成本占比" value={formatPercent(summary.cost_ratio)} tone="amber" />
                <MetricCard label="成交次数" value={formatNumber(summary.trade_count, 0)} />
                <MetricCard label="最终净值" value={formatNumber(summary.final_nav, 2)} tone="green" />
              </div>
            ) : (
              <TableEmpty message="运行回测后，这里会汇总收益、回撤、成本和成交表现。" />
            )}
          </section>

          <section className="panel-section fixed-height-pane">
            <div className="section-head">
              <h2>最新实验</h2>
              <span>{activeExperiment?.runs?.length ? `${activeExperiment.runs.length} 组` : `${experiments.length} 条历史`}</span>
            </div>
            {activeExperiment?.runs?.length ? (
              <div className="table-scroll">
                <table className="compact-table">
                  <thead>
                    <tr>
                      <th>评分</th>
                      <th>收益</th>
                      <th>回撤</th>
                      <th>参数</th>
                    </tr>
                  </thead>
                  <tbody>
                    {activeExperiment.runs.slice(0, 6).map((run) => (
                      <tr key={run.run_id} onClick={() => applyRun(run)}>
                        <td>{formatNumber(run.summary.score, 3)}</td>
                        <td>{formatPercent(run.summary.total_return)}</td>
                        <td>{formatPercent(run.summary.max_drawdown)}</td>
                        <td>{formatParamEntries(run.params)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <TableEmpty message="运行参数实验后，这里会展示得分最高的组合，点击即可回填。" />
            )}
          </section>

          <section className="panel-section report-pane">
            <div className="section-head">
              <h2>AI 分析报告</h2>
              <button className="ghost-button" onClick={applyAiSuggestions} disabled={!report}>
                应用建议
              </button>
            </div>
            {report ? (
              <div className="report-scroll">
                <div className="report-meta">
                  <span>{report.title}</span>
                  <span>{formatMarketRegimeLabel(report.structured_recommendations?.market_regime)}</span>
                </div>
                {report.sections.map((section) => (
                  <article key={section.title} className="report-card">
                    <h3>{section.title}</h3>
                    <p>{section.content}</p>
                  </article>
                ))}
                <div className="recommendation-box">
                  <strong>风险提示</strong>
                  <ul>
                    {(report.structured_recommendations?.risk_flags || []).map((item) => (
                      <li key={item.message}>
                        <b>{formatRiskLevelLabel(item.level)}：</b>
                        {item.message}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="recommendation-box">
                  <strong>下一轮实验</strong>
                  <ul>
                    {(report.next_experiments || []).map((item) => (
                      <li key={item.name}>
                        <b>{item.title || item.name}：</b>
                        {item.reason}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="recommendation-box">
                  <strong>参数调整建议</strong>
                  <ul>
                    {(report.structured_recommendations?.recommended_param_changes || []).map((item) => (
                      <li key={`${item.parameter}-${item.action}`}>
                        <b>{item.parameter_label || formatParamLabel(item.parameter)}：</b>
                        建议{item.action_label || formatActionLabel(item.action)}，{item.reason}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <TableEmpty message="生成 AI 报告后，这里会汇总策略表现、风险提示和下一轮实验建议。" />
            )}
          </section>
        </aside>
      </section>
    </main>
  );
}
