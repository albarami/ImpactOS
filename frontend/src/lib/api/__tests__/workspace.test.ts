import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getDevWorkspaceId } from '../workspace';

describe('getDevWorkspaceId', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
  });

  it('returns workspace ID when env var is set', () => {
    process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID = 'ws-test-123';
    expect(getDevWorkspaceId()).toBe('ws-test-123');
  });

  it('throws when env var is missing', () => {
    delete process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID;
    expect(() => getDevWorkspaceId()).toThrow(
      'NEXT_PUBLIC_DEV_WORKSPACE_ID is required'
    );
  });

  it('throws when env var is empty string', () => {
    process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID = '';
    expect(() => getDevWorkspaceId()).toThrow(
      'NEXT_PUBLIC_DEV_WORKSPACE_ID is required'
    );
  });

  it('throws when env var is whitespace only', () => {
    process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID = '   ';
    expect(() => getDevWorkspaceId()).toThrow(
      'NEXT_PUBLIC_DEV_WORKSPACE_ID is required'
    );
  });
});
