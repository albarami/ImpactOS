'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface SessionControlsProps {
  status: string;
  onCommit: () => void;
  onExport: () => void;
  isCommitting: boolean;
}

export function SessionControls({
  status,
  onCommit,
  onExport,
  isCommitting,
}: SessionControlsProps) {
  const canCommit = status === 'draft' && !isCommitting;
  const canExport = status === 'committed';

  return (
    <Card>
      <CardHeader>
        <CardTitle>Session Actions</CardTitle>
      </CardHeader>
      <CardContent className="flex items-center gap-3">
        <Button
          onClick={onCommit}
          disabled={!canCommit}
        >
          {isCommitting ? 'Committing...' : 'Commit Run'}
        </Button>
        <Button
          variant="outline"
          onClick={onExport}
          disabled={!canExport}
        >
          Export
        </Button>
        <span className="ml-auto text-sm text-muted-foreground">
          Status: <span className="font-medium">{status}</span>
        </span>
      </CardContent>
    </Card>
  );
}
