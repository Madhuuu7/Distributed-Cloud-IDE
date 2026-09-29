import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import * as monaco from 'monaco-editor';
import { errorMessage, executeApi, filesApi } from '../services/api';
import type { ExecutionResult, FileNode } from '../types';

const RUNNABLE_LANGUAGES = ['python', 'javascript'];

const IDLE_TERMINAL = 'Terminal ready. Open a .py or .js file and press Run.';

export default function IDEPage() {
  const { projectId } = useParams();

  const editorContainerRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);

  const [files, setFiles] = useState<FileNode[]>([]);
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [status, setStatus] = useState('');
  const [terminal, setTerminal] = useState(IDLE_TERMINAL);
  const [result, setResult] = useState<ExecutionResult | null>(null);

  // The save handler is bound into a Monaco keybinding, so keep it in a ref to
  // avoid re-registering the command on every render.
  const saveRef = useRef<() => void>(() => {});

  const loadFiles = useCallback(async () => {
    if (!projectId) return;

    try {
      const { data } = await filesApi.list(projectId);
      setFiles(data);
    } catch (error) {
      setStatus(errorMessage(error, 'Could not load files'));
    }
  }, [projectId]);

  const openFile = async (file: FileNode) => {
    if (dirty && !window.confirm('Discard unsaved changes?')) {
      return;
    }

    try {
      const { data } = await filesApi.get(file.id);

      setSelectedFile(data);
      setDirty(false);
      setStatus('');

      const model = editorRef.current?.getModel();

      if (model) {
        model.setValue(data.content);
        monaco.editor.setModelLanguage(model, data.language);
      }
    } catch (error) {
      setStatus(errorMessage(error, 'Could not open the file'));
    }
  };

  const createFile = async () => {
    if (!projectId) return;

    const name = window.prompt('File name (e.g. main.py)');

    if (!name?.trim()) return;

    try {
      const { data } = await filesApi.create(projectId, { name: name.trim(), content: '' });
      await loadFiles();
      await openFile(data);
    } catch (error) {
      setStatus(errorMessage(error, 'Could not create the file'));
    }
  };

  const deleteFile = async (file: FileNode) => {
    if (!window.confirm(`Delete "${file.name}"?`)) return;

    try {
      await filesApi.delete(file.id);

      if (selectedFile?.id === file.id) {
        setSelectedFile(null);
        setDirty(false);
        editorRef.current?.getModel()?.setValue('');
      }

      await loadFiles();
    } catch (error) {
      setStatus(errorMessage(error, 'Could not delete the file'));
    }
  };

  const saveFile = useCallback(async () => {
    const editor = editorRef.current;

    if (!selectedFile || !editor) return;

    setSaving(true);

    try {
      const { data } = await filesApi.update(selectedFile.id, { content: editor.getValue() });
      setSelectedFile(data);
      setDirty(false);
      setStatus('Saved');
    } catch (error) {
      setStatus(errorMessage(error, 'Could not save the file'));
    } finally {
      setSaving(false);
    }
  }, [selectedFile]);

  saveRef.current = saveFile;

  const runCode = async () => {
    const editor = editorRef.current;

    if (!selectedFile || !editor) return;

    setRunning(true);
    setResult(null);
    setTerminal(`Running ${selectedFile.name} in an isolated container...`);

    try {
      const { data } = await executeApi.run({
        language: selectedFile.language,
        code: editor.getValue()
      });

      setResult(data);

      const combined = [data.stdout, data.stderr].filter(Boolean).join('\n');
      setTerminal(combined || '(no output)');
    } catch (error) {
      setResult(null);
      setTerminal(errorMessage(error, 'Execution failed'));
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (!editorContainerRef.current) return;

    const editor = monaco.editor.create(editorContainerRef.current, {
      value: '',
      language: 'plaintext',
      theme: 'vs-dark',
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 14,
      scrollBeyondLastLine: false
    });

    editorRef.current = editor;

    const changeSubscription = editor.onDidChangeModelContent(() => {
      setDirty(true);
      setStatus('');
    });

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => saveRef.current());

    return () => {
      changeSubscription.dispose();
      editor.dispose();
      editorRef.current = null;
    };
  }, []);

  useEffect(() => {
    loadFiles();
  }, [loadFiles]);

  const canRun = Boolean(selectedFile) && RUNNABLE_LANGUAGES.includes(selectedFile?.language ?? '');

  return (
    <div className="grid gap-4 lg:grid-cols-[260px_1fr] lg:grid-rows-[1fr_220px]">
      <aside className="rounded-2xl border border-slate-800 bg-slate-900/80 p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Explorer</h2>

          <button
            onClick={createFile}
            className="rounded bg-brand-500 px-3 py-1 text-sm text-white transition hover:bg-brand-600"
          >
            + New
          </button>
        </div>

        <ul className="mt-4 space-y-1 text-sm">
          {files.length === 0 ? (
            <li className="px-3 py-2 text-slate-500">No files yet</li>
          ) : (
            files.map((file) => (
              <li
                key={file.id}
                className={`group flex items-center justify-between rounded px-3 py-2 ${
                  selectedFile?.id === file.id
                    ? 'bg-slate-800 text-white'
                    : 'text-slate-400 hover:bg-slate-800/60'
                }`}
              >
                <button onClick={() => openFile(file)} className="flex-1 truncate text-left">
                  {file.name}
                  {selectedFile?.id === file.id && dirty && (
                    <span className="ml-2 text-amber-400" title="Unsaved changes">
                      &bull;
                    </span>
                  )}
                </button>

                <button
                  onClick={() => deleteFile(file)}
                  title={`Delete ${file.name}`}
                  className="ml-2 text-slate-600 opacity-0 transition hover:text-red-400 group-hover:opacity-100"
                >
                  &times;
                </button>
              </li>
            ))
          )}
        </ul>
      </aside>

      <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80">
        <div className="flex items-center justify-between gap-4 border-b border-slate-800 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-white">
              {selectedFile?.name ?? 'No file selected'}
              {dirty && <span className="ml-2 text-xs text-amber-400">unsaved</span>}
            </p>
            <p className="text-xs text-slate-500">
              {selectedFile?.language ?? 'Select a file from the explorer'}
              {status && <span className="ml-2 text-slate-400">{status}</span>}
            </p>
          </div>

          <div className="flex shrink-0 gap-2">
            <button
              onClick={saveFile}
              disabled={!selectedFile || saving || !dirty}
              title="Ctrl+S"
              className="rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>

            <button
              onClick={runCode}
              disabled={!canRun || running}
              title={canRun ? 'Run in an isolated container' : 'Only Python and JavaScript can run'}
              className="rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white transition hover:bg-brand-600 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {running ? 'Running...' : 'Run'}
            </button>
          </div>
        </div>

        <div ref={editorContainerRef} className="h-[520px]" />
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 lg:col-span-2">
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
          <h3 className="text-sm font-semibold text-white">Output</h3>

          {result && (
            <p className="flex gap-3 text-xs text-slate-500">
              <span className={result.exit_code === 0 ? 'text-emerald-400' : 'text-red-400'}>
                exit {result.exit_code ?? 'killed'}
              </span>
              <span>{result.duration_ms} ms</span>
              <span>{result.backend}</span>
              {result.timed_out && <span className="text-amber-400">timed out</span>}
            </p>
          )}
        </div>

        <pre className="h-[180px] overflow-auto bg-black p-4 font-mono text-sm whitespace-pre-wrap text-slate-200">
          {terminal}
        </pre>
      </section>
    </div>
  );
}
