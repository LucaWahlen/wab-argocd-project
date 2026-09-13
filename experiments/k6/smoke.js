import http from 'k6/http';
import { check } from 'k6';

export const options = {
  vus: 1,
  duration: '30s',
};

const payload = JSON.stringify({
  weightKg: 4.5,
  lengthCm: 40,
  widthCm: 30,
  heightCm: 20,
  destinationZone: 'EU',
  service: 'express',
});
const params = { headers: { 'Content-Type': 'application/json' } };

export default function () {
  const res = http.post('http://localhost:8000/v1/quotes', payload, params);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'has shippingClass': (r) => r.json('shippingClass') !== undefined,
    'has version header': (r) =>
      Object.keys(r.headers).some((h) => h.toLowerCase() === 'x-application-version'),
  });
}

export function handleSummary(data) {
  const checks = data.metrics.checks.values.rate;
  const reqs = data.metrics.http_reqs.values;
  const p95 = data.metrics.http_req_duration.values['p(95)'];
  const lines = [
    '',
    '========================================',
    checks === 1 ? 'SMOKE TEST PASSED' : 'SMOKE TEST FAILED',
    `checks passed : ${(checks * 100).toFixed(1)}%`,
    `requests      : ${reqs.count} (${reqs.rate.toFixed(1)}/s)`,
    `p95 latency   : ${p95.toFixed(2)}ms`,
    '========================================',
    '',
  ];
  return { stdout: lines.join('\n') };
}
