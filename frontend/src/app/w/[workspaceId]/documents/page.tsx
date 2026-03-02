import { DocumentsPageContent } from '@/components/documents/documents-page-content';

interface DocumentsPageProps {
  params: Promise<{ workspaceId: string }>;
}

export default async function DocumentsPage({ params }: DocumentsPageProps) {
  const { workspaceId } = await params;
  return <DocumentsPageContent workspaceId={workspaceId} />;
}
