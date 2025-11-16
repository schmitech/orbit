const path = require('path');

module.exports = {
  content: [
    path.resolve(__dirname, './dashboard.html'),
    path.resolve(__dirname, './dashboard.js')
  ],
  theme: {
    extend: {}
  },
  plugins: []
};
