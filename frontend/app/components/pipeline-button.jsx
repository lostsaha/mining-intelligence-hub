"use client";

import { useEffect, useState } from "react";

export default function PipelineButton() {
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");
  const [polling, setPolling] = useState(false);

  async function checkStatus() {
    try {
      const res = await fetch("/api/stats", { cache: "no-store" });
      if (!res.ok) return false;
      const data = await res.json();
      return Boolean(data.job_running);
    } catch {
      return false;
    }
  }

  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(async () => {
      const busy = await checkStatus();
      if (!busy) {
        setPolling(false);
        setRunning(false);
        setMsg("完成！正在刷新页面…");
        setTimeout(() => window.location.reload(), 1200);
      }
    }, 3000);
    return () => clearInterval(timer);
  }, [polling]);

  async function start() {
    setRunning(true);
    setMsg("管线运行中：采集 → AI 过滤打分 → 周报生成，约需 1~3 分钟");
    try {
      const res = await fetch("/admin-api/run-pipeline", {
        method: "POST",
        headers: { "X-Requested-With": "mining-admin" },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `HTTP ${res.status}`);
      }
      if (!data.started) {
        setRunning(true);
        setPolling(true);
        setMsg("已有任务在运行中，等待完成…");
      } else {
        setPolling(true);
      }
    } catch (e) {
      setRunning(false);
      setMsg(`启动失败：${e.message || "请确认后端服务已运行"}`);
    }
  }

  return (
    <div className="run-bar">
      <button className="run" onClick={start} disabled={running}>
        {running ? "运行中…" : "▶ 运行采集管线"}
      </button>
      {msg && <span className="run-msg">{msg}</span>}
    </div>
  );
}
