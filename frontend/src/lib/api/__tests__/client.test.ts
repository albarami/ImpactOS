import { describe, it, expect } from 'vitest';
import { api } from '../client';

describe('api client', () => {
  it('should be defined', () => {
    expect(api).toBeDefined();
    expect(api.GET).toBeDefined();
    expect(api.POST).toBeDefined();
  });
});
