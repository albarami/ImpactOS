'use client';

import { useState } from 'react';
import { signIn } from 'next-auth/react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

const authMode = process.env.NEXT_PUBLIC_AUTH_MODE || 'credentials';

export default function LoginPage() {
  const [email, setEmail] = useState('dev@impactos.local');
  const [isLoading, setIsLoading] = useState(false);

  async function handleCredentialsSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);
    await signIn('credentials', {
      email,
      callbackUrl: '/',
    });
    setIsLoading(false);
  }

  async function handleOidcSignIn() {
    setIsLoading(true);
    await signIn('impactos-oidc', { callbackUrl: '/' });
    // No setIsLoading(false) — page redirects to IdP
  }

  if (authMode === 'oidc') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <Card className="w-full max-w-sm">
          <CardHeader className="space-y-1">
            <CardTitle className="text-2xl font-bold">ImpactOS</CardTitle>
            <CardDescription>Sign in with your organization account</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              className="w-full"
              disabled={isLoading}
              onClick={handleOidcSignIn}
            >
              {isLoading ? 'Redirecting...' : 'Sign in with SSO'}
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-bold">ImpactOS</CardTitle>
          <CardDescription>Dev Login (not for production)</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCredentialsSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                placeholder="dev@impactos.local"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? 'Signing in...' : 'Sign In'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
