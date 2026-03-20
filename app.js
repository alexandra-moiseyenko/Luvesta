// app.js
App({
  onLaunch: function () {
    // Restore wallet from storage if available
    var saved = wx.getStorageSync('wallet');
    if (saved) {
      this.globalData.wallet = saved;
    }
  },

  globalData: {
    // Wallet state populated by wallet/connect page
    // { address, avatarUrl, cid, nickname, uid }
    wallet: null
  }
})