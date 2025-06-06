/** @type {import('next').NextConfig} */
const nextConfig = {
    // set basepath based on environment
    basePath: process.env.NEXT_PUBLIC_BASE_PATH ?? "",
    output: "standalone",
};

export default nextConfig;
