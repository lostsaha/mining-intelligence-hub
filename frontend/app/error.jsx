"use client";

export default function Error({ error, reset }) {
  return (
    <div className="card" style={{ padding: 24 }}>
      <h1 style={{ marginTop: 0 }}>页面加载失败</h1>
      <p style={{ color: "#b91c1c" }}>{error?.message || "未知错误"}</p>
      <p className="sub">
        请检查后端 API 是否运行、数据库是否可连接；修复后可重试。
      </p>
      <button className="run" onClick={() => reset()}>重试</button>
    </div>
  );
}
