import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

describe('auth provider configuration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    vi.resetModules();
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it('uses CredentialsProvider when NEXTAUTH_PROVIDER is not set', async () => {
    delete process.env.NEXTAUTH_PROVIDER;
    const { buildProviders } = await import('@/lib/auth');
    const providers = buildProviders();
    expect(providers).toHaveLength(1);
    expect(providers[0]).toHaveProperty('id', 'credentials');
  });

  it('uses CredentialsProvider when NEXTAUTH_PROVIDER is "credentials"', async () => {
    process.env.NEXTAUTH_PROVIDER = 'credentials';
    const { buildProviders } = await import('@/lib/auth');
    const providers = buildProviders();
    expect(providers).toHaveLength(1);
    expect(providers[0]).toHaveProperty('id', 'credentials');
  });

  it('uses OIDC provider when NEXTAUTH_PROVIDER is "oidc"', async () => {
    process.env.NEXTAUTH_PROVIDER = 'oidc';
    process.env.OIDC_ISSUER = 'https://idp.example.com';
    process.env.OIDC_CLIENT_ID = 'test-client-id';
    process.env.OIDC_CLIENT_SECRET = 'test-client-secret';
    const { buildProviders } = await import('@/lib/auth');
    const providers = buildProviders();
    expect(providers).toHaveLength(1);
    expect(providers[0]).toHaveProperty('id', 'impactos-oidc');
    expect(providers[0]).toHaveProperty('type', 'oauth');
  });

  // buildProviders() is called at module load time via authOptions,
  // so missing OIDC env vars cause the import itself to throw (fail-fast).
  it('fails to import when OIDC_ISSUER is missing', async () => {
    process.env.NEXTAUTH_PROVIDER = 'oidc';
    delete process.env.OIDC_ISSUER;
    process.env.OIDC_CLIENT_ID = 'test-client-id';
    process.env.OIDC_CLIENT_SECRET = 'test-client-secret';
    await expect(import('@/lib/auth')).rejects.toThrow('OIDC_ISSUER');
  });

  it('fails to import when OIDC_CLIENT_ID is missing', async () => {
    process.env.NEXTAUTH_PROVIDER = 'oidc';
    process.env.OIDC_ISSUER = 'https://idp.example.com';
    delete process.env.OIDC_CLIENT_ID;
    process.env.OIDC_CLIENT_SECRET = 'test-client-secret';
    await expect(import('@/lib/auth')).rejects.toThrow('OIDC_CLIENT_ID');
  });

  it('fails to import when OIDC_CLIENT_SECRET is missing', async () => {
    process.env.NEXTAUTH_PROVIDER = 'oidc';
    process.env.OIDC_ISSUER = 'https://idp.example.com';
    process.env.OIDC_CLIENT_ID = 'test-client-id';
    delete process.env.OIDC_CLIENT_SECRET;
    await expect(import('@/lib/auth')).rejects.toThrow('OIDC_CLIENT_SECRET');
  });

  it('OIDC provider uses wellKnown discovery', async () => {
    process.env.NEXTAUTH_PROVIDER = 'oidc';
    process.env.OIDC_ISSUER = 'https://idp.example.com';
    process.env.OIDC_CLIENT_ID = 'test-client-id';
    process.env.OIDC_CLIENT_SECRET = 'test-client-secret';
    const { buildProviders } = await import('@/lib/auth');
    const providers = buildProviders();
    const oidcProvider = providers[0] as Record<string, unknown>;
    expect(oidcProvider.wellKnown).toBe(
      'https://idp.example.com/.well-known/openid-configuration',
    );
  });

  it('authOptions secret uses env var without dev fallback when NEXTAUTH_PROVIDER is oidc', async () => {
    process.env.NEXTAUTH_PROVIDER = 'oidc';
    process.env.NEXTAUTH_SECRET = 'real-staging-secret-value';
    process.env.OIDC_ISSUER = 'https://idp.example.com';
    process.env.OIDC_CLIENT_ID = 'cid';
    process.env.OIDC_CLIENT_SECRET = 'csecret';
    const { authOptions } = await import('@/lib/auth');
    expect(authOptions.secret).toBe('real-staging-secret-value');
  });

  it('DEV_USER_ID is a valid UUID', async () => {
    const { DEV_USER_ID } = await import('@/lib/auth');
    const uuidRegex =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
    expect(DEV_USER_ID).toMatch(uuidRegex);
  });
});
