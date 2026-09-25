module.exports = {
  productionSourceMap: false,
  devServer: {
    proxy: {
      '^/(files|info|zip)': {
        target: process.env.VAULT_SERVER || 'http://localhost',
        ws: true,
        changeOrigin: true
      }
    }
  }
}
