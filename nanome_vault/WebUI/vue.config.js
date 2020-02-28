module.exports = {
  productionSourceMap: false,
  devServer: {
    proxy: {
      '^/(files|info)': {
        target: 'http://localhost',
        ws: true,
        changeOrigin: true
      }
    }
  }
}
