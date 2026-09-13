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
    'has version header': (r) => r.headers['x-application-version'] !== undefined,
  });
}
