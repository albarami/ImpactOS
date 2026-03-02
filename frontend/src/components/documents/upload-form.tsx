'use client';

import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useUploadDocument,
  useExtractDocument,
} from '@/lib/api/hooks/useDocuments';

const DEV_USER_ID = '00000000-0000-7000-8000-000000000001';

const DOC_TYPES = ['BOQ', 'CAPEX', 'POLICY', 'OTHER'] as const;
const SOURCE_TYPES = ['CLIENT', 'PUBLIC', 'INTERNAL'] as const;
const CLASSIFICATIONS = ['PUBLIC', 'INTERNAL', 'CONFIDENTIAL', 'RESTRICTED'] as const;
const LANGUAGES = ['en', 'ar', 'bilingual'] as const;

export interface UploadResult {
  docId: string;
  jobId: string;
}

interface UploadFormProps {
  workspaceId: string;
  onUploaded: (result: UploadResult) => void;
}

export function UploadForm({ workspaceId, onUploaded }: UploadFormProps) {
  const [file, setFile] = useState<File | null>(null);
  const [docType, setDocType] = useState<string>('BOQ');
  const [sourceType, setSourceType] = useState<string>('CLIENT');
  const [classification, setClassification] = useState<string>('INTERNAL');
  const [language, setLanguage] = useState<string>('en');

  const upload = useUploadDocument(workspaceId);
  const extract = useExtractDocument(workspaceId);

  const isPending = upload.isPending || extract.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('doc_type', docType);
    formData.append('source_type', sourceType);
    formData.append('classification', classification);
    formData.append('language', language);
    formData.append('uploaded_by', DEV_USER_ID);

    const uploadResult = await upload.mutateAsync(formData);
    const extractResult = await extract.mutateAsync(uploadResult.doc_id);

    onUploaded({
      docId: uploadResult.doc_id,
      jobId: extractResult.job_id,
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload Document</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* File Input */}
          <div className="space-y-2">
            <Label htmlFor="file-input">File</Label>
            <Input
              id="file-input"
              type="file"
              accept=".pdf,.xlsx,.xls,.csv,.docx"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>

          {/* Document Type */}
          <div className="space-y-2">
            <Label>Document Type</Label>
            <Select value={docType} onValueChange={setDocType}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOC_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Source Type */}
          <div className="space-y-2">
            <Label>Source Type</Label>
            <Select value={sourceType} onValueChange={setSourceType}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SOURCE_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {t}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Classification */}
          <div className="space-y-2">
            <Label>Classification</Label>
            <Select value={classification} onValueChange={setClassification}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CLASSIFICATIONS.map((c) => (
                  <SelectItem key={c} value={c}>
                    {c}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Language */}
          <div className="space-y-2">
            <Label>Language</Label>
            <Select value={language} onValueChange={setLanguage}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LANGUAGES.map((l) => (
                  <SelectItem key={l} value={l}>
                    {l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Button type="submit" disabled={!file || isPending}>
            {isPending ? 'Uploading...' : 'Upload & Extract'}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
