import type { NextAuthOptions } from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';

export const DEV_USER_ID = '00000000-0000-7000-8000-000000000001';

/**
 * Build the NextAuth provider list based on NEXTAUTH_PROVIDER env var.
 *
 * - "credentials" (default): Dev-only CredentialsProvider with hardcoded user.
 * - "oidc": Generic OIDC provider using wellKnown discovery. Works with
 *   Azure AD, Auth0, Keycloak, or any OIDC-compliant IdP.
 *   Requires: OIDC_ISSUER, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET.
 */
export function buildProviders(): NextAuthOptions['providers'] {
  const provider = process.env.NEXTAUTH_PROVIDER || 'credentials';

  if (provider === 'oidc') {
    const missing: string[] = [];
    if (!process.env.OIDC_ISSUER) missing.push('OIDC_ISSUER');
    if (!process.env.OIDC_CLIENT_ID) missing.push('OIDC_CLIENT_ID');
    if (!process.env.OIDC_CLIENT_SECRET) missing.push('OIDC_CLIENT_SECRET');
    if (missing.length > 0) {
      throw new Error(
        `OIDC provider requires: ${missing.join(', ')}. ` +
          'Set these environment variables or use NEXTAUTH_PROVIDER=credentials for dev.',
      );
    }

    return [
      {
        id: 'impactos-oidc',
        name: 'SSO',
        type: 'oauth',
        wellKnown: `${process.env.OIDC_ISSUER}/.well-known/openid-configuration`,
        authorization: { params: { scope: 'openid email profile' } },
        clientId: process.env.OIDC_CLIENT_ID!,
        clientSecret: process.env.OIDC_CLIENT_SECRET!,
        idToken: true,
        checks: ['pkce', 'state'],
        profile(profile) {
          return {
            id: profile.sub,
            name: profile.name || profile.preferred_username || profile.email,
            email: profile.email,
          };
        },
      } as NextAuthOptions['providers'][number],
    ];
  }

  // Dev-only credentials provider — hardcoded user, no real auth.
  return [
    CredentialsProvider({
      name: 'Dev Login',
      credentials: {
        email: {
          label: 'Email',
          type: 'email',
          placeholder: 'dev@impactos.local',
        },
      },
      async authorize(credentials) {
        return {
          id: DEV_USER_ID,
          email: credentials?.email || 'dev@impactos.local',
          name: 'Dev User',
        };
      },
    }),
  ];
}

// In OIDC mode, NEXTAUTH_SECRET is mandatory — fail-fast to prevent
// silent fallback to a well-known dev secret in staging/prod.
const isOidc = (process.env.NEXTAUTH_PROVIDER || 'credentials') === 'oidc';
if (isOidc && !process.env.NEXTAUTH_SECRET) {
  throw new Error(
    'NEXTAUTH_SECRET is required when NEXTAUTH_PROVIDER=oidc. ' +
      'Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"',
  );
}

export const authOptions: NextAuthOptions = {
  providers: buildProviders(),
  callbacks: {
    async jwt({ token, account, profile }) {
      // For OIDC: map the external sub claim to token
      if (account && profile) {
        token.sub = (profile as Record<string, string>).sub || token.sub;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.sub!;
      }
      return session;
    },
  },
  pages: {
    signIn: '/login',
  },
  secret: process.env.NEXTAUTH_SECRET || 'dev-secret-do-not-use-in-production',
};
