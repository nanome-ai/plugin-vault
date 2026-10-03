module.exports = {
  presets: ['@vue/app'],
  // src/nanome2/pipeline.js uses ??, which this preset-env (7.3) predates
  plugins: ['@babel/plugin-proposal-nullish-coalescing-operator']
}
