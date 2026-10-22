import { NextResponse } from "next/server";

/**
 * 禁止把后端管理端点通过 Next 的 /api 代理暴露给浏览器。
 * 本地开发的管理入口是 /admin-api/run-pipeline，由服务端路由处理。
 */
export function middleware(request) {
  if (request.nextUrl.pathname.startsWith("/api/admin")) {
    return NextResponse.json(
      { detail: "管理 API 不通过前端代理暴露" },
      { status: 404 },
    );
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/api/admin", "/api/admin/:path*"],
};
