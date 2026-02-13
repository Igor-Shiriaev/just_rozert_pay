const BundleTracker = require('webpack-bundle-tracker'); // eslint-disable-line
const path = require('path'); // eslint-disable-line

// eslint-disable-line
module.exports = {
  mode: 'development',
  context: __dirname, // eslint-disable-line
  entry: './src/index.tsx',
  output: {
    path: path.join(__dirname, 'build'), // eslint-disable-line
    filename: '[name]-[hash].js',
  },
  plugins: [new BundleTracker({ filename: 'webpack-stats.json' })],
  module: {
    rules: [
      {
        test: /\.tsx?$/,
        use: ['ts-loader', 'source-map-loader'],
        exclude: /node_modules|build/,
      },
      {
        test: /\.less$/,
        use: ['style-loader', 'css-loader', 'less-loader'],
        exclude: /node_modules|build/,
      },
    ],
  },
  resolve: {
    extensions: ['.tsx', '.ts', '.js', '.less'],
    alias: {
      '@': path.resolve(__dirname, 'src'),
    }
  },
};
