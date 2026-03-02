import { CompileConfigForm } from '@/components/compiler/compile-config-form';

interface CompilePageProps {
  params: Promise<{ workspaceId: string; docId: string }>;
}

export default async function CompilePage({ params }: CompilePageProps) {
  const { workspaceId, docId } = await params;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          Compile Scenario
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Configure and trigger AI-assisted compilation from document line
          items.
        </p>
      </div>

      <CompileConfigForm workspaceId={workspaceId} documentId={docId} />
    </div>
  );
}
