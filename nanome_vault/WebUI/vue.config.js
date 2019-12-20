module.exports = {
  productionSourceMap: false,
  devServer: {
    proxy: {
      '^/files': {
        target: 'http://localhost',
        ws: true,
        changeOrigin: true
      }
    }
  }
}
