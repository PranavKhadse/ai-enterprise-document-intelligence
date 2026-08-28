import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Upload,
  Search as SearchIcon,
  Trash2,
  Copy,
  Check,
  Layers,
  AlertCircle,
} from 'lucide-react';
import { documentsApi } from '../api/documents';
import { DocumentItemResponse, DocumentChunkResponse } from '../types/document';
import { useToast } from '../hooks/useToast';
import { useDebounce } from '../hooks/useDebounce';
import { Button } from '../components/common/Button';
import { Input } from '../components/common/Input';
import { Badge } from '../components/common/Badge';
import { Table, Column } from '../components/common/Table';
import { Modal } from '../components/common/Modal';
import { formatDate, formatBytes, truncateHash } from '../utils/formatters';
import { ApiError } from '../types/api';

export const DocumentsPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { success, error: toastError } = useToast();

  const [searchQuery, setSearchQuery] = useState('');
  const debouncedQuery = useDebounce(searchQuery, 300);
  const [pageOffset, setPageOffset] = useState(0);
  const pageSize = 10;

  // Modals state
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [deleteDocTarget, setDeleteDocTarget] = useState<DocumentItemResponse | null>(null);

  // Upload Form State
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [customTitle, setCustomTitle] = useState('');
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  // Check URL parameters on mount (e.g. ?action=upload or ?selected=uuid)
  useEffect(() => {
    if (searchParams.get('action') === 'upload') {
      setIsUploadModalOpen(true);
    }
    const selectedParam = searchParams.get('selected');
    if (selectedParam) {
      setSelectedDocId(selectedParam);
    }
  }, [searchParams]);

  // Query: Documents List
  const {
    data: docsData,
    isLoading: isDocsLoading,
  } = useQuery({
    queryKey: ['documents', { query: debouncedQuery, offset: pageOffset, limit: pageSize }],
    queryFn: () =>
      documentsApi.list({
        query: debouncedQuery.trim() || undefined,
        limit: pageSize,
        offset: pageOffset,
      }),
  });

  // Query: Selected Document Details
  const {
    data: selectedDoc,
  } = useQuery({
    queryKey: ['document', selectedDocId],
    queryFn: () => documentsApi.getById(selectedDocId!),
    enabled: !!selectedDocId,
  });

  // Query: Selected Document Chunks
  const {
    data: docChunks,
    isLoading: isChunksLoading,
  } = useQuery({
    queryKey: ['document-chunks', selectedDocId],
    queryFn: () => documentsApi.getChunks(selectedDocId!, { limit: 50, offset: 0 }),
    enabled: !!selectedDocId,
  });

  // Mutation: Upload Document
  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!selectedFile) throw new Error('Please select a PDF file.');
      return documentsApi.upload(
        selectedFile,
        customTitle.trim() || undefined,
        undefined,
        (percent) => setUploadProgress(percent)
      );
    },
    onSuccess: (res) => {
      if (res.is_duplicate) {
        success(
          'Existing Document Resolved',
          `Document with identical SHA-256 hash already exists as '${res.title}'.`
        );
      } else {
        success('Document Ingested', `Successfully uploaded and queued '${res.title}' for intelligence extraction.`);
      }
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      setIsUploadModalOpen(false);
      setSelectedFile(null);
      setCustomTitle('');
      setUploadProgress(null);
      setUploadError(null);
    },
    onError: (err: unknown) => {
      const apiErr = err as ApiError;
      setUploadError(apiErr.message);
      toastError('Upload Failed', apiErr.message, apiErr.requestId);
      setUploadProgress(null);
    },
  });

  // Mutation: Delete Document
  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      return documentsApi.delete(id);
    },
    onSuccess: (res) => {
      success('Document Deleted', res.message);
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      setDeleteDocTarget(null);
      if (selectedDocId === deleteDocTarget?.id) {
        setSelectedDocId(null);
      }
    },
    onError: (err: unknown) => {
      const apiErr = err as ApiError;
      toastError('Deletion Failed', apiErr.message, apiErr.requestId);
    },
  });

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      validateAndSetFile(file);
    }
  };

  const validateAndSetFile = (file: File) => {
    setUploadError(null);
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      setUploadError('Only enterprise PDF documents (.pdf) are supported.');
      return;
    }
    // 50 MB Client-side guard matching backend settings
    if (file.size > 52428800) {
      setUploadError('File size exceeds maximum permitted limit (50 MB).');
      return;
    }
    setSelectedFile(file);
    if (!customTitle) {
      setCustomTitle(file.name.replace(/\.pdf$/i, ''));
    }
  };

  const copyToClipboard = (text: string, hashId: string) => {
    navigator.clipboard.writeText(text);
    setCopiedHash(hashId);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const columns: Column<DocumentItemResponse>[] = [
    {
      key: 'title',
      header: 'Title & Hash',
      render: (doc) => (
        <div>
          <span className="font-semibold text-slate-900 dark:text-slate-100 hover:text-indigo-600 transition-colors">
            {doc.title}
          </span>
          <div className="flex items-center space-x-1.5 mt-0.5">
            <span className="text-[11px] font-mono text-slate-400">{truncateHash(doc.file_hash)}</span>
            <button
              onClick={(e) => {
                e.stopPropagation();
                copyToClipboard(doc.file_hash, doc.id);
              }}
              className="text-slate-400 hover:text-indigo-600 transition-colors"
              title="Copy SHA-256 Hash"
            >
              {copiedHash === doc.id ? (
                <Check className="w-3 h-3 text-emerald-500" />
              ) : (
                <Copy className="w-3 h-3" />
              )}
            </button>
          </div>
        </div>
      ),
    },
    {
      key: 'file_type',
      header: 'Format',
      render: (doc) => (
        <Badge variant="indigo" size="sm">
          {doc.file_type.toUpperCase()}
        </Badge>
      ),
    },
    {
      key: 'version',
      header: 'Version',
      render: (doc) => (
        <span className="text-xs font-mono bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded text-slate-700 dark:text-slate-300">
          v{doc.current_version}
        </span>
      ),
    },
    {
      key: 'created_at',
      header: 'Uploaded Date',
      render: (doc) => <span className="text-xs text-slate-500">{formatDate(doc.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      className: 'text-right',
      render: (doc) => (
        <div className="flex items-center justify-end space-x-1" onClick={(e) => e.stopPropagation()}>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSelectedDocId(doc.id)}
            leftIcon={<Layers className="w-3.5 h-3.5" />}
          >
            Chunks
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/50"
            onClick={() => setDeleteDocTarget(doc)}
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6 text-left">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Enterprise Document Management
          </h1>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Authoritative corporate repository for structural parsing, indexing, and grounded intelligence.
          </p>
        </div>

        <Button
          variant="primary"
          size="md"
          onClick={() => setIsUploadModalOpen(true)}
          leftIcon={<Upload className="w-4 h-4" />}
        >
          Ingest Document
        </Button>
      </div>

      {/* Filter & Search Bar */}
      <div className="flex items-center space-x-3 bg-white dark:bg-slate-900 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 shadow-sm">
        <div className="relative flex-1">
          <Input
            placeholder="Search document titles or keywords..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPageOffset(0);
            }}
            leftIcon={<SearchIcon className="w-4 h-4" />}
            className="w-full"
          />
        </div>
      </div>

      {/* Documents Table */}
      <div className="space-y-4">
        <Table
          columns={columns}
          data={docsData?.items || []}
          keyExtractor={(doc) => doc.id}
          isLoading={isDocsLoading}
          emptyText={
            debouncedQuery
              ? `No documents matching query '${debouncedQuery}'.`
              : 'No enterprise documents ingested yet. Upload a PDF document to begin.'
          }
          onRowClick={(doc) => setSelectedDocId(doc.id)}
        />

        {/* Pagination Controls */}
        {docsData && docsData.total > pageSize && (
          <div className="flex items-center justify-between px-2 text-xs text-slate-500">
            <span>
              Showing {pageOffset + 1} to {Math.min(pageOffset + pageSize, docsData.total)} of{' '}
              {docsData.total} documents
            </span>
            <div className="flex space-x-2">
              <Button
                variant="outline"
                size="sm"
                disabled={pageOffset === 0}
                onClick={() => setPageOffset(Math.max(0, pageOffset - pageSize))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={pageOffset + pageSize >= docsData.total}
                onClick={() => setPageOffset(pageOffset + pageSize)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Upload Document Modal */}
      <Modal
        isOpen={isUploadModalOpen}
        onClose={() => {
          setIsUploadModalOpen(false);
          setSelectedFile(null);
          setUploadError(null);
          setUploadProgress(null);
          setSearchParams({});
        }}
        title="Upload & Ingest PDF Document"
        description="Select an enterprise document. The backend will validate magic bytes, compute SHA-256 hash, and execute structural extraction."
        maxWidth="lg"
      >
        <div className="space-y-4">
          {/* Drag & Drop Box */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleFileDrop}
            className="border-2 border-dashed border-slate-300 dark:border-slate-700 hover:border-indigo-500 dark:hover:border-indigo-500 rounded-xl p-6 text-center cursor-pointer transition-colors bg-slate-50/50 dark:bg-slate-800/30"
            onClick={() => document.getElementById('file-upload-input')?.click()}
          >
            <input
              id="file-upload-input"
              type="file"
              accept=".pdf,application/pdf"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  validateAndSetFile(e.target.files[0]);
                }
              }}
            />
            <div className="w-12 h-12 rounded-full bg-indigo-50 dark:bg-indigo-950 text-indigo-600 dark:text-indigo-400 flex items-center justify-center mx-auto mb-3">
              <Upload className="w-6 h-6" />
            </div>
            {selectedFile ? (
              <div>
                <p className="text-sm font-semibold text-slate-900 dark:text-slate-100">{selectedFile.name}</p>
                <p className="text-xs text-slate-500 mt-0.5">{formatBytes(selectedFile.size)}</p>
              </div>
            ) : (
              <div>
                <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
                  Drag and drop PDF here, or click to browse
                </p>
                <p className="text-xs text-slate-400 mt-1">Supported: PDF up to 50 MB</p>
              </div>
            )}
          </div>

          {/* Title Override Input */}
          <Input
            label="Document Title (Optional)"
            placeholder="Defaults to original file name"
            value={customTitle}
            onChange={(e) => setCustomTitle(e.target.value)}
          />

          {uploadError && (
            <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/60 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-200 text-xs flex items-start space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{uploadError}</span>
            </div>
          )}

          {/* Progress Indicator */}
          {uploadProgress !== null && (
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs font-mono text-slate-500">
                <span>Uploading...</span>
                <span>{uploadProgress}%</span>
              </div>
              <div className="w-full h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-indigo-600 transition-all duration-300 rounded-full"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
            </div>
          )}

          <div className="flex justify-end space-x-3 pt-4 border-t border-slate-100 dark:border-slate-800">
            <Button
              variant="secondary"
              onClick={() => {
                setIsUploadModalOpen(false);
                setSelectedFile(null);
                setSearchParams({});
              }}
            >
              Cancel
            </Button>
            <Button
              variant="primary"
              disabled={!selectedFile || uploadMutation.isPending}
              isLoading={uploadMutation.isPending}
              onClick={() => uploadMutation.mutate()}
            >
              Start Ingestion
            </Button>
          </div>
        </div>
      </Modal>

      {/* Document Chunks Explorer Drawer/Modal */}
      <Modal
        isOpen={!!selectedDocId}
        onClose={() => {
          setSelectedDocId(null);
          setSearchParams({});
        }}
        title={selectedDoc?.title || 'Document Exploration'}
        description={`Document UUID: ${selectedDocId}`}
        maxWidth="4xl"
      >
        <div className="space-y-6">
          {/* Metadata Grid */}
          {selectedDoc && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-4 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/80 text-xs">
              <div>
                <span className="text-slate-400">Current Version</span>
                <p className="font-mono font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                  v{selectedDoc.current_version}
                </p>
              </div>
              <div>
                <span className="text-slate-400">Total Pages</span>
                <p className="font-mono font-semibold text-slate-800 dark:text-slate-200 mt-0.5">
                  {selectedDoc.total_pages ?? 'Parsed on index'}
                </p>
              </div>
              <div>
                <span className="text-slate-400">SHA-256 Hash</span>
                <p className="font-mono text-slate-800 dark:text-slate-200 mt-0.5">
                  {truncateHash(selectedDoc.file_hash)}
                </p>
              </div>
              <div>
                <span className="text-slate-400">Ingested At</span>
                <p className="text-slate-800 dark:text-slate-200 mt-0.5">
                  {formatDate(selectedDoc.created_at)}
                </p>
              </div>
            </div>
          )}

          {/* Parsed Chunks List */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
                <Layers className="w-4 h-4 text-indigo-500" />
                <span>Extracted Structural Chunks ({docChunks?.total ?? 0})</span>
              </h4>
            </div>

            {isChunksLoading ? (
              <div className="p-8 text-center text-xs text-slate-400">Loading passage chunks...</div>
            ) : docChunks?.items.length === 0 ? (
              <div className="p-6 text-center text-xs text-slate-400 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-dashed border-slate-200 dark:border-slate-700">
                No passage chunks stored for this document. Chunks are generated upon indexing execution.
              </div>
            ) : (
              <div className="space-y-2.5 max-h-[50vh] overflow-y-auto pr-1">
                {docChunks?.items.map((chunk: DocumentChunkResponse) => (
                  <div
                    key={chunk.id}
                    className="p-4 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:border-slate-300 dark:hover:border-slate-700 transition-colors text-xs space-y-2"
                  >
                    <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                      <span>Chunk #{chunk.chunk_index + 1} · Page {chunk.page_number ?? '1'}</span>
                      {chunk.section_path && (
                        <Badge variant="slate" size="sm">
                          {chunk.section_path}
                        </Badge>
                      )}
                    </div>
                    <p className="text-slate-800 dark:text-slate-200 leading-relaxed font-mono bg-slate-50 dark:bg-slate-950/60 p-2.5 rounded-lg border border-slate-100 dark:border-slate-800">
                      {chunk.content}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={!!deleteDocTarget}
        onClose={() => setDeleteDocTarget(null)}
        title="Confirm Document Deletion"
        description="Are you sure you want to permanently delete this document and all associated embeddings?"
        maxWidth="sm"
      >
        <div className="space-y-4">
          <p className="text-xs text-slate-600 dark:text-slate-300">
            Document: <span className="font-semibold text-slate-900 dark:text-white">{deleteDocTarget?.title}</span>
          </p>
          <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/50 border border-rose-200 dark:border-rose-900 text-rose-800 dark:text-rose-200 text-xs">
            This action purges vectors from Qdrant, postings from BM25, and creates an immutable audit event.
          </div>
          <div className="flex justify-end space-x-3 pt-4 border-t border-slate-100 dark:border-slate-800">
            <Button variant="secondary" onClick={() => setDeleteDocTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              isLoading={deleteMutation.isPending}
              onClick={() => deleteDocTarget && deleteMutation.mutate(deleteDocTarget.id)}
            >
              Permanently Delete
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
