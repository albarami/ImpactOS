import { DocumentDetailContent } from '@/components/documents/document-detail-content';

interface DocumentDetailPageProps {
  params: Promise<{ workspaceId: string; docId: string }>;
  searchParams: Promise<{ jobId?: string }>;
}

export default async function DocumentDetailPage({
  params,
  searchParams,
}: DocumentDetailPageProps) {
  const { workspaceId, docId } = await params;
  const { jobId } = await searchParams;

  return (
    <DocumentDetailContent
      workspaceId={workspaceId}
      docId={docId}
      initialJobId={jobId ?? null}
    />
  );
}
