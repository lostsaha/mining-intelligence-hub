import { NextResponse } from "next/server";

const BACKEND = process.env.API_URL || "http://127.0.0.1:8100";
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || "";

export const dynamic = "force-dynamic";

export async function POST(request) {
  // 只接受同源浏览器请求，降低 CSRF 风险（CLI 无 Origin 头仍可用）。
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (origin) {
    try {
      if (new URL(origin).host !== host) {
        return NextResponse.json({ detail: "跨源管理请求被拒绝" }, { status: 403 });
      }
    } catch {
      return NextResponse.json({ detail: "非法 Origin" }, { status: 403 });
    }
  }

  // 生产环境默认关闭浏览器端管理入口；单机本地开发可用。
  // 生产部署请用 CLI/curl 直接带 X-Admin-Token 调用后端，或显式设置
  // ALLOW_ADMIN_UI=1 并自行在网关层加登录/访问控制。
  const allowed =
    process.env.NODE_ENV !== "production" ||
    process.env.ALLOW_ADMIN_UI === "1";
  if (!allowed) {
    return NextResponse.json(
      { detail: "管理入口已关闭；请使用 CLI 并配置 ADMIN_TOKEN" },
      { status: 403 },
    );
  }
  if (process.env.NODE_ENV === "production" && !ADMIN_TOKEN) {
    return NextResponse.json(
      { detail: "生产环境必须为 Next 服务端配置 ADMIN_TOKEN" },
      { status: 503 },
    );
  }

  const headers = { "X-Requested-With": "mining-admin" };
  if (ADMIN_TOKEN) headers["X-Admin-Token"] = ADMIN_TOKEN;

  try {
    const res = await fetch(`${BACKEND}/api/admin/run-pipeline`, {
      method: "POST",
      headers,
      cache: "no-store",
    });
    const text = await res.text();
    return new NextResponse(text, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") || "application/json",
      },
    });
  } catch (err) {
    return NextResponse.json(
      { detail: `后端不可达：${err.message || "connection failed"}` },
      { status: 502 },
    );
  }
}
