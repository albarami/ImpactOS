import type { NextAuthOptions } from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';

export const DEV_USER_ID = '00000000-0000-7000-8000-000000000001';

export const authOptions: NextAuthOptions = {
  providers: [
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
  ],
  callbacks: {
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
