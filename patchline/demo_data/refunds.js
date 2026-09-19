// Consumer code — written against PayAPI v1
async function refundCharge(client, chargeId, amount) {
  return client.post("/v1/refunds", { charge: chargeId, amount });
}

module.exports = { refundCharge };
