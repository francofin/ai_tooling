import type { NextConfig } from 'next';
// import withPlugins from 'next-compose-plugins';
// import reactSvg from 'next-react-svg';


const nextConfig: NextConfig = {
  /* config options here */
  experimental: {
    // Targets `next build`, which is the memory-hungry step here (see FRONTEND.md).
    // Measured effect on `next dev` is ~1% (2084 MB vs 2108 MB after compiling four
    // routes cold), i.e. none — do not expect this to help the dev server.
    webpackMemoryOptimizations: true,
    // Compile route entries on demand instead of preloading them all at startup.
    // Also no measurable dev win in this repo; kept as it costs nothing.
    preloadEntriesOnStart: false,
  },
  typescript: {
    ignoreBuildErrors: false,
  },
  images: {
  	unoptimized: true,
  	dangerouslyAllowSVG: true,
    deviceSizes: [320, 480, 640, 750, 828, 1080, 1200, 1920, 2048, 3840],
    domains: ['placehold.co', 'img.youtube.com', "thetradingfloor.s3.amazonaws.com","www.bing.com",'res.cloudinary.com',], // Add the domain you're using here
  },
  webpack(config) {
      config.module.rules.push({
        test: /\.svg$/i,
        issuer: /\.[jt]sx?$/,
        use: [
          {
            loader: "@svgr/webpack",
            options: {
              svgoConfig: {
                plugins: [
                  {
                    name: "removeUselessDefs",
                    active: false,
                  },
                ],
              },
            },
          },
        ],
      })
  
      return config
    }
}

export default nextConfig
