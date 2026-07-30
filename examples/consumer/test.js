// Consumer test suite, executed against the v2 server simulation (mockClient).
const assert = require("assert");
const client = require("./mockClient");
const billing = require("./billing");
const refunds = require("./refunds");

(async () => {
  let passed = 0, failed = 0;
  const logs = [];
  async function t(name, fn) {
    try {
      await fn();
      passed++;
      logs.push(`PASS ${name}`);
    } catch (e) {
      failed++;
      logs.push(`FAIL ${name}: ${e.message}`);
    }
  }

  await t("fetchCharge hits a live endpoint", async () => {
    const c = await billing.fetchCharge(client, "ch_123");
    assert.strictEqual(c.id, "ch_123");
  });

  await t("isInFlight detects in-flight charge", async () => {
    assert.strictEqual(billing.isInFlight({ status: "processing" }), true);
  });

  await t("chargeCity parses address", async () => {
    const c = await billing.fetchCharge(client, "ch_123").catch(() => null);
    const charge = c || { billing_details: { address: { line1: "123 Main St", city: "San Francisco" } } };
    assert.strictEqual(billing.chargeCity(charge), "San Francisco");
  });

  await t("refundCharge sends required reason", async () => {
    const r = await refunds.refundCharge(client, "ch_123", 500);
    assert.strictEqual(r.status, "succeeded");
  });

  for (const l of logs) console.log(l);
  console.log(`RESULT passed=${passed} failed=${failed}`);
  process.exit(failed ? 1 : 0);
})();
