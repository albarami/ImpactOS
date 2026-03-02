import { redirect } from 'next/navigation';

export default function Home() {
  const workspaceId = process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID;
  if (!workspaceId) redirect('/login');
  redirect(`/w/${workspaceId}/documents`);
}
