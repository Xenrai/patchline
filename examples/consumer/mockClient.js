// Simulates the PayAPI **v2** server. Consumer code written for v1 breaks here.
const charges = {
  ch_123: {
    id: "ch_123",
    status: "processing",
    billing_details: { address: { line1: "123 Main St", city: "San Francisco" } },
  },
};

function get(path) {
  const m = path.match(/^\/v1\/payments\/(\w+)$/);
  if (m && charges[m[1]]) return Promise.resolve(charges[m[1]]);
  const err = new Error(`404 NOT FOUND: GET ${path} (endpoint removed in v2)`);
  err.status = 404;
  return Promise.reject(err);
}

function post(path, body) {
  if (path === "/v1/refunds") {
    if (!body || typeof body.reason !== "string") {
      const err = new Error("400 BAD REQUEST: missing required field 'reason' (added in v2)");
      err.status = 400;
      return Promise.reject(err);
    }
    return Promise.resolve({ id: "re_1", ...body, status: "succeeded" });
  }
  return Promise.reject(new Error(`404 NOT FOUND: POST ${path}`));
}

module.exports = { get, post };
