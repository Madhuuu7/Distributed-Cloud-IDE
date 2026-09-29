import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import * as monaco from 'monaco-editor';
import { aiApi, errorMessage, executeApi, filesApi } from '../services/api';
import type { ExecutionResult, ExplainResponse, FileNode } from '../types';
import AssistantPanel from '../components/ai/AssistantPanel';
import ReviewPanel from '../components/ai/ReviewPanel';
import SearchPanel from '../components/ai/SearchPanel';
import FixRunPanel from '../components/fix/FixRunPanel';
import { Button, formatCost } from '../components/ui';

const RUNNABLE_LANGUAGES = ['python', 'javascript'];

const IDLE_TERMINAL = 'Terminal ready. Open a .py or .js file and press Run.';

const TABS = ['Assistant', 'Search', 'Review', 'Fix'] as const;
type Tab = (typeof TABS)[number];

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
  const [tab, setTab] = useState<Tab>('Assistant');
  const [explaining, setExplaining] = useState(false);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);

  // The save handler is bound into a Monaco keybinding, so keep it in a ref to
  // avoid re-registering the command on every render.
  const saveRef = useRef<() => void>(() => {});

  // `openFileByPath` is called from panels rendered below it and needs the
  // current file list, which a stale closure would not have.
  const filesRef = useRef<FileNode[]>([]);
  filesRef.current = files;

  // Monaco fires onDidChangeModelContent for programmatic setValue too, so
  // loading a file would otherwise mark it unsaved the instant it opened -
  // a dirty dot on every file and a "discard changes?" prompt on the next
  // click.
  //
  // A suppress-flag around setValue is the obvious fix and it does not hold:
  // the event does not always arrive before the flag is cleared. Comparing
  // against the content we loaded is immune to that timing, and it also gets
  // the case where someone types an edit and then undoes it - the file really
  // is unmodified again.
  const loadedContentRef = useRef('');

  const setEditorContent = (content: string, language?: string) => {
    const model = editorRef.current?.getModel();

    if (!model) return;

    loadedContentRef.current = content;
    model.setValue(content);

    if (language) {
      monaco.editor.setModelLanguage(model, language);
    }

    setDirty(false);
  };

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
      setEditorContent(data.content, data.language);

      return data;
    } catch (error) {
      setStatus(errorMessage(error, 'Could not open the file'));
    }
  };

  /**
   * Jump to a cited range.
   *
   * This is what makes a citation worth printing: a claim you can check in one
   * click is evidence, and one you have to go hunting for is decoration.
   */
  const openFileByPath = async (path: string, startLine?: number, endLine?: number) => {
    const target = filesRef.current.find((file) => file.name === path);

    if (!target) {
      setStatus(`${path} is not in this project`);
      return;
    }

    if (selectedFile?.id !== target.id) {
      const opened = await openFile(target);
      if (!opened) return;
    }

    const editor = editorRef.current;

    if (!editor || !startLine) return;

    const lastLine = editor.getModel()?.getLineCount() ?? startLine;
    const from = Math.min(startLine, lastLine);
    const to = Math.min(endLine ?? startLine, lastLine);

    editor.revealLinesInCenter(from, to);
    editor.setSelection(new monaco.Range(from, 1, to, 1));
    editor.focus();
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
        setEditorContent('');
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
      // What is on disk is now the baseline the dirty check compares against.
      loadedContentRef.current = data.content;
      setDirty(false);
      setStatus('Saved');
    } catch (error) {
      setStatus(errorMessage(error, 'Could not save the file'));
    } finally {
      setSaving(false);
    }
  }, [selectedFile]);

  saveRef.current = saveFile;

  const explainSelection = async () => {
    const editor = editorRef.current;

    if (!selectedFile || !editor) return;

    const selection = editor.getSelection();
    // No selection means "explain the whole file", which is what someone who
    // clicked the button without selecting anything almost certainly wants.
    const hasRange = selection && !selection.isEmpty();

    setExplaining(true);
    setExplanation(null);

    try {
      const { data } = await aiApi.explain({
        file_id: selectedFile.id,
        start_line: hasRange ? selection.startLineNumber : undefined,
        end_line: hasRange ? selection.endLineNumber : undefined
      });

      setExplanation(data);
    } catch (error) {
      setStatus(errorMessage(error, 'Could not explain that'));
    } finally {
      setExplaining(false);
    }
  };

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
      const changed = editor.getValue() !== loadedContentRef.current;

      setDirty(changed);

      if (changed) {
        setStatus('');
      }
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
  const numericProjectId = Number(projectId);

  // Below lg the three panes stack, so the height stays natural there: pinning
  // the viewport height while stacked squeezes the editor into a sliver.
  return (
    <div className="grid gap-4 lg:h-[calc(100vh_-_9rem)] lg:grid-cols-[220px_1fr_380px]">
      <aside className="flex max-h-72 min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 p-4 lg:max-h-none">
        <div className="flex shrink-0 items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Explorer</h2>

          <Button variant="primary" size="sm" onClick={createFile}>
            + New
          </Button>
        </div>

        <ul className="mt-4 min-h-0 flex-1 space-y-1 overflow-y-auto text-sm">
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

      <div className="grid min-h-0 gap-4 lg:grid-rows-[1fr_180px]">
        <section className="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80">
          <div className="flex shrink-0 items-center justify-between gap-4 border-b border-slate-800 px-4 py-3">
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
              <Button
                onClick={explainSelection}
                disabled={!selectedFile || explaining}
                title="Explain the selection, or the whole file if nothing is selected"
              >
                {explaining ? 'Explaining...' : 'Explain'}
              </Button>

              <Button onClick={saveFile} disabled={!selectedFile || saving || !dirty} title="Ctrl+S">
                {saving ? 'Saving...' : 'Save'}
              </Button>

              <Button
                variant="primary"
                onClick={runCode}
                disabled={!canRun || running}
                title={canRun ? 'Run in an isolated container' : 'Only Python and JavaScript can run'}
              >
                {running ? 'Running...' : 'Run'}
              </Button>
            </div>
          </div>

          <div ref={editorContainerRef} className="h-[420px] min-h-0 lg:h-auto lg:flex-1" />
        </section>

        <section className="flex h-[220px] min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 lg:h-auto">
          <div className="flex shrink-0 items-center justify-between border-b border-slate-800 px-4 py-2">
            <h3 className="text-sm font-semibold text-white">
              {explanation ? 'Explanation' : 'Output'}
            </h3>

            <div className="flex items-center gap-3 text-xs text-slate-500">
              {explanation && (
                <>
                  <span className="font-mono">
                    {explanation.path}:{explanation.start_line}-{explanation.end_line}
                  </span>
                  <span>{explanation.cached ? 'cached' : formatCost(explanation.cost_usd)}</span>
                  <button onClick={() => setExplanation(null)} className="hover:text-slate-300">
                    show output
                  </button>
                </>
              )}

              {!explanation && result && (
                <>
                  <span className={result.exit_code === 0 ? 'text-emerald-400' : 'text-red-400'}>
                    exit {result.exit_code ?? 'killed'}
                  </span>
                  <span>{result.duration_ms} ms</span>
                  <span>{result.backend}</span>
                  {result.timed_out && <span className="text-amber-400">timed out</span>}
                </>
              )}
            </div>
          </div>

          {explanation ? (
            <div className="min-h-0 flex-1 overflow-auto p-4 text-sm leading-relaxed whitespace-pre-wrap text-slate-300">
              {explanation.explanation}
            </div>
          ) : (
            <pre className="min-h-0 flex-1 overflow-auto bg-black p-4 font-mono text-sm whitespace-pre-wrap text-slate-200">
              {terminal}
            </pre>
          )}
        </section>
      </div>

      <aside className="flex h-[520px] min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-900/80 lg:h-auto">
        <nav className="flex shrink-0 border-b border-slate-800">
          {TABS.map((name) => (
            <button
              key={name}
              onClick={() => setTab(name)}
              className={`flex-1 px-2 py-2.5 text-xs font-medium transition ${
                tab === name
                  ? 'border-b-2 border-brand-500 text-white'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {name}
            </button>
          ))}
        </nav>

        <div className="min-h-0 flex-1">
          {/* Each panel is keyed to the tab so switching away discards its
              in-flight work rather than leaving a stream running unseen. */}
          {tab === 'Assistant' && (
            <AssistantPanel
              projectId={numericProjectId}
              onOpenCitation={(citation) =>
                openFileByPath(citation.path, citation.start_line, citation.end_line)
              }
            />
          )}

          {tab === 'Search' && (
            <SearchPanel
              projectId={numericProjectId}
              onOpenResult={(result) =>
                openFileByPath(result.path, result.start_line, result.end_line)
              }
            />
          )}

          {tab === 'Review' && (
            <ReviewPanel
              projectId={numericProjectId}
              onOpenFinding={(finding) => openFileByPath(finding.path, finding.line, finding.line)}
            />
          )}

          {tab === 'Fix' && (
            <FixRunPanel
              projectId={numericProjectId}
              onApplied={async () => {
                await loadFiles();

                // Re-read the open file: the patch changed it underneath the
                // editor, and showing the pre-patch content would be a lie.
                if (selectedFile) {
                  const { data } = await filesApi.get(selectedFile.id);
                  setSelectedFile(data);
                  setEditorContent(data.content, data.language);
                  setDirty(false);
                }
              }}
            />
          )}
        </div>
      </aside>
    </div>
  );
}
