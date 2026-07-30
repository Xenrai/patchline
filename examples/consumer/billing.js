// Consumer code — written against PayAPI v1
const CHARGE_URL = (id) => `/v1/charges/${id}`;

async function fetchCharge(client, id) {
  return client.get(CHARGE_URL(id));
}

function isInFlight(charge) {
  return charge.status === "pending";
}

function chargeCity(charge) {
  return charge.billing_details.address.split(",")[1].trim();
}

module.exports = { fetchCharge, isInFlight, chargeCity };
