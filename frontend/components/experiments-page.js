"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import {
  formatDateLabel,
  formatNumber,
  formatParamEntries,
  formatPercent,
  formatStrategyLabel,
  translateError,
} from "../lib/presentation";


function HistoryMetric({ label, value }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}


export default function ExperimentsPage() {
  const [experiments, setExperiments] = useState([]);
  const [status, setStatus] = useState("正在加载实验历史...");

  useEffect(() => {
    let active = true;
    api("/api/experiments")
      .then((payload) => {
        if (!active) {
          return;
        }
        setExperiments(payload);
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
  }, []);

  return (
    <main className="history-shell">
      <header className="history-header">
        <div>
          <div className="brand-row">
            <p className="eyebrow">实验历史</p>
            <span className="subtle-tag">可复现快照</span>
          </div>
          <h1>参数实验记录</h1>
          <p className="muted">
            每次实验都会保存评分公式、引擎版本、策略版本和最优参数组合，方便复盘、复现和继续迭代。
          </p>
        </div>
        <div className="toolbar-actions">
          <Link className="ghost-button" href="/lab">
            返回工作台
          </Link>
        </div>
      </header>

      {status ? <div className="status-banner">{status}</div> : null}

      {!status && !experiments.length ? (
        <div className="empty-card">暂无实验记录，请先到工作台运行一次参数实验。</div>
      ) : null}

      <section className="history-grid">
        {experiments.map((experiment) => (
          <article className="history-card" key={experiment.experiment_id}>
            <div className="history-meta">
              <span>{formatStrategyLabel(experiment.strategy_type)}</span>
              <span>{formatDateLabel(experiment.created_at, "15m")}</span>
            </div>
            <div className="brand-row">
              <h2>{experiment.experiment_id}</h2>
              <span className="subtle-tag">{experiment.engine_version}</span>
            </div>
            <p className="muted">评分公式：{experiment.ranking_formula}</p>

            <div className="history-stats">
              <HistoryMetric label="实验组数" value={formatNumber(experiment.total_runs, 0)} />
              <HistoryMetric label="最佳收益" value={formatPercent(experiment.top_run?.summary?.total_return)} />
              <HistoryMetric label="最佳回撤" value={formatPercent(experiment.top_run?.summary?.max_drawdown)} />
              <HistoryMetric label="最佳评分" value={formatNumber(experiment.top_run?.summary?.score, 3)} />
              <HistoryMetric label="胜率" value={formatPercent(experiment.top_run?.summary?.win_rate)} />
              <HistoryMetric label="交易次数" value={formatNumber(experiment.top_run?.summary?.trade_count, 0)} />
            </div>

            <div className="info-stack">
              <p>
                <strong>数据集：</strong>
                {experiment.dataset_id}
              </p>
              <p>
                <strong>数据哈希：</strong>
                {experiment.dataset_hash}
              </p>
              <p>
                <strong>排名指标：</strong>
                {experiment.ranking_metric}
              </p>
            </div>

            <pre className="history-params">{formatParamEntries(experiment.top_run?.params || {}) || "--"}</pre>
          </article>
        ))}
      </section>
    </main>
  );
}
