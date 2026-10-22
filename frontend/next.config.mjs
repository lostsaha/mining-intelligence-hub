/** @type {import('next').NextConfig} */
const backend = process.env.API_URL || "http://127.0.0.1:8100";

const nextConfig = {
  reactStrictMode: true,
  // 浏览器只访问同源 /api/*，由 Next 服务端代理到 FastAPI：
  // 避免 CORS/端口不一致，也便于生产环境只暴露一个入口。
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
