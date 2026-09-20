"use client";

import { useEffect, useState } from "react";

export default function PipelineButton() {
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");
  const [polling, setPolling] = useState(false);

  async function checkStatus() {
    try {
      const res = await fetch("http://127.0.0.1:8100/api/stats", { cache: "no-store" });
      const data = await res.json();
      if (data.job_running) return true;
      return false;
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
      const res = await fetch("http://127.0.0.1:8100/api/admin/run-pipeline", { method: "POST" });
      const data = await res.json();
      if (!data.started) {
        setRunning(true);
        setPolling(true);
        setMsg("已有任务在运行中，等待完成…");
      } else {
        setPolling(true);
      }
    } catch {
      setRunning(false);
      setMsg("启动失败：请确认后端服务（127.0.0.1:8100）已运行");
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
