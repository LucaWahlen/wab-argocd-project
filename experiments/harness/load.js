import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    load: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.TARGET_RPS || 500),
      timeUnit: '1s',
      duration: __ENV.RUN_DURATION || '180s',
      preAllocatedVUs: 20,
      maxVUs: 60,
    },
  },
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
    'status is 2xx': (r) => r.status >= 200 && r.status < 300,
    'has shippingClass': (r) => r.status > 0 && r.json('shippingClass') !== undefined,
    'has version header': (r) =>
      Object.keys(r.headers).some((h) => h.toLowerCase() === 'x-application-version'),
  });
}

export function handleSummary(data) {
  const checks = data.metrics.checks.values.rate;
  const reqs = data.metrics.http_reqs.values;
  const p95 = data.metrics.http_req_duration.values['p(95)'];
  const med = data.metrics.http_req_duration.values['med'];
  const lines = [
    '',
    '========================================',
    checks === 1 ? 'LOAD TEST PASSED' : 'LOAD TEST FINISHED',
    `checks passed : ${(checks * 100).toFixed(2)}%`,
    `requests      : ${reqs.count} (${reqs.rate.toFixed(1)}/s)`,
    `median latency: ${med.toFixed(2)}ms`,
    `p95 latency   : ${p95.toFixed(2)}ms`,
    '========================================',
    '',
  ];
  return { stdout: lines.join('\n') };
}
