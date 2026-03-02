export function getDevWorkspaceId(): string {
  const id = process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID;
  if (!id || id.trim() === '') {
    throw new Error(
      'NEXT_PUBLIC_DEV_WORKSPACE_ID is required. Set it in .env.local or environment.'
    );
  }
  return id;
}
